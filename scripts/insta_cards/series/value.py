"""value — 넛지 상위 후보 중 min_hhld·min_smallest_area 통과 + ㎡당 가격 오름차순 TOP 5.

의미론 (변경 금지, PRD §9): min_hhld 미달 혼입·price 전무·5개 미만은 모두
예외로 발행 중단. fallback 없음.

min_smallest_area 는 필수다(2026-07-25). 없으면 ㎡당 가격 오름차순 정렬이
도시형생활주택·오피스텔급 소형 단지(전용 20~55㎡)를 상위로 끌어올려 "가성비
아파트" 훅과 실제 물건이 어긋난다. 값의 출처는 rotation.yaml 의
series.value.min_smallest_area 다.

면적 밴드(min_area~max_area)도 필수다(2026-08-01 6일차). 대형 평형은 ㎡당 단가가
구조적으로 낮아(면적 할인), 단지 전체 평균 ㎡당 가격으로 정렬하면 대형 편중
단지가 상위를 점령한다 — 서초 실측으로 110㎡~ 밴드가 2,152만원/㎡, 60~85㎡ 가
3,106만원/㎡ 였다. 그래서 순위는 apt_price_score(단지 전체 평균)가 아니라
**밴드 내 거래만으로 계산한 ㎡당 평균**으로 매긴다. 질문을 "같은 크기 집,
어디가 싼가"로 고정하는 것이 이 시리즈의 계약이다.
"""

from __future__ import annotations

from datetime import date, datetime

from scripts.insta_cards.copywriting import (
    apply_overrides,
    build_value_copy,
    contributor_labels,
)
from scripts.insta_cards.datasources import (
    open_local_db,
    post_nudge_score,
    query_all,
    stale_trade_warning,
)
from scripts.insta_cards.publication import (
    SCHEMA_VERSION,
    Condition,
    Item,
    MapCta,
    Metric,
    Narrative,
    Publication,
    Series,
)
from scripts.insta_cards.theme import format_eok, format_price_per_m2

# 밴드 필터가 후보의 70~80% 를 걷어내므로 풀이 작으면 "가성비"가 성립하지 않는다 —
# 서초 실측(2026-08-01): top_n=30 이면 밴드 통과 6건뿐이라 TOP5 중 3곳이 구 평균보다
# 비쌌다(45억 반포자이 포함). top_n=100 이면 27건이 남고 TOP5 가 구 평균의 절반대다.
CANDIDATE_POOL_SIZE = 100
LIST_SIZE = 5

# 밴드 한정 집계라 90일이면 표본이 얇다 — 용산 60~85㎡ 가 90일에 5건(=LIST_SIZE)
# 이라 한 건만 빠져도 발행이 중단된다(2026-08-01 실측). 180일이면 최소 17건.
BAND_TRADE_DAYS = 180
# 단발 거래로 순위가 뒤집히지 않도록 최소 표본 수.
MIN_BAND_TRADES = 2
# 직거래는 가족·특수관계 간 저가 거래가 섞여 ㎡당 평균을 끌어내린다 — 송파 거여우방이
# 1층 직거래 6.61억(같은 84.9㎡ 중개 12.75억의 절반)으로 구 2위에 올랐다(2026-09-29).
# 값은 국토부 실거래 API 의 dealingGbn 원문. NULL(필드 수집 이전 거래)은 구분 불가라
# 유지한다 — 제외하면 과거 표본이 통째로 사라진다.
EXCLUDED_DEALING_GBN = "직거래"
# 단지 밴드 거래의 ㎡당 중앙값에서 이 비율 넘게 벗어난 거래는 평균에서 뺀다.
# 동작 현진에버빌 84.9㎡ 가 8.4억·8.25억 사이에 5.5억 중개거래 한 건(-33%, 같은 층·금액이
# 2/23 에도 있어 중복 신고 의심)이 섞여 ㎡당 평균이 869만원으로 내려가 구 1위가 됐다
# (2026-10-13). 같은 단지·같은 밴드의 층·향 차이는 실측 10~15% 이내라 25% 면 정상 거래를
# 건드리지 않는다. 표본 2건이 서로 이 비율 넘게 벌어지면 둘 다 빠져 후보에서 탈락한다
# (어느 쪽이 정상인지 판단할 근거가 없으므로). 구 평균(fetch_district_band_avg)은 표본이
# 커서 단발 이상치 영향이 작아 적용하지 않는다.
BAND_OUTLIER_MAX_DEVIATION = 0.25


