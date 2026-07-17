"""compare — 비교표는 지역 집계, 후보 장은 각 지역 넛지 1위 단지 (spec §5-3).

점수는 '넛지 상위 10개 단지 평균' — '지역 전체 평균' 표현 금지 (PRD 계약).
"""

from __future__ import annotations

from datetime import date, datetime

from scripts.insta_cards.copywriting import (
    NUDGE_LABELS,
    apply_overrides,
    build_compare_copy,
)
from scripts.insta_cards.datasources import (
    INFO_NONE,
    extract_candidate_metrics,
    get_apartment_detail,
    get_region_name,
    open_local_db,
    post_nudge_score,
    query_all,
    stale_trade_warning,
)
from scripts.insta_cards.publication import (
    SCHEMA_VERSION,
    Comparison,
    ComparisonColumn,
    Condition,
    Item,
    MapCta,
    Metric,
    Narrative,
    Publication,
    Series,
)
from scripts.insta_cards.theme import format_eok

TOP_N = 10
AGGREGATE_DAYS = 90
COMPARISON_ROW_LABELS = (
    "넛지 점수(상위10 평균)",
    "중위 실거래가(90일)",
    "거래 건수(90일)",
    "평균 연식",
)


def fetch_region_aggregate(conn, sigungu_code: str, days: int = AGGREGATE_DAYS) -> dict:
    price_rows = query_all(
        conn,
        """
        SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY t.deal_amount) AS median_amount,
               COUNT(*) AS trade_count
        FROM trade_history t
        JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        JOIN apartments a ON a.pnu = m.pnu
        WHERE a.sigungu_code = %s
          AND make_date(t.deal_year, t.deal_month, t.deal_day)
              >= CURRENT_DATE - (%s || ' days')::interval
        """,
        [sigungu_code, days],
    )
    age_rows = query_all(
        conn,
        """
        SELECT AVG(EXTRACT(YEAR FROM CURRENT_DATE)
                   - CAST(SUBSTRING(a.use_apr_day, 1, 4) AS INTEGER)) AS avg_age
        FROM apartments a
        WHERE a.sigungu_code = %s AND a.use_apr_day ~ '^[0-9]{4}'
        """,
        [sigungu_code],
    )
    return {
        "median_amount": price_rows[0]["median_amount"] if price_rows else None,
        "trade_count": (price_rows[0]["trade_count"] if price_rows else 0) or 0,
        "avg_age": age_rows[0]["avg_age"] if age_rows else None,
    }


def _column_values(avg_score: float, aggregate: dict) -> tuple[str, ...]:
    median = aggregate["median_amount"]
    avg_age = aggregate["avg_age"]
    return (
        f"{avg_score:.1f}점",
        format_eok(round(median)) if median else INFO_NONE,
        f"{aggregate['trade_count']:,}건",
        f"{avg_age:.0f}년" if avg_age is not None else INFO_NONE,
    )


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    codes = [c.strip() for c in args.regions.split(",") if c.strip()]
    if len(codes) != 2:
        raise ValueError(
            "compare 는 --regions 에 시군구 코드 2개(콤마 구분)가 필요합니다."
        )
    nudge = args.nudge
    nudge_label = NUDGE_LABELS[nudge]

    regions = []
    for code in codes:
        name = get_region_name(code)
        top10 = post_nudge_score(
            {"nudges": [nudge], "top_n": TOP_N, "sigungu_code": code}
        )
        if not top10:
            raise ValueError(f"{name}({code}) 에 대한 넛지 점수 결과가 없습니다.")
        regions.append(
            {
                "code": code,
                "name": name,
                "avg_score": sum(r["score"] for r in top10) / len(top10),
                "top1": top10[0],
            }
        )

    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        for region in regions:
            region["aggregate"] = fetch_region_aggregate(conn, region["code"])
    finally:
        conn.close()

    items = []
    for rank, region in enumerate(regions, start=1):
        top1 = region["top1"]
        detail = get_apartment_detail(top1["pnu"])
        metrics = [Metric(f"{nudge_label} 점수", f"{top1['score']:.1f}점", "")]
        metrics.extend(extract_candidate_metrics(detail, None))
        items.append(
            Item(
                rank=rank,
                name=top1["bld_nm"],
                region=region["name"],
                pnu=top1["pnu"],
                metrics=tuple(metrics),
                reasons=(),
            )
        )

    winner = max(regions, key=lambda r: r["avg_score"])
    copy = build_compare_copy(
        regions[0]["name"], regions[1]["name"], nudge_label, winner["name"]
    )
    if copy_overrides:
        copy = apply_overrides(copy, copy_overrides)

    today = date.today().isoformat()
    return Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        status=status,
        series=Series.COMPARE,
        title=f"{regions[0]['name']} vs {regions[1]['name']} — {nudge_label}",
        eyebrow="동네 비교",
        hook=copy.hook,
        summary=f"{nudge_label} 기준으로 두 지역의 추천 상위 단지와 시세를 비교했습니다.",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label=f"계약일 기준 최근 {AGGREGATE_DAYS}일 실거래 + 넛지 점수",
        cover_image="01-cover.png",
        cover_alt=f"{regions[0]['name']} {regions[1]['name']} 아파트 비교 카드",
        conditions=(
            Condition("비교 기준", f"{nudge_label} 넛지"),
            Condition("지역", f"{regions[0]['name']} / {regions[1]['name']}"),
            Condition("기준일", today),
        ),
        items=tuple(items),
        secondary_items=None,
        comparison=Comparison(
            row_labels=COMPARISON_ROW_LABELS,
            columns=tuple(
                ComparisonColumn(
                    name=r["name"],
                    values=_column_values(r["avg_score"], r["aggregate"]),
                )
                for r in regions
            ),
        ),
        narrative=Narrative(why=copy.why, fit_for=copy.fit_for),
        methodology=(
            f"점수는 각 지역 {nudge_label} 넛지 상위 {TOP_N}개 단지의 평균 (지역 전체 평균 아님)",
            f"가격·거래량은 계약일 기준 최근 {AGGREGATE_DAYS}일 실거래 집계",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "신고 지연으로 최근 거래가 늦게 반영될 수 있습니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=tuple(
            MapCta(
                id=f"map-{'ab'[i]}",
                label=f"{r['name']} 추천 보기",
                nudges=(nudge,),
                sigungu_code=r["code"],
                region_label=r["name"],
                filters={},
            )
            for i, r in enumerate(regions)
        ),
    )
