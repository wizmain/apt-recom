"""trade_top — 적재 기준 최고가 TOP 5 + 직전 기간 대비 신규 적재 급증 동네 TOP 5.

의미론 (변경 금지):
- 최고가: 적재일(created_at) 기준 최근 N일, 단지별 최고가 1건 (DISTINCT ON).
- 급증: 직전 동일 기간 대비 증가 건수 — 카운트만으로 '급증' 표현 금지 (spec §5-5).

표기 (2026-07-25 정정): created_at 은 **우리 파이프라인 적재일**이다. 거래 스키마에
신고일 컬럼이 없어(PRD §1) 이전에는 이 창을 "신고일 기준"으로 표기했으나, 계약일과
적재일이 2주 이상 벌어지는 사례가 실재해(1일차 검수: 계약 7/3~7/13 → 적재 7/20~7/24)
"적재 기준"으로 정직하게 표기한다 (PRD §7-2 원칙).

세대수 가드 (2026-07-26): total_hhld_cnt 가 확인된 단지만 후보다. 없으면 14세대급
부티크 빌라가 대단지와 나란히 "아파트 최고가"로 실린다(1일차 검수: 이니그마빌 3위).
매핑되지 않은 거래(pnu NULL)도 함께 제외된다 — 세대수를 확인할 수 없고 표시명이
API 원본이라 단지명 신뢰도가 낮다.

적재 케이던스 공시 (2026-08-17): 급증은 **적재 건수** 비교라 수집 배치가 빠진 기간이
있으면 그 차이가 그대로 섞인다. 취소된 배치는 수집분을 메모리에 모았다 반환 후
적재하는 구조라 **한 건도 쓰지 않고** 통째로 비고, 밀린 물량은 다음 성공 런에서
한꺼번에 들어온다 — 즉 결손이 있던 창은 과소, 그 다음 창은 과대로 잡힌다.
실측(2026-08-17): 직전 창 배치 9/15회 성공 vs 현재 창 11/14회, 전체 적재 2,844 → 5,243건.
그래서 두 창의 **적재 발생일 수**를 조건에 공시한다. 배치 성공 횟수 자체는 GitHub
Actions 사실이라 카드가 검증할 수 없어 쓰지 않는다 — DB 로 계산되는 값만 공시한다.
"""

from __future__ import annotations

from datetime import date, datetime

from scripts.insta_cards.copywriting import apply_overrides, build_trade_top_copy
from scripts.insta_cards.datasources import (
    open_local_db,
    query_all,
    stale_trade_warning,
)
from scripts.insta_cards.publication import (
    SCHEMA_VERSION,
    Condition,
    Item,
    Metric,
    Narrative,
    Publication,
    Series,
)

LIST_SIZE = 5
MIN_REPORT_COUNT = 20  # 표본 미달 지역 제외 (제안서 '표본 적은 지역 순위 제외')


def fetch_top_price_trades(conn, days: int, min_hhld: int) -> list[dict]:
    # JOIN(LEFT 아님) + total_hhld_cnt 조건이 세대수 미확인·미매핑 거래를 함께 걸러낸다.
    rows = query_all(
        conn,
        """
        SELECT pnu, apt_display_name, sgg_cd, deal_amount, exclu_use_ar
        FROM (
            SELECT DISTINCT ON (m.pnu)
                m.pnu,
                COALESCE(a.display_name, a.bld_nm) AS apt_display_name,
                t.sgg_cd,
                t.deal_amount,
                t.exclu_use_ar
            FROM trade_history t
            JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
            JOIN apartments a ON a.pnu = m.pnu
            WHERE t.created_at >= NOW() - (%s || ' days')::interval
              AND a.total_hhld_cnt >= %s
            ORDER BY m.pnu, t.deal_amount DESC
        ) per_complex
        ORDER BY deal_amount DESC
        LIMIT %s
        """,
        [days, min_hhld, LIST_SIZE],
    )
    names = _load_sigungu_names(conn)
    return [
        {
            "pnu": r["pnu"],
            "apt_display_name": r["apt_display_name"],
            "sigungu_name": names.get(r["sgg_cd"], r["sgg_cd"]),
            "deal_amount": r["deal_amount"],
            "exclu_use_ar": r["exclu_use_ar"],
        }
        for r in rows
    ]


def fetch_hot_districts(conn, days: int) -> list[dict]:
    rows = query_all(
        conn,
        """
        WITH current_window AS (
            SELECT sgg_cd, COUNT(*) AS cnt FROM trade_history
            WHERE created_at >= NOW() - (%s || ' days')::interval
            GROUP BY sgg_cd
        ), prev_window AS (
            SELECT sgg_cd, COUNT(*) AS cnt FROM trade_history
            WHERE created_at >= NOW() - (%s || ' days')::interval * 2
              AND created_at <  NOW() - (%s || ' days')::interval
            GROUP BY sgg_cd
        )
        SELECT c.sgg_cd,
               c.cnt AS current_count,
               COALESCE(p.cnt, 0) AS prev_count,
               c.cnt - COALESCE(p.cnt, 0) AS delta
        FROM current_window c
        LEFT JOIN prev_window p ON p.sgg_cd = c.sgg_cd
        WHERE c.cnt >= %s AND c.cnt > COALESCE(p.cnt, 0)
        ORDER BY delta DESC, c.cnt DESC
        LIMIT %s
        """,
        [days, days, days, MIN_REPORT_COUNT, LIST_SIZE],
    )
    if not rows:
        return []
    names = _load_sigungu_names(conn)
    return [
        {
            "sigungu_name": names.get(r["sgg_cd"], r["sgg_cd"]),
            "current_count": r["current_count"],
            "prev_count": r["prev_count"],
            "delta": r["delta"],
        }
        for r in rows
    ]


