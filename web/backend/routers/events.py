"""클라이언트 이벤트 수집 라우터.

단지 상세 → 라이프스타일 추천 전환 퍼널 측정용 클라이언트 이벤트를 수집한다.
허용 event_type 만 user_event 테이블에 적재하고, 그 외는 422로 거부.

적재는 BackgroundTasks 로 비동기 수행 — 응답 지연 없음.
device_id 식별 불가(헤더 미포함) 시 log_event 가 no-op 처리하므로 요청 자체는 200 반환.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, field_validator

from services.activity_log import log_event
from services.identity import get_user_identifier

router = APIRouter()

# 허용 event_type 화이트리스트 — 변경 시 이 상수만 수정.
ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "detail_recommend_cta_view",
        "detail_recommend_cta_click",
    }
)


class ClientEventRequest(BaseModel):
    """클라이언트 이벤트 요청 본문.

    event_type 은 ALLOWED_EVENT_TYPES 에 포함된 값만 허용.
    payload 는 그대로 user_event.payload(JSONB) 에 저장.

    페이로드 계약:
    - detail_recommend_cta_view : { "pnu": str, "top_nudges": [str, ...] }
    - detail_recommend_cta_click: { "pnu": str, "preset_nudges": [str, ...], "sigungu_code": str }
    """

    event_type: str
    payload: dict

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in ALLOWED_EVENT_TYPES:
            allowed = ", ".join(sorted(ALLOWED_EVENT_TYPES))
            raise ValueError(f"허용되지 않는 event_type입니다. 허용 목록: {allowed}")
        return v


@router.post("/events", status_code=202)
def collect_event(
    req: ClientEventRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """클라이언트 이벤트 1건을 user_event 테이블에 비동기 적재한다.

    - 허용 event_type 이 아니면 422 반환(Pydantic validator 에서 처리).
    - device_id 식별 불가(헤더 없음) 시 log_event 가 no-op — 요청은 202 반환.
    - 적재는 BackgroundTasks 로 비동기 처리 — HTTP 응답 지연 없음.
    """
    device_id = get_user_identifier(request)
    background_tasks.add_task(
        log_event,
        device_id,
        req.event_type,
        None,
        req.payload,
    )
    return {"accepted": True}
