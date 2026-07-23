"""value — 가성비 넛지 상위 후보 중 min_hhld 통과 + ㎡당 가격 오름차순 TOP 5.

의미론 (변경 금지, PRD §9): min_hhld 미달 혼입·price 전무·5개 미만은 모두
예외로 발행 중단. fallback 없음.
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
from scripts.insta_cards.theme import format_price_per_m2

CANDIDATE_POOL_SIZE = 30
LIST_SIZE = 5


def fetch_price_per_m2_by_pnu(conn, pnu_list: list[str]) -> dict[str, float]:
    if not pnu_list:
        return {}
    placeholders = ",".join(["%s"] * len(pnu_list))
    rows = query_all(
        conn,
        f"SELECT pnu, price_per_m2 FROM apt_price_score "
        f"WHERE pnu IN ({placeholders}) AND price_per_m2 IS NOT NULL",
        pnu_list,
    )
    return {r["pnu"]: r["price_per_m2"] for r in rows}


def select_candidates(
    candidates: list[dict], price_map: dict[str, float], min_households: int
) -> list[dict]:
    undersized = [
        c for c in candidates if (c.get("total_hhld_cnt") or 0) < min_households
    ]
    if undersized:
        raise ValueError(
            f"nudge/score 응답에 min_hhld({min_households}) 미달 단지 "
            f"{len(undersized)}건 포함 — API 필터 동작을 확인할 것."
        )
    merged = [
        {**c, "price_per_m2": price_map[c["pnu"]]}
        for c in candidates
        if c["pnu"] in price_map
    ]
    if len(merged) < LIST_SIZE:
        raise ValueError(
            f"price_per_m2 보유 후보 {len(merged)}건 — {LIST_SIZE}건 미만이라 발행 중단"
        )
    merged.sort(key=lambda c: (c["price_per_m2"], c["pnu"]))  # 결정적 tie-break
    return merged[:LIST_SIZE]


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    candidates = post_nudge_score(
        {
            "nudges": [args.nudge],
            "top_n": CANDIDATE_POOL_SIZE,
            "keyword": args.region,
            "min_hhld": args.min_hhld,
        }
    )
    if not candidates:
        raise ValueError(f"'{args.region}' 에 대한 넛지 점수 결과가 없습니다.")

    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        price_map = fetch_price_per_m2_by_pnu(conn, [c["pnu"] for c in candidates])
    finally:
        conn.close()

    top5 = select_candidates(candidates, price_map, args.min_hhld)

    items = tuple(
        Item(
            rank=i + 1,
            name=c["bld_nm"],
            region=args.region,
            pnu=c["pnu"],
            metrics=(
                Metric("㎡당 가격", format_price_per_m2(c["price_per_m2"]), ""),
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
        summary=f"{args.region} 가성비 넛지 상위 후보 중 ㎡당 가격이 낮은 5곳입니다.",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label=f"가성비 넛지 상위 {CANDIDATE_POOL_SIZE} 후보 기준",
        cover_image="01-cover.png",
        cover_alt=f"{args.region} 숨은 가성비 아파트 TOP 5 카드",
        conditions=(
            Condition("지역", args.region),
            Condition("최소 세대수", f"{args.min_hhld}세대"),
            Condition("기준일", today),
        ),
        items=items,
        secondary_items=None,
        comparison=None,
        narrative=Narrative(why=copy.why, fit_for=copy.fit_for),
        methodology=(
            f"가성비 넛지 상위 {CANDIDATE_POOL_SIZE}개 후보 중 ㎡당 가격 오름차순 {LIST_SIZE}곳",
            "가격은 apt_price_score 의 ㎡당 가격 (로컬 적재 기준)",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "가격 데이터는 로컬 적재 시점 기준입니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=(
            MapCta(
                id="map-main",
                label=f"가성비 조건 그대로 {args.region} 지도에서 보기",
                nudges=(args.nudge,),
                sigungu_code=None,
                region_label=args.region,
                keyword=args.region,  # 시군구 코드가 없는 시리즈 — 키워드로 지역 재현
                filters={"min_hhld": args.min_hhld},
            ),
        ),
    )
