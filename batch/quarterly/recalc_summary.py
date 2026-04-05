"""apt_facility_summary + apt_safety_score v2 재계산 (BallTree).

v2 점수 구조:
    최종안전점수 = 미시환경(55%) + 접근성(20%) + 광역위험(15%) + 단지내부(10%)
"""

import numpy as np
from batch.db import query_all, execute_values_chunked

EARTH_RADIUS_M = 6_371_000

# 범죄 심각도 가중치 (살인 > 강도 > 성범죄 > 폭력 > 절도)
CRIME_WEIGHTS = {"murder": 10, "robbery": 5, "sexual_assault": 3, "violence": 2, "theft": 1}


def _percentile_rank(values):
    """배열 내 각 값의 percentile rank (0~1)."""
    if len(values) == 0:
        return np.array([])
    sorted_vals = np.sort(values)
    ranks = np.searchsorted(sorted_vals, values, side="right") / len(values)
    return ranks


def _distance_decay_score(dist_m, max_score, half_dist=2000):
    """거리 기반 하이퍼볼릭 감쇄 점수. half_dist에서 정확히 max_score/2."""
    if dist_m is None or dist_m <= 0:
        return float(max_score)
    return max(0.0, float(max_score) * half_dist / (dist_m + half_dist))


def _build_balltree(conn, subtype):
    """시설 subtype용 BallTree 구축. 없으면 None 반환."""
    from sklearn.neighbors import BallTree
    facs = query_all(conn,
        "SELECT lat, lng FROM facilities WHERE facility_subtype = %s AND lat IS NOT NULL AND is_active = TRUE",
        [subtype])
    if not facs:
        return None, 0
    coords = np.radians(np.array([[f["lat"], f["lng"]] for f in facs]))
    return BallTree(coords, metric="haversine"), len(facs)


def _query_nearest_and_counts(tree, apt_coords, radii_m=None):
    """BallTree에서 최근접 거리(m) + 반경별 개수 조회."""
    if tree is None:
        n = len(apt_coords)
        nearest = np.full(n, np.inf)
        counts = {r: np.zeros(n, dtype=int) for r in (radii_m or [])}
        return nearest, counts

    dists, _ = tree.query(apt_coords, k=1)
    nearest = dists[:, 0] * EARTH_RADIUS_M
    counts = {}
    for r in (radii_m or []):
        counts[r] = tree.query_radius(apt_coords, r=r / EARTH_RADIUS_M, count_only=True)
    return nearest, counts


def _load_crime_scores(conn):
    """시군구별 범죄 안전 점수 로드."""
    rows = query_all(conn, "SELECT sigungu_code, crime_safety_score FROM sigungu_crime_detail")
    return {r["sigungu_code"]: r["crime_safety_score"] or 50.0 for r in rows}


def _load_traffic_accident_rates(conn):
    """시군구별 교통사고율 점수 (다발지역 건수 기반)."""
    rows = query_all(conn,
        "SELECT sigungu_name, SUM(accident_cnt) as total_acc, SUM(death_cnt) as total_death "
        "FROM traffic_accident_hotspot GROUP BY sigungu_name")
    if not rows:
        return {}

    # 시군구명 → 코드 매핑 (population_by_district 활용)
    pop_rows = query_all(conn,
        "SELECT sigungu_code, sigungu_name, sido_name, total_pop "
        "FROM population_by_district WHERE age_group = '계'")
    name_to_code = {}
    code_to_pop = {}
    for r in pop_rows:
        full_name = f"{r['sido_name']} {r['sigungu_name']}"
        name_to_code[full_name] = r["sigungu_code"]
        # 짧은 이름도 매핑 (교통사고 데이터가 "서울 강남구" 형식)
        short_sido = r["sido_name"].replace("특별시", "").replace("광역시", "").replace("특별자치시", "").replace("도", "")[:2]
        name_to_code[f"{short_sido} {r['sigungu_name']}"] = r["sigungu_code"]
        code_to_pop[r["sigungu_code"]] = r["total_pop"] or 100000

    # 사고율 계산 (인구 10만명당)
    acc_rates = {}
    for r in rows:
        sgg_name = r["sigungu_name"]
        code = name_to_code.get(sgg_name)
        if code:
            pop = code_to_pop.get(code, 100000)
            acc_rates[code] = float(r["total_acc"]) / pop * 100000

    if not acc_rates:
        return {}

    # percentile rank → 0~100 점수 (낮은 사고율 = 높은 점수)
    codes = list(acc_rates.keys())
    rates = np.array([acc_rates[c] for c in codes])
    pct = _percentile_rank(rates)
    return {codes[i]: round(float(100 - pct[i] * 100), 1) for i in range(len(codes))}


