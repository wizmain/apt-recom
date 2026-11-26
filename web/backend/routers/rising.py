"""오르는 단지 API — 파라미터 검증만 하고 조회는 services/rising.py 에 맡긴다."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from database import DictConnection
from services import rising as rising_service

router = APIRouter()

MAX_QUERY_LENGTH = 100
# 예산 파라미터 상한(억). inf/초대형 값이 금액 환산(만원 정수)에서 OverflowError 500 이 되지 않게 422 로 막는다.
MAX_BUDGET_EOK = 1000  # 1,000억 — 어떤 단지 가격보다 충분히 큼
# 지도 면적 필터 상한(㎡) — 어떤 주택형보다 충분히 큼(inf·초대형 값 422).
MAX_AREA_M2 = 1000


class MapTrendRequest(BaseModel):
    pnus: list[str] = Field(default_factory=list, description="지도에 보이는 단지 PNU")
    min_area: float | None = Field(
        None, ge=0, le=MAX_AREA_M2, description="면적 하한(㎡)"
    )
    max_area: float | None = Field(
        None, ge=0, le=MAX_AREA_M2, description="면적 상한(㎡)"
    )


def _require_band(conn, area_band: str) -> rising_service.AreaBand:
    band = rising_service.load_area_bands(conn).get(area_band)
    if band is None:
        raise HTTPException(status_code=422, detail=f"알 수 없는 면적대: {area_band}")
    return band


@router.get("/rising/meta")
def get_rising_meta():
    with DictConnection() as conn:
        return rising_service.get_meta(conn)


@router.get("/rising")
def list_rising(
    area_band: str = Query(
        ..., description="면적대 코드 (common_code rising_area_band)"
    ),
    budget_min: float | None = Query(
        None, ge=0, le=MAX_BUDGET_EOK, description="예산 하한(억)"
    ),
    budget_max: float | None = Query(
        None, ge=0, le=MAX_BUDGET_EOK, description="예산 상한(억)"
    ),
    sido: str | None = Query(None, description="시도 코드 2자리"),
    sgg: list[str] = Query([], description="시군구 코드 (복수)"),
    q: str = Query("", max_length=MAX_QUERY_LENGTH, description="단지명·주소 검색어"),
    sort: str = Query(rising_service.DEFAULT_SORT),
    page: int = Query(1, ge=1),
):
    if sort not in rising_service.SORT_ORDER_SQL:
        raise HTTPException(status_code=422, detail=f"알 수 없는 정렬: {sort}")
    if budget_min is not None and budget_max is not None and budget_min > budget_max:
        raise HTTPException(
            status_code=422, detail="예산 하한이 상한보다 클 수 없습니다"
        )
    with DictConnection() as conn:
        _require_band(conn, area_band)
        filters = rising_service.ListFilters(
            area_band=area_band,
            budget_min_eok=budget_min,
            budget_max_eok=budget_max,
            sido=sido or None,
            sgg_codes=[code for code in sgg if code],
            query=q,
        )
        return rising_service.list_complexes(conn, filters, sort, page)


@router.post("/rising/map")
def get_rising_map(body: MapTrendRequest):
    """지도 마커·팝업용 단지별 추세 요약 (면적 필터와 겹치는 면적대 중 거래 최다)."""
    if len(body.pnus) > rising_service.MAP_TREND_MAX_PNUS:
        raise HTTPException(
            status_code=422,
            detail=f"PNU 는 최대 {rising_service.MAP_TREND_MAX_PNUS}개까지 요청할 수 있습니다",
        )
    if (
        body.min_area is not None
        and body.max_area is not None
        and body.min_area > body.max_area
    ):
        raise HTTPException(status_code=422, detail="min_area 가 max_area 보다 큽니다")
    with DictConnection() as conn:
        return rising_service.get_map_trends(
            conn, body.pnus, body.min_area, body.max_area
        )


@router.get("/rising/complex/{pnu}")
def get_rising_complex(pnu: str):
    """가격흐름 탭 — 단지의 전 면적대 요약(요청 PNU 의 대표 단지 기준)."""
    with DictConnection() as conn:
        summary = rising_service.get_complex_summary(conn, pnu)
    if summary is None:
        raise HTTPException(status_code=404, detail="단지를 찾을 수 없습니다")
    return summary


@router.get("/rising/{pnu}")
def get_rising_detail(
    pnu: str,
    area_band: str = Query(
        ..., description="면적대 코드 (common_code rising_area_band)"
    ),
):
    with DictConnection() as conn:
        band = _require_band(conn, area_band)
        detail = rising_service.get_detail(conn, pnu, band)
    if detail is None:
        raise HTTPException(status_code=404, detail="이 면적대 집계 행이 없습니다")
    return detail
