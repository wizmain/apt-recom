"""Apartment detail + trade history API."""

import threading

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from database import DictConnection
from services.activity_log import log_event
from services.identity import get_user_identifier
from services.mgmt_cost_calc import compute_by_area
from services.scoring import (
    get_nudge_weights,
    get_region_profile,
    facility_score,
    calculate_nudge_score,
)

router = APIRouter()


# 시군구·월 단위 관리비 percentile 결과 캐시 (process-lifetime).
# detail 호출마다 시군구 전 단지를 percentile_cont 로 집계하던 것을 첫 1회만 계산.
# K-APT 관리비는 월 단위로만 갱신되므로 stale 위험 매우 낮음.
_MGMT_PCT_CACHE: dict[tuple[str, str], dict[str, float | None]] = {}
_MGMT_PCT_LOCK = threading.Lock()


def _mgmt_percentiles(conn, sgg: str, ym: str) -> dict[str, float | None]:
    """시군구·월 단위 관리비 median (per_unit, per_m2) 조회.

    조회 우선순위:
      1) process-lifetime in-memory cache
      2) sigungu_mgmt_cost_stats 캐시 테이블 (batch.compute_mgmt_cost_stats 가 갱신)
      3) raw 집계 fallback (캐시 테이블 미반영 신규 시군구·월)
    """
    key = (sgg, ym)
    cached = _MGMT_PCT_CACHE.get(key)
    if cached is not None:
        return cached

    # 1) 캐시 테이블 lookup
    row = conn.execute(
        "SELECT median_per_unit, median_per_m2 "
        "FROM sigungu_mgmt_cost_stats WHERE sigungu_code = %s AND year_month = %s",
        [sgg, ym],
    ).fetchone()

    if row is None:
        # 2) fallback: 캐시 미스 시 직접 계산 (신규 시군구·월 또는 batch 미실행 환경)
        row = conn.execute(
            """
            WITH eligible AS (
                SELECT m.pnu, m.total_cost, m.cost_per_unit
                FROM apt_mgmt_cost m
                JOIN apartments a ON m.pnu = a.pnu
                WHERE a.sigungu_code = %s
                  AND m.year_month = %s
                  AND m.cost_per_unit >= 10000
                  AND m.total_cost >= 100000
                  AND m.cost_per_unit != m.total_cost
            ),
            with_area AS (
                SELECT e.total_cost::float / at.mgmt_area_total AS per_m2
                FROM eligible e
                JOIN (
                    SELECT pnu, MAX(mgmt_area_total) AS mgmt_area_total
                    FROM apt_area_type
                    WHERE mgmt_area_total > 0
                    GROUP BY pnu
                ) at ON e.pnu = at.pnu
            )
            SELECT
                (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY cost_per_unit) FROM eligible) AS median_per_unit,
                (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY per_m2) FROM with_area) AS median_per_m2
            """,
            [sgg, ym],
        ).fetchone()

    result = {
        "per_unit": float(row["median_per_unit"]) if row and row["median_per_unit"] else None,
        "per_m2": float(row["median_per_m2"]) if row and row["median_per_m2"] else None,
    }
    with _MGMT_PCT_LOCK:
        _MGMT_PCT_CACHE[key] = result
    return result


