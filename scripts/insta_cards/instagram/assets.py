"""인스타 발행용 자산 — PNG 캐러셀을 JPEG + 순서 manifest 로 변환.

Instagram Content Publishing 은 사진을 JPEG 기준으로 처리한다 (spec §3-1).
세대(generation)는 원본 publication.json 바이트의 SHA-256 앞 12자 —
재발행 시 내용이 바뀌면 경로가 바뀌어 immutable 캐시와 충돌하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image

MAX_JPEG_BYTES = 8 * 1024 * 1024  # Instagram 사진 한도
JPEG_QUALITY = 90
MIN_SLIDES = 2  # 캐러셀 최소
MAX_SLIDES = 10  # 캐러셀 최대

SLIDE_PNG_PATTERN = re.compile(r"^\d{2}-[a-z0-9-]+\.png$")


class InstagramAssetError(RuntimeError):
    pass


def compute_generation(publication_bytes: bytes) -> str:
    return hashlib.sha256(publication_bytes).hexdigest()[:12]


def build_ig_assets(source_dir: Path, dest_dir: Path) -> dict:
    """source 의 PNG 전 장 → dest 에 JPEG + manifest 포함 publication.json.

    반환: instagram_assets/asset_generation 이 추가된 manifest dict.
    """
    pub_path = source_dir / "publication.json"
    if not pub_path.is_file():
        raise InstagramAssetError(f"publication.json 없음: {source_dir}")
    pngs = sorted(
        p for p in source_dir.glob("*.png") if SLIDE_PNG_PATTERN.match(p.name)
    )
    if not MIN_SLIDES <= len(pngs) <= MAX_SLIDES:
        raise InstagramAssetError(
            f"캐러셀 장수 {len(pngs)} — {MIN_SLIDES}~{MAX_SLIDES}장이어야 발행 가능"
        )

    pub_bytes = pub_path.read_bytes()
    manifest = json.loads(pub_bytes)
    generation = compute_generation(pub_bytes)

    dest_dir.mkdir(parents=True, exist_ok=True)
    asset_names: list[str] = []
    for png in pngs:
        jpg_name = png.name[:-4] + ".jpg"
        out = dest_dir / jpg_name
        Image.open(png).convert("RGB").save(out, format="JPEG", quality=JPEG_QUALITY)
        if out.stat().st_size > MAX_JPEG_BYTES:
            raise InstagramAssetError(f"{jpg_name}: 8MB 초과 — 발행 불가")
        asset_names.append(jpg_name)

    manifest["instagram_assets"] = asset_names
    manifest["asset_generation"] = generation
    (dest_dir / "publication.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
