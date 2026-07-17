"""--publish 시 프론트 레지스트리 반영 — posts.json upsert + cover 복사.

cover 경로가 slug 고정(/content/instagram/{slug}/cover.png)이라 재발행 시
한쪽만 교체되면 구 레코드가 새 cover 를 가리켜 "같은 실행의 동일 데이터"
원칙이 깨진다 → 2파일 백업 스왑 (spec §3):
  새 파일들을 임시 경로에 준비 → cover 백업 후 새 cover 배치 →
  posts.json 교체, 실패 시 cover 원복 후 re-raise.
어떤 실패 경로에서도 "새 cover + 구 레코드"(또는 역) 조합이 남지 않는다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "web" / "frontend-next"
POSTS_JSON_RELPATH = Path("src/content/instagram/posts.json")
COVER_PUBLIC_RELDIR = Path("public/content/instagram")
COVER_FILENAME = "cover.png"
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class FrontendPublishError(RuntimeError):
    pass


def public_cover_path(slug: str) -> str:
    return f"/content/instagram/{slug}/{COVER_FILENAME}"


def upsert_posts(posts: list[dict], record: dict) -> list[dict]:
    """같은 slug 교체 후 결정적 정렬: published_at DESC → generated_at DESC → slug ASC."""
    merged = [p for p in posts if p.get("slug") != record["slug"]] + [record]
    merged.sort(key=lambda p: p.get("slug") or "")  # 3차: slug ASC (stable sort 활용)
    merged.sort(
        key=lambda p: (p.get("published_at") or "", p.get("generated_at") or ""),
        reverse=True,
    )
    return merged


def _load_posts(posts_path: Path) -> list[dict]:
    if not posts_path.exists():
        return []
    try:
        data = json.loads(posts_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise FrontendPublishError(f"posts.json 파싱 실패: {posts_path} — {e}") from e
    if not isinstance(data, list):
        raise FrontendPublishError(f"posts.json 이 배열이 아닙니다: {posts_path}")
    return data


def publish_to_frontend(
    record: dict, cover_src: Path, frontend_root: Path = FRONTEND_ROOT
) -> Path:
    if not cover_src.is_file():
        raise FrontendPublishError(f"cover 원본이 없습니다: {cover_src}")

    try:
        slug = record["slug"]
    except KeyError:
        raise FrontendPublishError("record에 'slug' 필드가 없습니다") from None
    if not SLUG_PATTERN.match(slug):
        raise FrontendPublishError(f"slug 형식 오류: {slug} — 소문자 ASCII+하이픈만 허용")
    posts_path = frontend_root / POSTS_JSON_RELPATH
    cover_dst = frontend_root / COVER_PUBLIC_RELDIR / slug / COVER_FILENAME

    rec = dict(record)
    rec["cover_image"] = public_cover_path(slug)
    new_posts = upsert_posts(_load_posts(posts_path), rec)

    pid = os.getpid()
    posts_tmp = posts_path.with_name(f"posts.json.tmp-{pid}")
    cover_tmp = cover_dst.with_name(f"{COVER_FILENAME}.tmp-{pid}")
    cover_bak = cover_dst.with_name(f"{COVER_FILENAME}.bak-{pid}")

    posts_path.parent.mkdir(parents=True, exist_ok=True)
    cover_dst.parent.mkdir(parents=True, exist_ok=True)
    posts_tmp.write_text(
        json.dumps(new_posts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copyfile(cover_src, cover_tmp)

    had_cover = cover_dst.exists()
    try:
        if had_cover:
            os.replace(cover_dst, cover_bak)  # ① 기존 cover 백업 (rename — 원복 가능)
        os.replace(cover_tmp, cover_dst)  # ② 새 cover 배치
        try:
            os.replace(posts_tmp, posts_path)  # ③ posts.json 교체
        except BaseException:
            # ③ 실패 → 새 cover 를 치우고 백업 원복: "새 cover + 구 레코드" 방지
            os.replace(cover_dst, cover_tmp)
            if had_cover:
                os.replace(cover_bak, cover_dst)
            raise
        if had_cover:
            cover_bak.unlink(missing_ok=True)  # ④ 성공 — 백업 정리
    finally:
        posts_tmp.unlink(missing_ok=True)
        cover_tmp.unlink(missing_ok=True)
    return posts_path