@router.get("/apartment/{pnu}")
def apartment_detail(pnu: str, request: Request, background_tasks: BackgroundTasks):
    """Return full detail for one apartment: basic info, scores, facilities, school.

    log_event 는 BackgroundTasks 로 실행되어 응답 반환 후 비동기 기록.
    응답 경로에서 INSERT 블로킹 제거.
    """
    background_tasks.add_task(
        log_event,
        get_user_identifier(request),
        "detail_view",
        None,
        {"pnu": pnu},
    )

    conn = DictConnection()
    try:
        basic = conn.execute(
            "SELECT * FROM apartments WHERE pnu = %s", [pnu]
        ).fetchone()
        if not basic:
            raise HTTPException(status_code=404, detail="Apartment not found")
        basic = dict(basic)

        # Area info (전용/공급 면적 범위)
        area_row = conn.execute(
            "SELECT min_area, max_area, avg_area, "
            "min_supply_area, max_supply_area, avg_supply_area "
            "FROM apt_area_info WHERE pnu = %s",
            [pnu],
        ).fetchone()
        if area_row:
            for col in (
                "min_area",
                "max_area",
                "avg_area",
                "min_supply_area",
                "max_supply_area",
                "avg_supply_area",
            ):
                basic[col] = area_row[col]

        # Facility summary
        summary_rows = conn.execute(
            "SELECT facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km "
            "FROM apt_facility_summary WHERE pnu = %s",
            [pnu],
        ).fetchall()

        facility_summary = {
            row["facility_subtype"]: {
                "nearest_distance_m": row["nearest_distance_m"],
                "count_1km": row["count_1km"],
                "count_3km": row["count_3km"],
                "count_5km": row["count_5km"],
            }
            for row in summary_rows
        }

        profile = get_region_profile(basic.get("sigungu_code"))
        facility_scores = {
            row["facility_subtype"]: facility_score(
                row["nearest_distance_m"],
                row["count_1km"],
                row["facility_subtype"],
                profile=profile,
            )
            for row in summary_rows
        }

        # Price/safety scores
        price_row = conn.execute(
            "SELECT price_score, jeonse_ratio, price_per_m2 FROM apt_price_score WHERE pnu = %s",
            [pnu],
        ).fetchone()
        if price_row:
            facility_scores["score_price"] = price_row["price_score"] or 50.0
            facility_scores["score_jeonse"] = price_row["jeonse_ratio"] or 50.0
            basic["price_per_m2"] = price_row["price_per_m2"]

        safety_row = None
        try:
            safety_row = conn.execute(
                "SELECT safety_score, micro_score, access_score, macro_score, "
                "complex_score, data_reliability, score_version, "
                "complex_cctv_score, complex_security_score, complex_mgr_score, "
                "complex_parking_score, regional_safety_score, crime_adjust_score, "
                "complex_data_source, crime_safety_score "
                "FROM apt_safety_score WHERE pnu = %s",
                [pnu],
            ).fetchone()
        except Exception:
            pass
        if safety_row:
            facility_scores["score_safety"] = safety_row["safety_score"] or 50.0

        scores = {
            nid: calculate_nudge_score(facility_scores, nid)
            for nid in get_nudge_weights()
        }

        # Nearby facilities — 아파트 좌표 기반으로 시설 유형별 최근접 3개 조회.
        # subtype 별 N+1 쿼리(17회) 를 LATERAL JOIN 단일 쿼리로 통합 (~95ms → ~10ms).
        nearby: dict[str, list] = {}
        if basic.get("lat") and basic.get("lng") and summary_rows:
            apt_lat, apt_lng = basic["lat"], basic["lng"]
            subtypes = [r["facility_subtype"] for r in summary_rows]
            fac_rows = conn.execute(
                """
                SELECT s.facility_subtype AS subtype,
                       f.name, f.lat, f.lng,
                       (6371000 * acos(
                           cos(radians(%s)) * cos(radians(f.lat)) *
                           cos(radians(f.lng) - radians(%s)) +
                           sin(radians(%s)) * sin(radians(f.lat))
                       )) AS dist_m
                FROM unnest(%s::text[]) AS s(facility_subtype)
                CROSS JOIN LATERAL (
                    SELECT name, lat, lng
                    FROM facilities
                    WHERE facility_subtype = s.facility_subtype AND lat IS NOT NULL
                    ORDER BY (lat - %s)^2 + (lng - %s)^2
                    LIMIT 3
                ) f
                """,
                [apt_lat, apt_lng, apt_lat, subtypes, apt_lat, apt_lng],
            ).fetchall()
            for r in fac_rows:
                if not r["dist_m"] or r["dist_m"] > 2000:
                    continue
                nearby.setdefault(r["subtype"], []).append(
                    {
                        "subtype": r["subtype"],
                        "name": r["name"],
                        "distance_m": round(r["dist_m"], 1),
                        "lat": r["lat"],
                        "lng": r["lng"],
                    }
                )
        # School zone — 법정동 LIKE로 1회 조회 후 PNU 비교
        school = None
        bjd = basic.get("bjd_code") or pnu[:10]
        school_rows = conn.execute(
            "SELECT * FROM school_zones WHERE pnu LIKE %s", [f"{bjd}%"]
        ).fetchall()
        if school_rows:
            exact = next((r for r in school_rows if r["pnu"] == pnu), None)
            school = dict(exact if exact else school_rows[0])
            school["estimated"] = exact is None

        # 아래 두 fetch 는 safety.kapt_security 와 kapt_info / mgmt_cost 처리에서
        # 동일하게 재사용. 매 영역에서 별도로 쿼리하던 것을 한 번으로 통합.
        kapt_rows = conn.execute(
            "SELECT * FROM apt_kapt_info WHERE pnu = %s ORDER BY kapt_code", [pnu]
        ).fetchall()
        cost_rows = conn.execute(
            "SELECT year_month, common_cost, individual_cost, repair_fund, "
            "total_cost, cost_per_unit, detail "
            "FROM apt_mgmt_cost WHERE pnu = %s ORDER BY year_month DESC LIMIT 6",
            [pnu],
        ).fetchall()

        # CCTV/safety info + crime score
        safety_info = None
        try:
            safety_score_val = safety_row["safety_score"] if safety_row else None

            # 범죄율 점수 + 상세
            crime_score = None
            crime_detail = None
            sigungu = (
                basic.get("sigungu_code", "")[:5] if basic.get("sigungu_code") else None
            )
            if sigungu:
                crime_row = conn.execute(
                    "SELECT * FROM sigungu_crime_detail WHERE sigungu_code = %s",
                    [sigungu],
                ).fetchone()
                if crime_row:
                    crime_score = crime_row["crime_safety_score"]
                    crime_detail = {
                        "murder": crime_row.get("murder", 0),
                        "robbery": crime_row.get("robbery", 0),
                        "sexual_assault": crime_row.get("sexual_assault", 0),
                        "theft": crime_row.get("theft", 0),
                        "violence": crime_row.get("violence", 0),
                        "total_crime": crime_row.get("total_crime", 0),
                        "resident_pop": crime_row.get("resident_pop", 0),
                        "effective_pop": crime_row.get("effective_pop", 0),
                        "crime_rate": crime_row.get("crime_rate", 0),
                        "float_pop_ratio": crime_row.get("float_pop_ratio", 1.0),
                    }
                else:
                    score_row = conn.execute(
                        "SELECT crime_safety_score FROM sigungu_crime_score WHERE sigungu_code = %s",
                        [sigungu],
                    ).fetchone()
                    if score_row:
                        crime_score = score_row["crime_safety_score"]

            police_dist = facility_summary.get("police", {}).get("nearest_distance_m")
            fire_dist = facility_summary.get("fire_station", {}).get(
                "nearest_distance_m"
            )
            fire_center_dist = facility_summary.get("fire_center", {}).get(
                "nearest_distance_m"
            )
            hospital_dist = facility_summary.get("hospital", {}).get(
                "nearest_distance_m"
            )

            # v3 세부 점수
            v3_scores = None
            score_version = safety_row.get("score_version", 2) if safety_row else 2
            if safety_row and score_version == 3:
                v3_scores = {
                    "complex_score": safety_row.get("complex_score"),
                    "complex_cctv_score": safety_row.get("complex_cctv_score"),
                    "complex_security_score": safety_row.get("complex_security_score"),
                    "complex_mgr_score": safety_row.get("complex_mgr_score"),
                    "complex_parking_score": safety_row.get("complex_parking_score"),
                    "access_score": safety_row.get("access_score"),
                    "regional_safety_score": safety_row.get("regional_safety_score"),
                    "crime_adjust_score": safety_row.get("crime_adjust_score"),
                    "data_reliability": safety_row.get("data_reliability"),
                    "complex_data_source": safety_row.get("complex_data_source"),
                }
            elif safety_row and safety_row.get("micro_score") is not None:
                # v2 호환
                v3_scores = {
                    "micro_score": safety_row["micro_score"],
                    "access_score": safety_row["access_score"],
                    "macro_score": safety_row["macro_score"],
                    "complex_score": safety_row["complex_score"],
                    "data_reliability": safety_row["data_reliability"],
                }

            # 행안부 지역안전지수 등급
            regional_grades = None
            if sigungu:
                si_row = conn.execute(
                    "SELECT s.traffic_grade, s.fire_grade, s.crime_grade, s.living_safety_grade, "
                    "c.extra || ' ' || c.name AS region_name "
                    "FROM sigungu_safety_index s "
                    "LEFT JOIN common_code c ON c.group_id = 'sigungu' AND c.code = %s "
                    "WHERE s.sigungu_code = %s",
                    [sigungu, sigungu],
                ).fetchone()
                if si_row:
                    regional_grades = {
                        "traffic": si_row["traffic_grade"],
                        "fire": si_row["fire_grade"],
                        "crime": si_row["crime_grade"],
                        "living_safety": si_row["living_safety_grade"],
                        "region_name": si_row["region_name"],
                    }

            # K-APT 단지 보안 현황 — 위에서 미리 fetch 한 kapt_rows / cost_rows 재사용
            kapt_security = None
            try:
                kapt_row = kapt_rows[0] if kapt_rows else None
                if kapt_row:
                    hhld = basic.get("total_hhld_cnt") or None
                    # 최신 경비비 — cost_rows[0] 가 가장 최근 월
                    security_cost = None
                    if cost_rows and cost_rows[0].get("detail"):
                        detail = cost_rows[0]["detail"]
                        security_cost = detail.get("경비비") or detail.get("security")

                    kapt_security = {
                        "cctv_cnt": kapt_row.get("cctv_cnt"),
                        "parking_cnt": kapt_row.get("parking_cnt"),
                        "mgr_type": kapt_row.get("mgr_type"),
                        "total_hhld_cnt": hhld,
                        "security_cost_per_unit": round(int(security_cost) / hhld)
                        if security_cost and hhld
                        else None,
                    }
            except Exception:
                pass

            safety_info = {
                "safety_score": safety_score_val,
                "score_version": score_version,
                "crime_safety_score": crime_score,
                "crime_detail": crime_detail,
                "police_nearest_m": police_dist,
                "fire_nearest_m": fire_dist,
                "fire_center_nearest_m": fire_center_dist,
                "hospital_nearest_m": hospital_dist,
                "nudge_safety_score": scores.get("safety", 0),
                "v3": v3_scores,
                "regional_grades": regional_grades,
                "kapt_security": kapt_security,
            }
        except Exception:
            pass

        # Population
        population = None
        try:
            sigungu = basic.get("sigungu_code")
            if sigungu:
                pop_rows = conn.execute(
                    """
                    SELECT age_group, total_pop, male_pop, female_pop
                    FROM population_by_district
                    WHERE sigungu_code = %s AND age_group != '계'
                    ORDER BY age_group
                """,
                    [sigungu],
                ).fetchall()
                pop_total_row = conn.execute(
                    """
                    SELECT total_pop, male_pop, female_pop, sigungu_name
                    FROM population_by_district
                    WHERE sigungu_code = %s AND age_group = '계'
                """,
                    [sigungu],
                ).fetchone()
                if pop_rows and pop_total_row:
                    total = pop_total_row["total_pop"] or 1
                    population = {
                        "sigungu_name": pop_total_row["sigungu_name"],
                        "total_pop": total,
                        "male_pop": pop_total_row["male_pop"],
                        "female_pop": pop_total_row["female_pop"],
                        "age_groups": [
                            {
                                "age_group": r["age_group"],
                                "total": r["total_pop"],
                                "ratio": round(r["total_pop"] / total * 100, 1),
                                "male": r["male_pop"],
                                "female": r["female_pop"],
                            }
                            for r in pop_rows
                        ],
                    }
        except Exception:
            pass

        # K-APT 상세정보 — 위에서 미리 fetch 한 kapt_rows 재사용.
        # 같은 PNU 에 분양/임대가 별도 K-APT 행으로 등록된 단지(예: 청구e편한세상)는
        # 호수/동수 등 가산 가능한 컬럼만 합산하여 통합 마스터 정보로 노출한다.
        # 단일 행만 매핑된 단지는 합산값이 자기 자신과 같아 동작 변화 없음.
        kapt_info = None
        if kapt_rows:
            kapt_info = dict(kapt_rows[0])
            kapt_info.pop("updated_at", None)
            # 가산 가능한 카운트 컬럼은 SUM 으로 통합 (분양 + 임대)
            sum_cols = (
                "ho_cnt", "dong_cnt",
                "sale_ho_cnt", "rent_ho_cnt", "rent_public_cnt", "rent_private_cnt",
            )
            for c in sum_cols:
                kapt_info[c] = sum((row[c] or 0) for row in kapt_rows)
            # K-APT 값이 있으면 기본정보를 K-APT 값으로 override.
            # (건축물대장은 주차/부속동까지 세어 dong_count 부풀려지는 등 정확도 낮음)
            # 단, 호수/동수는 apartments 정정값(분양+임대 통합 마스터 값)이 더 큰 경우
            # apartments 를 신뢰한다 (K-APT 가 임대 단지만 PNU 매핑된 케이스 대응).
            apt_hhld = basic.get("total_hhld_cnt") or 0
            apt_dong = basic.get("dong_count") or 0
            kapt_ho = kapt_info.get("ho_cnt") or 0
            kapt_dong = kapt_info.get("dong_cnt") or 0
            if max(apt_hhld, kapt_ho):
                basic["total_hhld_cnt"] = max(apt_hhld, kapt_ho)
            if max(apt_dong, kapt_dong):
                basic["dong_count"] = max(apt_dong, kapt_dong)
            # 최고층 우선순위: top_floor_official > top_floor(>3 일 때) > 건축물대장 max_floor
            # K-APT 원본의 top_floor 가 일부 단지에서 1·2·0 등으로 오염된 케이스 대응.
            kapt_top_official = kapt_info.get("top_floor_official") or 0
            kapt_top = kapt_info.get("top_floor") or 0
            if kapt_top_official > 0:
                basic["max_floor"] = kapt_top_official
            elif kapt_top > 3:
                basic["max_floor"] = kapt_top
            if kapt_info.get("use_date"):
                basic["use_apr_day"] = kapt_info["use_date"]

        # 관리비 (최근 3개월 + 지역 평균) — 위에서 미리 fetch 한 cost_rows 재사용.
        mgmt_cost = None
        if cost_rows:
            # 지역 평균 (같은 시군구, 같은 월) — 두 percentile 한 번에, process-cache.
            sgg = basic.get("sigungu_code", "")[:5]
            latest_ym = cost_rows[0]["year_month"]
            percentiles = _mgmt_percentiles(conn, sgg, latest_ym)
            region_avg_per_unit = (
                round(percentiles["per_unit"]) if percentiles["per_unit"] else None
            )
            region_avg_per_m2 = (
                round(percentiles["per_m2"]) if percentiles["per_m2"] else None
            )

            # 주택형별 관리비 (공식 B: 공용+장충금은 전용면적 비례, 개별은 평균)
            # 정수 면적(=평형) 그룹화는 compute_by_area 에서 처리.
            area_types = conn.execute(
                "SELECT exclusive_area, unit_count, priv_area_total, mgmt_area_total "
                "FROM apt_area_type WHERE pnu = %s ORDER BY exclusive_area",
                [pnu],
            ).fetchall()
            by_area = compute_by_area(
                dict(cost_rows[0]),
                [dict(r) for r in area_types],
            )

            # 단위면적당 관리비: 단지 총 관리비 / 관리비부과면적 (K-APT 실제 부과 기준)
            cost_per_m2 = None
            if area_types:
                mgmt_area = float(area_types[0]["mgmt_area_total"] or 0)
                if mgmt_area > 0:
                    cost_per_m2 = round(cost_rows[0]["total_cost"] / mgmt_area)

            mgmt_cost = {
                "months": [dict(r) for r in cost_rows],
                "region_avg_per_unit": region_avg_per_unit,
                "by_area": by_area,
                "cost_per_m2": cost_per_m2,
                "region_avg_per_m2": region_avg_per_m2,
                "latest_year_month": cost_rows[0]["year_month"] if cost_rows else None,
            }

        return {
            "basic": basic,
            "scores": scores,
            "facility_summary": facility_summary,
            "nearby_facilities": nearby,
            "school": school,
            "safety": safety_info,
            "population": population,
            "kapt_info": kapt_info,
            "mgmt_cost": mgmt_cost,
        }
    finally:
        conn.close()


