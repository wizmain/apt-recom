"""MCP 사용량 집계 — 관리자 화면 전용.

`mcp_call_log`(services/mcp_logger.py 가 적재)를 기간 단위로 집계해
요약 KPI · 일별 추이 · tool 별 · 클라이언트별 · 최근 오류를 한 번에 반환한다.

mcp_call_log 에는 두 종류의 행이 섞여 있다.
    - tool 호출: tool_name = 실제 tool 이름 (log_mcp_call 데코레이터가 적재)
    - 프로토콜: tool_name = 'protocol:initialize' / 'protocol:tools/list'
      (미들웨어가 적재). initialize 의 arguments.client_info.name 이
      클라이언트가 스스로 밝힌 이름이다.

사용자 수는 client_ip(/24 마스킹) 고유 개수로 추정한 근사치다.

내부 점검 호출(운영자의 curl 점검 등)은 집계에서 제외한다. 판별 기준은
common_code `mcp_internal_ua` 그룹의 code(User-Agent 접두어) 목록이며, 원본 행은
삭제하지 않고 집계 시점에만 거른다. 제외 건수는 summary.count_excluded_internal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from common_codes import get_codes

# 일별 버킷 기준 시간대 — 관리자 화면은 KST 날짜로 본다.
USAGE_TIMEZONE = "Asia/Seoul"
# 최근 오류 목록 최대 건수
RECENT_ERROR_LIMIT = 20
# 프로토콜 행 식별 (services/mcp_logger.py 의 _PROTOCOL_LOGGED_METHODS 라벨과 일치)
PROTOCOL_PATTERN = "protocol:%"
CONNECTION_TOOL_NAME = "protocol:initialize"
# clientInfo 를 보내지 않은 연결의 표시명
UNNAMED_CLIENT = "unknown"

# 내부 점검 User-Agent 접두어를 관리하는 common_code 그룹
INTERNAL_UA_CODE_GROUP = "mcp_internal_ua"

# 기간 + 내부 점검 제외 필터 — 모든 집계 쿼리에 공통.
# 기간은 BRIN idx_mcp_call_log_created_brin 사용. 파라미터는 _UsageScope.params 순서.
_RANGE_WHERE = "created_at BETWEEN %s AND %s"
_INTERNAL_MATCH = "COALESCE(user_agent, '') LIKE ANY(%s::text[])"
_SCOPE_WHERE = f"{_RANGE_WHERE} AND NOT {_INTERNAL_MATCH}"
_TOOL_CALL_WHERE = f"{_SCOPE_WHERE} AND tool_name NOT LIKE %s"


@dataclass(frozen=True)
class _UsageScope:
    """집계 대상 범위: 기간 + 내부 점검 제외용 LIKE 패턴."""

    frm: datetime
    to: datetime
    internal_ua_patterns: list[str]

    @property
    def params(self) -> list:
        """_SCOPE_WHERE 의 바인딩 파라미터."""
        return [self.frm, self.to, self.internal_ua_patterns]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def load_internal_ua_patterns(conn) -> list[str]:
    """common_code 에 등록된 내부 점검 UA 접두어 → LIKE 패턴 목록."""
    return [
        f"{_escape_like(c['code'])}%"
        for c in get_codes(INTERNAL_UA_CODE_GROUP, conn)
        if c["code"]
    ]


# tool 호출 공통 집계식
_TOOL_CALL_STATS_COLUMNS = """
    COUNT(*) AS count_calls,
    COUNT(*) FILTER (WHERE NOT success) AS count_errors,
    COUNT(DISTINCT client_ip) AS count_ip_prefixes,
    ROUND(AVG(duration_ms))::int AS avg_duration_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms))::int AS p95_duration_ms
