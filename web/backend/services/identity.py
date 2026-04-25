"""사용자 식별자 추출 서비스.

웹과 Toss 미니앱이 동일한 백엔드를 공유하기 위한 헬퍼.

식별자 우선순위:
    1. `x-anon-key`  — Toss 미니앱이 발급한 익명 hash (앱별 고유)
    2. `x-device-id` — 기존 웹 클라이언트의 익명 UUID

값이 비어있거나 헤더가 없으면 None 반환 → 호출 측은 no-op 처리.
포맷 검증은 하지 않는다(저장은 raw text). 비정상 값은 DB 컬럼 길이 제약으로 차단.

사용 예:
    from services.identity import get_user_identifier
    user_id = get_user_identifier(request)
"""

from __future__ import annotations

from fastapi import Request

_HEADER_ANON_KEY = "x-anon-key"
_HEADER_DEVICE_ID = "x-device-id"


def get_user_identifier(request: Request) -> str | None:
    """Toss anon-key 우선, 없으면 기존 device_id를 반환. 둘 다 없으면 None."""
    anon = request.headers.get(_HEADER_ANON_KEY)
    if anon:
        anon = anon.strip()
        if anon:
            return anon
    device = request.headers.get(_HEADER_DEVICE_ID)
    if device:
        device = device.strip()
        if device:
            return device
    return None
