"""데일리 로테이션 리졸버 (Phase 0 — read-only).

발행일 → (series, 파라미터, slug, 생성 명령)을 결정론적으로 산출한다. 생성·발행은
하지 않는다(기존 `python -m scripts.insta_cards ...`를 사람이 실행). PRD §5·§9-2.

사용:
  .venv/bin/python -m scripts.insta_cards.rotation            # 오늘(KST) 배정
  .venv/bin/python -m scripts.insta_cards.rotation 2026-07-30 # 특정일
  .venv/bin/python -m scripts.insta_cards.rotation --calendar 14  # 앵커부터 14일 표
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import yaml

ROTATION_PATH = Path(__file__).resolve().parent / "rotation.yaml"

# date.weekday(): Mon=0 … Sun=6 → yaml 키.
_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# series 내부명 → CLI --series 값 (하이픈).
_CLI_NAME = {
    "trade_top": "trade-top",
    "value": "value",
    "compare": "compare",
    "lifestyle": "lifestyle",
    "budget_choice": "budget-choice",
}

# 포맷별 착지 힌트(PRD §4). 운영자 참고용 — 실제 프로필 링크는 고정 /content 인덱스.
_CTA_HINT = {
    "trade_top": "실거래 대시보드",
    "value": "지도(넛지 프리셋)",
    "compare": "지도/검색",
    "lifestyle": "넛지 지도",
    "budget_choice": "검색(예산 필터)",
}


def load_rotation(path: Path = ROTATION_PATH) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or "weekday_format" not in cfg:
        raise ValueError(f"rotation.yaml 형식 오류: {path}")
    return cfg


def _series_for(cfg: dict, target: date) -> str:
    return cfg["weekday_format"][_WEEKDAY_KEYS[target.weekday()]]


def series_occurrence_index(cfg: dict, target: date) -> int:
    """앵커일(포함)부터 target(포함)까지 같은 series 가 등장한 횟수 − 1 (0-based).

    각 요일이 정확히 한 series 에 매핑되므로, 이 값이 해당 series 큐의 순환 위치다.
    """
    anchor = date.fromisoformat(cfg["anchor_date"])
    if target < anchor:
        raise ValueError(f"anchor_date({anchor}) 이후 날짜만 지원합니다: {target}")
    target_series = _series_for(cfg, target)
    count = 0
    d = anchor
    while d <= target:
        if _series_for(cfg, d) == target_series:
            count += 1
        d += timedelta(days=1)
    return count - 1


def _build_command(series: str, params: dict, slug: str) -> str:
    parts = [
        "python -m scripts.insta_cards",
        f"--series {_CLI_NAME[series]}",
        f"--slug {slug}",
    ]
    if series == "trade_top":
        parts.append(f"--days {params['days']}")
        parts.append(f"--min-hhld {params['min_hhld']}")
    elif series == "value":
        parts.append(f'--region "{params["keyword"]}"')
        # 코드가 있으면 모집단을 그 시군구로 한정한다 (동명 시군구 방지, 2026-08-22).
        if params.get("code"):
            parts.append(f"--sigungu-code {params['code']}")
        parts.append(f"--nudge {params['nudge']}")
        parts.append(f"--min-smallest-area {params['min_smallest_area']}")
        parts.append(f"--min-area {params['min_area']}")
        parts.append(f"--max-area {params['max_area']}")
    elif series == "compare":
        parts.append(f"--regions {params['regions']}")
        parts.append(f"--nudge {params['nudge']}")
        parts.append(f"--min-hhld {params['min_hhld']}")
    elif series == "lifestyle":
        parts.append(f"--profile {params['profile']}")
        parts.append(f"--region {params['region']}")
        parts.append(f"--min-hhld {params['min_hhld']}")
        parts.append(f"--min-smallest-area {params['min_smallest_area']}")
    elif series == "budget_choice":
        parts.append(f"--regions {params['regions']}")
        parts.append(f"--budget {params['budget']}")
        parts.append(f"--area-a {params['area_a']}")
        parts.append(f"--area-b {params['area_b']}")
        parts.append(f"--min-hhld {params['min_hhld']}")
        parts.append(f"--min-budget-ratio {params['min_budget_ratio']}")
    return " ".join(parts)


def resolve(cfg: dict, target: date) -> dict:
    """target 날짜의 배정을 결정론적으로 반환."""
    series = _series_for(cfg, target)
    occ = series_occurrence_index(cfg, target)
    stamp = target.strftime("%Y%m%d")
    s = cfg["series"][series]

    if series == "trade_top":
        params = {"days": s["days"], "min_hhld": s["min_hhld"]}
        slug = f"trade-top-{stamp}"
    elif series == "value":
        region = s["regions"][occ % len(s["regions"])]
        params = {
            "keyword": region["keyword"],
            "code": region.get("code"),
            "nudge": s["nudge"],
            "min_smallest_area": s["min_smallest_area"],
            "min_area": s["min_area"],
            "max_area": s["max_area"],
        }
        slug = f"value-{region['slug']}-{stamp}"
    elif series == "compare":
        pair = s["pairs"][occ % len(s["pairs"])]
        params = {"regions": pair, "nudge": s["nudge"], "min_hhld": s["min_hhld"]}
        slug = f"compare-{pair.replace(',', '-vs-')}-{stamp}"
    elif series == "lifestyle":
        profile = s["profiles"][occ % len(s["profiles"])]
        code = s["regions"][occ % len(s["regions"])]
        params = {
            "profile": profile,
            "region": code,
            "min_hhld": s["min_hhld"],
            "min_smallest_area": s["min_smallest_area"],
        }
        slug = f"lifestyle-{profile}-{code}-{stamp}"
    elif series == "budget_choice":
        item = s["items"][occ % len(s["items"])]
        params = {
            **item,
            "min_hhld": s["min_hhld"],
            "min_budget_ratio": s["min_budget_ratio"],
        }
        slug = f"budget-choice-{item['regions'].replace(',', '-vs-')}-{stamp}"
    else:
        raise ValueError(f"알 수 없는 series: {series}")

    return {
        "date": target.isoformat(),
        "weekday": _WEEKDAY_KEYS[target.weekday()],
        "series": series,
        "occurrence": occ,
        "params": params,
        "slug": slug,
        "command": _build_command(series, params, slug),
        "cta_hint": _CTA_HINT[series],
        # 프로필 링크는 고정 /content 인덱스(ig_daily). 포맷 성과는 content_view.series 로 측정(PRD 확정).
        "utm_campaign": "ig_daily",
    }


def _print_one(a: dict) -> None:
    print(f"[{a['date']} {a['weekday']}] {a['series']} (#{a['occurrence']})")
    print(f"  slug : {a['slug']}")
    print(f"  cta  : {a['cta_hint']}")
    print(f"  run  : {a['command']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="데일리 로테이션 배정 리졸버(read-only)"
    )
    parser.add_argument("target", nargs="?", help="YYYY-MM-DD (기본: 오늘 KST)")
    parser.add_argument(
        "--calendar", type=int, default=None, help="앵커일부터 N일 표 출력"
    )
    args = parser.parse_args(argv)
    cfg = load_rotation()

    if args.calendar:
        start = date.fromisoformat(cfg["anchor_date"])
        for i in range(args.calendar):
            _print_one(resolve(cfg, start + timedelta(days=i)))
        return 0

    if args.target:
        target = date.fromisoformat(args.target)
    else:
        # date.today() 는 실행 환경 로컬. 파일럿은 KST 환경에서 실행 가정.
        target = date.today()
    _print_one(resolve(cfg, target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
