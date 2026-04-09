"""아파트 서브벡터 생성 — 유사 아파트 추천용.

아파트별 4개 서브벡터 그룹(총 30차원)을 생성하여 apt_vectors 테이블에 저장.
각 그룹별 독립 StandardScaler로 정규화하여 코사인 유사도 계산에 최적화.

그룹:
  - basic (4): building_age, max_floor, total_hhld_cnt, avg_area
  - price (3): price_per_m2, price_score, jeonse_ratio
  - facility (20): 15 count_1km + 5 nearest_dist
  - safety (3): complex_score, access_score, regional_crime_score

사용법:
  uv run python -m batch.ml.build_vectors
"""

from datetime import date
from pathlib import Path

import joblib
import numpy as np
from psycopg2.extras import execute_values
from sklearn.preprocessing import StandardScaler

from batch.db import get_connection
from batch.logger import setup_logger

VECTOR_VERSION = 1

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"

FACILITY_SUBTYPES = [
    "subway", "bus", "school", "kindergarten", "hospital",
    "park", "mart", "convenience_store", "library", "pharmacy",
    "pet_facility", "animal_hospital", "police", "fire_station", "cctv",
]

DIST_SUBTYPES = ["subway", "school", "park", "mart", "hospital"]

FEATURE_GROUPS = {
    "basic": ["building_age", "max_floor", "total_hhld_cnt", "avg_area"],
    "price": ["price_per_m2", "price_score", "jeonse_ratio"],
    "facility": (
        [f"{s}_count_1km" for s in FACILITY_SUBTYPES]
        + [f"{s}_dist" for s in DIST_SUBTYPES]
    ),
    "safety": ["complex_score", "access_score", "regional_crime_score"],
}

# 안전 점수 NULL 대체값 (최대값의 50%)
SAFETY_DEFAULTS = {
    "complex_score": 17.5,
    "access_score": 15.0,
    "regional_crime_score": 17.5,
}

DEFAULT_BUILDING_AGE = 20
DEFAULT_MAX_FLOOR = 15
DEFAULT_TOTAL_HHLD_CNT = 100
DEFAULT_AVG_AREA = 60.0
DEFAULT_FACILITY_COUNT = 0
DEFAULT_FACILITY_DIST = 5000.0
DEFAULT_PRICE_PER_M2 = 0.0
DEFAULT_PRICE_SCORE = 50.0
DEFAULT_JEONSE_RATIO = 0.0
CURRENT_YEAR = date.today().year
BATCH_INSERT_SIZE = 1000
MIN_COUNT_RATIO = 0.8


def _fetch_basic_data(cur):
    """아파트 기본 정보 + 면적 조회 -> {pnu: [age, floor, hhld, area]}."""
    cur.execute("""
        SELECT a.pnu, a.total_hhld_cnt, a.max_floor, a.use_apr_day,
               COALESCE(ai.avg_area, %s) AS avg_area
        FROM apartments a
        LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
        WHERE a.group_pnu = a.pnu AND a.lat IS NOT NULL
    """, (DEFAULT_AVG_AREA,))

    result = {}
    for pnu, hhld, floor, apr_day, area in cur.fetchall():
        try:
            year = int(str(apr_day)[:4]) if apr_day else CURRENT_YEAR - DEFAULT_BUILDING_AGE
            age = CURRENT_YEAR - year
        except (ValueError, TypeError):
            age = DEFAULT_BUILDING_AGE

        result[pnu] = [
            age,
            floor or DEFAULT_MAX_FLOOR,
            hhld or DEFAULT_TOTAL_HHLD_CNT,
            area or DEFAULT_AVG_AREA,
        ]
    return result


def _fetch_price_data(cur, pnu_set):
    """가격 점수 조회 -> {pnu: [price_per_m2, price_score, jeonse_ratio]}."""
    cur.execute("SELECT pnu, price_per_m2, price_score, jeonse_ratio FROM apt_price_score")
    result = {}
    for pnu, price_per_m2, price_score, jeonse_ratio in cur.fetchall():
        if pnu in pnu_set:
            result[pnu] = [
                price_per_m2 or DEFAULT_PRICE_PER_M2,
                price_score or DEFAULT_PRICE_SCORE,
                jeonse_ratio or DEFAULT_JEONSE_RATIO,
            ]
    return result


