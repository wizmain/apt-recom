"""Facility score assembly — nudge.py 의 3~4e 단계를 이동한 공용 모듈.

시설 요약(apt_facility_summary) bulk 조회부터 score_* pseudo-subtype 결측
중립화까지, 아파트 후보군의 시설별 점수를 조립하는 파이프라인을 제공한다.
호출측(HTTP 라우터, MCP tool 등)은 apt_map/pnu_list 를 준비한 뒤 이 함수만
호출하면 되며, 결과 dict 를 calculate_nudge_score() 등에 그대로 넘긴다.
"""

import logging

from services.scoring import (
    DERIVED_FACILITY_SUBTYPES,
    INFRA_MISSING_NEUTRAL_SCORE,
    get_nudge_weights,
    get_region_profile,
    facility_score,
    jeonse_ratio_to_score,
    elevator_to_score,
    parking_ratio_to_score,
)

logger = logging.getLogger(__name__)


def resolve_sigungu_codes(conn, keywords: list[str]) -> list[str]:
    """키워드 목록에 대응하는 시군구 코드 조회 (주소 없는 비수도권 아파트 지원)."""
    sgg_code_list: list[str] = []
    for kw in keywords:
        sgg_rows = conn.execute(
            "SELECT code FROM common_code WHERE group_id = 'sigungu' AND (name LIKE %s OR extra || name LIKE %s)",
            [f"%{kw}%", f"%{kw}%"],
        ).fetchall()
        sgg_code_list.extend(r["code"] for r in sgg_rows)
    return sgg_code_list


def build_facility_scores(
    conn,
    pnu_list: list[str],
    nudge_ids: list[str],
    apt_map: dict[str, dict],
    *,
    weights: dict[str, dict[str, float]] | None = None,
) -> dict[str, dict[str, float]]:
    """후보 아파트(pnu_list)에 대해 nudge_ids 가 요구하는 시설/점수 축을 조립한다.

    호출측은 all_subtypes 가 비어있지 않음(즉 nudge_ids 가 유효한 가중치를
    가짐)을 보장한 뒤 호출해야 한다 — 비어 있으면 빈 dict 를 반환한다.
    apt_map[pnu] 는 최소 sigungu_code, total_hhld_cnt 를 담아야 한다.
    """
    # 2. Collect all relevant subtypes from requested nudges
    all_subtypes = set()
    for nid in nudge_ids:
        ws = (weights or {}).get(nid) if weights else None
        subtypes = ws if ws else get_nudge_weights().get(nid, {})
        all_subtypes.update(subtypes.keys())

    if not all_subtypes:
        return {}

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
        summary_rows.extend(conn.execute(sql, chunk + list(all_subtypes)).fetchall())

    # 4. Build per-apartment facility scores (거리 70% + 밀도 30% 블렌딩)
    pnu_profiles = {
        pnu: get_region_profile(apt_map[pnu].get("sigungu_code")) for pnu in pnu_list
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
    # score_* pseudo-subtype 은 각 로더가 결측 기본값을 처리한다.
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
    if price_nudges & set(nudge_ids):
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
    if safety_nudges & set(nudge_ids):
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
    if crime_nudges & set(nudge_ids):
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
    if quality_nudges & set(nudge_ids):
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
                hhld = row["register_hhld_cnt"] or apt_map[pnu].get("total_hhld_cnt")
                fscores["score_elevator"] = elevator_to_score(
                    row["elevator_count"], hhld
                )
                fscores["score_parking"] = parking_ratio_to_score(
                    row["parking_per_hhld"]
                )

    # 4g. Air quality scores (에어코리아 PM2.5 백분위 — Phase 2-4)
    nature_nudges = {"nature"}
    if nature_nudges & set(nudge_ids):
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
    # 발동 조건: 위 각 로더가 값을 채우지 못한 pnu × score_* 조합.
    score_subtypes = {s for s in all_subtypes if s.startswith("score_")}
    if score_subtypes:
        for pnu in pnu_list:
            fscores = apt_facility_scores.setdefault(pnu, {})
            for subtype in score_subtypes:
                fscores.setdefault(subtype, INFRA_MISSING_NEUTRAL_SCORE)

    return apt_facility_scores
