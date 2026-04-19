"""사용자 행동 로그·챗봇 대화 로그 저장 서비스.

익명 device_id 기반으로 수집. 개인정보(IP, UA, 로그인 정보)는 저장하지 않는다.

정책:
- device_id 없으면 no-op (opt-out 또는 미설정 상황)
- INSERT 실패는 본 요청을 죽이지 않도록 logger.warning 으로 흡수
- tool_calls 는 {name, arguments} 만 저장, result 본문은 저장하지 않음
- context 는 화이트리스트 필드만 저장
"""

from __future__ import annotations

import json
import logging

from database import DictConnection

logger = logging.getLogger(__name__)

# 화이트리스트: chat_log.context 에 저장 가능한 키
_CONTEXT_WHITELIST = ("apartment_pnu", "apartment_name", "nudges", "selected_region")


def _sanitize_context(context: dict | None) -> dict | None:
    if not context:
        return None
    sanitized = {k: context[k] for k in _CONTEXT_WHITELIST if k in context}
    return sanitized or None


def _sanitize_tool_calls(tool_calls: list | None) -> list:
    """tool_calls에서 name/arguments만 남기고 result/result_preview 등 본문은 제거."""
    if not tool_calls:
        return []
    sanitized = []
    for t in tool_calls:
        if not isinstance(t, dict):
            continue
        sanitized.append({
            "name": t.get("name"),
            "arguments": t.get("arguments"),
        })
    return sanitized


def log_event(
    device_id: str | None,
    event_type: str,
    event_name: str | None = None,
    payload: dict | None = None,
) -> None:
    """사용자 행동 이벤트 1건 저장.

    device_id 가 없으면 no-op. 실패는 warning 만 남기고 흡수한다.
    try/finally 로 INSERT 중 예외가 나도 conn 반납 보장 (pool leak 방지).
    """
    if not device_id or not event_type:
        return
    conn = None
    try:
        conn = DictConnection()
        conn.execute(
            "INSERT INTO user_event (device_id, event_type, event_name, payload) "
            "VALUES (%s, %s, %s, %s::jsonb)",
            [device_id, event_type, event_name, json.dumps(payload or {}, ensure_ascii=False)],
        )
    except Exception as e:
        logger.warning(f"log_event failed (type={event_type}): {e}")
    finally:
        if conn is not None:
            conn.close()


def log_chat(
    device_id: str | None,
    session_id: str | None,
    user_message: str,
    assistant_message: str,
    tool_calls: list | None = None,
    context: dict | None = None,
    terminated_early: bool = False,
) -> None:
    """챗봇 대화 1건 저장. user_message 가 비어있으면 저장하지 않는다.

    try/finally 로 INSERT 예외 시에도 conn 반납 보장 (pool leak 방지).
    """
    if not (user_message or "").strip():
        return
    conn = None
    try:
        conn = DictConnection()
        conn.execute(
            "INSERT INTO chat_log (device_id, session_id, user_message, assistant_message, "
            "  tool_calls, context, terminated_early) "
            "VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)",
            [
                device_id,
                session_id,
                user_message,
                assistant_message or "",
                json.dumps(_sanitize_tool_calls(tool_calls), ensure_ascii=False),
                json.dumps(_sanitize_context(context) or {}, ensure_ascii=False),
                terminated_early,
            ],
        )
    except Exception as e:
        logger.warning(f"log_chat failed: {e}")
    finally:
        if conn is not None:
            conn.close()
