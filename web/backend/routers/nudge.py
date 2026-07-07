"""Nudge scoring API."""

import logging

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel
from database import DictConnection
from services.activity_log import log_event
from services.identity import get_user_identifier
from services.facility_scores import build_facility_scores, resolve_sigungu_codes
from services.scoring import (
    get_nudge_weights,
    calculate_nudge_score,
    calculate_multi_nudge_score,
    get_top_contributors,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class NudgeScoreRequest(BaseModel):
    nudges: list[str]
    weights: dict[str, dict[str, float]] | None = None
    top_n: int = 20
    sw_lat: float | None = None
    sw_lng: float | None = None
    ne_lat: float | None = None
    ne_lng: float | None = None
    keyword: str | None = None
    keywords: list[str] | None = None
    sigungu_code: str | None = None
    bjd_code: str | None = None
    # Filters
    min_area: float | None = None
    max_area: float | None = None
    min_price: int | None = None
    max_price: int | None = None
    min_floor: int | None = None
    min_hhld: int | None = None
    max_hhld: int | None = None
    built_after: int | None = None
    built_before: int | None = None


@router.post("/nudge/score")
def nudge_score(
    req: NudgeScoreRequest, request: Request, background_tasks: BackgroundTasks
):
    """Calculate nudge scores for apartments and return top_n.

    log_event 는 BackgroundTasks 로 비동기 기록.
    """
    background_tasks.add_task(
        log_event,
        get_user_identifier(request),
        "nudge_score",
        None,
        {
            "nudges": req.nudges,
            "top_n": req.top_n,
            "keyword": req.keyword,
            "sigungu_code": req.sigungu_code,
            "bjd_code": req.bjd_code,
        },
    )

    conn = DictConnection()
    try:
        # 1. Get apartments (keyword, bounds, and property filters)
        apt_sql = """SELECT a.pnu, COALESCE(a.display_name, a.bld_nm) AS bld_nm, a.lat, a.lng, a.total_hhld_cnt, a.new_plat_plc, a.sigungu_code
            FROM apartments a
            LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
            LEFT JOIN apt_price_score ps ON a.pnu = ps.pnu"""
        conditions: list[str] = [
            "a.lat IS NOT NULL",
            "a.pnu NOT LIKE 'TRADE_%%'",
            "a.total_hhld_cnt > 0",
            "a.use_apr_day IS NOT NULL AND a.use_apr_day != ''",
        ]
        params: list = []

        # 다중 키워드 지원 (keywords 우선, 없으면 keyword 단일 호환)
        import re

        kw_list: list[str] = []
        if req.keywords:
            kw_list = [k.strip() for k in req.keywords if k.strip()]
        elif req.keyword and req.keyword.strip():
            kw_list = [req.keyword.strip()]

        # 지역 필터 (동일명 지역 구분용 — 텍스트 매칭보다 우선 적용)
        if req.bjd_code:
            conditions.append("a.bjd_code = %s")
            params.append(req.bjd_code)
        elif req.sigungu_code:
            conditions.append("a.sigungu_code = %s")
            params.append(req.sigungu_code)

        if kw_list and not (req.bjd_code or req.sigungu_code):
            # 시군구명→코드 매칭 (주소 없는 비수도권 아파트 지원)
            sgg_code_list = resolve_sigungu_codes(conn, kw_list)

            or_clauses = []
            for kw in kw_list:
                pattern = f"%{kw}%"
                norm_kw = re.sub(r"[\s()\-·]", "", kw)
                norm_pattern = f"%{norm_kw}%"
                or_clauses.append(
                    "(a.new_plat_plc LIKE %s OR a.plat_plc LIKE %s OR a.bld_nm LIKE %s OR a.bld_nm_norm LIKE %s OR a.display_name LIKE %s)"
                )
                params.extend([pattern, pattern, pattern, norm_pattern, pattern])
            if sgg_code_list:
                ph_sgg = ",".join(["%s"] * len(sgg_code_list))
                or_clauses.append(f"a.sigungu_code IN ({ph_sgg})")
                params.extend(sgg_code_list)
            conditions.append(f"({' OR '.join(or_clauses)})")

        # 지역 필터가 설정되면 bounds 무시 (지도 이동해도 결과 고정)
        if not (req.bjd_code or req.sigungu_code) and all(
            v is not None for v in [req.sw_lat, req.sw_lng, req.ne_lat, req.ne_lng]
        ):
            conditions.append("a.lat BETWEEN %s AND %s AND a.lng BETWEEN %s AND %s")
            params.extend([req.sw_lat, req.ne_lat, req.sw_lng, req.ne_lng])

        # Property filters
        if req.min_area is not None:
            conditions.append("ai.max_area >= %s")
            params.append(req.min_area)
        if req.max_area is not None:
            conditions.append("ai.min_area <= %s")
            params.append(req.max_area)
        if req.min_price is not None:
            conditions.append(
                "ps.price_per_m2 * COALESCE(ai.avg_area, 60) / 10000 >= %s"
            )
            params.append(req.min_price)
        if req.max_price is not None:
            conditions.append(
                "ps.price_per_m2 * COALESCE(ai.avg_area, 60) / 10000 <= %s"
            )
            params.append(req.max_price)
        if req.min_floor is not None:
            conditions.append("a.max_floor >= %s")
            params.append(req.min_floor)
        if req.min_hhld is not None:
            conditions.append("a.total_hhld_cnt >= %s")
            params.append(req.min_hhld)
        if req.max_hhld is not None:
            conditions.append("a.total_hhld_cnt <= %s")
            params.append(req.max_hhld)
        if req.built_after is not None:
            conditions.append(
                "a.use_apr_day ~ '^[0-9]{4}' AND LEFT(a.use_apr_day, 4)::int >= %s"
            )
            params.append(req.built_after)
        if req.built_before is not None:
            conditions.append(
                "a.use_apr_day ~ '^[0-9]{4}' AND LEFT(a.use_apr_day, 4)::int <= %s"
            )
            params.append(req.built_before)

        if conditions:
            apt_sql += " WHERE " + " AND ".join(conditions)

        apartments = conn.execute(apt_sql, params).fetchall()
        pnu_list = [a["pnu"] for a in apartments]
        apt_map = {a["pnu"]: a for a in apartments}

        if not pnu_list:
            return []

        # 2. Collect all relevant subtypes from requested nudges
        all_subtypes = set()
        for nid in req.nudges:
            ws = (req.weights or {}).get(nid) if req.weights else None
            subtypes = ws if ws else get_nudge_weights().get(nid, {})
            all_subtypes.update(subtypes.keys())

        if not all_subtypes:
            return []

        # 3~4e. 시설/가격/안전/범죄/건축물대장/대기질 점수 조립 — 공용 서비스로 위임
        # (nudge.py 와 MCP tool 이 동일 파이프라인을 쓰도록 facility_scores.py 로 이동)
        apt_facility_scores = build_facility_scores(
            conn, pnu_list, req.nudges, apt_map, weights=req.weights
        )

        # 5. Calculate scores
        results = []
        for pnu in pnu_list:
            fscores = apt_facility_scores.get(pnu, {})
            if req.nudges:
                breakdown = {}
                for nid in req.nudges:
                    cw = (req.weights or {}).get(nid) if req.weights else None
                    breakdown[nid] = calculate_nudge_score(fscores, nid, cw)
                score = calculate_multi_nudge_score(fscores, req.nudges, req.weights)
                top_contributors = get_top_contributors(
                    fscores, req.nudges, req.weights, top_n=3
                )
            else:
                score = 0.0
                breakdown = {}
                top_contributors = []

            apt = apt_map[pnu]
            results.append(
                {
                    "pnu": pnu,
                    "bld_nm": apt["bld_nm"],
                    "lat": apt["lat"],
                    "lng": apt["lng"],
                    "total_hhld_cnt": apt["total_hhld_cnt"],
                    "score": score,
                    "score_breakdown": breakdown,
                    "top_contributors": top_contributors,
                }
            )

        # 6. Sort and return top_n
        results.sort(key=lambda x: x["score"], reverse=True)

        # 후보군 내 백분위(표시 보조 지표) — 상위권 절대점수가 1~4점 폭으로
        # 압축되어 변별이 어려우므로 "이 후보군에서 상위 몇 %인가"를 함께 제공.
        # 정렬 순위 기반(1위=100.0)이며 기존 score/순위는 변경하지 않는다.
        candidate_count = len(results)
        for rank_index, item in enumerate(results):
            item["score_percentile"] = round(
                (candidate_count - rank_index) / candidate_count * 100.0, 1
            )

        return results[: req.top_n]
    finally:
        conn.close()


@router.get("/nudge/weights")
def nudge_weights_api():
    """Return the nudge weight configuration."""
    return get_nudge_weights()