@router.get("/apartment/{pnu}/trades")
def apartment_trades(
    pnu: str,
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="trade/rent 각각 반환할 최근 N건 (기본 100, 최대 1000)",
    ),
):
    """Return trade and rent history for an apartment.

    응답 사이즈 제어를 위해 trade·rent 각각 최근 limit 건만 반환.
    DetailModal 의 차트는 100건이면 충분하며, 광장 같은 대형 단지에서
    1.8MB 응답이 50KB 수준으로 줄어 모바일 체감 로딩이 크게 개선된다.
    """
    conn = DictConnection()
    try:
        mappings = conn.execute(
            "SELECT apt_seq, apt_nm, sgg_cd FROM trade_apt_mapping WHERE pnu = %s",
            [pnu],
        ).fetchall()

        trades = []
        rents = []

        if mappings:
            apt_seqs = [m["apt_seq"] for m in mappings]
            ph = ",".join(["%s"] * len(apt_seqs))
            trades = conn.execute(
                f"SELECT * FROM trade_history WHERE apt_seq IN ({ph}) "
                "ORDER BY deal_year DESC, deal_month DESC, deal_day DESC LIMIT %s",
                apt_seqs + [limit],
            ).fetchall()
            rents = conn.execute(
                f"SELECT * FROM rent_history WHERE apt_seq IN ({ph}) "
                "ORDER BY deal_year DESC, deal_month DESC, deal_day DESC LIMIT %s",
                apt_seqs + [limit],
            ).fetchall()
        else:
            apt = conn.execute(
                "SELECT bld_nm, display_name, sigungu_code FROM apartments WHERE pnu = %s",
                [pnu],
            ).fetchone()
            label = (apt and (apt["display_name"] or apt["bld_nm"])) if apt else None
            if label:
                name_pattern = f"%{label}%"
                sgg = apt["sigungu_code"][:5] if apt["sigungu_code"] else None
                if sgg:
                    trades = conn.execute(
                        "SELECT * FROM trade_history WHERE sgg_cd = %s AND apt_nm LIKE %s "
                        "ORDER BY deal_year DESC, deal_month DESC, deal_day DESC LIMIT %s",
                        [sgg, name_pattern, limit],
                    ).fetchall()
                    rents = conn.execute(
                        "SELECT * FROM rent_history WHERE sgg_cd = %s AND apt_nm LIKE %s "
                        "ORDER BY deal_year DESC, deal_month DESC, deal_day DESC LIMIT %s",
                        [sgg, name_pattern, limit],
                    ).fetchall()

        return {"trades": [dict(r) for r in trades], "rents": [dict(r) for r in rents]}
    finally:
        conn.close()
