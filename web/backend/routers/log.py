"""사용자 행동 이벤트 수집 엔드포인트.

프론트가 페이지뷰/필터 변경 등 서버 핸들러가 별도로 없는 이벤트를
직접 기록하기 위한 공용 엔드포인트. 검색/넛지/상세처럼 이미 서버
핸들러가 있는 이벤트는 해당 라우터에서 직접 로깅한다.

스키마·정책:
- 요청 헤더 `X-Device-Id` 필수 (없으면 no-op, 응답은 성공)
- event_type 은 약속된 문자열 (page_view, filter_change, detail_view_client 등)
- payload 는 JSON 객체 (크기 제한 없음 — 프론트에서 의미 있는 필드만)
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from services.activity_log import log_event
from services.identity import get_user_identifier

router = APIRouter()


class LogEventRequest(BaseModel):
    event_type: str
    event_name: str | None = None
    payload: dict | None = None


@router.post("/log/event")
def log_event_endpoint(body: LogEventRequest, request: Request):
    """사용자 행동 이벤트 1건 저장.

    device_id 가 헤더에 없으면 no-op (opt-out 된 사용자). 응답은 항상 성공.
    """
    device_id = get_user_identifier(request)
    log_event(device_id, body.event_type, body.event_name, body.payload)
    return {"ok": True}
