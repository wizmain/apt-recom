"""공통 코드 관리 — DB 기반 코드 조회 유틸리티.

코드 그룹:
  - sigungu: 시군구 코드 (code=시군구5자리, name=시군구명, extra=시도명)
  - nudge: 넛지 라벨 (code=nudge_id, name=표시명)
  - nudge_keyword: 넛지 키워드 (code=nudge_id, name=키워드)
  - nudge_weight: 넛지 가중치 (code=nudge_id, name=시설subtype, extra=가중치)
  - facility_label: 시설 라벨 (code=subtype, name=표시명, extra=facility_type)
  - facility_distance: 시설 최대거리 (code=subtype, name=max_distance_m)
  - feedback_tag: 피드백 태그 (code=tag_id, name=표시명)
  - path_type: 교통수단 (code=type_code, name=표시명)
  - tool_label: LLM 도구 라벨 (code=tool_name, name=표시명)
"""

from database import DictConnection


def get_codes(group: str, conn: DictConnection | None = None) -> list[dict]:
    """특정 그룹의 코드 목록 조회."""
    close = False
    if conn is None:
        conn = DictConnection()
        close = True
    rows = conn.execute(
        "SELECT code, name, extra, sort_order FROM common_code WHERE group_id = %s ORDER BY sort_order, code",
        [group]
    ).fetchall()
    if close:
        conn.close()
    return [dict(r) for r in rows]


def get_code_map(group: str, conn: DictConnection | None = None) -> dict[str, str]:
    """코드 → 이름 딕셔너리 반환."""
    codes = get_codes(group, conn)
    return {c["code"]: c["name"] for c in codes}


def get_code_map_with_extra(group: str, conn: DictConnection | None = None) -> dict[str, tuple[str, str]]:
    """코드 → (이름, extra) 딕셔너리 반환."""
    codes = get_codes(group, conn)
    return {c["code"]: (c["name"], c["extra"] or "") for c in codes}