def fetch_band_price_per_m2(
    conn, pnu_list: list[str], min_area: float, max_area: float
) -> dict[str, dict]:
    """면적 밴드 내 거래만으로 단지별 ㎡당 평균 + 대표 거래를 계산.

    apt_price_score.price_per_m2 를 쓰지 않는 이유: 그 값은 단지 전체 거래의
    평균이라 대형 평형 비중이 큰 단지가 구조적으로 싸 보인다(2026-08-01 6일차).
    단지 중앙값에서 BAND_OUTLIER_MAX_DEVIATION 넘게 벗어난 거래는 평균·대표 거래에서 뺀다.
    반환: pnu → {price_per_m2, trade_count, recent_amount, recent_area}
    """
    if not pnu_list:
        return {}
    placeholders = ",".join(["%s"] * len(pnu_list))
    rows = query_all(
        conn,
        f"""
        WITH band AS (
            SELECT m.pnu,
                   t.deal_amount,
                   t.exclu_use_ar,
                   make_date(t.deal_year, t.deal_month, t.deal_day) AS deal_date,
                   t.deal_amount * 10000.0 / t.exclu_use_ar AS price_per_m2
            FROM trade_history t
            JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
            WHERE m.pnu IN ({placeholders})
              AND t.deal_amount > 0
              AND t.exclu_use_ar BETWEEN %s AND %s
              AND t.dealing_gbn IS DISTINCT FROM %s
              AND make_date(t.deal_year, t.deal_month, t.deal_day)
                  >= CURRENT_DATE - (%s || ' days')::interval
        ),
        band_median AS (
            SELECT pnu,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_per_m2) AS median_price_per_m2
            FROM band
            GROUP BY pnu
        )
        SELECT b.pnu,
               AVG(b.price_per_m2) AS price_per_m2,
               COUNT(*) AS trade_count,
               (ARRAY_AGG(b.deal_amount ORDER BY b.deal_date DESC, b.deal_amount DESC))[1]
                   AS recent_amount,
               (ARRAY_AGG(b.exclu_use_ar ORDER BY b.deal_date DESC, b.deal_amount DESC))[1]
                   AS recent_area
        FROM band b
        JOIN band_median bm ON bm.pnu = b.pnu
        WHERE ABS(b.price_per_m2 - bm.median_price_per_m2)
              <= bm.median_price_per_m2 * %s
        GROUP BY b.pnu
        HAVING COUNT(*) >= %s
        """,
        [
            *pnu_list,
            min_area,
            max_area,
            EXCLUDED_DEALING_GBN,
            BAND_TRADE_DAYS,
            BAND_OUTLIER_MAX_DEVIATION,
            MIN_BAND_TRADES,
        ],
    )
    return {r["pnu"]: dict(r) for r in rows}


def fetch_district_band_avg(
    conn, pnu_list: list[str], min_area: float, max_area: float
) -> float | None:
    """후보가 속한 시군구의 밴드 ㎡당 평균 — "가격은 낮은데" 훅의 판정 기준.

    후보 풀 평균이 아니라 **구 전체 평균**이어야 한다. 풀은 이미 가성비 넛지로
    걸러진 집합이라 그 안의 평균을 쓰면 기준이 함께 올라간다.
    """
    if not pnu_list:
        return None
    placeholders = ",".join(["%s"] * len(pnu_list))
    rows = query_all(
        conn,
        f"""
        SELECT AVG(t.deal_amount * 10000.0 / t.exclu_use_ar) AS price_per_m2
        FROM trade_history t
        JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        JOIN apartments a ON a.pnu = m.pnu
        WHERE a.sigungu_code IN (
                  SELECT DISTINCT sigungu_code FROM apartments
                  WHERE pnu IN ({placeholders})
              )
          AND t.deal_amount > 0
          AND t.exclu_use_ar BETWEEN %s AND %s
          AND t.dealing_gbn IS DISTINCT FROM %s
          AND make_date(t.deal_year, t.deal_month, t.deal_day)
              >= CURRENT_DATE - (%s || ' days')::interval
        """,
        [*pnu_list, min_area, max_area, EXCLUDED_DEALING_GBN, BAND_TRADE_DAYS],
    )
    return rows[0]["price_per_m2"] if rows else None


