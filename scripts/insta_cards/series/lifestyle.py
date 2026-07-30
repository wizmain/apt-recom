"""lifestyle — 넛지 프로필 파라미터화 추천 (파일럿: newlywed, spec §5-2).

통근시간 조건은 지원하지 않는다 — 조건 칩에 '지하철·버스 접근성 반영'으로
표기 (통근시간 사칭 금지). /api/commute 표시 연동은 후속 (--destination).

min_hhld·min_smallest_area 는 둘 다 필수다. 세대수 하한만으로는 전 주택형이
소형인 단지가 통과해 라이프스타일 훅과 실제 물건이 어긋난다(2026-07-30 4일차:
강남 반려동물 4위가 294세대인데 전용 35~51㎡, 23~34억 사이에 4.6억). 값의 출처는
rotation.yaml 의 series.lifestyle.* 다.
"""

from __future__ import annotations

from datetime import date, datetime

from scripts.insta_cards.copywriting import (
    NUDGE_LABELS,
    apply_overrides,
    build_lifestyle_copy,
    contributor_labels,
)
from scripts.insta_cards.datasources import (
    extract_candidate_metrics,
    fetch_recent_trades,
    get_apartment_detail,
    get_region_name,
    open_local_db,
    post_nudge_score,
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
from scripts.insta_cards.theme import format_eok

SCORE_POOL_SIZE = 50
MAX_CANDIDATES = 5
MIN_CANDIDATES = 3


def select_candidates(
    eligible: dict[str, dict], scored: list[dict], min_households: int
) -> list[dict]:
    undersized = [r for r in scored if (r.get("total_hhld_cnt") or 0) < min_households]
    if undersized:
        raise ValueError(
            f"nudge/score 응답에 min_hhld({min_households}) 미달 단지 "
            f"{len(undersized)}건 포함 — API 필터 동작을 확인할 것."
        )
    picked = [
        {**row, "trade": eligible[row["pnu"]]}
        for row in scored
        if row["pnu"] in eligible
    ][:MAX_CANDIDATES]
    if len(picked) < MIN_CANDIDATES:
        raise ValueError(
            f"적격 후보 {len(picked)}건 — {MIN_CANDIDATES}건 미만이라 발행 중단 "
            f"(적격 집합 {len(eligible)}건 / 점수 상위 {len(scored)}건)"
        )
    return picked


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    profile_label = NUDGE_LABELS[args.profile]
    region_name = get_region_name(args.region)

    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        eligible = fetch_recent_trades(
            conn,
            args.region,
            max_amount=args.max_price,
            min_area=args.min_area,
            max_area=args.max_area,
        )
    finally:
        conn.close()
    if not eligible:
        raise ValueError(f"{region_name}: 조건에 맞는 최근 90일 계약 거래가 없습니다.")

    payload = {
        "nudges": [args.profile],
        "top_n": SCORE_POOL_SIZE,
        "sigungu_code": args.region,
        "min_hhld": args.min_hhld,
        "min_smallest_area": args.min_smallest_area,
    }
    if args.max_price is not None:
        payload["max_price"] = args.max_price
    if args.min_area is not None:
        payload["min_area"] = args.min_area
    if args.max_area is not None:
        payload["max_area"] = args.max_area
    scored = post_nudge_score(payload)

    # min_hhld 는 응답의 total_hhld_cnt 로 사후 검증한다(select_candidates). 주택형
    # 하한은 응답에 대응 필드가 없어 검증할 수 없고 API 적용을 신뢰한다 — value 와 동일.
    picked = select_candidates(eligible, scored, args.min_hhld)

    items = []
    for rank, row in enumerate(picked, start=1):
        trade = row["trade"]
        detail = get_apartment_detail(row["pnu"])
        built_year = (trade.get("use_apr_day") or "")[:4] or "정보 없음"
        metrics = [
            Metric("최근 실거래가", format_eok(trade["deal_amount"]), ""),
            Metric("전용면적", f"{trade['exclu_use_ar']:.1f}㎡", ""),
            Metric(
                "준공연도",
                f"{built_year}년" if built_year != "정보 없음" else built_year,
                "",
            ),
        ]
        metrics.extend(extract_candidate_metrics(detail, trade["exclu_use_ar"]))
        items.append(
            Item(
                rank=rank,
                name=trade["bld_nm"],
                region=region_name,
                pnu=row["pnu"],
                metrics=tuple(metrics),
                reasons=tuple(contributor_labels(row["top_contributors"], 3)),
            )
        )

    top_contribs = contributor_labels(picked[0]["top_contributors"], 3)
    copy = build_lifestyle_copy(profile_label, region_name, top_contribs)
    if copy_overrides:
        copy = apply_overrides(copy, copy_overrides)

    today = date.today().isoformat()
    conditions = [
        Condition("라이프스타일", profile_label),
        Condition("지역", region_name),
        Condition("접근성", "지하철·버스 접근성 반영"),
    ]
    if args.max_price is not None:
        conditions.append(Condition("예산", f"{format_eok(args.max_price)} 이하"))
    # 두 하한은 payload 로 이미 적용된다 — 카드에도 공시한다(2026-07-29·07-30).
    # 한 칩으로 묶는 이유: 조건 칩은 6개가 상한(textrules.MAX_CONDITIONS, 조건 슬라이드
    # 레이아웃)인데 lifestyle 은 --max-price 까지 붙으면 초과한다. 정확한 문장은
    # 방법론에 각각 남기고, 칩은 요약만 싣는다.
    conditions.append(
        Condition(
            "후보 하한",
            f"{args.min_hhld}세대 · 전용 {args.min_smallest_area:g}㎡ 이상",
        )
    )
    conditions.append(Condition("기준일", today))

    cta_filters = {
        "min_hhld": args.min_hhld,
        "min_smallest_area": args.min_smallest_area,
    }
    if args.max_price is not None:
        cta_filters["max_price"] = args.max_price
    if args.min_area is not None:
        cta_filters["min_area"] = args.min_area
    if args.max_area is not None:
        cta_filters["max_area"] = args.max_area

    return Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        status=status,
        series=Series.LIFESTYLE,
        title=f"{region_name} {profile_label} 추천 단지",
        eyebrow=f"라이프스타일 추천 · {profile_label}",
        hook=copy.hook,
        summary=f"{region_name}에서 {profile_label} 넛지 점수가 높고 최근 거래가 있는 단지입니다.",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label="계약일 기준 최근 90일 실거래 + 넛지 점수",
        cover_image="01-cover.png",
        cover_alt=f"{region_name} {profile_label} 아파트 추천 카드",
        conditions=tuple(conditions),
        items=tuple(items),
        secondary_items=None,
        comparison=None,
        narrative=Narrative(why=copy.why, fit_for=copy.fit_for),
        methodology=(
            f"{profile_label} 넛지 상위 {SCORE_POOL_SIZE} 후보와 최근 90일 계약 거래 보유 단지의 교집합",
            f"{args.min_hhld}세대 이상 단지만 후보 (세대수 미확인 단지 제외)",
            f"모든 주택형이 전용 {args.min_smallest_area:g}㎡ 이상인 단지만 후보",
            "표시 가격은 각 단지의 최근 계약 거래 기준",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "통근시간이 아닌 지하철·버스 접근성 점수 기준입니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=(
            MapCta(
                id="map-main",
                label=f"{profile_label} 조건 그대로 {region_name} 지도에서 보기",
                nudges=(args.profile,),
                sigungu_code=args.region,
                region_label=region_name,
                filters=cta_filters,
            ),
        ),
    )