"""


def _error_rate(count_errors: int, count_calls: int) -> float:
    return round(count_errors / count_calls, 4) if count_calls else 0.0


def _tool_call_stats(row: dict) -> dict:
    return {
        "count_calls": row["count_calls"],
        "count_errors": row["count_errors"],
        "error_rate": _error_rate(row["count_errors"], row["count_calls"]),
        "count_ip_prefixes": row["count_ip_prefixes"],
        "avg_duration_ms": row["avg_duration_ms"],
        "p95_duration_ms": row["p95_duration_ms"],
    }


def _fetch_summary(conn, scope: _UsageScope) -> dict:
    tool_row = conn.execute(
        f"SELECT {_TOOL_CALL_STATS_COLUMNS} FROM mcp_call_log WHERE {_TOOL_CALL_WHERE}",
        [*scope.params, PROTOCOL_PATTERN],
    ).fetchone()
    overall_row = conn.execute(
        f"""
        SELECT COUNT(*) FILTER (WHERE tool_name = %s) AS count_connections,
               COUNT(DISTINCT client_ip) AS count_ip_prefixes
        FROM mcp_call_log
        WHERE {_SCOPE_WHERE}
        """,
        [CONNECTION_TOOL_NAME, *scope.params],
    ).fetchone()
    excluded_row = conn.execute(
        f"SELECT COUNT(*) AS c FROM mcp_call_log WHERE {_RANGE_WHERE} AND {_INTERNAL_MATCH}",
        scope.params,
    ).fetchone()
    return {
        "count_tool_calls": tool_row["count_calls"],
        "count_connections": overall_row["count_connections"],
        "count_errors": tool_row["count_errors"],
        "error_rate": _error_rate(tool_row["count_errors"], tool_row["count_calls"]),
        # 연결만 하고 tool 을 호출하지 않은 클라이언트도 포함
        "count_ip_prefixes": overall_row["count_ip_prefixes"],
        "avg_duration_ms": tool_row["avg_duration_ms"],
        "p95_duration_ms": tool_row["p95_duration_ms"],
        # 내부 점검으로 판별돼 위 집계에서 빠진 행 수 (tool 호출 + 프로토콜)
        "count_excluded_internal": excluded_row["c"],
    }


def _fetch_daily(conn, scope: _UsageScope) -> list[dict]:
    """KST 일별 집계. 호출이 없는 날도 0 으로 채워 차트가 날짜를 건너뛰지 않게 한다."""
    rows = conn.execute(
        f"""
        WITH days AS (
            SELECT generate_series(
                (%s::timestamptz AT TIME ZONE %s)::date,
                (%s::timestamptz AT TIME ZONE %s)::date,
                INTERVAL '1 day'
            )::date AS day
        ),
        daily AS (
            SELECT (created_at AT TIME ZONE %s)::date AS day,
                   COUNT(*) FILTER (WHERE tool_name NOT LIKE %s) AS count_tool_calls,
                   COUNT(*) FILTER (WHERE tool_name = %s) AS count_connections,
                   COUNT(*) FILTER (WHERE tool_name NOT LIKE %s AND NOT success) AS count_errors,
                   COUNT(DISTINCT client_ip) AS count_ip_prefixes
            FROM mcp_call_log
            WHERE {_SCOPE_WHERE}
            GROUP BY 1
        )
        SELECT days.day,
               COALESCE(daily.count_tool_calls, 0) AS count_tool_calls,
               COALESCE(daily.count_connections, 0) AS count_connections,
               COALESCE(daily.count_errors, 0) AS count_errors,
               COALESCE(daily.count_ip_prefixes, 0) AS count_ip_prefixes
        FROM days LEFT JOIN daily USING (day)
        ORDER BY days.day
        """,
        [
            scope.frm,
            USAGE_TIMEZONE,
            scope.to,
            USAGE_TIMEZONE,
            USAGE_TIMEZONE,
            PROTOCOL_PATTERN,
            CONNECTION_TOOL_NAME,
            PROTOCOL_PATTERN,
            *scope.params,
        ],
    ).fetchall()
    return [
        {
            "day": r["day"].isoformat(),
            "count_tool_calls": r["count_tool_calls"],
            "count_connections": r["count_connections"],
            "count_errors": r["count_errors"],
            "count_ip_prefixes": r["count_ip_prefixes"],
        }
        for r in rows
    ]


def _fetch_by_tool(conn, scope: _UsageScope) -> list[dict]:
    rows = conn.execute(
        f"""
        SELECT tool_name AS name, {_TOOL_CALL_STATS_COLUMNS}
        FROM mcp_call_log
        WHERE {_TOOL_CALL_WHERE}
        GROUP BY tool_name
        ORDER BY count_calls DESC
        """,
        [*scope.params, PROTOCOL_PATTERN],
    ).fetchall()
    return [{"name": r["name"], **_tool_call_stats(r)} for r in rows]


def _fetch_by_client_kind(conn, scope: _UsageScope) -> list[dict]:
    """User-Agent 로 분류한 client_kind 별 tool 호출 통계."""
    rows = conn.execute(
        f"""
        SELECT COALESCE(client_kind, %s) AS name, {_TOOL_CALL_STATS_COLUMNS}
        FROM mcp_call_log
        WHERE {_TOOL_CALL_WHERE}
        GROUP BY 1
        ORDER BY count_calls DESC
        """,
        [UNNAMED_CLIENT, *scope.params, PROTOCOL_PATTERN],
    ).fetchall()
    return [{"name": r["name"], **_tool_call_stats(r)} for r in rows]


def _fetch_by_client_name(conn, scope: _UsageScope) -> list[dict]:
    """initialize 시 클라이언트가 밝힌 clientInfo.name 별 연결 수."""
    rows = conn.execute(
        f"""
        SELECT COALESCE(NULLIF(arguments->'client_info'->>'name', ''), %s) AS name,
               COUNT(*) AS count_connections,
               COUNT(DISTINCT client_ip) AS count_ip_prefixes,
               MAX(created_at) AS last_connected_at
        FROM mcp_call_log
        WHERE {_SCOPE_WHERE} AND tool_name = %s
        GROUP BY 1
        ORDER BY count_connections DESC
        """,
        [UNNAMED_CLIENT, *scope.params, CONNECTION_TOOL_NAME],
    ).fetchall()
    return [
        {
            "name": r["name"],
            "count_connections": r["count_connections"],
            "count_ip_prefixes": r["count_ip_prefixes"],
            "last_connected_at": r["last_connected_at"].isoformat(),
        }
        for r in rows
    ]


def _fetch_recent_errors(conn, scope: _UsageScope) -> list[dict]:
    rows = conn.execute(
        f"""
        SELECT id, tool_name, client_kind, arguments, error_message,
               duration_ms, created_at
        FROM mcp_call_log
        WHERE {_SCOPE_WHERE} AND NOT success
        ORDER BY created_at DESC
        LIMIT %s
        """,
        [*scope.params, RECENT_ERROR_LIMIT],
    ).fetchall()
    return [
        {
            "id": r["id"],
            "tool_name": r["tool_name"],
            "client_kind": r["client_kind"],
            "arguments": r["arguments"],
            "error_message": r["error_message"],
            "duration_ms": r["duration_ms"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


def get_mcp_usage(conn, frm: datetime, to: datetime) -> dict:
    """기간 [frm, to] 의 MCP 사용량 집계 (내부 점검 호출 제외)."""
    scope = _UsageScope(frm, to, load_internal_ua_patterns(conn))
    return {
        "range": {"from": frm.isoformat(), "to": to.isoformat()},
        "summary": _fetch_summary(conn, scope),
        "daily": _fetch_daily(conn, scope),
        "by_tool": _fetch_by_tool(conn, scope),
        "by_client_kind": _fetch_by_client_kind(conn, scope),
        "by_client_name": _fetch_by_client_name(conn, scope),
        "recent_errors": _fetch_recent_errors(conn, scope),
    }
