"""Apartment detail + trade history API."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from database import DictConnection
from services.activity_log import log_event
from services.mgmt_cost_calc import compute_by_area
from services.scoring import (
    get_nudge_weights,
    get_region_profile,
    facility_score,
    calculate_nudge_score,
)

router = APIRouter()


@router.get("/apartment/{pnu}")
def apartment_detail(pnu: str, request: Request, background_tasks: BackgroundTasks):
    """Return full detail for one apartment: basic info, scores, facilities, school.

    log_event 는 BackgroundTasks 로 실행되어 응답 반환 후 비동기 기록.
    응답 경로에서 INSERT 블로킹 제거.
    """
    background_tasks.add_task(
        log_event,
        request.headers.get("x-device-id"),
        "detail_view",
        None,
        {"pnu": pnu},
    )

    conn = DictConnection()
    try:
        basic = conn.execute("SELECT * FROM apartments WHERE pnu = %s", [pnu]).fetchone()
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
            for col in ("min_area", "max_area", "avg_area",
                         "min_supply_area", "max_supply_area", "avg_supply_area"):
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
            "SELECT price_score, jeonse_ratio, price_per_m2 FROM apt_price_score WHERE pnu = %s", [pnu]
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
                "FROM apt_safety_score WHERE pnu = %s", [pnu]
            ).fetchone()
        except Exception:
            pass
        if safety_row:
            facility_scores["score_safety"] = safety_row["safety_score"] or 50.0

        scores = {
            nid: calculate_nudge_score(facility_scores, nid)
            for nid in get_nudge_weights()
        }

        # Nearby facilities — 아파트 좌표 기반으로 시설 유형별 최근접 3개 조회
        nearby: dict[str, list] = {}
        if basic.get("lat") and basic.get("lng"):
            apt_lat, apt_lng = basic["lat"], basic["lng"]
            subtypes = [r["facility_subtype"] for r in summary_rows]
            for subtype in subtypes:
                fac_rows = conn.execute(
                    """
                    SELECT name, lat, lng,
                           (6371000 * acos(
                               cos(radians(%s)) * cos(radians(lat)) *
                               cos(radians(lng) - radians(%s)) +
                               sin(radians(%s)) * sin(radians(lat))
                           )) as dist_m
                    FROM facilities
                    WHERE facility_subtype = %s AND lat IS NOT NULL
                    ORDER BY (lat - %s)^2 + (lng - %s)^2
                    LIMIT 3
                    """,
                    [apt_lat, apt_lng, apt_lat, subtype, apt_lat, apt_lng],
                ).fetchall()
                if fac_rows:
                    items = [
                        {
                            "subtype": subtype,
                            "name": r["name"],
                            "distance_m": round(r["dist_m"], 1),
                            "lat": r["lat"],
                            "lng": r["lng"],
                        }
                        for r in fac_rows if r["dist_m"] and r["dist_m"] <= 2000
                    ]
                    if items:
                        nearby[subtype] = items

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

        # CCTV/safety info + crime score
        safety_info = None
        try:
            safety_score_val = safety_row["safety_score"] if safety_row else None

            # 범죄율 점수 + 상세
            crime_score = None
            crime_detail = None
            sigungu = basic.get("sigungu_code", "")[:5] if basic.get("sigungu_code") else None
            if sigungu:
                crime_row = conn.execute(
                    "SELECT * FROM sigungu_crime_detail WHERE sigungu_code = %s", [sigungu]
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
                        "SELECT crime_safety_score FROM sigungu_crime_score WHERE sigungu_code = %s", [sigungu]
                    ).fetchone()
                    if score_row:
                        crime_score = score_row["crime_safety_score"]

            police_dist = facility_summary.get("police", {}).get("nearest_distance_m")
            fire_dist = facility_summary.get("fire_station", {}).get("nearest_distance_m")
            fire_center_dist = facility_summary.get("fire_center", {}).get("nearest_distance_m")
            hospital_dist = facility_summary.get("hospital", {}).get("nearest_distance_m")

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
                    "WHERE s.sigungu_code = %s", [sigungu, sigungu]
                ).fetchone()
                if si_row:
                    regional_grades = {
                        "traffic": si_row["traffic_grade"],
                        "fire": si_row["fire_grade"],
                        "crime": si_row["crime_grade"],
                        "living_safety": si_row["living_safety_grade"],
                        "region_name": si_row["region_name"],
                    }

            # K-APT 단지 보안 현황
            kapt_security = None
            try:
                kapt_row = conn.execute(
                    "SELECT cctv_cnt, parking_cnt, mgr_type FROM apt_kapt_info WHERE pnu = %s", [pnu]
                ).fetchone()
                if kapt_row:
                    hhld_row = conn.execute(
                        "SELECT total_hhld_cnt FROM apartments WHERE pnu = %s", [pnu]
                    ).fetchone()
                    hhld = hhld_row["total_hhld_cnt"] if hhld_row and hhld_row["total_hhld_cnt"] else None
                    # 최신 경비비
                    mgmt_row = conn.execute(
                        "SELECT detail FROM apt_mgmt_cost WHERE pnu = %s ORDER BY year_month DESC LIMIT 1", [pnu]
                    ).fetchone()
                    security_cost = None
                    if mgmt_row and mgmt_row.get("detail"):
                        detail = mgmt_row["detail"]
                        security_cost = detail.get("경비비") or detail.get("security")

                    kapt_security = {
                        "cctv_cnt": kapt_row.get("cctv_cnt"),
                        "parking_cnt": kapt_row.get("parking_cnt"),
                        "mgr_type": kapt_row.get("mgr_type"),
                        "total_hhld_cnt": hhld,
                        "security_cost_per_unit": round(int(security_cost) / hhld) if security_cost and hhld else None,
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
                pop_rows = conn.execute("""
                    SELECT age_group, total_pop, male_pop, female_pop
                    FROM population_by_district
                    WHERE sigungu_code = %s AND age_group != '계'
                    ORDER BY age_group
                """, [sigungu]).fetchall()
                pop_total_row = conn.execute("""
                    SELECT total_pop, male_pop, female_pop, sigungu_name
                    FROM population_by_district
                    WHERE sigungu_code = %s AND age_group = '계'
                """, [sigungu]).fetchone()
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

        # K-APT 상세정보
        kapt_info = None
        kapt_row = conn.execute("SELECT * FROM apt_kapt_info WHERE pnu = %s", [pnu]).fetchone()
        if kapt_row:
            kapt_info = dict(kapt_row)
            kapt_info.pop("updated_at", None)
            # K-APT 값이 있으면 기본정보를 K-APT로 override
            # (건축물대장은 주차/부속동까지 세어 dong_count 부풀려지는 등 정확도 낮음)
            kapt_overrides = {
                "total_hhld_cnt": kapt_info.get("ho_cnt"),
                "dong_count": kapt_info.get("dong_cnt"),
                "max_floor": kapt_info.get("top_floor"),
                "use_apr_day": kapt_info.get("use_date"),
            }
            for k, v in kapt_overrides.items():
                if v is not None:
                    basic[k] = v

        # 관리비 (최근 3개월 + 지역 평균)
        mgmt_cost = None
        cost_rows = conn.execute(
            "SELECT year_month, common_cost, individual_cost, repair_fund, total_cost, cost_per_unit, detail "
            "FROM apt_mgmt_cost WHERE pnu = %s ORDER BY year_month DESC LIMIT 6",
            [pnu],
        ).fetchall()
        if cost_rows:
            # 지역 평균 (같은 시군구, 같은 월)
            sgg = basic.get("sigungu_code", "")[:5]
            latest_ym = cost_rows[0]["year_month"]
            # 지역 median 계산 시 비정상 row 제외:
            #   - cost_per_unit = total_cost: 분모=1 등 fallback 오류
            #   - cost_per_unit < 10,000 또는 total_cost < 100,000: K-APT 엑셀 오입력
            #     (예: 총액 268원 같은 극저 단지가 median 을 끌어내림)
            avg_row = conn.execute("""
                SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY cost_per_unit) as median_per_unit
                FROM apt_mgmt_cost m
                JOIN apt_kapt_info k ON m.pnu = k.pnu
                JOIN apartments a ON m.pnu = a.pnu
                WHERE a.sigungu_code = %s AND m.year_month = %s
                  AND m.cost_per_unit >= 10000
                  AND m.total_cost >= 100000
                  AND m.cost_per_unit != m.total_cost
            """, [sgg, latest_ym]).fetchone()

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
                "region_avg_per_unit": round(avg_row["median_per_unit"]) if avg_row and avg_row["median_per_unit"] else None,
                "by_area": by_area,
                "cost_per_m2": cost_per_m2,
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
def apartment_trades(pnu: str):
    """Return trade and rent history for an apartment."""
    conn = DictConnection()
    try:
        mappings = conn.execute(
            "SELECT apt_seq, apt_nm, sgg_cd FROM trade_apt_mapping WHERE pnu = %s", [pnu]
        ).fetchall()

        trades = []
        rents = []

        if mappings:
            apt_seqs = [m["apt_seq"] for m in mappings]
            ph = ",".join(["%s"] * len(apt_seqs))
            trades = conn.execute(
                f"SELECT * FROM trade_history WHERE apt_seq IN ({ph}) ORDER BY deal_year DESC, deal_month DESC, deal_day DESC",
                apt_seqs,
            ).fetchall()
            rents = conn.execute(
                f"SELECT * FROM rent_history WHERE apt_seq IN ({ph}) ORDER BY deal_year DESC, deal_month DESC, deal_day DESC",
                apt_seqs,
            ).fetchall()
        else:
            apt = conn.execute(
                "SELECT bld_nm, sigungu_code FROM apartments WHERE pnu = %s", [pnu]
            ).fetchone()
            if apt and apt["bld_nm"]:
                name_pattern = f"%{apt['bld_nm']}%"
                sgg = apt["sigungu_code"][:5] if apt["sigungu_code"] else None
                if sgg:
                    trades = conn.execute(
                        "SELECT * FROM trade_history WHERE sgg_cd = %s AND apt_nm LIKE %s ORDER BY deal_year DESC, deal_month DESC, deal_day DESC",
                        [sgg, name_pattern],
                    ).fetchall()
                    rents = conn.execute(
                        "SELECT * FROM rent_history WHERE sgg_cd = %s AND apt_nm LIKE %s ORDER BY deal_year DESC, deal_month DESC, deal_day DESC",
                        [sgg, name_pattern],
                    ).fetchall()

        return {"trades": [dict(r) for r in trades], "rents": [dict(r) for r in rents]}
    finally:
        conn.close()
