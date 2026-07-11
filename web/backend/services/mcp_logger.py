"""MCP (Model Context Protocol) tool 호출 로깅.

외부 MCP 클라이언트(Claude Desktop / Cursor 등)의 tool 호출을 mcp_call_log 에
1건씩 적재한다. 사용자 분석은 (client_kind, client_ip /24 마스킹, created_at)
기준으로 수행.

구성:
    - ``McpRequestMeta``: 요청 단위 메타(IP / UA / kind) ContextVar.
    - ``mcp_logging_middleware``: ASGI 미들웨어. 헤더에서 IP/UA 추출 후 ContextVar set.
    - ``log_mcp_call``: tool 함수 데코레이터. 시그니처를 보존(FastMCP schema 생성에
      필수)하고 호출 전후로 시간 측정 + DB INSERT.

정책:
    - IP 는 X-Forwarded-For 첫 IP 의 /24 프리픽스로 마스킹 (개인정보 위험 ↓).
    - DB INSERT 실패는 logger.warning 으로 흡수 — MCP 응답 자체는 막지 않는다.
    - error_message 는 500자로 trim.
    - arguments 는 JSON 직렬화 가능 값만 보존; 직렬화 실패 시 ``{"_repr": str(...)}``.
"""

from __future__ import annotations

import functools
import inspect
import ipaddress
import json
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass

from database import DictConnection

logger = logging.getLogger(__name__)

_ERROR_MESSAGE_MAX = 500
_USER_AGENT_MAX = 256


@dataclass(frozen=True)
class McpRequestMeta:
    """단일 MCP 요청의 식별 메타데이터."""

    client_ip: str | None
    user_agent: str | None
    client_kind: str


_request_meta: ContextVar[McpRequestMeta | None] = ContextVar(
    "mcp_request_meta", default=None
)


def current_meta() -> McpRequestMeta | None:
    """현재 처리 중인 MCP 요청의 메타데이터 (없으면 None)."""
    return _request_meta.get()


# ── 클라이언트 분류 ────────────────────────────────────────────────────────

_CLIENT_KIND_PATTERNS: tuple[tuple[str, str], ...] = (
    # 매칭 우선순위 순. 더 구체적인 패턴을 앞에 둔다.
    ("claude-desktop", "claude-desktop"),
    ("claude", "claude"),
    ("anthropic", "claude"),
    ("cursor", "cursor"),
    ("openai", "openai"),
    ("chatgpt", "openai"),
    ("gemini", "gemini"),
    ("python-mcp", "mcp-sdk-python"),
    ("typescript-mcp", "mcp-sdk-ts"),
    ("modelcontextprotocol", "mcp-sdk"),
)


def parse_client_kind(user_agent: str | None) -> str:
    """UA 문자열에서 클라이언트 종류를 추정. 미상이면 'unknown' / 'other'."""
    if not user_agent:
        return "unknown"
    ua_lower = user_agent.lower()
    for needle, kind in _CLIENT_KIND_PATTERNS:
        if needle in ua_lower:
            return kind
    return "other"


# ── IP 마스킹 ───────────────────────────────────────────────────────────────


def _mask_ip(raw_ip: str | None) -> str | None:
    """IPv4 는 /24, IPv6 는 /48 프리픽스로 마스킹.

    실패 시 None 반환 (잘못된 형식의 헤더 값 보호).
    """
    if not raw_ip:
        return None
    candidate = raw_ip.split(",")[0].strip()
    if not candidate:
        return None
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv4Address):
        network = ipaddress.ip_network(f"{candidate}/24", strict=False)
    else:
        network = ipaddress.ip_network(f"{candidate}/48", strict=False)
    return str(network)


# ── ASGI 미들웨어 ──────────────────────────────────────────────────────────


