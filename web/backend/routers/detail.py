"""Apartment detail + trade history API."""

from fastapi import APIRouter, HTTPException
from database import DictConnection
from services.scoring import (
    get_nudge_weights,
    facility_score,
    calculate_nudge_score,
)

router = APIRouter()


@router.get("/apartment/{pnu}")
def apartment_detail(pnu: str):
    """Return full detail for one apartment: basic info, scores, facilities, school."""
    conn = DictConnection()
    try:
        basic = conn.execute("SELECT * FROM apartments WHERE pnu = %s", [pnu]).fetchone()
        if not basic:
            raise HTTPException(status_code=404, detail="Apartment not found")
        basic = dict(basic)

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

        facility_scores = {
            row["facility_subtype"]: facility_score(
                row["nearest_distance_m"], row["count_1km"], row["facility_subtype"]
            )
            for row in summary_rows
        }

        # Price/safety scores
        price_row = conn.execute(
            "SELECT price_score, jeonse_ratio FROM apt_price_score WHERE pnu = %s", [pnu]
        ).fetchone()
        if price_row:
            facility_scores["score_price"] = price_row["price_score"] or 50.0
            facility_scores["score_jeonse"] = price_row["jeonse_ratio"] or 50.0

        safety_row = None
        try:
            safety_row = conn.execute(
                "SELECT safety_score, micro_score, access_score, macro_score, "
                "complex_score, data_reliability "
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

            # CCTV: apt_safety_score (500m) + apt_facility_summary (거리, 1km)
            cctv_fs = facility_summary.get("cctv", {})
            cctv_nearest = cctv_fs.get("nearest_distance_m")
            cctv_1km = cctv_fs.get("count_1km", 0)
            cctv_500m = 0
            if safety_row:
                ss_row = conn.execute(
                    "SELECT cctv_count_500m, cctv_count_1km, nearest_cctv_m FROM apt_safety_score WHERE pnu = %s", [pnu]
                ).fetchone()
                if ss_row:
                    cctv_500m = ss_row["cctv_count_500m"] or 0
                    if cctv_nearest is None:
                        cctv_nearest = ss_row["nearest_cctv_m"]
                    if cctv_1km == 0 and ss_row["cctv_count_1km"]:
                        cctv_1km = ss_row["cctv_count_1km"]

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

            # 보안등/소방센터/병원 거리
            light_dist = facility_summary.get("security_light", {}).get("nearest_distance_m")
            light_500m = facility_summary.get("security_light", {}).get("count_1km", 0)
            fire_center_dist = facility_summary.get("fire_center", {}).get("nearest_distance_m")
            hospital_dist = facility_summary.get("hospital", {}).get("nearest_distance_m")

            # v2 세부 점수
            v2_scores = None
            if safety_row and safety_row.get("micro_score") is not None:
                v2_scores = {
                    "micro_score": safety_row["micro_score"],
                    "access_score": safety_row["access_score"],
                    "macro_score": safety_row["macro_score"],
                    "complex_score": safety_row["complex_score"],
                    "data_reliability": safety_row["data_reliability"],
                }

            safety_info = {
                "safety_score": safety_score_val,
                "crime_safety_score": crime_score,
                "crime_detail": crime_detail,
                "cctv_nearest_m": cctv_nearest,
                "cctv_count_500m": cctv_500m,
                "cctv_count_1km": cctv_1km,
                "police_nearest_m": police_dist,
                "police_count_3km": facility_summary.get("police", {}).get("count_3km", 0),
                "fire_nearest_m": fire_dist,
                "fire_count_3km": facility_summary.get("fire_station", {}).get("count_3km", 0),
                "light_nearest_m": light_dist,
                "light_count_1km": light_500m,
                "fire_center_nearest_m": fire_center_dist,
                "hospital_nearest_m": hospital_dist,
                "nudge_safety_score": scores.get("safety", 0),
                "v2": v2_scores,
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
            avg_row = conn.execute("""
                SELECT AVG(cost_per_unit) as avg_per_unit, AVG(total_cost) as avg_total
                FROM apt_mgmt_cost m
                JOIN apt_kapt_info k ON m.pnu = k.pnu
                JOIN apartments a ON m.pnu = a.pnu
                WHERE a.sigungu_code = %s AND m.year_month = %s AND m.cost_per_unit > 0
            """, [sgg, latest_ym]).fetchone()

            mgmt_cost = {
                "months": [dict(r) for r in cost_rows],
                "region_avg_per_unit": round(avg_row["avg_per_unit"]) if avg_row and avg_row["avg_per_unit"] else None,
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
