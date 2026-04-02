"""유사 아파트 추천 API — 코사인 유사도 기반."""

import numpy as np
from fastapi import APIRouter, Query
from database import DictConnection

router = APIRouter()


@router.get("/apartment/{pnu}/similar")
def get_similar_apartments(
    pnu: str,
    top_n: int = Query(5, ge=1, le=20),
    exclude_same_sigungu: bool = Query(False, description="같은 시군구 제외"),
):
    """선택한 아파트와 유사한 아파트 Top N 반환."""
    conn = DictConnection()

    # 대상 아파트 벡터 조회
    target = conn.execute(
        "SELECT vector FROM apt_vectors WHERE pnu = %s", [pnu]
    ).fetchone()

    if not target:
        conn.close()
        return {"error": "해당 아파트의 벡터 데이터가 없습니다."}

    target_vec = np.array(target["vector"])

    # 대상 시군구 조회 (같은 시군구 제외 옵션용)
    target_sgg = ""
    if exclude_same_sigungu:
        apt = conn.execute("SELECT sigungu_code FROM apartments WHERE pnu = %s", [pnu]).fetchone()
        target_sgg = (apt["sigungu_code"] or "")[:5] if apt else ""

    # 전체 벡터 로드
    rows = conn.execute("""
        SELECT v.pnu, v.vector, a.bld_nm, a.sigungu_code, a.lat, a.lng,
               a.total_hhld_cnt, a.use_apr_day,
               p.price_per_m2
        FROM apt_vectors v
        JOIN apartments a ON v.pnu = a.pnu
        LEFT JOIN apt_price_score p ON v.pnu = p.pnu
        WHERE v.pnu != %s AND a.group_pnu = a.pnu
    """, [pnu]).fetchall()

    conn.close()

    # 코사인 유사도 계산
    candidates = []
    for r in rows:
        if exclude_same_sigungu and (r["sigungu_code"] or "")[:5] == target_sgg:
            continue

        vec = np.array(r["vector"])
        # 코사인 유사도
        dot = np.dot(target_vec, vec)
        norm = np.linalg.norm(target_vec) * np.linalg.norm(vec)
        similarity = float(dot / norm) if norm > 0 else 0

        candidates.append({
            "pnu": r["pnu"],
            "bld_nm": r["bld_nm"],
            "sigungu_code": (r["sigungu_code"] or "")[:5],
            "lat": r["lat"],
            "lng": r["lng"],
            "total_hhld_cnt": r["total_hhld_cnt"],
            "use_apr_day": r["use_apr_day"],
            "price_per_m2": round(float(r["price_per_m2"])) if r["price_per_m2"] else None,
            "similarity": round(similarity, 4),
        })

    # 유사도 상위 N개
    candidates.sort(key=lambda x: x["similarity"], reverse=True)
    results = candidates[:top_n]

    # 시군구 이름 매핑
    sgg_names = {}
    if results:
        conn2 = DictConnection()
        name_rows = conn2.execute(
            "SELECT code, name, extra FROM common_code WHERE group_id = %s", ["sigungu"]
        ).fetchall()
        conn2.close()
        for r in name_rows:
            sgg_names[r["code"]] = f"{r['name']}({r['extra']})" if r["extra"] and r["extra"] != r["name"] else r["name"]

    for r in results:
        r["sigungu_name"] = sgg_names.get(r["sigungu_code"], r["sigungu_code"])
        r["similarity_pct"] = round(r["similarity"] * 100, 1)

    return {"pnu": pnu, "similar": results}