def _load_kapt_data(conn):
    """K-APT 단지 정보 로드 (CCTV, 경비, 관리)."""
    rows = query_all(conn,
        "SELECT pnu, cctv_cnt, mgr_type FROM apt_kapt_info WHERE pnu IS NOT NULL")
    kapt_map = {}
    for r in rows:
        kapt_map[r["pnu"]] = {
            "cctv_cnt": r.get("cctv_cnt") or 0,
            "mgr_type": r.get("mgr_type") or "",
        }
    return kapt_map


def _load_kapt_security_cost(conn):
    """K-APT 경비비 (최신 월) 로드."""
    rows = query_all(conn, """
        SELECT DISTINCT ON (pnu) pnu, detail
        FROM apt_mgmt_cost
        WHERE detail IS NOT NULL
        ORDER BY pnu, year_month DESC
    """)
    cost_map = {}
    for r in rows:
        detail = r.get("detail") or {}
        # detail JSONB에서 경비비 추출
        security_cost = detail.get("경비비") or detail.get("security") or 0
        cost_map[r["pnu"]] = int(security_cost) if security_cost else 0
    return cost_map


def _load_apt_hhld(conn):
    """아파트 세대수 로드."""
    rows = query_all(conn,
        "SELECT pnu, total_hhld_cnt FROM apartments WHERE total_hhld_cnt IS NOT NULL AND total_hhld_cnt > 0")
    return {r["pnu"]: r["total_hhld_cnt"] for r in rows}


def _calc_safety_v2(apt_pnus, apt_sgg_codes, apt_coords, summary_map,
                     cctv_data, light_data, accident_data,
                     crime_scores, accident_scores, kapt_map, security_costs, hhld_map,
                     fire_data, hospital_data):
    """v2 안전점수 계산: 4영역 + 데이터 신뢰도.

    반환: [(pnu, safety_score, cctv_500m, cctv_1km, nearest_cctv_m, crime_safety_score,
            micro_score, access_score, macro_score, complex_score, data_reliability), ...]
    """
    cctv_500m, cctv_1km, cctv_nearest = cctv_data
    light_500m, light_nearest = light_data
    acc_500m, acc_nearest = accident_data
    fire_nearest = fire_data
    hospital_nearest = hospital_data
    n = len(apt_pnus)

    # -- percentile rank 사전 계산 (전체 아파트 기준) --
    cctv_500m_pct = _percentile_rank(cctv_500m.astype(float))
    light_500m_pct = _percentile_rank(light_500m.astype(float))
    # 교통사고: 높을수록 위험 → 역순
    acc_500m_pct = _percentile_rank(acc_500m.astype(float))

    # K-APT CCTV 비율 percentile
    kapt_cctv_ratios = np.zeros(n)
    for i, pnu in enumerate(apt_pnus):
        kapt = kapt_map.get(pnu)
        hhld = hhld_map.get(pnu, 0)
        if kapt and hhld > 0:
            kapt_cctv_ratios[i] = kapt["cctv_cnt"] / hhld
    kapt_cctv_pct = _percentile_rank(kapt_cctv_ratios)

    # 경비비/세대 percentile
    security_ratios = np.zeros(n)
    for i, pnu in enumerate(apt_pnus):
        cost = security_costs.get(pnu, 0)
        hhld = hhld_map.get(pnu, 0)
        if cost > 0 and hhld > 0:
            security_ratios[i] = cost / hhld
    security_pct = _percentile_rank(security_ratios)

    safety_rows = []
    for i, pnu in enumerate(apt_pnus):
        sgg = apt_sgg_codes[i] if i < len(apt_sgg_codes) else ""

        # ===== 1. 미시환경점수 (55점) =====
        # CCTV 밀도: 12점
        cctv_score = cctv_500m_pct[i] * 12
        # 야간조명 (보안등): 10점
        light_score = light_500m_pct[i] * 10
        # 교통안전: 13점 (사고 적을수록 높은 점수)
        traffic_score = (1 - acc_500m_pct[i]) * 13
        # 범죄주의구간: 20점 (추후) → 현재 비율 재조정
        # 현재 가용: CCTV 12 + 보안등 10 + 교통 13 = 35점 → 55점 만점으로 스케일
        micro_raw = cctv_score + light_score + traffic_score  # 0~35
        micro_score = micro_raw / 35 * 55

        # ===== 2. 접근성점수 (20점) =====
        police_dist = summary_map.get(pnu, {}).get("police", 10000)
        fire_dist = float(fire_nearest[i]) if fire_nearest[i] < 100000 else 10000
        hosp_dist = float(hospital_nearest[i]) if hospital_nearest[i] < 100000 else 10000

        police_s = _distance_decay_score(police_dist, 6, half_dist=3000)
        fire_s = _distance_decay_score(fire_dist, 7, half_dist=3000)
        hosp_s = _distance_decay_score(hosp_dist, 7, half_dist=5000)
        access_score = police_s + fire_s + hosp_s

        # ===== 3. 광역위험점수 (15점) =====
        crime_s = crime_scores.get(sgg, 50.0) / 100 * 6  # 0~6점
        acc_s = accident_scores.get(sgg, 50.0) / 100 * 4  # 0~4점
        # 자연재해(3) + 안전지수(2) = 추후 → 현재 10점 만점 → 15점 스케일
        macro_raw = crime_s + acc_s  # 0~10
        macro_score = macro_raw / 10 * 15

        # ===== 4. 단지내부점수 (10점) =====
        kapt = kapt_map.get(pnu)
        if kapt:
            cctv_complex = kapt_cctv_pct[i] * 4
            security_complex = security_pct[i] * 3
            mgr = kapt.get("mgr_type", "")
            mgr_score = 3.0 if "위탁" in mgr else (2.0 if "자치" in mgr else 1.0)
            complex_score = cctv_complex + security_complex + mgr_score
        else:
            complex_score = 5.0  # 데이터 없으면 중간값

        # ===== 종합 =====
        safety_total = round(micro_score + access_score + macro_score + complex_score, 1)

        # ===== 데이터 신뢰도 =====
        reliability = _calc_reliability(pnu, sgg, kapt_map, crime_scores, light_500m[i])

        # 기존 호환 필드
        crime_safety = crime_scores.get(sgg, 50.0)
        nearest_cctv = round(float(cctv_nearest[i]), 1) if cctv_nearest[i] < 100000 else None

        safety_rows.append((
            pnu, float(safety_total), int(cctv_500m[i]), int(cctv_1km[i]),
            float(nearest_cctv) if nearest_cctv is not None else None,
            float(crime_safety),
            round(float(micro_score), 1), round(float(access_score), 1),
            round(float(macro_score), 1), round(float(complex_score), 1),
            round(float(reliability), 1),
        ))

    return safety_rows


