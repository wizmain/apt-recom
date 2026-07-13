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
    # candidate 는 정확한 slug 이름으로만 조회하므로 임시(.tmp-)·백업(.bak-)
    # 디렉토리(slug + 접미사)는 매치되지 않는다 — 별도 필터 불필요.
    if not root.exists():
        return None
    for date_dir in sorted(root.iterdir()):
        if not date_dir.is_dir():
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
        _swap_into_place(tmp_dir, final_dir, existing)
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return final_dir


def _swap_into_place(tmp_dir: Path, final_dir: Path, existing: Path | None) -> None:
    """완성된 tmp_dir 을 final_dir 로 배치한다.

    어떤 실패 경로에서도 기존 발행물이 소실되지 않도록,
    기존 디렉토리 삭제는 항상 새 디렉토리 배치가 성공한 뒤에만 수행한다.
    """
    if existing is None:
        # 신규 발행: final_dir 미존재 → 단일 atomic rename
        os.replace(tmp_dir, final_dir)
        return

    if existing != final_dir:
        # 다른 날짜 재발행(--force): final_dir 은 미존재라 먼저 배치해도 안전.
        # 구 디렉토리 삭제는 성공 후 정리 단계 — replace 실패 시 구 발행물 유지.
        os.replace(tmp_dir, final_dir)
        shutil.rmtree(existing)
        return

    # 같은 날짜 재발행(--force): 백업 스왑 — 교체 실패 시 백업에서 원복.
    # 백업 이름은 slug + ".bak-" 접미사라 find_existing_slug_dir(정확한 slug
    # 이름 매치)에는 잡히지 않는다.
    backup_dir = final_dir.with_name(f"{final_dir.name}.bak-{os.getpid()}")
    os.replace(final_dir, backup_dir)
    try:
        os.replace(tmp_dir, final_dir)
    except BaseException:
        os.replace(backup_dir, final_dir)  # 기존 발행물 원복
        raise
    shutil.rmtree(backup_dir)