def select_candidates(
    candidates: list[dict],
    price_map: dict[str, dict],
    min_households: int,
    district_avg: float | None = None,
) -> list[dict]:
    undersized = [
        c for c in candidates if (c.get("total_hhld_cnt") or 0) < min_households
    ]
    if undersized:
        raise ValueError(
            f"nudge/score 응답에 min_hhld({min_households}) 미달 단지 "
            f"{len(undersized)}건 포함 — API 필터 동작을 확인할 것."
        )
    merged = [{**c, **price_map[c["pnu"]]} for c in candidates if c["pnu"] in price_map]
    if len(merged) < LIST_SIZE:
        raise ValueError(
            f"면적 밴드 내 거래 {MIN_BAND_TRADES}건 이상인 후보 {len(merged)}건 — "
            f"{LIST_SIZE}건 미만이라 발행 중단 (밴드·기간을 조정하거나 slot skip)"
        )
    # "가격은 낮은데" 훅의 최소 조건 — 구 평균보다 비싼 단지는 가성비 후보가 아니다.
    # 조용히 순위만 매기면 45억 반포자이가 "숨은 가성비"로 실린다(2026-08-01 6일차).
    if district_avg is not None:
        affordable = [c for c in merged if c["price_per_m2"] <= district_avg]
        if len(affordable) < LIST_SIZE:
            raise ValueError(
                f"구 평균({district_avg / 10000:,.0f}만원/㎡) 이하 후보 "
                f"{len(affordable)}건 — {LIST_SIZE}건 미만이라 발행 중단 "
                f"(밴드 통과 {len(merged)}건). 풀 크기·밴드를 조정하거나 slot skip."
            )
        merged = affordable
    merged.sort(key=lambda c: (c["price_per_m2"], c["pnu"]))  # 결정적 tie-break
    return merged[:LIST_SIZE]


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    # 지역 한정은 코드가 있으면 코드로 한다. 키워드는 동명 시군구를 구분하지 못한다 —
    # '중구' 로 검색하면 울산 중구가 나온다(2026-08-22 실측). --region 은 표기용으로 남는다.
    region_filter = (
        {"sigungu_code": args.sigungu_code}
        if args.sigungu_code
        else {"keyword": args.region}
    )
    candidates = post_nudge_score(
        {
            "nudges": [args.nudge],
            "top_n": CANDIDATE_POOL_SIZE,
            **region_filter,
            "min_hhld": args.min_hhld,
            "min_smallest_area": args.min_smallest_area,
            # 밴드 주택형이 있는 단지로 모집단을 좁힌다 — 순위 계산과 같은 밴드.
            "min_area": args.min_area,
            "max_area": args.max_area,
        }
    )
    if not candidates:
        raise ValueError(f"'{args.region}' 에 대한 넛지 점수 결과가 없습니다.")

    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        pnus = [c["pnu"] for c in candidates]
        price_map = fetch_band_price_per_m2(conn, pnus, args.min_area, args.max_area)
        district_avg = fetch_district_band_avg(conn, pnus, args.min_area, args.max_area)
    finally:
        conn.close()

    top5 = select_candidates(candidates, price_map, args.min_hhld, district_avg)

    items = tuple(
        Item(
            rank=i + 1,
            name=c["bld_nm"],
            region=args.region,
            pnu=c["pnu"],
            # 총액·면적을 함께 싣는다 — ㎡당 가격만 보이면 독자가 물건 크기를 알 수
            # 없어 대형 고가 단지를 저렴하다고 읽는다(2026-08-01 6일차).
            metrics=(
                Metric("㎡당 가격", format_price_per_m2(c["price_per_m2"]), ""),
                Metric("최근 실거래가", format_eok(c["recent_amount"]), ""),
                Metric("전용면적", f"{c['recent_area']:.1f}㎡", ""),
                Metric("가성비 점수", f"{c['score']:.1f}", ""),
            ),
            reasons=tuple(contributor_labels(c["top_contributors"], 2)),
        )
        for i, c in enumerate(top5)
    )

    copy = build_value_copy(args.region)
    if copy_overrides:
        copy = apply_overrides(copy, copy_overrides)

    today = date.today().isoformat()
    return Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        status=status,
        series=Series.VALUE,
        title=f"숨은 가성비 TOP 5 — {args.region}",
        eyebrow="가성비 랭킹",
        hook=copy.hook,
        summary=(
            f"{args.region}에서 전용 {args.min_area:g}~{args.max_area:g}㎡ 거래 기준 "
            f"㎡당 가격이 낮은 5곳입니다."
        ),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label=f"계약일 기준 최근 {BAND_TRADE_DAYS}일 실거래 + 가성비 넛지 점수",
        cover_image="01-cover.png",
        cover_alt=f"{args.region} 숨은 가성비 아파트 TOP 5 카드",
        conditions=(
            Condition("지역", args.region),
            # 비교 면적대가 랭킹의 전제다 — 칩으로 먼저 보이게 한다(2026-08-01).
            Condition("비교 면적", f"전용 {args.min_area:g}~{args.max_area:g}㎡"),
            Condition("최소 세대수", f"{args.min_hhld}세대"),
            Condition("최소 주택형", f"{args.min_smallest_area:g}㎡ 이상"),
            Condition(
                "가격 기준",
                f"구 평균 {format_price_per_m2(district_avg)} 이하"
                if district_avg
                else "구 평균 이하",
            ),
            Condition("기준일", today),
        ),
        items=items,
        secondary_items=None,
        comparison=None,
        narrative=Narrative(why=copy.why, fit_for=copy.fit_for),
        methodology=(
            f"가성비 넛지 상위 {CANDIDATE_POOL_SIZE}개 후보 중 ㎡당 가격 오름차순 {LIST_SIZE}곳",
            f"㎡당 가격은 전용 {args.min_area:g}~{args.max_area:g}㎡ 거래만으로 계산 "
            f"(최근 {BAND_TRADE_DAYS}일 · {EXCLUDED_DEALING_GBN} 제외 · "
            f"단지 중앙값 대비 ±{BAND_OUTLIER_MAX_DEVIATION:.0%} 초과 거래 제외 · "
            f"밴드 내 {MIN_BAND_TRADES}건 이상)",
            f"모든 주택형이 전용 {args.min_smallest_area:g}㎡ 이상 · "
            f"{args.min_hhld}세대 이상인 단지만 후보",
            "㎡당 가격이 같은 밴드 구 평균 이하인 단지만 후보",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "면적대가 다르면 ㎡당 가격은 직접 비교되지 않습니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=(
            MapCta(
                id="map-main",
                label=f"가성비 조건 그대로 {args.region} 지도에서 보기",
                nudges=(args.nudge,),
                # 랜딩 후보와 지도 재계산 모집단을 일치시킨다 — 코드가 있으면 코드로.
                sigungu_code=args.sigungu_code,
                region_label=args.region,
                keyword=None if args.sigungu_code else args.region,
                # 랜딩 선정 조건과 동일한 필터를 지도에도 실어 모집단을 일치시킨다.
                filters={
                    "min_hhld": args.min_hhld,
                    "min_smallest_area": args.min_smallest_area,
                    "min_area": args.min_area,
                    "max_area": args.max_area,
                },
            ),
        ),
    )