def _calc_reliability(pnu, sgg, kapt_map, crime_scores, light_count):
    """데이터 신뢰도 점수 (0~100).

    최신성 35 + 완전성 25 + 좌표정확도 20 + 커버리지 20
    """
    score = 0.0

    # 최신성 (35점): 현재 사용 데이터 모두 2024년 기준 → 기본 30점
    score += 30.0

    # 완전성 (25점): K-APT + 범죄 + 보안등 데이터 존재 여부
    completeness = 0.0
    if pnu in kapt_map:
        completeness += 10.0
    if sgg in crime_scores:
        completeness += 10.0
    if light_count > 0:
        completeness += 5.0
    score += completeness

    # 좌표정확도 (20점): 시설 좌표 기반 → 기본 15점 (좌표 검증 미실시)
    score += 15.0

    # 커버리지 (20점): 수도권 데이터 풍부 → 시도별 차등
    sido = sgg[:2] if sgg else ""
    if sido in ("11", "28", "41"):  # 서울/인천/경기
        score += 18.0
    elif sido in ("26", "27", "29", "30"):  # 부산/대구/광주/대전
        score += 14.0
    else:
        score += 10.0

    return min(100.0, score)


def _build_cctv_data(conn, apt_coords, apt_count):
    """CCTV BallTree 데이터 구축."""
    tree, cnt = _build_balltree(conn, "cctv")
    if tree:
        nearest, counts = _query_nearest_and_counts(tree, apt_coords, [500, 1000])
        return counts[500], counts[1000], nearest
    return np.zeros(apt_count, dtype=int), np.zeros(apt_count, dtype=int), np.full(apt_count, np.inf)


def _build_light_data(conn, apt_coords, apt_count):
    """보안등 BallTree 데이터 구축."""
    tree, cnt = _build_balltree(conn, "security_light")
    if tree:
        nearest, counts = _query_nearest_and_counts(tree, apt_coords, [500])
        return counts[500], nearest
    return np.zeros(apt_count, dtype=int), np.full(apt_count, np.inf)


