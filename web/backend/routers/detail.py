"""Apartment detail + trade history API."""

from fastapi import APIRouter, HTTPException
from database import DictConnection
from services.scoring import (
    NUDGE_WEIGHTS,
    distance_to_score,
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
            row["facility_subtype"]: distance_to_score(
                row["nearest_distance_m"], row["facility_subtype"]
            )
            for row in summary_rows
        }

        # Price/safety scores
        price_row = conn.execute(
            "SELECT price_score, jeonse_ratio FROM apt_price_score WHERE pnu = %s", [pnu]
        ).fetchone()
        if price_row:
            facility_scores["_price"] = price_row["price_score"] or 50.0
            facility_scores["_jeonse"] = price_row["jeonse_ratio"] or 50.0

        safety_row = None
        try:
            safety_row = conn.execute(
                "SELECT safety_score FROM apt_safety_score WHERE pnu = %s", [pnu]
            ).fetchone()
        except Exception:
            pass
        if safety_row:
            facility_scores["_safety"] = safety_row["safety_score"] or 50.0

        scores = {
            nid: calculate_nudge_score(facility_scores, nid)
            for nid in NUDGE_WEIGHTS
        }

        # Nearby facilities
        nearby_rows = conn.execute(
            """
            SELECT m.facility_type, m.facility_subtype, m.distance_m,
                   f.name, f.lat, f.lng
            FROM apt_facility_mapping m
            JOIN facilities f ON m.facility_id = f.facility_id
            WHERE m.pnu = %s AND m.distance_m <= 2000
            ORDER BY m.facility_type, m.distance_m
            """,
            [pnu],
        ).fetchall()

        nearby: dict[str, list] = {}
        for row in nearby_rows:
            ft = row["facility_type"]
            if ft not in nearby:
                nearby[ft] = []
            if len(nearby[ft]) < 3:
                nearby[ft].append(
                    {
                        "subtype": row["facility_subtype"],
                        "name": row["name"],
                        "distance_m": row["distance_m"],
                        "lat": row["lat"],
                        "lng": row["lng"],
                    }
                )

        # School zone
        school = conn.execute(
            "SELECT * FROM school_zones WHERE pnu = %s", [pnu]
        ).fetchone()
        if school:
            school = dict(school)

        # CCTV/safety info
        safety_info = None
        try:
            cctv_row = conn.execute(
                "SELECT nearest_distance_m, cctv_count_500m, cctv_count_1km FROM apt_cctv_summary WHERE pnu = %s", [pnu]
            ).fetchone()
            safety_score_val = safety_row["safety_score"] if safety_row else None
            if cctv_row:
                safety_info = {
                    "safety_score": safety_score_val,
                    "cctv_nearest_m": cctv_row["nearest_distance_m"],
                    "cctv_count_500m": cctv_row["cctv_count_500m"],
                    "cctv_count_1km": cctv_row["cctv_count_1km"],
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

        return {
            "basic": basic,
            "scores": scores,
            "facility_summary": facility_summary,
            "nearby_facilities": nearby,
            "school": school,
            "safety": safety_info,
            "population": population,
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
