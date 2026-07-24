"""posts.json → 백엔드 content_index.json 투영 생성/검증.

백엔드는 Railway 배포 시 web/frontend-next 를 볼 수 없으므로, 발행 시점에
published 메타를 백엔드로 투영해 커밋한다(생성 아티팩트, router.gen.ts 와 동일 철학).
--check 는 커밋된 인덱스가 posts.json 투영과 일치하는지 CI 에서 검증한다(드리프트 차단).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTS_PATH = (
    ROOT / "web" / "frontend-next" / "src" / "content" / "instagram" / "posts.json"
)
INDEX_PATH = ROOT / "web" / "backend" / "content" / "content_index.json"

# content_index 로 투영하는 메타 필드 (본문/구조 필드는 웹이 렌더하므로 제외).
INDEX_FIELDS = (
    "slug",
    "series",
    "title",
    "eyebrow",
    "summary",
    "cover_image",
    "cover_alt",
    "data_as_of",
    "published_at",
)


def read_posts(posts_path: Path = POSTS_PATH) -> list[dict]:
    data = json.loads(posts_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"posts.json 이 배열이 아닙니다: {posts_path}")
    return data


def build_index(posts: list[dict]) -> list[dict]:
    """published 만, 인덱스 필드만, published_at DESC (동률 slug ASC)."""
    published = [p for p in posts if p.get("status") == "published"]
    for p in published:
        missing = [f for f in INDEX_FIELDS if not p.get(f)]
        if missing:
            raise ValueError(
                f"published 레코드 필수 필드 누락 [{p.get('slug')}]: {missing}"
            )
    published.sort(key=lambda p: p["slug"])  # 3차: slug ASC (stable sort)
    published.sort(key=lambda p: p["published_at"], reverse=True)  # 1차: 최신 우선
    return [{f: p[f] for f in INDEX_FIELDS} for p in published]


def _serialize(index: list[dict]) -> str:
    return json.dumps(index, ensure_ascii=False, indent=2) + "\n"


def write_index(index: list[dict], out_path: Path = INDEX_PATH) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(f"{out_path.name}.tmp-{os.getpid()}")
    tmp.write_text(_serialize(index), encoding="utf-8")
    tmp.replace(out_path)  # 원자적 rename


def check(posts_path: Path = POSTS_PATH, index_path: Path = INDEX_PATH) -> bool:
    expected = _serialize(build_index(read_posts(posts_path)))
    actual = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    return actual == expected


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="content_index.json 생성/검증")
    parser.add_argument(
        "--check", action="store_true", help="드리프트 검사(파일을 쓰지 않음)"
    )
    args = parser.parse_args(argv)
    if args.check:
        if check():
            print("content_index.json: in sync")
            return 0
        print(
            "content_index.json: DRIFT — `python -m scripts.sync_content_index` 실행 후 커밋",
            file=sys.stderr,
        )
        return 1
    write_index(build_index(read_posts()))
    print(f"content_index.json 갱신: {INDEX_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