def _build_accident_data(conn, apt_coords, apt_count):
    """교통사고 다발지역 BallTree 구축."""
    from sklearn.neighbors import BallTree
    rows = query_all(conn,
        "SELECT lat, lng FROM traffic_accident_hotspot WHERE lat IS NOT NULL AND lng IS NOT NULL")
    if rows:
        coords = np.radians(np.array([[r["lat"], r["lng"]] for r in rows]))
        tree = BallTree(coords, metric="haversine")
        nearest, _ = _query_nearest_and_counts(tree, apt_coords, [])
        counts_500m = tree.query_radius(apt_coords, r=500 / EARTH_RADIUS_M, count_only=True)
        return counts_500m, nearest
    return np.zeros(apt_count, dtype=int), np.full(apt_count, np.inf)


def _build_facility_nearest(conn, apt_coords, apt_count, subtype):
    """시설 subtype별 최근접 거리."""
    tree, cnt = _build_balltree(conn, subtype)
    if tree:
        nearest, _ = _query_nearest_and_counts(tree, apt_coords, [])
        return nearest
    return np.full(apt_count, np.inf)


def _load_all_v2_data(conn, apt_pnus, apt_sgg_codes, apt_coords, apt_count, summary_map, logger):
    """v2 점수 계산에 필요한 모든 데이터를 로드."""
    logger.info("  v2 데이터 로드: CCTV, 보안등, 교통사고, 소방, 병원, 범죄, K-APT...")

    cctv_data = _build_cctv_data(conn, apt_coords, apt_count)
    light_data = _build_light_data(conn, apt_coords, apt_count)
    accident_data = _build_accident_data(conn, apt_coords, apt_count)
    fire_nearest = _build_facility_nearest(conn, apt_coords, apt_count, "fire_station")
    # fire_center도 고려: 둘 중 가까운 쪽
    fire_center_nearest = _build_facility_nearest(conn, apt_coords, apt_count, "fire_center")
    fire_combined = np.minimum(fire_nearest, fire_center_nearest)
    hospital_nearest = _build_facility_nearest(conn, apt_coords, apt_count, "hospital")

    crime_scores = _load_crime_scores(conn)
    accident_scores = _load_traffic_accident_rates(conn)
    kapt_map = _load_kapt_data(conn)
    security_costs = _load_kapt_security_cost(conn)
    hhld_map = _load_apt_hhld(conn)

    return {
        "cctv_data": cctv_data,
        "light_data": light_data,
        "accident_data": accident_data,
        "fire_data": fire_combined,
        "hospital_data": hospital_nearest,
        "crime_scores": crime_scores,
        "accident_scores": accident_scores,
        "kapt_map": kapt_map,
        "security_costs": security_costs,
        "hhld_map": hhld_map,
    }


def recalc_for_new_apartments(conn, logger, pnu_list):
    """신규 아파트만 대상으로 시설 집계 + 안전점수 v2 계산."""
    if not pnu_list:
        return

    try:
        from sklearn.neighbors import BallTree
    except ImportError:
        logger.error("scikit-learn 미설치, 시설 집계 생략")
        return

    RADII = {"1km": 1000, "3km": 3000, "5km": 5000}

    ph = ",".join(["%s"] * len(pnu_list))
    apts = query_all(conn,
        f"SELECT pnu, lat, lng, sigungu_code FROM apartments WHERE pnu IN ({ph}) AND lat IS NOT NULL AND lng IS NOT NULL",
        pnu_list)
    if not apts:
        return

    apt_pnus = [a["pnu"] for a in apts]
    apt_sgg_codes = [a.get("sigungu_code", "")[:5] for a in apts]
    apt_coords = np.radians(np.array([[a["lat"], a["lng"]] for a in apts]))
    apt_count = len(apt_pnus)

    logger.info(f"  신규 아파트 시설 집계: {apt_count}건")

    # 시설 summary 계산
    subtypes = query_all(conn, "SELECT DISTINCT facility_subtype FROM facilities WHERE is_active = TRUE")
    summary_rows = []

    for st in subtypes:
        subtype = st["facility_subtype"]
        tree, cnt = _build_balltree(conn, subtype)
        if not tree:
            continue

        nearest, counts = _query_nearest_and_counts(tree, apt_coords, [1000, 3000, 5000])
        for i, pnu in enumerate(apt_pnus):
            summary_rows.append((
                pnu, subtype, round(float(nearest[i]), 1),
                int(counts[1000][i]), int(counts[3000][i]), int(counts[5000][i])
            ))

    cur = conn.cursor()
    cur.execute(f"DELETE FROM apt_facility_summary WHERE pnu IN ({ph})", pnu_list)
    if summary_rows:
        execute_values_chunked(conn,
            "INSERT INTO apt_facility_summary (pnu, facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km) VALUES %s",
            summary_rows)

    # summary_map 구축
    summary_map = {}
    for row in summary_rows:
        pnu, subtype, dist = row[0], row[1], row[2]
        if pnu not in summary_map:
            summary_map[pnu] = {}
        summary_map[pnu][subtype] = dist

    # v2 안전점수
    v2_data = _load_all_v2_data(conn, apt_pnus, apt_sgg_codes, apt_coords, apt_count, summary_map, logger)
    safety_rows = _calc_safety_v2(
        apt_pnus, apt_sgg_codes, apt_coords, summary_map, **v2_data)

    cur.execute(f"DELETE FROM apt_safety_score WHERE pnu IN ({ph})", pnu_list)
    if safety_rows:
        execute_values_chunked(conn,
            "INSERT INTO apt_safety_score "
            "(pnu, safety_score, cctv_count_500m, cctv_count_1km, nearest_cctv_m, crime_safety_score, "
            " micro_score, access_score, macro_score, complex_score, data_reliability) VALUES %s",
            safety_rows)

    conn.commit()
    logger.info(f"  신규 아파트 시설 집계 완료: summary={len(summary_rows)}, safety={len(safety_rows)}")


