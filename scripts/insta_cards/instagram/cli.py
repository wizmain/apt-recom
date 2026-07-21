"""인스타 캐러셀 발행 CLI.

사용 (배포 완료 후):
  .venv/bin/python -m scripts.insta_cards.instagram value-seoul-20260718
  옵션: --dry-run(검증·캡션 미리보기만) --force(중복 게이트 통과)
        --check(원격 기게시 확인) --caption-file f.txt --refresh-token
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from scripts.insta_cards.instagram.api import (  # noqa: E402
    InstagramApiError,
    InstagramClient,
    read_log_status,
)
from scripts.insta_cards.instagram.caption import (  # noqa: E402
    CaptionError,
    build_caption,
    validate_caption,
)

DEFAULT_SITE_URL = "https://apt-recom.kr"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="인스타그램 캐러셀 발행")
    parser.add_argument("slug", nargs="?", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true", help="원격 기게시 여부 확인")
    parser.add_argument("--caption-file", type=str, default=None)
    parser.add_argument("--refresh-token", action="store_true")
    return parser


def make_client() -> InstagramClient:
    user_id = os.getenv("INSTAGRAM_USER_ID")
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not user_id or not token:
        raise SystemExit(
            "INSTAGRAM_USER_ID / INSTAGRAM_ACCESS_TOKEN 미설정 — "
            "docs/guides/instagram-api-setup.md 참조"
        )
    site_url = os.getenv("INSTAGRAM_SITE_URL", DEFAULT_SITE_URL)
    return InstagramClient(user_id, token, site_url)


def run_publish(
    client, slug: str, *, caption_file: str | None, force: bool, dry_run: bool
) -> None:
    me = client.verify_token()
    print(f"계정 확인: @{me.get('username', '?')}")

    prior = read_log_status(slug)
    if prior in ("published", "published_pending") and not force:
        raise SystemExit(
            f"'{slug}' 는 로그상 {prior} 상태입니다 — 실게시 여부는 --check 로 확인, "
            "중복 게시를 감수하려면 --force"
        )

    manifest = client.fetch_manifest(slug)
    if caption_file:
        caption = Path(caption_file).read_text(encoding="utf-8").strip()
        validate_caption(caption, slug)
    else:
        caption = build_caption(manifest)

    if dry_run:
        quota = client.publishing_quota()
        client.verify_assets(slug, manifest)
        print(f"쿼터: {quota}")
        print(
            f"자산 {len(manifest['instagram_assets'])}장 검증 통과 (gen {manifest['asset_generation']})"
        )
        print("--- 캡션 미리보기 ---")
        print(caption)
        print("--- dry-run: 발행하지 않았습니다 ---")
        return

    result = client.publish_carousel(slug, manifest, caption)
    print(f"발행 완료: {result['permalink']} (media_id {result['media_id']})")


def run_check(client, slug: str) -> None:
    marker = f"apt-recom.kr/content/{slug}"
    for item in client.recent_permalinks():
        if marker in (item.get("caption") or ""):
            print(f"기게시 확인: {item.get('permalink')}")
            return
    print(f"최근 25건에 '{slug}' 게시물 없음")


def _run(args: argparse.Namespace) -> None:
    client = make_client()
    if args.refresh_token:
        data = client.refresh_token()
        print(
            "새 장기 토큰 (60일) — .env 의 INSTAGRAM_ACCESS_TOKEN 을 직접 교체하세요:"
        )
        print(data.get("access_token", ""))
        return
    if not args.slug:
        raise SystemExit("slug 를 지정하세요 (또는 --refresh-token)")
    if args.check:
        run_check(client, args.slug)
        return
    run_publish(
        client,
        args.slug,
        caption_file=args.caption_file,
        force=args.force,
        dry_run=args.dry_run,
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        _run(args)
    except (InstagramApiError, CaptionError) as e:
        # 원인 예외(__cause__)에 언마스킹 토큰이 남을 수 있어 메시지만 출력하고
        # 풀 트레이스백은 노출하지 않는다 (Task 4 리뷰 이월 계약).
        raise SystemExit(str(e)) from None


if __name__ == "__main__":
    main()
