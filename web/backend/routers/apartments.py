"""Apartment listing API."""

from fastapi import APIRouter, Query
from database import DictConnection

router = APIRouter()


@router.get("/apartments")
def list_apartments(
    sw_lat: float | None = Query(None),
    sw_lng: float | None = Query(None),
    ne_lat: float | None = Query(None),
    ne_lng: float | None = Query(None),
):
    """Return all apartments, optionally filtered by map bounds."""
    conn = DictConnection()
    try:
        sql = "SELECT pnu, bld_nm, lat, lng, total_hhld_cnt, sigungu_code FROM apartments"
        params: list = []

        if all(v is not None for v in [sw_lat, sw_lng, ne_lat, ne_lng]):
            sql += " WHERE lat BETWEEN %s AND %s AND lng BETWEEN %s AND %s"
            params = [sw_lat, ne_lat, sw_lng, ne_lng]

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/apartments/search")
def search_apartments(q: str = Query(..., min_length=1)):
    """키워드로 아파트 검색 (지역명, 단지명)"""
    conn = DictConnection()
    try:
        pattern = f"%{q}%"
        rows = conn.execute("""
            SELECT pnu, bld_nm, lat, lng, total_hhld_cnt, sigungu_code, new_plat_plc
            FROM apartments
            WHERE new_plat_plc LIKE %s OR plat_plc LIKE %s OR bld_nm LIKE %s
            LIMIT 100
        """, [pattern, pattern, pattern]).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
