"""apt_facility_summary + apt_safety_score 재계산 (BallTree)."""

import numpy as np
from batch.db import query_all, execute_values_chunked


# 범죄 심각도 가중치 (살인 > 강도 > 성범죄 > 폭력 > 절도)
CRIME_WEIGHTS = {"murder": 10, "robbery": 5, "sexual_assault": 3, "violence": 2, "theft": 1}


def _load_crime_scores(conn):
    """시군구별 범죄 안전 점수 로드 (가중 범죄율 기반)."""
    rows = query_all(conn, "SELECT * FROM sigungu_crime_detail")
    if not rows:
        return {}

    # 가중 범죄 점수 계산
    weighted = {}
    for r in rows:
        w_crime = (
            (r.get("murder") or 0) * CRIME_WEIGHTS["murder"]
            + (r.get("robbery") or 0) * CRIME_WEIGHTS["robbery"]
            + (r.get("sexual_assault") or 0) * CRIME_WEIGHTS["sexual_assault"]
            + (r.get("violence") or 0) * CRIME_WEIGHTS["violence"]
            + (r.get("theft") or 0) * CRIME_WEIGHTS["theft"]
        )
        pop = r.get("effective_pop") or r.get("resident_pop") or 1
        weighted[r["sigungu_code"]] = w_crime / pop * 100000  # 10만명당 가중 범죄율

    if not weighted:
        return {}

    # 정규화: 0~100 (낮을수록 안전)
    max_rate = max(weighted.values())
    crime_scores = {}
    for sgg, rate in weighted.items():
        crime_scores[sgg] = round(max(0, 100 - (rate / max_rate * 100)), 1)

    return crime_scores


def _calc_safety_rows(apt_pnus, apt_sgg_codes, apt_coords, summary_rows_or_map, cctv_data, crime_scores):
    """안전 점수 계산 공통 로직.

    safety = 시설안전(60%) + 범죄안전(40%)
    시설안전 = CCTV(35%) + 가로등/보안등(15%) + 경찰서(25%) + 소방서(25%)
    (가로등/보안등 데이터 없으면 CCTV 50% + 경찰 25% + 소방 25%)
    """
    cctv_500m, cctv_1km, cctv_nearest = cctv_data

    # summary에서 경찰서/소방서/가로등/보안등 거리 조회
    SAFETY_SUBTYPES = ("police", "fire_station", "streetlight", "security_light")
    if isinstance(summary_rows_or_map, dict):
        summary_map = summary_rows_or_map
    else:
        summary_map: dict[str, dict[str, float]] = {}
        for row in summary_rows_or_map:
            pnu, subtype, dist = row[0], row[1], row[2]
            if subtype in SAFETY_SUBTYPES:
                if pnu not in summary_map:
                    summary_map[pnu] = {}
                summary_map[pnu][subtype] = dist

    # 가로등/보안등 데이터 존재 여부
    has_lights = any(
        summary_map.get(pnu, {}).get("streetlight") is not None
        or summary_map.get(pnu, {}).get("security_light") is not None
        for pnu in apt_pnus[:100]  # 샘플 체크
    )

    safety_rows = []
    for i, pnu in enumerate(apt_pnus):
        # 시설 안전 (60%)
        cctv_score = min(100.0, int(cctv_500m[i]) * 2)
        police_dist = summary_map.get(pnu, {}).get("police", 5000)
        fire_dist = summary_map.get(pnu, {}).get("fire_station", 5000)
        police_score = max(0, 100 - police_dist / 50)
        fire_score = max(0, 100 - fire_dist / 50)

        if has_lights:
            # 가로등/보안등 중 가까운 쪽 사용
            sl_dist = summary_map.get(pnu, {}).get("streetlight", 5000)
            scl_dist = summary_map.get(pnu, {}).get("security_light", 5000)
            light_dist = min(sl_dist, scl_dist)
            light_score = max(0, 100 - light_dist / 10)  # 1km=0점
            infra_score = cctv_score * 0.35 + light_score * 0.15 + police_score * 0.25 + fire_score * 0.25
        else:
            infra_score = cctv_score * 0.5 + police_score * 0.25 + fire_score * 0.25

        # 범죄 안전 (40%)
        sgg = apt_sgg_codes[i] if i < len(apt_sgg_codes) else ""
        crime_score = crime_scores.get(sgg, 50.0)  # 데이터 없으면 중간값

        # 종합 안전 점수
        safety = round(infra_score * 0.6 + crime_score * 0.4, 1)

        nearest = round(float(cctv_nearest[i]), 1) if cctv_nearest[i] < 100000 else None
        safety_rows.append((pnu, safety, int(cctv_500m[i]), int(cctv_1km[i]), nearest, crime_score))

    return safety_rows


def _build_cctv_data(conn, apt_coords, apt_count):
    """CCTV BallTree 데이터 구축."""
    from sklearn.neighbors import BallTree
    EARTH_RADIUS_M = 6_371_000

    cctv_facs = query_all(conn,
        "SELECT lat, lng FROM facilities WHERE facility_subtype = 'cctv' AND lat IS NOT NULL AND is_active = TRUE")

    if cctv_facs:
        cctv_coords = np.radians(np.array([[f["lat"], f["lng"]] for f in cctv_facs]))
        cctv_tree = BallTree(cctv_coords, metric="haversine")
        cctv_dists, _ = cctv_tree.query(apt_coords, k=1)
        cctv_nearest = cctv_dists[:, 0] * EARTH_RADIUS_M
        cctv_500m = cctv_tree.query_radius(apt_coords, r=500 / EARTH_RADIUS_M, count_only=True)
        cctv_1km = cctv_tree.query_radius(apt_coords, r=1000 / EARTH_RADIUS_M, count_only=True)
    else:
        cctv_nearest = np.full(apt_count, np.inf)
        cctv_500m = np.zeros(apt_count, dtype=int)
        cctv_1km = np.zeros(apt_count, dtype=int)

    return cctv_500m, cctv_1km, cctv_nearest


