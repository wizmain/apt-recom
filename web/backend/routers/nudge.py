"""Nudge scoring API."""

from fastapi import APIRouter
from pydantic import BaseModel
from database import DictConnection
from services.scoring import (
    NUDGE_WEIGHTS,
    distance_to_score,
    calculate_nudge_score,
    calculate_multi_nudge_score,
)

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


@router.post("/nudge/score")
def nudge_score(req: NudgeScoreRequest):
    """Calculate nudge scores for apartments and return top_n."""
    conn = DictConnection()
    try:
        # 1. Get apartments (keyword and/or bounds filter)
        apt_sql = "SELECT pnu, bld_nm, lat, lng, total_hhld_cnt, new_plat_plc, sigungu_code FROM apartments"
        conditions: list[str] = []
        params: list = []

        if req.keyword and req.keyword.strip():
            import re
            kw = req.keyword.strip()
            pattern = f"%{kw}%"
            norm_kw = re.sub(r'[\s()\-·]', '', kw)
            norm_pattern = f"%{norm_kw}%"
            conditions.append("(new_plat_plc LIKE %s OR plat_plc LIKE %s OR bld_nm LIKE %s OR bld_nm_norm LIKE %s)")
            params.extend([pattern, pattern, pattern, norm_pattern])

        if all(v is not None for v in [req.sw_lat, req.sw_lng, req.ne_lat, req.ne_lng]):
            conditions.append("lat BETWEEN %s AND %s AND lng BETWEEN %s AND %s")
            params.extend([req.sw_lat, req.ne_lat, req.sw_lng, req.ne_lng])

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
            subtypes = ws if ws else NUDGE_WEIGHTS.get(nid, {})
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
                f"SELECT pnu, facility_subtype, nearest_distance_m "
                f"FROM apt_facility_summary "
                f"WHERE pnu IN ({ph_pnu}) AND facility_subtype IN ({ph_sub})"
            )
            summary_rows.extend(conn.execute(sql, chunk + list(all_subtypes)).fetchall())

        # 4. Build per-apartment facility scores
        apt_facility_scores: dict[str, dict[str, float]] = {}
        for row in summary_rows:
            pnu = row["pnu"]
            if pnu not in apt_facility_scores:
                apt_facility_scores[pnu] = {}
            apt_facility_scores[pnu][row["facility_subtype"]] = distance_to_score(
                row["nearest_distance_m"], row["facility_subtype"]
            )

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
                    apt_facility_scores[pnu]["_price"] = row["price_score"] or 50.0
                    apt_facility_scores[pnu]["_jeonse"] = row["jeonse_ratio"] or 50.0

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
                        apt_facility_scores[pnu]["_safety"] = row["safety_score"] or 50.0
                except Exception:
                    pass

        # 4d. Crime scores (시군구별 범죄율 기반)
        crime_nudges = {"safety"}
        if crime_nudges & set(req.nudges):
            try:
                # 시군구코드 → 범죄안전점수 로드
                sgg_codes = list(set(apt_map[p].get("sigungu_code", "")[:5] for p in pnu_list if apt_map[p].get("sigungu_code")))
                if sgg_codes:
                    ph = ",".join(["%s"] * len(sgg_codes))
                    crime_rows = conn.execute(
                        f"SELECT sigungu_code, crime_safety_score FROM sigungu_crime_score WHERE sigungu_code IN ({ph})",
                        sgg_codes,
                    ).fetchall()
                    sgg_crime = {r["sigungu_code"]: r["crime_safety_score"] for r in crime_rows}
                    for pnu in pnu_list:
                        sgg = (apt_map[pnu].get("sigungu_code") or "")[:5]
                        if sgg in sgg_crime:
                            if pnu not in apt_facility_scores:
                                apt_facility_scores[pnu] = {}
                            apt_facility_scores[pnu]["_crime"] = sgg_crime[sgg]
            except Exception:
                pass

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
            else:
                score = 0.0
                breakdown = {}

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
                }
            )

        # 6. Sort and return top_n
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[: req.top_n]
    finally:
        conn.close()


@router.get("/nudge/weights")
def get_nudge_weights():
    """Return the nudge weight configuration."""
    return NUDGE_WEIGHTS