def _extract_request_meta(scope: dict) -> McpRequestMeta:
    """ASGI scope 의 헤더에서 (IP, UA, kind) 추출."""
    raw_headers = scope.get("headers") or []
    headers: dict[bytes, bytes] = {}
    for name, value in raw_headers:
        # 같은 키 다중 값 — 마지막 값 사용 (FastAPI 와 동일 동작).
        headers[name.lower()] = value

    user_agent = headers.get(b"user-agent", b"").decode("latin-1", errors="replace")
    user_agent = user_agent.strip() or None
    if user_agent and len(user_agent) > _USER_AGENT_MAX:
        user_agent = user_agent[:_USER_AGENT_MAX]

    xff = headers.get(b"x-forwarded-for", b"").decode("latin-1", errors="replace")
    raw_ip: str | None = xff.strip() or None
    if not raw_ip:
        client = scope.get("client") or (None, None)
        raw_ip = client[0] if client else None

    return McpRequestMeta(
        client_ip=_mask_ip(raw_ip),
        user_agent=user_agent,
        client_kind=parse_client_kind(user_agent),
    )


# 연결 수준(프로토콜) 로깅 대상 JSON-RPC method → mcp_call_log.tool_name 라벨.
# tools/call 은 데코레이터(log_mcp_call)가 tool 단위로 기록하므로 여기서 제외
# (이중 집계 방지). initialize 는 클라이언트가 "연결"했다는 유일한 신호라
# tool 미호출 클라이언트 파악에 필수.
_PROTOCOL_LOGGED_METHODS: dict[str, str] = {
    "initialize": "protocol:initialize",
    "tools/list": "protocol:tools/list",
}
# JSON-RPC 본문 파싱 상한 — MCP 요청은 수 KB 수준이며, 상한 초과 시
# 프로토콜 로깅만 생략하고 요청 처리는 그대로 진행한다.
_BODY_PARSE_MAX = 64 * 1024


def _extract_protocol_calls(body: bytes) -> list[tuple[str, str]]:
    """요청 본문에서 (tool_name 라벨, arguments_json) 목록 추출.

    로깅 대상 method 가 아니거나 파싱 불가면 빈 목록. initialize 는
    clientInfo/protocolVersion 을 arguments 로 보존해 클라이언트 식별에 쓴다.
    """
    if not body or len(body) > _BODY_PARSE_MAX:
        return []
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return []
    requests = parsed if isinstance(parsed, list) else [parsed]
    calls: list[tuple[str, str]] = []
    for req in requests:
        if not isinstance(req, dict):
            continue
        label = _PROTOCOL_LOGGED_METHODS.get(req.get("method", ""))
        if not label:
            continue
        params = req.get("params") or {}
        arguments = (
            {
                "protocol_version": params.get("protocolVersion"),
                "client_info": params.get("clientInfo"),
            }
            if req.get("method") == "initialize"
            else {}
        )
        calls.append((label, _safe_json_arguments(arguments)))
    return calls


