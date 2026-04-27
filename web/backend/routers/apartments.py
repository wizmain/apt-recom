"""Apartment listing API with filtering."""

from fastapi import APIRouter, BackgroundTasks, Query, Request
from database import DictConnection
from services.activity_log import log_event
from services.identity import get_user_identifier

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
    sigungu_code: str | None = Query(None, description="시군구 코드 (5자리)"),
    bjd_code: str | None = Query(
        None, description="법정동 코드 (10자리, 시군구보다 우선 적용)"
    ),
):
    """Return apartments with optional filters."""
    conn = DictConnection()
    try:
        # Base query with LEFT JOIN for area/price/K-APT info
        # 세대수/최고층/사용승인일은 K-APT가 있으면 K-APT 값 우선 (건축물대장은 여러 건물을
        # 합산해 과대 집계되는 문제가 있음)
        # 최고층 우선순위: K-APT 공식값(top_floor_official) > K-APT 평균값(top_floor) > 건축물대장(max_floor)
        # K-APT 원본의 top_floor 컬럼은 일부 단지에서 1·2·0 등으로 오염된 값이 들어있어
        # top_floor_official 을 우선 사용한다 (≤3 인 비정상값은 NULLIF 로 무시).
        sql = """
            SELECT a.pnu, a.bld_nm, a.lat, a.lng,
                   COALESCE(k.ho_cnt, a.total_hhld_cnt) AS total_hhld_cnt,
                   a.sigungu_code,
                   COALESCE(
                       NULLIF(k.top_floor_official, 0),
                       CASE WHEN k.top_floor > 3 THEN k.top_floor END,
                       a.max_floor
                   ) AS max_floor,
                   COALESCE(NULLIF(k.use_date, ''), a.use_apr_day) AS use_apr_day,
                   ai.min_area as area_min, ai.max_area as area_max, ai.avg_area,
                   ps.price_per_m2, ps.jeonse_ratio
            FROM apartments a
            LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
            LEFT JOIN apt_price_score ps ON a.pnu = ps.pnu
            LEFT JOIN apt_kapt_info k ON a.pnu = k.pnu
        """
        conditions: list[str] = [
            "a.pnu NOT LIKE 'TRADE_%%'",
            "a.lat IS NOT NULL",
            "COALESCE(k.ho_cnt, a.total_hhld_cnt) > 0",
            "COALESCE(NULLIF(k.use_date, ''), a.use_apr_day) IS NOT NULL",
            "COALESCE(NULLIF(k.use_date, ''), a.use_apr_day) != ''",
        ]
        params: list = []

        # Region filter (bjd_code 우선 — 동일명 지역 구분)
        if bjd_code:
            conditions.append("a.bjd_code = %s")
            params.append(bjd_code)
        elif sigungu_code:
            conditions.append("a.sigungu_code = %s")
            params.append(sigungu_code)

        # Map bounds (지역 필터가 설정되면 bounds는 무시 — 사용자가 지도를 이동해도 지역 결과 고정)
        elif all(v is not None for v in [sw_lat, sw_lng, ne_lat, ne_lng]):
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
            conditions.append(
                "ps.price_per_m2 * COALESCE(ai.avg_area, 60) / 10000 >= %s"
            )
            params.append(min_price)
        if max_price is not None:
            conditions.append(
                "ps.price_per_m2 * COALESCE(ai.avg_area, 60) / 10000 <= %s"
            )
            params.append(max_price)

        # Floor filter — SELECT 절과 동일한 우선순위(top_floor_official > top_floor > max_floor)
        if min_floor is not None:
            conditions.append(
                "COALESCE("
                "NULLIF(k.top_floor_official, 0), "
                "CASE WHEN k.top_floor > 3 THEN k.top_floor END, "
                "a.max_floor"
                ") >= %s"
            )
            params.append(min_floor)

        # Household count
        if min_hhld is not None:
            conditions.append("COALESCE(k.ho_cnt, a.total_hhld_cnt) >= %s")
            params.append(min_hhld)
        if max_hhld is not None:
            conditions.append("COALESCE(k.ho_cnt, a.total_hhld_cnt) <= %s")
            params.append(max_hhld)

        # Built year — K-APT use_date 우선, 없으면 건축물대장 use_apr_day
        built_date_expr = "COALESCE(NULLIF(k.use_date, ''), a.use_apr_day)"
        if built_after is not None:
            conditions.append(
                f"{built_date_expr} ~ '^[0-9]{{4}}' AND LEFT({built_date_expr}, 4)::int >= %s"
            )
            params.append(built_after)
        if built_before is not None:
            conditions.append(
                f"{built_date_expr} ~ '^[0-9]{{4}}' AND LEFT({built_date_expr}, 4)::int <= %s"
            )
            params.append(built_before)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/apartments/search")
def search_apartments(
    request: Request,
    background_tasks: BackgroundTasks,
    q: str = Query(..., min_length=1),
):
    """검색어를 분석하여 지역/단지명을 자동 분류 후 아파트 검색.

    반환: {"results": [...], "region_candidates": [...]?}
    - results: 개별 아파트 목록 (최대 100건)
    - region_candidates: 동일 명칭의 지역이 2곳 이상 매칭된 경우 후보 목록 (선택적)

    log_event 는 BackgroundTasks 로 비동기 기록.
    """
    from services.search_engine import search

    background_tasks.add_task(
        log_event,
        get_user_identifier(request),
        "search",
        "keyword",
        {"keyword": q},
    )

    conn = DictConnection()
    try:
        return search(conn, q)
    finally:
        conn.close()