def _fetch_facility_data(cur, pnu_set):
    """시설 거리/개수 조회 -> {pnu: {subtype: (dist, count)}}."""
    cur.execute(
        "SELECT pnu, facility_subtype, nearest_distance_m, count_1km "
        "FROM apt_facility_summary"
    )
    result = {}
    for pnu, subtype, dist, count in cur.fetchall():
        if pnu in pnu_set:
            if pnu not in result:
                result[pnu] = {}
            result[pnu][subtype] = (
                dist or DEFAULT_FACILITY_DIST,
                count or DEFAULT_FACILITY_COUNT,
            )
    return result


def _fetch_safety_data(cur, pnu_set):
    """안전 점수 조회 -> {pnu: [complex, access, regional_crime]}.

    regional_crime_score = regional_safety_score + crime_adjust_score
    """
    cur.execute(
        "SELECT pnu, complex_score, access_score, "
        "regional_safety_score, crime_adjust_score "
        "FROM apt_safety_score"
    )
    result = {}
    for pnu, complex_sc, access_sc, regional_sc, crime_adj in cur.fetchall():
        if pnu in pnu_set:
            regional_crime = (
                (regional_sc or 0) + (crime_adj or 0)
                if regional_sc is not None and crime_adj is not None
                else None
            )
            result[pnu] = [
                complex_sc if complex_sc is not None else SAFETY_DEFAULTS["complex_score"],
                access_sc if access_sc is not None else SAFETY_DEFAULTS["access_score"],
                regional_crime if regional_crime is not None else SAFETY_DEFAULTS["regional_crime_score"],
            ]
    return result


def _build_facility_vector(facility_map_entry):
    """시설 맵 엔트리에서 20차원 벡터 생성: count_1km(15) + dist(5)."""
    fac = facility_map_entry or {}
    counts = [
        fac.get(s, (DEFAULT_FACILITY_DIST, DEFAULT_FACILITY_COUNT))[1]
        for s in FACILITY_SUBTYPES
    ]
    dists = [
        fac.get(s, (DEFAULT_FACILITY_DIST, DEFAULT_FACILITY_COUNT))[0]
        for s in DIST_SUBTYPES
    ]
    return counts + dists


