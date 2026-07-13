"""CLI — 시리즈 디스패치. 검증 실패·데이터 부족은 그대로 예외로 죽는다.

사용:
  .venv/bin/python -m scripts.insta_cards --series budget-choice \
      --budget 70000 --regions 11440,41135 --area-a 59 --area-b 84
  .venv/bin/python -m scripts.insta_cards --series value --region 서울 --slug value-seoul-20260713
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# 직접 실행(-m 없이 shim 경유) 대비 — 프로젝트 루트를 sys.path 에 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.insta_cards.copywriting import NUDGE_LABELS, load_copy_overrides  # noqa: E402
from scripts.insta_cards.output import OUTPUT_ROOT, write_publication  # noqa: E402
from scripts.insta_cards.publication import (  # noqa: E402
    SERIES_CLI_NAMES,
    SERIES_SLUGS,
    SLUG_PATTERN,
    Series,
    validate,
)
from scripts.insta_cards.slides import build_slides  # noqa: E402

DEFAULT_TRADE_TOP_DAYS = 7
DEFAULT_MIN_HOUSEHOLDS = 100
DEFAULT_AREA_TOLERANCE = 5.0
DEFAULT_NUDGES = {
    Series.COMPARE: "newlywed",
    Series.VALUE: "cost",
    Series.BUDGET_CHOICE: "cost",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="인스타그램 카드뉴스 캐러셀 생성")
    parser.add_argument("--series", required=True, choices=sorted(SERIES_CLI_NAMES))
    parser.add_argument("--slug", type=str, default=None, help="미지정 시 자동 생성")
    parser.add_argument(
        "--publish", action="store_true", help="status=published 로 발행"
    )
    parser.add_argument(
        "--copy-file", type=str, default=None, help="문구 오버라이드 YAML"
    )
    parser.add_argument("--dry-run", action="store_true", help="검증·선정 결과만 출력")
    parser.add_argument(
        "--force", action="store_true", help="동일 slug 디렉토리 통째 교체"
    )
    # trade-top
    parser.add_argument("--days", type=int, default=DEFAULT_TRADE_TOP_DAYS)
    # compare / budget-choice
    parser.add_argument(
        "--regions", type=str, default=None, help="시군구 코드 2개, 콤마 구분"
    )
    parser.add_argument("--nudge", type=str, default=None)
    # value / lifestyle
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="value: 키워드 / lifestyle: 시군구 코드",
    )
    parser.add_argument("--min-hhld", type=int, default=DEFAULT_MIN_HOUSEHOLDS)
    # budget-choice
    parser.add_argument("--budget", type=int, default=None, help="예산 상한 (만원)")
    parser.add_argument("--area-a", type=float, default=None)
    parser.add_argument("--area-b", type=float, default=None)
    parser.add_argument("--area-tolerance", type=float, default=DEFAULT_AREA_TOLERANCE)
    parser.add_argument("--pnu-a", type=str, default=None)
    parser.add_argument("--pnu-b", type=str, default=None)
    # lifestyle
    parser.add_argument(
        "--profile", type=str, default=None, choices=sorted(NUDGE_LABELS)
    )
    parser.add_argument("--max-price", type=int, default=None)
    parser.add_argument("--min-area", type=float, default=None)
    parser.add_argument("--max-area", type=float, default=None)
    return parser


def build_auto_slug(series: Series, args) -> str:
    stamp = date.today().strftime("%Y%m%d")
    series_slug = SERIES_SLUGS[series]
    if series is Series.TRADE_TOP:
        slug = f"{series_slug}-{stamp}"
    elif series in (Series.COMPARE, Series.BUDGET_CHOICE):
        codes = [c.strip() for c in (args.regions or "").split(",") if c.strip()]
        slug = f"{series_slug}-{'-vs-'.join(codes)}-{stamp}"
    elif series is Series.LIFESTYLE:
        slug = f"{series_slug}-{args.profile}-{args.region}-{stamp}"
    else:  # VALUE
        slug = f"{series_slug}-{args.region}-{stamp}"
    if not SLUG_PATTERN.match(slug):
        raise SystemExit(
            f"자동 slug '{slug}' 가 형식(소문자 ASCII+하이픈)에 맞지 않습니다 — "
            "한글 지역 키워드는 --slug 를 직접 지정하세요. "
            f"예: --slug {series_slug}-seoul-{stamp}"
        )
    return slug


def _validate_series_args(parser, series: Series, args) -> None:
    def require(names: list[str]) -> None:
        missing = [n for n in names if getattr(args, n.replace("-", "_")) is None]
        if missing:
            parser.error(
                f"--series {SERIES_SLUGS[series]} 에는 --{' --'.join(missing)} 가 필요합니다."
            )

    if series in (Series.COMPARE, Series.BUDGET_CHOICE):
        require(["regions"])
    if series is Series.BUDGET_CHOICE:
        require(["budget", "area-a", "area-b"])
    if series is Series.LIFESTYLE:
        require(["profile", "region"])
    if series is Series.VALUE and args.region is None:
        args.region = "서울"  # 기존 CLI 기본값 하위호환
    if args.nudge is None:
        args.nudge = DEFAULT_NUDGES.get(series, "cost")
    if args.nudge not in NUDGE_LABELS:
        parser.error(
            f"알 수 없는 넛지 id: {args.nudge} (허용: {', '.join(sorted(NUDGE_LABELS))})"
        )


def _print_dry_run_summary(pub) -> None:
    print(f"[dry-run] slug={pub.slug} series={pub.series.value} status={pub.status}")
    print(f"[dry-run] title: {pub.title}")
    print(f"[dry-run] hook:  {pub.hook}")
    print(f"[dry-run] items ({len(pub.items)}):")
    for item in pub.items:
        first = item.metrics[0]
        print(f"  {item.rank}. {item.name} — {first.label} {first.value}{first.unit}")
    if pub.secondary_items:
        print(f"[dry-run] secondary_items: {len(pub.secondary_items)}건")
    print(f"[dry-run] map_ctas: {[cta.id for cta in pub.map_ctas]}")
    print("[dry-run] 파일은 생성하지 않았습니다.")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    series = SERIES_CLI_NAMES[args.series]
    _validate_series_args(parser, series, args)

    slug = args.slug or build_auto_slug(series, args)
    if not SLUG_PATTERN.match(slug):
        raise SystemExit(f"slug '{slug}' 형식 오류 — 소문자 ASCII+하이픈만 허용")
    status = "published" if args.publish else "draft"
    published_at = date.today().isoformat() if args.publish else None
    copy_overrides = load_copy_overrides(args.copy_file) if args.copy_file else None

    # 시리즈 모듈은 지연 임포트 — batch.db 의존을 실제 사용 시점으로 미룬다
    from scripts.insta_cards.series import (  # noqa: PLC0415
        budget_choice,
        compare,
        lifestyle,
        trade_top,
        value,
    )

    runners = {
        Series.TRADE_TOP: trade_top.run,
        Series.COMPARE: compare.run,
        Series.VALUE: value.run,
        Series.BUDGET_CHOICE: budget_choice.run,
        Series.LIFESTYLE: lifestyle.run,
    }
    pub = runners[series](
        args,
        slug=slug,
        status=status,
        published_at=published_at,
        copy_overrides=copy_overrides,
    )
    validate(pub)

    if args.dry_run:
        _print_dry_run_summary(pub)
        return

    slides = build_slides(pub)
    final_dir = write_publication(pub, slides, force=args.force, root=OUTPUT_ROOT)
    print(f"saved: {final_dir} ({len(slides)}장 + publication.json)")


if __name__ == "__main__":
    main()
