"""apt_facility_summary + apt_safety_score 재계산 (BallTree)."""

import numpy as np
from batch.db import query_all, execute_values_chunked


def recalc_summary(conn, logger):
    """시설 변경 후 apt_facility_summary 및 apt_safety_score 재계산."""
    try:
        from sklearn.neighbors import BallTree
    except ImportError:
        logger.error("scikit-learn 미설치. pip install scikit-learn 필요.")
        return

    EARTH_RADIUS_M = 6_371_000
    RADII = {"1km": 1000, "3km": 3000, "5km": 5000}

    # 아파트 좌표 로드
    apts = query_all(conn, "SELECT pnu, lat, lng FROM apartments WHERE lat IS NOT NULL AND lng IS NOT NULL")
    if not apts:
        logger.info("아파트 데이터 없음")
        return

    apt_pnus = [a["pnu"] for a in apts]
    apt_coords = np.radians(np.array([[a["lat"], a["lng"]] for a in apts]))

    # 시설 subtype별로 처리 (활성 시설만)
    subtypes = query_all(conn, "SELECT DISTINCT facility_subtype FROM facilities WHERE is_active = TRUE")
    subtype_list = [r["facility_subtype"] for r in subtypes]

    logger.info(f"BallTree 재계산: {len(apt_pnus):,}개 아파트 x {len(subtype_list)}개 시설유형")

    all_summary_rows = []

    for subtype in subtype_list:
        facs = query_all(conn,
            "SELECT lat, lng FROM facilities WHERE facility_subtype = %s AND lat IS NOT NULL AND is_active = TRUE",
            [subtype])
        if not facs:
            continue

        fac_coords = np.radians(np.array([[f["lat"], f["lng"]] for f in facs]))
        tree = BallTree(fac_coords, metric="haversine")

        # 최근접 거리
        dists, _ = tree.query(apt_coords, k=1)
        nearest_m = dists[:, 0] * EARTH_RADIUS_M

        # 반경별 개수
        counts = {}
        for label, radius in RADII.items():
            cnt_list = tree.query_radius(apt_coords, r=radius / EARTH_RADIUS_M, count_only=True)
            counts[label] = cnt_list

        for i, pnu in enumerate(apt_pnus):
            all_summary_rows.append((
                pnu, subtype, round(float(nearest_m[i]), 1),
                int(counts["1km"][i]), int(counts["3km"][i]), int(counts["5km"][i])
            ))

        logger.info(f"  {subtype}: {len(facs):,}개 시설 처리 완료")

    # DB 갱신 (TRUNCATE + INSERT)
    cur = conn.cursor()
    cur.execute("TRUNCATE apt_facility_summary")
    execute_values_chunked(conn,
        "INSERT INTO apt_facility_summary (pnu, facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km) VALUES %s",
        all_summary_rows)

    logger.info(f"apt_facility_summary 재계산 완료: {len(all_summary_rows):,}건")

    # apt_safety_score 재계산 (CCTV 40% + 경찰서 30% + 소방서 30%)
    logger.info("apt_safety_score 재계산 중...")

    safety_rows = []
    # CCTV subtype 데이터
    cctv_facs = query_all(conn,
        "SELECT lat, lng FROM facilities WHERE facility_subtype = %s AND lat IS NOT NULL AND is_active = TRUE",
        ["cctv"])

    if cctv_facs:
        cctv_coords = np.radians(np.array([[f["lat"], f["lng"]] for f in cctv_facs]))
        cctv_tree = BallTree(cctv_coords, metric="haversine")
        cctv_dists, _ = cctv_tree.query(apt_coords, k=1)
        cctv_nearest = cctv_dists[:, 0] * EARTH_RADIUS_M
        cctv_500m = cctv_tree.query_radius(apt_coords, r=500 / EARTH_RADIUS_M, count_only=True)
        cctv_1km = cctv_tree.query_radius(apt_coords, r=1000 / EARTH_RADIUS_M, count_only=True)
    else:
        cctv_nearest = np.full(len(apt_pnus), np.inf)
        cctv_500m = np.zeros(len(apt_pnus), dtype=int)
        cctv_1km = np.zeros(len(apt_pnus), dtype=int)

    # 경찰서/소방서 거리 (summary에서 조회)
    summary_map: dict[str, dict[str, float]] = {}
    for row in all_summary_rows:
        pnu, subtype, dist = row[0], row[1], row[2]
        if subtype in ("police", "fire_station"):
            if pnu not in summary_map:
                summary_map[pnu] = {}
            summary_map[pnu][subtype] = dist

    for i, pnu in enumerate(apt_pnus):
        cctv_score = min(100.0, int(cctv_500m[i]) * 2)
        police_dist = summary_map.get(pnu, {}).get("police", 5000)
        fire_dist = summary_map.get(pnu, {}).get("fire_station", 5000)
        police_score = max(0, 100 - police_dist / 50)
        fire_score = max(0, 100 - fire_dist / 50)
        safety = round(cctv_score * 0.4 + police_score * 0.3 + fire_score * 0.3, 1)

        nearest = round(float(cctv_nearest[i]), 1) if cctv_nearest[i] < 100000 else None
        safety_rows.append((pnu, safety, int(cctv_500m[i]), int(cctv_1km[i]), nearest))

    cur.execute("TRUNCATE apt_safety_score")
    execute_values_chunked(conn,
        "INSERT INTO apt_safety_score (pnu, safety_score, cctv_count_500m, cctv_count_1km, nearest_cctv_m) VALUES %s",
        safety_rows)

    logger.info(f"apt_safety_score 재계산 완료: {len(safety_rows):,}건")
