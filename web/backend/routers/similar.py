"""유사 아파트 추천 API — 4가지 모드(location, price, lifestyle, combined) 지원."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from database import DictConnection
from services.similarity import (
    DEFAULT_FILTERS,
    calc_combined,
    calc_lifestyle,
    calc_location,
    calc_price,
    parse_vectors,
)

logger = logging.getLogger(__name__)

router = APIRouter()

VECTOR_VERSION = 1

# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class LifestyleRequest(BaseModel):
    nudge_weights: dict[str, float] = Field(
        ..., description="넛지 카테고리별 가중치 (예: {'교통': 0.9, '교육': 0.7})"
    )
    top_n: int = Field(5, ge=1, le=20)
    exclude_same_sigungu: bool = False


# ---------------------------------------------------------------------------
# Hard Filter 빌더
# ---------------------------------------------------------------------------

MIN_CANDIDATE_MULTIPLIER = 2
FILTER_EXPANSION_FACTOR = 1.5


def _build_filter_sql(
    mode: str,
    area_range: Optional[float],
    hhld_range: Optional[float],
    age_range: Optional[float],
    target_info: dict,
) -> tuple[str, list]:
    """하드 필터 WHERE 절을 생성한다.

    각 파라미터가 None이면 DEFAULT_FILTERS에서 해당 모드의 기본값을 사용한다.
    값이 0이면 해당 필터를 건너뛴다.

    Returns:
        (추가 WHERE 조건 문자열, 파라미터 리스트)
    """
    defaults = DEFAULT_FILTERS.get(mode, {})
    effective_area = area_range if area_range is not None else defaults.get("area_range", 0)
    effective_hhld = hhld_range if hhld_range is not None else defaults.get("hhld_range", 0)
    effective_age = age_range if age_range is not None else defaults.get("age_range", 0)

    clauses: list[str] = []
    params: list = []

    # 면적 필터 (apt_area_info.avg_area 기준 ± percentage)
    if effective_area > 0 and target_info.get("avg_area"):
        avg_area = float(target_info["avg_area"])
        area_low = avg_area * (1 - effective_area)
        area_high = avg_area * (1 + effective_area)
        clauses.append("ai.avg_area BETWEEN %s AND %s")
        params.extend([area_low, area_high])

    # 세대수 필터 (apartments.total_hhld_cnt 기준 ± percentage)
    if effective_hhld > 0 and target_info.get("total_hhld_cnt"):
        hhld = int(target_info["total_hhld_cnt"])
        hhld_low = hhld * (1 - effective_hhld)
        hhld_high = hhld * (1 + effective_hhld)
        clauses.append("a.total_hhld_cnt BETWEEN %s AND %s")
        params.extend([hhld_low, hhld_high])

    # 건물 연식 필터 (use_apr_day 기준 ± years)
    if effective_age > 0 and target_info.get("use_apr_day"):
        target_year = int(str(target_info["use_apr_day"])[:4])
        year_low = target_year - int(effective_age)
        year_high = target_year + int(effective_age)
        clauses.append(
            "CAST(SUBSTRING(a.use_apr_day FROM 1 FOR 4) AS INTEGER) BETWEEN %s AND %s"
        )
        params.extend([year_low, year_high])

    where = " AND ".join(clauses) if clauses else ""
    return where, params


# ---------------------------------------------------------------------------
# 시군구 이름 매핑 헬퍼
# ---------------------------------------------------------------------------


def _load_sigungu_names(conn) -> dict[str, str]:
    """common_code 테이블에서 시군구 코드→이름 매핑을 로드한다."""
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s",
        ["sigungu"],
    ).fetchall()
    mapping: dict[str, str] = {}
    for r in rows:
        if r["extra"] and r["extra"] != r["name"]:
            mapping[r["code"]] = f"{r['name']}({r['extra']})"
        else:
            mapping[r["code"]] = r["name"]
    return mapping


# ---------------------------------------------------------------------------
# 대상 아파트 정보 조회
# ---------------------------------------------------------------------------


def _fetch_target_info(conn, pnu: str) -> dict:
    """대상 아파트의 벡터·메타 정보를 조회한다. 없으면 HTTPException."""
    row = conn.execute(
        """
        SELECT v.pnu, v.vec_basic, v.vec_price, v.vec_facility, v.vec_safety,
               a.bld_nm, a.sigungu_code, a.lat, a.lng,
               a.total_hhld_cnt, a.use_apr_day, a.group_pnu,
               ai.avg_area,
               p.price_per_m2
        FROM apt_vectors v
        JOIN apartments a ON v.pnu = a.pnu
        LEFT JOIN apt_area_info ai ON v.pnu = ai.pnu
        LEFT JOIN apt_price_score p ON v.pnu = p.pnu
        WHERE v.pnu = %s AND v.vector_version = %s
        """,
        [pnu, VECTOR_VERSION],
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="해당 아파트의 벡터 데이터가 없습니다.")

    return row


# ---------------------------------------------------------------------------
# 후보 조회 (하드 필터 적용)
# ---------------------------------------------------------------------------


def _fetch_candidates(
    conn,
    pnu: str,
    mode: str,
    area_range: Optional[float],
    hhld_range: Optional[float],
    age_range: Optional[float],
    target_info: dict,
    exclude_same_sigungu: bool,
    top_n: int,
) -> tuple[list[dict], bool]:
    """후보 아파트 목록을 조회한다. 필터 확장 여부도 반환."""

    def _query_with_filter(
        ar: Optional[float], hr: Optional[float], agr: Optional[float]
    ) -> list[dict]:
        filter_where, filter_params = _build_filter_sql(
            mode, ar, hr, agr, target_info
        )
        base_params = [pnu, VECTOR_VERSION]
        where_parts = ["v.pnu != %s", "v.vector_version = %s", "a.pnu NOT LIKE 'TRADE_%%'"]

        if exclude_same_sigungu and target_info.get("sigungu_code"):
            target_sgg = str(target_info["sigungu_code"])[:5]
            where_parts.append("SUBSTRING(a.sigungu_code FROM 1 FOR 5) != %s")
            base_params.append(target_sgg)

        if filter_where:
            where_parts.append(filter_where)
            base_params.extend(filter_params)

        sql = f"""
            SELECT v.pnu, v.vec_basic, v.vec_price, v.vec_facility, v.vec_safety,
                   a.bld_nm, a.sigungu_code, a.lat, a.lng,
                   a.total_hhld_cnt, a.use_apr_day,
                   ai.avg_area,
                   p.price_per_m2
            FROM apt_vectors v
            JOIN apartments a ON v.pnu = a.pnu
            LEFT JOIN apt_area_info ai ON v.pnu = ai.pnu
            LEFT JOIN apt_price_score p ON v.pnu = p.pnu
            WHERE {' AND '.join(where_parts)}
        """  # noqa: S608
        return conn.execute(sql, base_params).fetchall()

    rows = _query_with_filter(area_range, hhld_range, age_range)
    filters_expanded = False

    # 후보가 부족하면 필터를 1.5배 확장하여 재시도 (lifestyle 모드 제외: 필터가 없음)
    filter_where, _ = _build_filter_sql(mode, area_range, hhld_range, age_range, target_info)
    if len(rows) < top_n * MIN_CANDIDATE_MULTIPLIER and filter_where:
        expanded_area = (
            area_range * FILTER_EXPANSION_FACTOR
            if area_range is not None and area_range > 0
            else (
                DEFAULT_FILTERS.get(mode, {}).get("area_range", 0) * FILTER_EXPANSION_FACTOR
                if DEFAULT_FILTERS.get(mode, {}).get("area_range", 0) > 0
                else area_range
            )
        )
        expanded_hhld = (
            hhld_range * FILTER_EXPANSION_FACTOR
            if hhld_range is not None and hhld_range > 0
            else (
                DEFAULT_FILTERS.get(mode, {}).get("hhld_range", 0) * FILTER_EXPANSION_FACTOR
                if DEFAULT_FILTERS.get(mode, {}).get("hhld_range", 0) > 0
                else hhld_range
            )
        )
        expanded_age = (
            age_range * FILTER_EXPANSION_FACTOR
            if age_range is not None and age_range > 0
            else (
                DEFAULT_FILTERS.get(mode, {}).get("age_range", 0) * FILTER_EXPANSION_FACTOR
                if DEFAULT_FILTERS.get(mode, {}).get("age_range", 0) > 0
                else age_range
            )
        )
        expanded_rows = _query_with_filter(expanded_area, expanded_hhld, expanded_age)
        if len(expanded_rows) > len(rows):
            rows = expanded_rows
            filters_expanded = True

    return rows, filters_expanded


# ---------------------------------------------------------------------------
# 결과 포맷팅
# ---------------------------------------------------------------------------


def _format_result(row: dict, score: float, score_key: str, sgg_names: dict[str, str]) -> dict:
    """후보 행을 응답 dict로 변환한다."""
    sgg_code = (str(row["sigungu_code"]) or "")[:5]
    result = {
        "pnu": row["pnu"],
        "bld_nm": row["bld_nm"],
        "sigungu_code": sgg_code,
        "sigungu_name": sgg_names.get(sgg_code, sgg_code),
        "lat": row["lat"],
        "lng": row["lng"],
        "total_hhld_cnt": row["total_hhld_cnt"],
        "use_apr_day": row["use_apr_day"],
        "avg_area": round(float(row["avg_area"]), 1) if row.get("avg_area") else None,
        "price_per_m2": round(float(row["price_per_m2"])) if row.get("price_per_m2") else None,
    }
    if score_key == "similarity_pct":
        result["similarity_pct"] = round(score * 100, 1)
    elif score_key == "preference_score":
        result["preference_score"] = round(score, 4)
    return result


# ---------------------------------------------------------------------------
# GET /apartment/{pnu}/similar — location, price, combined 모드
# ---------------------------------------------------------------------------


@router.get("/apartment/{pnu}/similar")
def get_similar_apartments(
    pnu: str,
    mode: str = Query("combined", pattern="^(location|price|combined)$"),
    top_n: int = Query(5, ge=1, le=20),
    exclude_same_sigungu: bool = Query(False, description="같은 시군구 제외"),
    include_price: bool = Query(False, description="combined 모드에서 가격 벡터 포함"),
    area_range: Optional[float] = Query(None, ge=0, description="면적 필터 비율 (0이면 비활성)"),
    hhld_range: Optional[float] = Query(None, ge=0, description="세대수 필터 비율 (0이면 비활성)"),
    age_range: Optional[float] = Query(None, ge=0, description="건물연식 필터 ± 년 (0이면 비활성)"),
):
    """선택한 아파트와 유사한 아파트 Top N 반환 (location/price/combined 모드)."""
    conn = DictConnection()
    try:
        target_info = _fetch_target_info(conn, pnu)
        target_vecs = parse_vectors(target_info)

        rows, filters_expanded = _fetch_candidates(
            conn, pnu, mode,
            area_range, hhld_range, age_range,
            target_info, exclude_same_sigungu, top_n,
        )

        sgg_names = _load_sigungu_names(conn)
    finally:
        conn.close()

    # 유사도 계산
    candidates = []
    for row in rows:
        cand_vecs = parse_vectors(row)

        if mode == "location":
            score = calc_location(target_vecs, cand_vecs)
        elif mode == "price":
            score = calc_price(target_vecs, cand_vecs)
        else:  # combined
            score = calc_combined(target_vecs, cand_vecs, include_price=include_price)

        candidates.append((row, score))

    # 상위 N개 정렬
    candidates.sort(key=lambda x: x[1], reverse=True)
    results = [
        _format_result(row, score, "similarity_pct", sgg_names)
        for row, score in candidates[:top_n]
    ]

    return {
        "pnu": pnu,
        "mode": mode,
        "similar": results,
        "filters_expanded": filters_expanded,
    }


# ---------------------------------------------------------------------------
# POST /apartment/{pnu}/similar/lifestyle — lifestyle 모드
# ---------------------------------------------------------------------------


@router.post("/apartment/{pnu}/similar/lifestyle")
def get_lifestyle_recommendations(pnu: str, body: LifestyleRequest):
    """라이프스타일 기반 아파트 추천 (넛지 가중치 기반 선호도 점수)."""
    conn = DictConnection()
    try:
        target_info = _fetch_target_info(conn, pnu)

        rows, filters_expanded = _fetch_candidates(
            conn, pnu, "lifestyle",
            None, None, None,
            target_info, body.exclude_same_sigungu, body.top_n,
        )

        sgg_names = _load_sigungu_names(conn)
    finally:
        conn.close()

    # 선호도 점수 계산
    candidates = []
    for row in rows:
        cand_vecs = parse_vectors(row)
        score = calc_lifestyle(cand_vecs, body.nudge_weights)
        candidates.append((row, score))

    # 상위 N개 정렬
    candidates.sort(key=lambda x: x[1], reverse=True)
    results = [
        _format_result(row, score, "preference_score", sgg_names)
        for row, score in candidates[: body.top_n]
    ]

    return {
        "pnu": pnu,
        "mode": "lifestyle",
        "nudge_weights_applied": body.nudge_weights,
        "results": results,
        "filters_expanded": filters_expanded,
    }