def _scale_and_save(group_name, raw_matrix, logger):
    """그룹별 StandardScaler 적용 및 저장."""
    X = np.array(raw_matrix, dtype=np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    scaler_path = MODEL_DIR / f"scaler_{group_name}.joblib"
    joblib.dump(scaler, scaler_path)
    logger.info(f"  스케일러 저장: {scaler_path}")

    return X_scaled


def _create_new_table(cur):
    """apt_vectors_new 테이블 생성."""
    cur.execute("DROP TABLE IF EXISTS apt_vectors_new")
    cur.execute("""
        CREATE TABLE apt_vectors_new (
            pnu TEXT PRIMARY KEY,
            vec_basic DOUBLE PRECISION[4] NOT NULL,
            vec_price DOUBLE PRECISION[3] NOT NULL,
            vec_facility DOUBLE PRECISION[20] NOT NULL,
            vec_safety DOUBLE PRECISION[3] NOT NULL,
            vector_version INTEGER NOT NULL DEFAULT 1,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def _atomic_rename(cur, conn, logger):
    """apt_vectors_new -> apt_vectors 원자적 교체."""
    cur.execute(
        "SELECT EXISTS ("
        "  SELECT 1 FROM information_schema.tables "
        "  WHERE table_name = 'apt_vectors'"
        ")"
    )
    old_exists = cur.fetchone()[0]

    if old_exists:
        # 교체 전 건수 검증
        cur.execute("SELECT COUNT(*) FROM apt_vectors")
        old_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM apt_vectors_new")
        new_count = cur.fetchone()[0]

        if old_count > 0 and new_count < old_count * MIN_COUNT_RATIO:
            cur.execute("DROP TABLE IF EXISTS apt_vectors_new")
            conn.commit()
            raise RuntimeError(
                f"새 벡터 건수({new_count:,})가 기존({old_count:,})의 "
                f"{MIN_COUNT_RATIO * 100:.0f}% 미만. 마이그레이션 중단."
            )

        cur.execute("DROP TABLE IF EXISTS apt_vectors_old")
        cur.execute("ALTER TABLE apt_vectors RENAME TO apt_vectors_old")
        cur.execute("ALTER TABLE apt_vectors_new RENAME TO apt_vectors")
        cur.execute("DROP TABLE IF EXISTS apt_vectors_old")
        logger.info(f"  원자적 교체 완료 (기존 {old_count:,} -> 신규 {new_count:,})")
    else:
        cur.execute("ALTER TABLE apt_vectors_new RENAME TO apt_vectors")
        cur.execute("SELECT COUNT(*) FROM apt_vectors")
        new_count = cur.fetchone()[0]
        logger.info(f"  신규 테이블 생성 완료 ({new_count:,}건)")

    conn.commit()


def build_all_vectors(conn, logger):
    """전체 아파트 서브벡터 재생성 (atomic rename 방식)."""
    cur = conn.cursor()

    logger.info("아파트 서브벡터 생성 시작 (v%d, 30차원)", VECTOR_VERSION)

    # 1. 데이터 수집
    basic_map = _fetch_basic_data(cur)
    pnu_list = sorted(basic_map.keys())
    pnu_set = set(pnu_list)
    logger.info(f"  벡터 대상 아파트: {len(pnu_list):,}건")

    price_map = _fetch_price_data(cur, pnu_set)
    facility_map = _fetch_facility_data(cur, pnu_set)
    safety_map = _fetch_safety_data(cur, pnu_set)

    logger.info(
        f"  데이터 수집 완료 — 가격: {len(price_map):,}, "
        f"시설: {len(facility_map):,}, 안전: {len(safety_map):,}"
    )

    # 데이터 미보유 아파트 로깅
    missing_price = sum(1 for p in pnu_list if p not in price_map)
    if missing_price:
        logger.warning(f"  가격 데이터 미보유 아파트: {missing_price:,}건 (기본값 적용)")

    missing_safety = sum(1 for p in pnu_list if p not in safety_map)
    if missing_safety:
        logger.warning(f"  안전점수 미보유 아파트: {missing_safety:,}건 (기본값 적용)")

    # 2. 그룹별 raw 벡터 구성
    raw_basic = []
    raw_price = []
    raw_facility = []
    raw_safety = []

    default_price = [DEFAULT_PRICE_PER_M2, DEFAULT_PRICE_SCORE, DEFAULT_JEONSE_RATIO]
    default_safety = [
        SAFETY_DEFAULTS["complex_score"],
        SAFETY_DEFAULTS["access_score"],
        SAFETY_DEFAULTS["regional_crime_score"],
    ]

    for pnu in pnu_list:
        raw_basic.append(basic_map[pnu])
        raw_price.append(price_map.get(pnu, default_price))
        raw_facility.append(_build_facility_vector(facility_map.get(pnu)))
        raw_safety.append(safety_map.get(pnu, default_safety))

    # 3. 그룹별 정규화 + 스케일러 저장
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    scaled_basic = _scale_and_save("basic", raw_basic, logger)
    scaled_price = _scale_and_save("price", raw_price, logger)
    scaled_facility = _scale_and_save("facility", raw_facility, logger)
    scaled_safety = _scale_and_save("safety", raw_safety, logger)

    # 4. 새 테이블 생성 + INSERT
    _create_new_table(cur)
    conn.commit()

    batch = []
    for i, pnu in enumerate(pnu_list):
        batch.append((
            pnu,
            scaled_basic[i].tolist(),
            scaled_price[i].tolist(),
            scaled_facility[i].tolist(),
            scaled_safety[i].tolist(),
            VECTOR_VERSION,
        ))
        if len(batch) >= BATCH_INSERT_SIZE:
            execute_values(
                cur,
                "INSERT INTO apt_vectors_new "
                "(pnu, vec_basic, vec_price, vec_facility, vec_safety, vector_version) "
                "VALUES %s",
                batch,
                page_size=BATCH_INSERT_SIZE,
            )
            batch = []

    if batch:
        execute_values(
            cur,
            "INSERT INTO apt_vectors_new "
            "(pnu, vec_basic, vec_price, vec_facility, vec_safety, vector_version) "
            "VALUES %s",
            batch,
            page_size=BATCH_INSERT_SIZE,
        )

    conn.commit()

    # 5. 원자적 교체
    _atomic_rename(cur, conn, logger)

    cur.execute("SELECT COUNT(*) FROM apt_vectors")
    count = cur.fetchone()[0]

    dim_total = sum(len(v) for v in FEATURE_GROUPS.values())
    logger.info(
        f"  서브벡터 재생성 완료: {count:,}건 "
        f"({len(FEATURE_GROUPS)}그룹, {dim_total}차원)"
    )
    return count


def main():
    logger = setup_logger("build_vectors")
    conn = get_connection()
    try:
        build_all_vectors(conn, logger)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