def recalc_for_new_apartments(conn, logger, pnu_list):
    """신규 아파트만 대상으로 시설 집계 + 안전점수 계산."""
    if not pnu_list:
        return

    try:
        from sklearn.neighbors import BallTree
    except ImportError:
        logger.error("scikit-learn 미설치, 시설 집계 생략")
        return

    EARTH_RADIUS_M = 6_371_000
    RADII = {"1km": 1000, "3km": 3000, "5km": 5000}

    # 대상 아파트 좌표
    ph = ",".join(["%s"] * len(pnu_list))
    apts = query_all(conn,
        f"SELECT pnu, lat, lng, sigungu_code FROM apartments WHERE pnu IN ({ph}) AND lat IS NOT NULL AND lng IS NOT NULL",
        pnu_list)
    if not apts:
        return

    apt_pnus = [a["pnu"] for a in apts]
    apt_sgg_codes = [a.get("sigungu_code", "")[:5] for a in apts]
    apt_coords = np.radians(np.array([[a["lat"], a["lng"]] for a in apts]))

    logger.info(f"  신규 아파트 시설 집계: {len(apt_pnus)}건")

    # 시설 subtype별 BallTree
    subtypes = query_all(conn, "SELECT DISTINCT facility_subtype FROM facilities WHERE is_active = TRUE")
    summary_rows = []

    for st in subtypes:
        subtype = st["facility_subtype"]
        facs = query_all(conn,
            "SELECT lat, lng FROM facilities WHERE facility_subtype = %s AND lat IS NOT NULL AND is_active = TRUE",
            [subtype])
        if not facs:
            continue

        fac_coords = np.radians(np.array([[f["lat"], f["lng"]] for f in facs]))
        tree = BallTree(fac_coords, metric="haversine")

        dists, _ = tree.query(apt_coords, k=1)
        nearest_m = dists[:, 0] * EARTH_RADIUS_M

        counts = {}
        for label, radius in RADII.items():
            counts[label] = tree.query_radius(apt_coords, r=radius / EARTH_RADIUS_M, count_only=True)

        for i, pnu in enumerate(apt_pnus):
            summary_rows.append((
                pnu, subtype, round(float(nearest_m[i]), 1),
                int(counts["1km"][i]), int(counts["3km"][i]), int(counts["5km"][i])
            ))

    # 기존 데이터 삭제 후 INSERT
    cur = conn.cursor()
    cur.execute(f"DELETE FROM apt_facility_summary WHERE pnu IN ({ph})", pnu_list)
    if summary_rows:
        execute_values_chunked(conn,
            "INSERT INTO apt_facility_summary (pnu, facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km) VALUES %s",
            summary_rows)

    # 안전점수 계산 (범죄 데이터 통합)
    cctv_data = _build_cctv_data(conn, apt_coords, len(apt_pnus))
    crime_scores = _load_crime_scores(conn)
    safety_rows = _calc_safety_rows(apt_pnus, apt_sgg_codes, apt_coords, summary_rows, cctv_data, crime_scores)

    cur.execute(f"DELETE FROM apt_safety_score WHERE pnu IN ({ph})", pnu_list)
    if safety_rows:
        execute_values_chunked(conn,
            "INSERT INTO apt_safety_score (pnu, safety_score, cctv_count_500m, cctv_count_1km, nearest_cctv_m, crime_safety_score) VALUES %s",
            safety_rows)

    conn.commit()
    logger.info(f"  신규 아파트 시설 집계 완료: summary={len(summary_rows)}, safety={len(safety_rows)}")


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
    apts = query_all(conn, "SELECT pnu, lat, lng, sigungu_code FROM apartments WHERE lat IS NOT NULL AND lng IS NOT NULL")
    if not apts:
        logger.info("아파트 데이터 없음")
        return

    apt_pnus = [a["pnu"] for a in apts]
    apt_sgg_codes = [a.get("sigungu_code", "")[:5] for a in apts]
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

    # apt_safety_score 재계산 (시설안전 60% + 범죄안전 40%)
    logger.info("apt_safety_score 재계산 중...")

    cctv_data = _build_cctv_data(conn, apt_coords, len(apt_pnus))
    crime_scores = _load_crime_scores(conn)
    safety_rows = _calc_safety_rows(apt_pnus, apt_sgg_codes, apt_coords, all_summary_rows, cctv_data, crime_scores)

    cur.execute("TRUNCATE apt_safety_score")
    execute_values_chunked(conn,
        "INSERT INTO apt_safety_score (pnu, safety_score, cctv_count_500m, cctv_count_1km, nearest_cctv_m, crime_safety_score) VALUES %s",
        safety_rows)

    logger.info(f"apt_safety_score 재계산 완료: {len(safety_rows):,}건")
