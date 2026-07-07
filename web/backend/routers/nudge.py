"""Nudge scoring API."""

import logging

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel
from database import DictConnection
from services.activity_log import log_event
from services.identity import get_user_identifier
from services.scoring import (
    DERIVED_FACILITY_SUBTYPES,
    INFRA_MISSING_NEUTRAL_SCORE,
    get_nudge_weights,
    get_region_profile,
    facility_score,
    jeonse_ratio_to_score,
    elevator_to_score,
    parking_ratio_to_score,
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
            sgg_code_list: list[str] = []
            for kw in kw_list:
                sgg_rows = conn.execute(
                    "SELECT code FROM common_code WHERE group_id = 'sigungu' AND (name LIKE %s OR extra || name LIKE %s)",
                    [f"%{kw}%", f"%{kw}%"],
                ).fetchall()
                sgg_code_list.extend(r["code"] for r in sgg_rows)

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

        # 3. Load facility summaries in bulk
        chunk_size = 500
        summary_rows = []
        for i in range(0, len(pnu_list), chunk_size):
            chunk = pnu_list[i : i + chunk_size]
            ph_pnu = ",".join(["%s"] * len(chunk))
            ph_sub = ",".join(["%s"] * len(all_subtypes))
            sql = (
                f"SELECT pnu, facility_subtype, nearest_distance_m, count_1km "
                f"FROM apt_facility_summary "
                f"WHERE pnu IN ({ph_pnu}) AND facility_subtype IN ({ph_sub})"
            )
            summary_rows.extend(
                conn.execute(sql, chunk + list(all_subtypes)).fetchall()
            )

        # 4. Build per-apartment facility scores (거리 70% + 밀도 30% 블렌딩)
        pnu_profiles = {
            pnu: get_region_profile(apt_map[pnu].get("sigungu_code"))
            for pnu in pnu_list
        }
        apt_facility_scores: dict[str, dict[str, float]] = {}
        for row in summary_rows:
            pnu = row["pnu"]
            if pnu not in apt_facility_scores:
                apt_facility_scores[pnu] = {}
            apt_facility_scores[pnu][row["facility_subtype"]] = facility_score(
                row["nearest_distance_m"],
                row["count_1km"],
                row["facility_subtype"],
                profile=pnu_profiles.get(pnu, "metro"),
            )

        # 4a. 지역 결측 subtype 중립화 — 후보군 전체에서 관측 0건인 시설 축은
        # 그 지역에 데이터/인프라가 없는 것으로 보고 전 후보 중립 점수 처리
        # (subway 특례의 일반화 — INFRA_MISSING_NEUTRAL_SCORE 주석 참조).
        # 일부 후보에만 없는 축은 실제 원거리로 간주해 기존대로 0점 유지.
        # score_* pseudo-subtype 은 각자 로더(4b~4d)가 결측 기본값을 처리한다.
        facility_subtypes = {s for s in all_subtypes if not s.startswith("score_")}
        observed_subtypes = {row["facility_subtype"] for row in summary_rows}
        region_missing_subtypes = facility_subtypes - observed_subtypes
        if region_missing_subtypes:
            for pnu in pnu_list:
                fscores = apt_facility_scores.setdefault(pnu, {})
                for subtype in region_missing_subtypes:
                    fscores[subtype] = INFRA_MISSING_NEUTRAL_SCORE

        # 4a-1. 파생 지표(DERIVED_FACILITY_SUBTYPES) per-apartment 결측 중립화 —
        # assigned_elementary 는 quarterly 배치가 계산하는 파생값이라, trade 배치로
        # 신규 등록된 아파트는 다음 quarterly 실행 전까지 이 subtype 행이 없다.
        # 4a는 "후보군 전체" 결측만 중립화하므로, 일부 아파트만 결측인 이 케이스는
        # 별도로 처리해야 education(가중 0.30) 축에서 신규 아파트가 0점으로 깔리지 않는다.
        # 발동 조건: 신규 아파트가 quarterly 학군 배정 배치 실행 전 창(window)에 있을 때.
        derived_requested = facility_subtypes & DERIVED_FACILITY_SUBTYPES
        if derived_requested:
            for pnu in pnu_list:
                fscores = apt_facility_scores.setdefault(pnu, {})
                for subtype in derived_requested:
                    fscores.setdefault(subtype, INFRA_MISSING_NEUTRAL_SCORE)

        # 4b. Price scores
        price_nudges = {"cost", "investment"}
        if price_nudges & set(req.nudges):
            for i in range(0, len(pnu_list), chunk_size):
                chunk = pnu_list[i : i + chunk_size]
                ph = ",".join(["%s"] * len(chunk))
                rows = conn.execute(
                    f"SELECT pnu, price_score, jeonse_ratio FROM apt_price_score WHERE pnu IN ({ph})",
                    chunk,
                ).fetchall()
                for row in rows:
                    pnu = row["pnu"]
                    if pnu not in apt_facility_scores:
                        apt_facility_scores[pnu] = {}
                    apt_facility_scores[pnu]["score_price"] = row["price_score"] or 50.0
                    # 전세가율 원값(0~215%)은 스케일이 달라 정규화 함수를 경유
                    apt_facility_scores[pnu]["score_jeonse"] = jeonse_ratio_to_score(
                        row["jeonse_ratio"]
                    )

        # 4c. Safety scores
        safety_nudges = {"cost", "newlywed", "senior", "safety"}
        if safety_nudges & set(req.nudges):
            for i in range(0, len(pnu_list), chunk_size):
                chunk = pnu_list[i : i + chunk_size]
                ph = ",".join(["%s"] * len(chunk))
                try:
                    rows = conn.execute(
                        f"SELECT pnu, safety_score FROM apt_safety_score WHERE pnu IN ({ph})",
                        chunk,
                    ).fetchall()
                    for row in rows:
                        pnu = row["pnu"]
                        if pnu not in apt_facility_scores:
                            apt_facility_scores[pnu] = {}
                        apt_facility_scores[pnu]["score_safety"] = (
                            row["safety_score"] or 50.0
                        )
                except Exception:
                    pass

        # 4d. Crime scores (시군구별 범죄율 기반)
        crime_nudges = {"safety"}
        if crime_nudges & set(req.nudges):
            try:
                # 시군구코드 → 범죄안전점수 로드
                sgg_codes = list(
                    set(
                        apt_map[p].get("sigungu_code", "")[:5]
                        for p in pnu_list
                        if apt_map[p].get("sigungu_code")
                    )
                )
                if sgg_codes:
                    ph = ",".join(["%s"] * len(sgg_codes))
                    # sigungu_crime_detail: 전국 268개 시군구 백분위 점수 (KOSIS 경찰청 통계).
                    # 구 sigungu_crime_score(77행, 초기 적재분)는 커버리지가 좁아 사용하지 않는다.
                    crime_rows = conn.execute(
                        f"SELECT sigungu_code, crime_safety_score FROM sigungu_crime_detail WHERE sigungu_code IN ({ph})",
                        sgg_codes,
                    ).fetchall()
                    sgg_crime = {
                        r["sigungu_code"]: r["crime_safety_score"] for r in crime_rows
                    }
                    for pnu in pnu_list:
                        sgg = (apt_map[pnu].get("sigungu_code") or "")[:5]
                        if sgg in sgg_crime:
                            if pnu not in apt_facility_scores:
                                apt_facility_scores[pnu] = {}
                            apt_facility_scores[pnu]["score_crime"] = sgg_crime[sgg]
            except Exception:
                pass

        # 4f. Building register scores (건축물대장 승강기/주차 — Phase 2-1)
        quality_nudges = {"senior", "cost", "newlywed"}
        if quality_nudges & set(req.nudges):
            for i in range(0, len(pnu_list), chunk_size):
                chunk = pnu_list[i : i + chunk_size]
                ph = ",".join(["%s"] * len(chunk))
                # try 는 조회만 감싼다 — 점수 함수 버그가 fallback 으로
                # 위장되지 않도록 행 처리 루프는 try 밖에서 수행.
                try:
                    rows = conn.execute(
                        f"SELECT pnu, elevator_count, parking_per_hhld, "
                        f"register_hhld_cnt FROM apt_building_register WHERE pnu IN ({ph})",
                        chunk,
                    ).fetchall()
                except Exception:
                    # 테이블 미생성 환경(마이그레이션 전) — 4e 결측 중립화에 위임
                    logger.warning(
                        "apt_building_register 조회 실패 — 4e 중립화로 위임",
                        exc_info=True,
                    )
                    rows = []
                for row in rows:
                    pnu = row["pnu"]
                    fscores = apt_facility_scores.setdefault(pnu, {})
                    hhld = row["register_hhld_cnt"] or apt_map[pnu].get(
                        "total_hhld_cnt"
                    )
                    fscores["score_elevator"] = elevator_to_score(
                        row["elevator_count"], hhld
                    )
                    fscores["score_parking"] = parking_ratio_to_score(
                        row["parking_per_hhld"]
                    )

        # 4g. Air quality scores (에어코리아 PM2.5 백분위 — Phase 2-4)
        nature_nudges = {"nature"}
        if nature_nudges & set(req.nudges):
            for i in range(0, len(pnu_list), chunk_size):
                chunk = pnu_list[i : i + chunk_size]
                ph = ",".join(["%s"] * len(chunk))
                # try 는 조회만 감싼다 — 4f 와 동일하게 테이블 미생성 환경은
                # 4e 결측 중립화에 위임하고, 행 처리 로직 버그는 감추지 않는다.
                try:
                    rows = conn.execute(
                        f"SELECT pnu, score_air FROM apt_air_score WHERE pnu IN ({ph})",
                        chunk,
                    ).fetchall()
                except Exception:
                    logger.warning(
                        "apt_air_score 조회 실패 — 4e 중립화로 위임", exc_info=True
                    )
                    rows = []
                for row in rows:
                    pnu = row["pnu"]
                    fscores = apt_facility_scores.setdefault(pnu, {})
                    fscores["score_air"] = row["score_air"] or 50.0

        # 4e. score_* pseudo-subtype 결측 중립화 — 원천 테이블(apt_price_score /
        # apt_safety_score / sigungu_crime_detail)에 해당 아파트·시군구가 없으면
        # 데이터 미보유이므로 0점 페널티 대신 중립 점수를 적용한다 (4a 와 동일 정책).
        # 발동 조건: 위 4b~4d 로더가 값을 채우지 못한 pnu × score_* 조합.
        score_subtypes = {s for s in all_subtypes if s.startswith("score_")}
        if score_subtypes:
            for pnu in pnu_list:
                fscores = apt_facility_scores.setdefault(pnu, {})
                for subtype in score_subtypes:
                    fscores.setdefault(subtype, INFRA_MISSING_NEUTRAL_SCORE)

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
