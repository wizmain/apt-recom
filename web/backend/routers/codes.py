"""공통코드 API."""

from fastapi import APIRouter
from database import DictConnection

router = APIRouter()


@router.get("/codes/{group}")
def get_codes(group: str):
    """그룹별 공통코드 조회."""
    conn = DictConnection()
    rows = conn.execute(
        "SELECT code, name, extra, sort_order FROM common_code WHERE group_id = %s ORDER BY sort_order, code",
        [group]
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/codes")
def get_all_groups():
    """전체 그룹 목록."""
    conn = DictConnection()
    rows = conn.execute(
        "SELECT group_id, COUNT(*) as cnt FROM common_code GROUP BY group_id ORDER BY group_id",
        []
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
