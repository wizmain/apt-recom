"""GET /api/content — 발행된 콘텐츠 목록(메타).

content_index.json(scripts.sync_content_index 생성물)을 읽어 published 목록을
반환한다. 상세 본문은 프론트(/content/[slug]/embed)가 렌더하므로 여기서는
목록 메타 + 커버 절대 URL 만 제공한다.

파일 누락/손상은 "발행분 없음"(정상 [])과 구분되는 배포 결함이므로 5xx 로 드러낸다.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from frontend_config import FRONTEND_BASE_URL

logger = logging.getLogger(__name__)
router = APIRouter()

INDEX_PATH = Path(__file__).resolve().parent.parent / "content" / "content_index.json"


def load_index(index_path: Path = INDEX_PATH) -> list[dict]:
    """인덱스 파일을 읽어 목록 반환. 파일 누락/손상/형식오류는 배포 결함 → 500."""
    try:
        raw = index_path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        logger.error("content_index.json 없음: %s", index_path)
        raise HTTPException(
            status_code=500, detail="content_index.json 없음 — 발행/배포 확인"
        ) from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("content_index.json 파싱 실패: %s", e)
        raise HTTPException(
            status_code=500, detail="content_index.json 파싱 실패"
        ) from e
    if not isinstance(data, list):
        logger.error("content_index.json 배열 아님")
        raise HTTPException(status_code=500, detail="content_index.json 형식 오류")
    return data


@router.get("/content")
def list_content() -> list[dict]:
    """published_at DESC 로 이미 정렬된 인덱스를 그대로 노출 + 커버 절대 URL."""
    return [
        {
            "slug": it["slug"],
            "series": it["series"],
            "title": it["title"],
            "eyebrow": it["eyebrow"],
            "summary": it["summary"],
            "cover_image_url": f"{FRONTEND_BASE_URL}{it['cover_image']}",
            "cover_alt": it["cover_alt"],
            "data_as_of": it["data_as_of"],
            "published_at": it["published_at"],
        }
        for it in load_index()
    ]
