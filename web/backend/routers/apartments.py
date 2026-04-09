"""Apartment listing API with filtering."""

from fastapi import APIRouter, Query
from database import DictConnection

router = APIRouter()


@router.get("/apartments")
def list_apartments(
    sw_lat: float | None = Query(None),
    sw_lng: float | None = Query(None),
    ne_lat: float | None = Query(None),
    ne_lng: float | None = Query(None),
    min_area: float | None = Query(None, description="최소 면적 (㎡)"),
    max_area: float | None = Query(None, description="최대 면적 (㎡)"),
    min_price: int | None = Query(None, description="최소 가격 (만원)"),
    max_price: int | None = Query(None, description="최대 가격 (만원)"),
    min_floor: int | None = Query(None, description="최소 최고층"),
    min_hhld: int | None = Query(None, description="최소 세대수"),
    max_hhld: int | None = Query(None, description="최대 세대수"),
    built_after: int | None = Query(None, description="준공연도 이후 (예: 2015)"),
    built_before: int | None = Query(None, description="준공연도 이전 (예: 2025)"),
):
    """Return apartments with optional filters."""
    conn = DictConnection()
    try:
        # Base query with LEFT JOIN for area/price info
        sql = """
            SELECT a.pnu, a.bld_nm, a.lat, a.lng, a.total_hhld_cnt, a.sigungu_code,
                   a.max_floor, a.use_apr_day,
                   ai.min_area as area_min, ai.max_area as area_max, ai.avg_area,
                   ps.price_per_m2, ps.jeonse_ratio
            FROM apartments a
            LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
            LEFT JOIN apt_price_score ps ON a.pnu = ps.pnu
        """
        conditions: list[str] = [
            "a.pnu NOT LIKE 'TRADE_%%'",
            "a.lat IS NOT NULL",
            "a.total_hhld_cnt > 0",
            "a.use_apr_day IS NOT NULL AND a.use_apr_day != ''",
        ]
        params: list = []

        # Map bounds
        if all(v is not None for v in [sw_lat, sw_lng, ne_lat, ne_lng]):
            conditions.append("a.lat BETWEEN %s AND %s AND a.lng BETWEEN %s AND %s")
            params.extend([sw_lat, ne_lat, sw_lng, ne_lng])

        # Area filter (면적)
        if min_area is not None:
            conditions.append("ai.max_area >= %s")
            params.append(min_area)
        if max_area is not None:
            conditions.append("ai.min_area <= %s")
            params.append(max_area)

        # Price filter (최근 거래가 기준 — price_per_m2 * avg_area / 10000)
        if min_price is not None:
            conditions.append("ps.price_per_m2 * COALESCE(ai.avg_area, 60) / 10000 >= %s")
            params.append(min_price)
        if max_price is not None:
            conditions.append("ps.price_per_m2 * COALESCE(ai.avg_area, 60) / 10000 <= %s")
            params.append(max_price)

        # Floor filter
        if min_floor is not None:
            conditions.append("a.max_floor >= %s")
            params.append(min_floor)

        # Household count
        if min_hhld is not None:
            conditions.append("a.total_hhld_cnt >= %s")
            params.append(min_hhld)
        if max_hhld is not None:
            conditions.append("a.total_hhld_cnt <= %s")
            params.append(max_hhld)

        # Built year
        if built_after is not None:
            conditions.append("a.use_apr_day ~ '^[0-9]{4}' AND LEFT(a.use_apr_day, 4)::int >= %s")
            params.append(built_after)
        if built_before is not None:
            conditions.append("a.use_apr_day ~ '^[0-9]{4}' AND LEFT(a.use_apr_day, 4)::int <= %s")
            params.append(built_before)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/apartments/search")
def search_apartments(q: str = Query(..., min_length=1)):
    """검색어를 분석하여 지역/단지명을 자동 분류 후 아파트 검색."""
    from services.search_engine import search

    conn = DictConnection()
    try:
        return search(conn, q)["results"]
    finally:
        conn.close()