def mcp_logging_middleware(app):
    """ASGI 미들웨어 — MCP 요청 메타데이터 ContextVar set + 연결 수준 로깅.

    - 모든 HTTP 요청: 헤더에서 IP/UA/kind 를 추출해 ContextVar 에 set (tool
      데코레이터가 소비), 종료 시 reset. HTTP 가 아닌 scope(lifespan 등) 통과.
    - POST 본문의 JSON-RPC method 가 initialize/tools/list 면 mcp_call_log 에
      protocol:* 행으로 기록 — tool 호출 없이 연결만 한 클라이언트도 집계.
      본문은 메시지 단위로 버퍼링 후 앱에 재전달(replay)하므로 처리 불변.
    """

    async def wrapped(scope, receive, send):
        if scope.get("type") != "http":
            await app(scope, receive, send)
            return
        meta = _extract_request_meta(scope)
        token = _request_meta.set(meta)

        replay_receive = receive
        protocol_calls: list[tuple[str, str]] = []
        if scope.get("method") == "POST":
            # 본문을 메시지 단위로 소진해 파싱하고, 동일 순서로 앱에 재전달.
            messages: list[dict] = []
            while True:
                message = await receive()
                messages.append(message)
                if message["type"] != "http.request" or not message.get(
                    "more_body", False
                ):
                    break
            body = b"".join(
                m.get("body", b"") for m in messages if m["type"] == "http.request"
            )
            protocol_calls = _extract_protocol_calls(body)

            async def replay_receive():  # type: ignore[no-redef]
                if messages:
                    return messages.pop(0)
                return await receive()

        status_holder: dict[str, int] = {}

        async def send_with_status(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        started = time.perf_counter()
        try:
            await app(scope, replay_receive, send_with_status)
        finally:
            _request_meta.reset(token)
            if protocol_calls:
                duration_ms = int((time.perf_counter() - started) * 1000)
                success = status_holder.get("status", 500) < 400
                for label, arguments_json in protocol_calls:
                    _persist(
                        tool_name=label,
                        arguments_json=arguments_json,
                        meta=meta,
                        duration_ms=duration_ms,
                        success=success,
                        error_message=None
                        if success
                        else f"http {status_holder.get('status', '?')}",
                    )

    return wrapped


# ── 데코레이터 ──────────────────────────────────────────────────────────────


def _safe_json_arguments(kwargs: dict) -> str:
    """tool 인자를 JSONB 적재 가능한 문자열로 직렬화. 실패 시 _repr fallback."""
    try:
        return json.dumps(kwargs, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps({"_repr": str(kwargs)[:1000]}, ensure_ascii=False)


def _persist(
    *,
    tool_name: str,
    arguments_json: str,
    meta: McpRequestMeta | None,
    duration_ms: int,
    success: bool,
    error_message: str | None,
) -> None:
    """mcp_call_log 1건 INSERT. 실패는 흡수."""
    conn = None
    try:
        conn = DictConnection()
        conn.execute(
            "INSERT INTO mcp_call_log "
            "(tool_name, arguments, client_ip, user_agent, client_kind, "
            " duration_ms, success, error_message) "
            "VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s)",
            [
                tool_name,
                arguments_json,
                meta.client_ip if meta else None,
                meta.user_agent if meta else None,
                meta.client_kind if meta else "unknown",
                duration_ms,
                success,
                error_message,
            ],
        )
    except Exception as e:  # pragma: no cover — 로깅 실패는 흡수
        logger.warning(f"mcp_call_log insert failed (tool={tool_name}): {e}")
    finally:
        if conn is not None:
            conn.close()


def log_mcp_call(func):
    """MCP tool 호출을 mcp_call_log 에 기록하는 데코레이터.

    원본 시그니처를 ``__signature__`` 로 보존해 FastMCP 의 JSON Schema 생성을 깨지
    않는다. 데코레이터 적용 순서는 다음과 같이 ``@mcp.tool()`` 이 위.

        @mcp.tool()
        @log_mcp_call
        async def search_apartments(...): ...

    ``eval_str=True`` 필수: mcp_server.py 는 ``from __future__ import annotations``
    를 쓰므로 어노테이션이 문자열로 저장된다. eval_str 없이 시그니처를 캡처하면
    FastMCP 가 반환 타입을 실제 타입이 아닌 문자열("list" 등)로 인식해 의도치 않게
    구조화 출력(output_schema)을 생성하고, `Image` 처럼 JSON 직렬화 불가능한 값이
    포함된 반환값에서 "Unable to serialize unknown type" 오류로 도구 호출 자체가
    실패한다 (get_apartment_detail 이미지 첨부 구현 중 발견).
    """
    sig = inspect.signature(func, eval_str=True)

    @functools.wraps(func)
    async def wrapper(**kwargs):
        meta = current_meta()
        start = time.perf_counter()
        success = True
        error_message: str | None = None
        try:
            return await func(**kwargs)
        except Exception as e:
            success = False
            error_message = f"{type(e).__name__}: {e}"[:_ERROR_MESSAGE_MAX]
            raise
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            _persist(
                tool_name=func.__name__,
                arguments_json=_safe_json_arguments(kwargs),
                meta=meta,
                duration_ms=duration_ms,
                success=success,
                error_message=error_message,
            )

    wrapper.__signature__ = sig  # type: ignore[attr-defined]
    return wrapper
