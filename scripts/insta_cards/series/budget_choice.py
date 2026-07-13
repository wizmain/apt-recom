"""budget_choice — 같은 예산으로 두 지역 대표 단지 비교 (spec §5-1).

'같은 예산' 보장: 대표 거래는 로컬 DB 적격 집합(면적 밴드 + 계약일 90일 +
예산 이하)에서 나온다. nudge/score 의 max_price 는 추정가라 후보 축소용으로만
쓰고, 카드 표기 가격의 근거로 쓰지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime

from scripts.insta_cards.copywriting import (
    apply_overrides,
    build_budget_choice_copy,
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

SCORE_POOL_SIZE = 50
ROW_LABELS = (
    "최근 실거래가",
    "전용면적",
    "준공연도",
    "지하철",
    "배정 초등학교",
    "안전점수",
    "월 관리비",
)


def select_representative(
    eligible: dict[str, dict], scored: list[dict], override_pnu: str | None
) -> tuple[dict, dict]:
    """적격 집합(예산·면적·기간 보장) ∩ 넛지 점수 순서 → 대표 1개.

    override 도 적격 집합 검증을 우회할 수 없다 (spec §5-1 규칙 4).
    """
    if override_pnu is not None:
        if override_pnu not in eligible:
            raise ValueError(
                f"--pnu 오버라이드 {override_pnu} 가 적격 집합(면적·예산·최근 90일 거래)에 없습니다."
            )
        row = next((r for r in scored if r["pnu"] == override_pnu), {})
        return eligible[override_pnu], row
    for row in scored:  # scored 는 점수 내림차순 (서버 정렬)
        if row["pnu"] in eligible:
            return eligible[row["pnu"]], row
    raise ValueError(
        f"적격 집합 {len(eligible)}건과 넛지 상위 {len(scored)}건의 교집합이 없습니다 — "
        "예산·면적 밴드를 조정하세요."
    )


def _build_candidate(
    trade: dict, scored_row: dict, region_name: str, target_area: float, rank: int
) -> tuple[Item, list[str]]:
    detail = get_apartment_detail(trade["pnu"])
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
    metrics.extend(extract_candidate_metrics(detail, target_area))
    contributors = contributor_labels(scored_row.get("top_contributors", []), 2)
    item = Item(
        rank=rank,
        name=trade["bld_nm"],
        region=region_name,
        pnu=trade["pnu"],
        metrics=tuple(metrics),
        reasons=tuple(f"{c} 접근성 기여" for c in contributors),
    )
    return item, contributors


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    codes = [c.strip() for c in args.regions.split(",") if c.strip()]
    if len(codes) != 2:
        raise ValueError("budget-choice 는 --regions 에 시군구 코드 2개가 필요합니다.")
    tol = args.area_tolerance
    plans = [
        {"code": codes[0], "area": args.area_a, "override": args.pnu_a},
        {"code": codes[1], "area": args.area_b, "override": args.pnu_b},
    ]

    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        for plan in plans:
            plan["name"] = get_region_name(plan["code"])
            plan["eligible"] = fetch_recent_trades(
                conn,
                plan["code"],
                max_amount=args.budget,
                min_area=plan["area"] - tol,
                max_area=plan["area"] + tol,
            )
            if not plan["eligible"]:
                raise ValueError(
                    f"{plan['name']}: 예산 {format_eok(args.budget)} 이하 · "
                    f"{plan['area']:.0f}±{tol:.0f}㎡ · 최근 90일 계약 거래가 없습니다."
                )
    finally:
        conn.close()

    for plan in plans:
        scored = post_nudge_score(
            {
                "nudges": [args.nudge],
                "top_n": SCORE_POOL_SIZE,
                "sigungu_code": plan["code"],
                "min_area": plan["area"] - tol,
                "max_area": plan["area"] + tol,
            }
        )
        plan["trade"], plan["scored_row"] = select_representative(
            plan["eligible"], scored, plan["override"]
        )

    items, contributors = [], []
    for rank, plan in enumerate(plans, start=1):
        item, contribs = _build_candidate(
            plan["trade"], plan["scored_row"], plan["name"], plan["area"], rank
        )
        items.append(item)
        contributors.append(contribs)

    copy = build_budget_choice_copy(
        plans[0]["name"],
        plans[1]["name"],
        plans[0]["trade"]["deal_amount"],
        plans[1]["trade"]["deal_amount"],
        plans[0]["trade"]["exclu_use_ar"],
        plans[1]["trade"]["exclu_use_ar"],
        contributors[0],
        contributors[1],
    )
    if copy_overrides:
        copy = apply_overrides(copy, copy_overrides)

    today = date.today().isoformat()
    budget_label = format_eok(args.budget)
    return Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        status=status,
        series=Series.BUDGET_CHOICE,
        title=f"같은 {budget_label}, {plans[0]['name']} vs {plans[1]['name']}",
        eyebrow="같은 예산, 다른 선택",
        hook=copy.hook,
        summary=f"{budget_label} 예산으로 두 지역의 대표 단지를 나란히 비교했습니다.",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label="계약일 기준 최근 90일 실거래",
        cover_image="01-cover.png",
        cover_alt=f"{budget_label} 예산 {plans[0]['name']} {plans[1]['name']} 아파트 비교 카드",
        conditions=(
            Condition("예산", f"{budget_label} 이하"),
            Condition("면적 A", f"{args.area_a:.0f}±{tol:.0f}㎡"),
            Condition("면적 B", f"{args.area_b:.0f}±{tol:.0f}㎡"),
            Condition("기준일", today),
        ),
        items=tuple(items),
        secondary_items=None,
        comparison=Comparison(
            row_labels=ROW_LABELS,
            columns=tuple(
                ComparisonColumn(
                    name=item.name, values=tuple(m.value for m in item.metrics)
                )
                for item in items
            ),
        ),
        narrative=Narrative(why=copy.why, fit_for=copy.fit_for),
        methodology=(
            "각 지역에서 목표 면적대의 최근 90일 계약 거래가 예산 이하인 단지만 후보로 구성",
            "후보 중 넛지 점수 1위를 대표로 선정 (--pnu 로 수동 지정 가능)",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "계약일 기준이라 신고 지연으로 최근 거래가 빠질 수 있습니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=tuple(
            MapCta(
                id=f"map-{'ab'[i]}",
                label=f"{plan['name']} 조건으로 보기",
                nudges=(args.nudge,),
                sigungu_code=plan["code"],
                region_label=plan["name"],
                filters={
                    "max_price": args.budget,
                    "min_area": round(plan["area"] - tol, 1),
                    "max_area": round(plan["area"] + tol, 1),
                },
            )
            for i, plan in enumerate(plans)
        ),
    )
