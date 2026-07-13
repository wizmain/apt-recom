"""출력 — 임시 디렉토리 렌더 후 atomic rename. 부분 산출물이 남지 않는다.

slug 는 랜딩 URL 키이므로 날짜와 무관하게 전역 유일해야 한다 (spec §3).
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import date
from pathlib import Path

from PIL import Image

from scripts.insta_cards.publication import Publication, to_json_dict

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "reports" / "insta"
TMP_MARKER = ".tmp-"


class SlugConflictError(RuntimeError):
    pass


def find_existing_slug_dir(slug: str, root: Path = OUTPUT_ROOT) -> Path | None:
    if not root.exists():
        return None
    for date_dir in sorted(root.iterdir()):
        if not date_dir.is_dir() or TMP_MARKER in date_dir.name:
            continue
        candidate = date_dir / slug
        if candidate.is_dir():
            return candidate
    return None


def write_publication(
    pub: Publication,
    slides: list[tuple[str, Image.Image]],
    *,
    force: bool = False,
    root: Path = OUTPUT_ROOT,
) -> Path:
    existing = find_existing_slug_dir(pub.slug, root)
    if existing is not None and not force:
        raise SlugConflictError(
            f"slug '{pub.slug}' 가 이미 존재합니다: {existing} — 덮어쓰려면 --force"
        )

    date_dir = root / date.today().isoformat()
    date_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = date_dir / f"{pub.slug}{TMP_MARKER}{os.getpid()}"
    final_dir = date_dir / pub.slug

    try:
        tmp_dir.mkdir()
        for filename, image in slides:
            image.save(tmp_dir / filename, format="PNG")
        (tmp_dir / "publication.json").write_text(
            json.dumps(to_json_dict(pub), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if existing is not None:
            shutil.rmtree(existing)  # --force: 이전 슬라이드 잔존 방지, 통째 교체
        os.replace(tmp_dir, final_dir)
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return final_dir
