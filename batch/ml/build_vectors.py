"""아파트 특성 벡터 생성 — 유사 아파트 추천용.

아파트별 34차원 벡터를 생성하여 apt_vectors 테이블에 저장.
StandardScaler로 정규화하여 코사인 유사도 계산에 최적화.

사용법:
  python -m batch.ml.build_vectors
"""

import numpy as np
from sklearn.preprocessing import StandardScaler
from batch.db import get_connection
from batch.logger import setup_logger

# 벡터에 포함할 시설 subtype 목록
FACILITY_SUBTYPES = [
    "subway", "bus", "school", "kindergarten", "hospital",
    "park", "mart", "convenience_store", "library", "pharmacy",
    "pet_facility", "animal_hospital", "police", "fire_station", "cctv",
]

# 피처 이름 목록
FEATURE_NAMES = (
    ["building_age", "max_floor", "total_hhld_cnt", "avg_area"]
    + ["price_per_m2", "price_score", "jeonse_ratio"]
    + [f"{s}_dist" for s in FACILITY_SUBTYPES]
    + [f"{s}_count_1km" for s in FACILITY_SUBTYPES]
    + ["safety_score", "cctv_count_500m"]
)


def build_all_vectors(conn, logger):
    """전체 아파트 유사도 벡터 재생성 (TRUNCATE → INSERT)."""
    cur = conn.cursor()

    logger.info("아파트 특성 벡터 생성 시작...")

    # apt_vectors 테이블 생성
    cur.execute("""
        CREATE TABLE IF NOT EXISTS apt_vectors (
            pnu TEXT PRIMARY KEY,
            vector DOUBLE PRECISION[] NOT NULL,
            feature_names TEXT DEFAULT '',
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.commit()

    # 1. 아파트 기본 정보
    cur.execute("""
        SELECT a.pnu, a.total_hhld_cnt, a.max_floor, a.use_apr_day,
               COALESCE(ai.avg_area, 60) as avg_area
        FROM apartments a
        LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
        WHERE a.group_pnu = a.pnu AND a.lat IS NOT NULL
    """)
    apt_rows = cur.fetchall()
    logger.info(f"  벡터 대상 아파트: {len(apt_rows):,}건")

    pnu_list = []
    basic_features = []

    for row in apt_rows:
        pnu, hhld, floor, apr_day, area = row
        try:
            year = int(str(apr_day)[:4]) if apr_day else 2000
            age = 2026 - year
        except (ValueError, TypeError):
            age = 20

        pnu_list.append(pnu)
        basic_features.append([
            age,
            floor or 15,
            hhld or 100,
            area or 60,
        ])

    pnu_set = set(pnu_list)

    # 2. 가격 정보
    cur.execute("SELECT pnu, price_per_m2, price_score, jeonse_ratio FROM apt_price_score")
    price_map = {}
    for row in cur.fetchall():
        if row[0] in pnu_set:
            price_map[row[0]] = [row[1] or 0, row[2] or 50, row[3] or 0]

    # 3. 시설 거리/개수
    cur.execute("SELECT pnu, facility_subtype, nearest_distance_m, count_1km FROM apt_facility_summary")
    facility_map: dict[str, dict[str, tuple]] = {}
    for row in cur.fetchall():
        if row[0] in pnu_set:
            if row[0] not in facility_map:
                facility_map[row[0]] = {}
            facility_map[row[0]][row[1]] = (row[2] or 5000, row[3] or 0)

    # 4. 안전 점수
    cur.execute("SELECT pnu, safety_score, cctv_count_500m FROM apt_safety_score")
    safety_map = {}
    for row in cur.fetchall():
        if row[0] in pnu_set:
            safety_map[row[0]] = [row[1] or 0, row[2] or 0]

    # 5. 벡터 조합
    vectors = []
    valid_pnus = []

    for i, pnu in enumerate(pnu_list):
        basic = basic_features[i]
        price = price_map.get(pnu, [0, 50, 0])
        fac = facility_map.get(pnu, {})
        safety = safety_map.get(pnu, [0, 0])

        fac_dist = [fac.get(s, (5000, 0))[0] for s in FACILITY_SUBTYPES]
        fac_count = [fac.get(s, (5000, 0))[1] for s in FACILITY_SUBTYPES]

        vector = basic + price + fac_dist + fac_count + safety
        vectors.append(vector)
        valid_pnus.append(pnu)

    # 6. 정규화
    X = np.array(vectors, dtype=np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 7. DB 저장
    cur.execute("TRUNCATE apt_vectors")

    feature_str = ",".join(FEATURE_NAMES)
    batch = []
    for i, pnu in enumerate(valid_pnus):
        vec = X_scaled[i].tolist()
        batch.append((pnu, vec, feature_str))
        if len(batch) >= 1000:
            from psycopg2.extras import execute_values
            execute_values(cur,
                "INSERT INTO apt_vectors (pnu, vector, feature_names) VALUES %s",
                batch, page_size=1000)
            batch = []

    if batch:
        from psycopg2.extras import execute_values
        execute_values(cur,
            "INSERT INTO apt_vectors (pnu, vector, feature_names) VALUES %s",
            batch, page_size=1000)

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM apt_vectors")
    count = cur.fetchone()[0]

    logger.info(f"  벡터 재생성 완료: {count:,}건 ({len(FEATURE_NAMES)}차원)")
    return count


def main():
    logger = setup_logger("build_vectors")
    conn = get_connection()
    build_all_vectors(conn, logger)
    conn.close()


if __name__ == "__main__":
    main()