def fetch_ingestion_coverage(conn, days: int) -> dict:
    """두 비교 창 각각에서 **적재가 발생한 날 수**. 급증 수치의 케이던스 공시용.

    건수가 아니라 날 수인 이유: 결손은 "그날 배치가 통째로 빠졌다"로 나타나므로
    날 수가 곧 케이던스다. 건수는 시장 활동과 케이던스가 섞여 분리되지 않는다.
    """
    rows = query_all(
        conn,
        """
        SELECT
            COUNT(DISTINCT DATE(created_at AT TIME ZONE 'Asia/Seoul'))
                FILTER (WHERE created_at >= NOW() - (%s || ' days')::interval)
                AS current_days,
            COUNT(DISTINCT DATE(created_at AT TIME ZONE 'Asia/Seoul'))
                FILTER (WHERE created_at >= NOW() - (%s || ' days')::interval * 2
                          AND created_at <  NOW() - (%s || ' days')::interval)
                AS prev_days
        FROM trade_history
        WHERE created_at >= NOW() - (%s || ' days')::interval * 2
        """,
        [days, days, days, days],
    )
    row = rows[0]
    return {"current_days": row["current_days"], "prev_days": row["prev_days"]}


def _load_sigungu_names(conn) -> dict[str, str]:
    rows = query_all(
        conn,
        "SELECT code, name, extra FROM common_code WHERE group_id = %s",
        ["sigungu"],
    )
    return {
        r["code"]: f"{r['name']}({r['extra']})"
        if r["extra"] and r["extra"] != r["name"]
        else r["name"]
        for r in rows
    }


def build_publication(
    price_rows: list[dict],
    hot_rows: list[dict],
    days: int,
    min_hhld: int,
    coverage: dict,
    *,
    slug: str,
    status: str,
    published_at: str | None,
    copy_overrides: dict | None,
) -> Publication:
    if len(price_rows) < LIST_SIZE:
        raise ValueError(
            f"최고가 거래가 {len(price_rows)}건 — {LIST_SIZE}건 미만이라 발행 중단"
        )
    if len(hot_rows) < LIST_SIZE:
        raise ValueError(
            f"급증 조건(현재 {MIN_REPORT_COUNT}건 이상 + 직전 대비 증가) 충족 지역이 "
            f"{len(hot_rows)}곳 — {LIST_SIZE}곳 미만이라 발행 중단"
        )

    from scripts.insta_cards.theme import format_eok

    items = tuple(
        Item(
            rank=i + 1,
            name=r["apt_display_name"] or "-",
            region=r["sigungu_name"],
            pnu=r["pnu"],
            metrics=(
                Metric("거래가", format_eok(r["deal_amount"]), ""),
                Metric("전용면적", f"{r['exclu_use_ar']:.0f}㎡", ""),
            ),
            reasons=(),
        )
        for i, r in enumerate(price_rows)
    )
    secondary = tuple(
        Item(
            rank=i + 1,
            name=r["sigungu_name"],
            region=None,
            pnu=None,
            metrics=(
                Metric("신규 거래", f"{r['current_count']:,}건", ""),
                Metric("직전 대비", f"+{r['delta']:,}건", ""),
            ),
            reasons=(),
        )
        for i, r in enumerate(hot_rows)
    )

    copy = build_trade_top_copy(days, price_rows[0]["deal_amount"])
    if copy_overrides:
        copy = apply_overrides(copy, copy_overrides)

    period_label = f"적재 기준 최근 {days}일"
    today = date.today().isoformat()
    return Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        status=status,
        series=Series.TRADE_TOP,
        title=f"최근 {days}일 최고가 TOP 5",
        eyebrow=f"적재 기준 · 최근 {days}일",
        hook=copy.hook,
        summary="새로 포착된 거래 중 최고가와, 신규 거래가 크게 늘어난 동네를 모았습니다.",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label=period_label,
        cover_image="01-cover.png",
        cover_alt=f"최근 {days}일 아파트 최고가 TOP 5 카드",
        conditions=(
            Condition("기간", period_label),
            Condition("집계 단위", "단지별 최고가 1건"),
            Condition("최소 세대수", f"{min_hhld}세대"),
            Condition(
                "적재 발생일",
                f"최근 {coverage['current_days']}일 · 직전 {coverage['prev_days']}일",
            ),
            Condition("기준일", today),
        ),
        items=items,
        secondary_items=secondary,
        comparison=None,
        narrative=Narrative(why=copy.why, fit_for=copy.fit_for),
        methodology=(
            "최고가: 최근 기간 새로 적재된 거래 중 단지별 최고가 1건만 집계",
            f"{min_hhld}세대 이상 단지만 후보 (세대수 미확인 단지 제외)",
            f"급증: 직전 {days}일 대비 신규 적재 건수 증가분 (현재 {MIN_REPORT_COUNT}건 이상 지역만)",
            "급증 수치에는 적재 케이던스 차이가 섞입니다 — 두 기간의 적재 발생일이 다르면 그만큼 과장됩니다",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "데이터 적재일 기준이라 실제 계약 시점은 이보다 앞섭니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=(),  # 랭킹은 넛지 조건이 아님 — 가짜 의도 부여 금지 (PRD Q3)
    )


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        price_rows = fetch_top_price_trades(conn, args.days, args.min_hhld)
        hot_rows = fetch_hot_districts(conn, args.days)
        coverage = fetch_ingestion_coverage(conn, args.days)
    finally:
        conn.close()
    return build_publication(
        price_rows,
        hot_rows,
        args.days,
        args.min_hhld,
        coverage,
        slug=slug,
        status=status,
        published_at=published_at,
        copy_overrides=copy_overrides,
    )