def recalc_summary(conn, logger):
    """시설 변경 후 apt_facility_summary + apt_safety_score v2 재계산."""
    try:
        from sklearn.neighbors import BallTree
    except ImportError:
        logger.error("scikit-learn 미설치. pip install scikit-learn 필요.")
        return

    RADII = {"1km": 1000, "3km": 3000, "5km": 5000}

    apts = query_all(conn, "SELECT pnu, lat, lng, sigungu_code FROM apartments WHERE lat IS NOT NULL AND lng IS NOT NULL")
    if not apts:
        logger.info("아파트 데이터 없음")
        return

    apt_pnus = [a["pnu"] for a in apts]
    apt_sgg_codes = [a.get("sigungu_code", "")[:5] for a in apts]
    apt_coords = np.radians(np.array([[a["lat"], a["lng"]] for a in apts]))
    apt_count = len(apt_pnus)

    # 시설 subtype별 처리
    subtypes = query_all(conn, "SELECT DISTINCT facility_subtype FROM facilities WHERE is_active = TRUE")
    subtype_list = [r["facility_subtype"] for r in subtypes]

    logger.info(f"BallTree 재계산: {apt_count:,}개 아파트 x {len(subtype_list)}개 시설유형")

    all_summary_rows = []

    for subtype in subtype_list:
        tree, cnt = _build_balltree(conn, subtype)
        if not tree:
            continue

        nearest, counts = _query_nearest_and_counts(tree, apt_coords, [1000, 3000, 5000])

        for i, pnu in enumerate(apt_pnus):
            all_summary_rows.append((
                pnu, subtype, round(float(nearest[i]), 1),
                int(counts[1000][i]), int(counts[3000][i]), int(counts[5000][i])
            ))

        logger.info(f"  {subtype}: {cnt:,}개 시설 처리 완료")

    cur = conn.cursor()
    cur.execute("TRUNCATE apt_facility_summary")
    execute_values_chunked(conn,
        "INSERT INTO apt_facility_summary (pnu, facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km) VALUES %s",
        all_summary_rows)

    logger.info(f"apt_facility_summary 재계산 완료: {len(all_summary_rows):,}건")

    # summary_map 구축
    summary_map = {}
    for row in all_summary_rows:
        pnu, subtype, dist = row[0], row[1], row[2]
        if pnu not in summary_map:
            summary_map[pnu] = {}
        summary_map[pnu][subtype] = dist

    # apt_safety_score v2 재계산
    logger.info("apt_safety_score v2 재계산 중...")

    v2_data = _load_all_v2_data(conn, apt_pnus, apt_sgg_codes, apt_coords, apt_count, summary_map, logger)
    safety_rows = _calc_safety_v2(
        apt_pnus, apt_sgg_codes, apt_coords, summary_map, **v2_data)

    cur.execute("TRUNCATE apt_safety_score")
    execute_values_chunked(conn,
        "INSERT INTO apt_safety_score "
        "(pnu, safety_score, cctv_count_500m, cctv_count_1km, nearest_cctv_m, crime_safety_score, "
        " micro_score, access_score, macro_score, complex_score, data_reliability) VALUES %s",
        safety_rows)

    logger.info(f"apt_safety_score v2 재계산 완료: {len(safety_rows):,}건")
