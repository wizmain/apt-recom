# 아파트 유사도 벡터 재설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 39차원 단일 벡터를 4개 서브벡터 그룹(30차원)으로 재설계하고, 4개 추천 모드(location/price/lifestyle/combined)를 구현한다.

**Architecture:** batch/ml/build_vectors.py가 4그룹 서브벡터를 독립 스케일링 후 DB에 저장. web/backend/services/similarity.py가 모드별 메트릭 계산을 담당하고, routers/similar.py가 hard filter + API 엔드포인트를 제공한다.

**Tech Stack:** Python 3.12, FastAPI, psycopg2 (raw SQL), numpy, scikit-learn (StandardScaler), joblib

**Spec:** `docs/superpowers/specs/2026-04-06-vector-redesign.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Rewrite | `batch/ml/build_vectors.py` | 4그룹 서브벡터 생성, 스케일러 저장, atomic rename 마이그레이션 |
| Create | `web/backend/services/similarity.py` | 모드별 메트릭 계산, 넛지 가중치 매핑, 그룹 가중치 적용 |
| Rewrite | `web/backend/routers/similar.py` | GET/POST API 엔드포인트, hard filter SQL, 필터 확장 |
| Modify | `web/backend/services/tools.py:188-211, 961-1025` | tool description + executor를 새 모드 API에 맞게 변경 |
| Modify | `web/backend/tests/test_core.py` (append) | 유사 아파트 추천 테스트 추가 |
| Rewrite | `docs/ml-features.md` | 30차원 피처 그룹 + 4개 모드 문서 |

---

### Task 1: build_vectors.py 서브벡터 생성 리팩토링

**Files:**
- Rewrite: `batch/ml/build_vectors.py`

- [ ] **Step 1: Write the complete build_vectors.py**

```python
"""아파트 특성 벡터 생성 -- 유사 아파트 추천용.

아파트별 30차원 벡터를 4개 서브벡터 그룹으로 생성하여 apt_vectors 테이블에 저장.
각 그룹은 독립 StandardScaler로 정규화.

사용법:
  uv run python -m batch.ml.build_vectors
"""

import numpy as np
import joblib
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from batch.db import get_connection
from batch.logger import setup_logger

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_DIR.mkdir(exist_ok=True)

VECTOR_VERSION = 1

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


def _fetch_basic(cur, pnu_set):
    """아파트 기본 정보 -> {pnu: [age, floor, hhld, area]}."""
    cur.execute("""
        SELECT a.pnu, a.total_hhld_cnt, a.max_floor, a.use_apr_day,
               COALESCE(ai.avg_area, 60) as avg_area
        FROM apartments a
        LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
        WHERE a.group_pnu = a.pnu AND a.lat IS NOT NULL
    """)
    result = {}
    for row in cur.fetchall():
        pnu = row[0]
        if pnu not in pnu_set:
            continue
        try:
            year = int(str(row[3])[:4]) if row[3] else 2000
            age = 2026 - year
        except (ValueError, TypeError):
            age = 20
        result[pnu] = [age, row[2] or 15, row[1] or 100, row[4] or 60]
    return result


def _fetch_price(cur, pnu_set):
    """가격 정보 -> {pnu: [price_m2, score, jeonse]}."""
    cur.execute("SELECT pnu, price_per_m2, price_score, jeonse_ratio FROM apt_price_score")
    result = {}
    for row in cur.fetchall():
        if row[0] in pnu_set:
            result[row[0]] = [row[1] or 0, row[2] or 50, row[3] or 0]
    return result


def _fetch_facility(cur, pnu_set):
    """시설 거리/밀도 -> {pnu: {subtype: (dist, count)}}."""
    cur.execute("SELECT pnu, facility_subtype, nearest_distance_m, count_1km FROM apt_facility_summary")
    result = {}
    for row in cur.fetchall():
        if row[0] in pnu_set:
            if row[0] not in result:
                result[row[0]] = {}
            result[row[0]][row[1]] = (row[2] or 5000, row[3] or 0)
    return result


def _fetch_safety(cur, pnu_set):
    """안전점수 v3 세부 축 -> {pnu: [complex, access, regional_crime]}."""
    cur.execute("""
        SELECT pnu, complex_score, access_score, regional_safety_score, crime_adjust_score
        FROM apt_safety_score
    """)
    result = {}
    for row in cur.fetchall():
        if row[0] in pnu_set:
            complex_s = row[1] if row[1] is not None else 17.5
            access_s = row[2] if row[2] is not None else 15.0
            regional = row[3] if row[3] is not None else 10.0
            crime_adj = row[4] if row[4] is not None else 7.5
            result[row[0]] = [complex_s, access_s, regional + crime_adj]
    return result


def _build_group_vector(pnu, group, basic_map, price_map, facility_map, safety_map):
    """PNU에 대해 지정 그룹의 원시 벡터를 생성."""
    if group == "basic":
        return basic_map.get(pnu, [20, 15, 100, 60])
    elif group == "price":
        return price_map.get(pnu, [0, 50, 0])
    elif group == "facility":
        fac = facility_map.get(pnu, {})
        counts = [fac.get(s, (5000, 0))[1] for s in FACILITY_SUBTYPES]
        dists = [fac.get(s, (5000, 0))[0] for s in DIST_SUBTYPES]
        return counts + dists
    elif group == "safety":
        return safety_map.get(pnu, [17.5, 15.0, 17.5])
    return []


def build_all_vectors(conn, logger):
    """전체 아파트 유사도 벡터 재생성 (atomic rename 방식)."""
    cur = conn.cursor()
    logger.info("아파트 특성 벡터 생성 시작...")

    # 대상 PNU 목록
    cur.execute("""
        SELECT pnu FROM apartments
        WHERE group_pnu = pnu AND lat IS NOT NULL
    """)
    pnu_list = [row[0] for row in cur.fetchall()]
    pnu_set = set(pnu_list)
    logger.info(f"  벡터 대상 아파트: {len(pnu_list):,}건")

    # 데이터 조회
    basic_map = _fetch_basic(cur, pnu_set)
    price_map = _fetch_price(cur, pnu_set)
    facility_map = _fetch_facility(cur, pnu_set)
    safety_map = _fetch_safety(cur, pnu_set)

    # 그룹별 원시 벡터 생성
    group_names = ["basic", "price", "facility", "safety"]
    group_raw = {g: [] for g in group_names}
    valid_pnus = []

    for pnu in pnu_list:
        if pnu not in basic_map:
            continue
        for g in group_names:
            group_raw[g].append(
                _build_group_vector(pnu, g, basic_map, price_map, facility_map, safety_map)
            )
        valid_pnus.append(pnu)

    logger.info(f"  유효 아파트: {len(valid_pnus):,}건")

    # 그룹별 독립 StandardScaler
    group_scaled = {}
    for g in group_names:
        X = np.array(group_raw[g], dtype=np.float64)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        scaler = StandardScaler()
        group_scaled[g] = scaler.fit_transform(X)
        joblib.dump(scaler, MODEL_DIR / f"scaler_{g}.joblib")
        logger.info(f"  {g}: {X.shape[1]}차원, scaler 저장")

    # apt_vectors_new 테이블 생성
    cur.execute("DROP TABLE IF EXISTS apt_vectors_new")
    cur.execute("""
        CREATE TABLE apt_vectors_new (
            pnu TEXT PRIMARY KEY,
            vec_basic DOUBLE PRECISION[4],
            vec_price DOUBLE PRECISION[3],
            vec_facility DOUBLE PRECISION[20],
            vec_safety DOUBLE PRECISION[3],
            vector_version INTEGER NOT NULL DEFAULT %s,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """, [VECTOR_VERSION])
    conn.commit()

    # INSERT
    from psycopg2.extras import execute_values
    batch = []
    for i, pnu in enumerate(valid_pnus):
        batch.append((
            pnu,
            group_scaled["basic"][i].tolist(),
            group_scaled["price"][i].tolist(),
            group_scaled["facility"][i].tolist(),
            group_scaled["safety"][i].tolist(),
            VECTOR_VERSION,
        ))
        if len(batch) >= 1000:
            execute_values(cur,
                "INSERT INTO apt_vectors_new (pnu, vec_basic, vec_price, vec_facility, vec_safety, vector_version) VALUES %s",
                batch, page_size=1000)
            batch = []
    if batch:
        execute_values(cur,
            "INSERT INTO apt_vectors_new (pnu, vec_basic, vec_price, vec_facility, vec_safety, vector_version) VALUES %s",
            batch, page_size=1000)
    conn.commit()

    # 건수 검증
    cur.execute("SELECT COUNT(*) FROM apt_vectors_new")
    new_count = cur.fetchone()[0]

    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'apt_vectors')")
    old_exists = cur.fetchone()[0]

    if old_exists:
        cur.execute("SELECT COUNT(*) FROM apt_vectors")
        old_count = cur.fetchone()[0]
        if old_count > 0 and new_count < old_count * 0.8:
            cur.execute("DROP TABLE apt_vectors_new")
            conn.commit()
            raise RuntimeError(
                f"건수 검증 실패: 기존 {old_count:,}건 -> 신규 {new_count:,}건 "
                f"({new_count/old_count*100:.1f}%, 80% 미달). 기존 테이블 유지."
            )

    # Atomic rename
    if old_exists:
        cur.execute("DROP TABLE IF EXISTS apt_vectors_old")
        cur.execute("ALTER TABLE apt_vectors RENAME TO apt_vectors_old")
    cur.execute("ALTER TABLE apt_vectors_new RENAME TO apt_vectors")
    conn.commit()

    if old_exists:
        cur.execute("DROP TABLE IF EXISTS apt_vectors_old")
        conn.commit()

    logger.info(f"  벡터 재생성 완료: {new_count:,}건 (v{VECTOR_VERSION}, {sum(len(FEATURE_GROUPS[g]) for g in group_names)}차원)")
    return new_count


def main():
    logger = setup_logger("build_vectors")
    conn = get_connection()
    try:
        build_all_vectors(conn, logger)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run build_vectors to verify**

Run: `uv run python -m batch.ml.build_vectors`
Expected: 로그에 `벡터 대상 아파트: ~15,000건`, 각 그룹별 차원/scaler 저장, `벡터 재생성 완료` 메시지. models/ 디렉토리에 scaler_basic.joblib, scaler_price.joblib, scaler_facility.joblib, scaler_safety.joblib 생성.

- [ ] **Step 3: Verify DB schema**

Run: `uv run python -c "from batch.db import get_connection; c=get_connection(); cur=c.cursor(); cur.execute(\"SELECT pnu, array_length(vec_basic,1), array_length(vec_facility,1), array_length(vec_safety,1), vector_version FROM apt_vectors LIMIT 3\"); print([dict(zip(['pnu','basic_dim','facility_dim','safety_dim','version'], r)) for r in cur.fetchall()]); c.close()"`
Expected: basic_dim=4, facility_dim=20, safety_dim=3, version=1

- [ ] **Step 4: Commit**

```bash
git add batch/ml/build_vectors.py models/scaler_*.joblib
git commit -m "feat: build_vectors 서브벡터 그룹 재설계 (39->30차원, 4그룹)"
```

---

### Task 2: similarity.py 서비스 생성

**Files:**
- Create: `web/backend/services/similarity.py`

- [ ] **Step 1: Write similarity.py**

```python
"""모드별 유사도/선호도 계산 서비스."""

import numpy as np
from database import DictConnection


# 모드별 그룹 가중치
GROUP_WEIGHTS = {
    "location": {"facility": 0.75, "safety": 0.25},
    "combined": {"basic": 0.25, "facility": 0.50, "safety": 0.25},
    "combined_with_price": {"basic": 0.2125, "facility": 0.425, "safety": 0.2125, "price": 0.15},
}

# 모드별 기본 hard filter
DEFAULT_FILTERS = {
    "location": {"area_range": 0.3, "hhld_range": 0.5},
    "price": {"area_range": 0.2},
    "lifestyle": {},
    "combined": {"area_range": 0.3, "age_range": 5},
}

# 넛지 카테고리 -> facility 피처 인덱스 매핑
# facility 벡터 순서: [15 x count_1km] + [5 x dist]
# count_1km 순서: subway(0), bus(1), school(2), kindergarten(3), hospital(4),
#   park(5), mart(6), convenience_store(7), library(8), pharmacy(9),
#   pet_facility(10), animal_hospital(11), police(12), fire_station(13), cctv(14)
# dist 순서: subway(15), school(16), park(17), mart(18), hospital(19)
NUDGE_FACILITY_MAP = {
    "교통": {"count": [0, 1], "dist": [15]},
    "교육": {"count": [2, 3, 8], "dist": [16]},
    "의료": {"count": [4, 9], "dist": [19]},
    "생활편의": {"count": [6, 7], "dist": [18]},
    "자연환경": {"count": [5], "dist": [17]},
    "반려동물": {"count": [10, 11], "dist": []},
    "안전": {"count": [12, 13, 14], "dist": []},
}

DEFAULT_NUDGE_WEIGHT = 0.1


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(dot / norm) if norm > 0 else 0.0


def _euclidean_similarity(a: np.ndarray, b: np.ndarray) -> float:
    dist = np.linalg.norm(a - b)
    return float(1 / (1 + dist))


def _apply_group_weights(vectors: dict[str, np.ndarray], weights: dict[str, float]) -> np.ndarray:
    """그룹별 가중치를 적용하여 concat된 벡터를 반환."""
    parts = []
    for group, weight in weights.items():
        if group in vectors:
            parts.append(vectors[group] * weight)
    return np.concatenate(parts)


def _build_nudge_weights_vector(nudge_weights: dict[str, float]) -> np.ndarray:
    """넛지 카테고리 가중치 -> 20차원 facility 가중치 벡터."""
    weights = np.full(20, DEFAULT_NUDGE_WEIGHT)
    for category, cat_weight in nudge_weights.items():
        mapping = NUDGE_FACILITY_MAP.get(category)
        if not mapping:
            continue
        count_indices = mapping["count"]
        dist_indices = mapping["dist"]
        n_features = len(count_indices) + len(dist_indices)
        if n_features == 0:
            continue
        per_feature = cat_weight / n_features
        for idx in count_indices:
            weights[idx] = per_feature
        for idx in dist_indices:
            weights[idx] = -per_feature  # dist는 부호 반전
    return weights


def calc_location(target: dict, candidate: dict) -> float:
    """입지 유사도: cosine(concat(facility*0.75, safety*0.25))."""
    w = GROUP_WEIGHTS["location"]
    t = _apply_group_weights({"facility": target["facility"], "safety": target["safety"]}, w)
    c = _apply_group_weights({"facility": candidate["facility"], "safety": candidate["safety"]}, w)
    return _cosine_similarity(t, c)


def calc_price(target: dict, candidate: dict) -> float:
    """가격 유사도: 1/(1+euclidean(price))."""
    return _euclidean_similarity(target["price"], candidate["price"])


def calc_lifestyle(candidate: dict, nudge_weights: dict[str, float]) -> float:
    """선호도 점수: sum(facility * weights)."""
    w = _build_nudge_weights_vector(nudge_weights)
    return float(np.dot(candidate["facility"], w))


def calc_combined(target: dict, candidate: dict, include_price: bool = False) -> float:
    """종합 유사도: cosine(concat(basic*w, facility*w, safety*w))."""
    if include_price:
        w = GROUP_WEIGHTS["combined_with_price"]
        groups = {"basic": target["basic"], "facility": target["facility"],
                  "safety": target["safety"], "price": target["price"]}
        groups_c = {"basic": candidate["basic"], "facility": candidate["facility"],
                    "safety": candidate["safety"], "price": candidate["price"]}
    else:
        w = GROUP_WEIGHTS["combined"]
        groups = {"basic": target["basic"], "facility": target["facility"], "safety": target["safety"]}
        groups_c = {"basic": candidate["basic"], "facility": candidate["facility"], "safety": candidate["safety"]}
    t = _apply_group_weights(groups, w)
    c = _apply_group_weights(groups_c, w)
    return _cosine_similarity(t, c)


def parse_vectors(row: dict) -> dict[str, np.ndarray]:
    """DB row -> numpy 벡터 dict."""
    return {
        "basic": np.array(row["vec_basic"]),
        "price": np.array(row["vec_price"]),
        "facility": np.array(row["vec_facility"]),
        "safety": np.array(row["vec_safety"]),
    }
```

- [ ] **Step 2: Commit**

```bash
git add web/backend/services/similarity.py
git commit -m "feat: similarity.py 모드별 메트릭 계산 서비스"
```

---

### Task 3: similar.py 라우터 재작성

**Files:**
- Rewrite: `web/backend/routers/similar.py`

- [ ] **Step 1: Write the complete similar.py router**

```python
"""유사 아파트 추천 API -- 4개 모드 지원."""

import numpy as np
from fastapi import APIRouter, Query
from pydantic import BaseModel
from database import DictConnection
from services.similarity import (
    calc_location, calc_price, calc_lifestyle, calc_combined,
    parse_vectors, DEFAULT_FILTERS,
)

router = APIRouter()

VECTOR_VERSION = 1


class LifestyleRequest(BaseModel):
    nudge_weights: dict[str, float]
    top_n: int = 5
    exclude_same_sigungu: bool = False


def _get_target_info(conn, pnu: str) -> dict | None:
    """대상 아파트의 벡터 + 기본 정보 조회."""
    row = conn.execute("""
        SELECT v.vec_basic, v.vec_price, v.vec_facility, v.vec_safety,
               a.bld_nm, a.sigungu_code, a.total_hhld_cnt, a.use_apr_day,
               COALESCE(ai.avg_area, 60) as avg_area
        FROM apt_vectors v
        JOIN apartments a ON v.pnu = a.pnu
        LEFT JOIN apt_area_info ai ON v.pnu = ai.pnu
        WHERE v.pnu = %s AND v.vector_version = %s
    """, [pnu, VECTOR_VERSION]).fetchone()
    return row


def _build_filter_sql(mode: str, target: dict, params: list,
                      area_range: float | None, hhld_range: float | None,
                      age_range: float | None) -> str:
    """모드별 hard filter WHERE 절 생성."""
    defaults = DEFAULT_FILTERS.get(mode, {})
    conditions = []

    ar = area_range if area_range is not None else defaults.get("area_range", 0)
    if ar > 0:
        avg_area = target["avg_area"] or 60
        conditions.append("ai.avg_area BETWEEN %s AND %s")
        params.extend([avg_area * (1 - ar), avg_area * (1 + ar)])

    hr = hhld_range if hhld_range is not None else defaults.get("hhld_range", 0)
    if hr > 0:
        hhld = target["total_hhld_cnt"] or 100
        conditions.append("a.total_hhld_cnt BETWEEN %s AND %s")
        params.extend([hhld * (1 - hr), hhld * (1 + hr)])

    agr = age_range if age_range is not None else defaults.get("age_range", 0)
    if agr > 0:
        try:
            year = int(str(target["use_apr_day"])[:4])
            age = 2026 - year
        except (ValueError, TypeError):
            age = 20
        conditions.append("(2026 - CAST(LEFT(a.use_apr_day::text, 4) AS INTEGER)) BETWEEN %s AND %s")
        params.extend([max(0, age - agr), age + agr])

    return " AND ".join(conditions) if conditions else ""


def _fetch_candidates(conn, pnu: str, mode: str, filter_sql: str, params: list,
                      exclude_sgg: str) -> list:
    """후보 아파트 벡터 + 정보 조회."""
    sgg_filter = ""
    if exclude_sgg:
        sgg_filter = "AND LEFT(a.sigungu_code, 5) != %s"
        params.append(exclude_sgg)

    where = f"AND {filter_sql}" if filter_sql else ""

    sql = f"""
        SELECT v.pnu, v.vec_basic, v.vec_price, v.vec_facility, v.vec_safety,
               a.bld_nm, a.sigungu_code, a.lat, a.lng,
               a.total_hhld_cnt, a.use_apr_day,
               p.price_per_m2
        FROM apt_vectors v
        JOIN apartments a ON v.pnu = a.pnu
        LEFT JOIN apt_area_info ai ON v.pnu = ai.pnu
        LEFT JOIN apt_price_score p ON v.pnu = p.pnu
        WHERE v.pnu != %s AND a.group_pnu = a.pnu
          AND v.vector_version = %s
          {sgg_filter} {where}
    """
    return conn.execute(sql, [pnu, VECTOR_VERSION] + params).fetchall()


def _format_result(r: dict, score: float, score_field: str) -> dict:
    """결과 행 포맷팅."""
    result = {
        "pnu": r["pnu"],
        "bld_nm": r["bld_nm"],
        "sigungu_code": (r["sigungu_code"] or "")[:5],
        "lat": r["lat"],
        "lng": r["lng"],
        "total_hhld_cnt": r["total_hhld_cnt"],
        "use_apr_day": r["use_apr_day"],
        "price_per_m2": round(float(r["price_per_m2"])) if r["price_per_m2"] else None,
    }
    result[score_field] = round(score, 4) if score_field == "preference_score" else round(score * 100, 1)
    return result


def _add_sigungu_names(results: list, conn) -> None:
    """시군구 이름 매핑 추가."""
    if not results:
        return
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s", ["sigungu"]
    ).fetchall()
    sgg_names = {}
    for r in rows:
        sgg_names[r["code"]] = f"{r['name']}({r['extra']})" if r["extra"] and r["extra"] != r["name"] else r["name"]
    for r in results:
        r["sigungu_name"] = sgg_names.get(r["sigungu_code"], r["sigungu_code"])


@router.get("/apartment/{pnu}/similar")
def get_similar_apartments(
    pnu: str,
    mode: str = Query("combined", regex="^(location|price|combined)$"),
    top_n: int = Query(5, ge=1, le=20),
    exclude_same_sigungu: bool = Query(False),
    include_price: bool = Query(False),
    area_range: float | None = Query(None, ge=0, le=1),
    hhld_range: float | None = Query(None, ge=0, le=1),
    age_range: float | None = Query(None, ge=0, le=30),
):
    """유사 아파트 추천 (location/price/combined 모드)."""
    conn = DictConnection()

    target_row = _get_target_info(conn, pnu)
    if not target_row:
        conn.close()
        return {"error": "해당 아파트의 벡터 데이터가 없습니다."}

    target_vecs = parse_vectors(target_row)
    exclude_sgg = (target_row["sigungu_code"] or "")[:5] if exclude_same_sigungu else ""

    # Hard filter
    params = []
    filter_sql = _build_filter_sql(mode, target_row, params, area_range, hhld_range, age_range)

    rows = _fetch_candidates(conn, pnu, mode, filter_sql, params, exclude_sgg)

    # 후보 부족 시 필터 1.5배 확장 (1회)
    filters_expanded = False
    filters_final = {}
    if len(rows) < top_n * 2 and filter_sql:
        params2 = []
        filter_sql2 = _build_filter_sql(
            mode, target_row, params2,
            (area_range or DEFAULT_FILTERS.get(mode, {}).get("area_range", 0)) * 1.5 or None,
            (hhld_range or DEFAULT_FILTERS.get(mode, {}).get("hhld_range", 0)) * 1.5 or None,
            (age_range or DEFAULT_FILTERS.get(mode, {}).get("age_range", 0)) * 1.5 or None,
        )
        rows = _fetch_candidates(conn, pnu, mode, filter_sql2, params2, exclude_sgg)
        filters_expanded = True

    # 메트릭 계산
    scored = []
    for r in rows:
        c_vecs = parse_vectors(r)
        if mode == "location":
            score = calc_location(target_vecs, c_vecs)
        elif mode == "price":
            score = calc_price(target_vecs, c_vecs)
        else:
            score = calc_combined(target_vecs, c_vecs, include_price=include_price)
        scored.append(_format_result(r, score, "similarity_pct"))

    scored.sort(key=lambda x: x["similarity_pct"], reverse=True)
    results = scored[:top_n]

    _add_sigungu_names(results, conn)
    conn.close()

    response = {"pnu": pnu, "mode": mode, "similar": results}
    if filters_expanded:
        response["filters_expanded"] = True
    return response


@router.post("/apartment/{pnu}/similar/lifestyle")
def get_lifestyle_ranking(pnu: str, req: LifestyleRequest):
    """선호도 랭킹 (lifestyle 모드)."""
    conn = DictConnection()

    target_row = _get_target_info(conn, pnu)
    if not target_row:
        conn.close()
        return {"error": "해당 아파트의 벡터 데이터가 없습니다."}

    exclude_sgg = (target_row["sigungu_code"] or "")[:5] if req.exclude_same_sigungu else ""

    rows = _fetch_candidates(conn, pnu, "lifestyle", "", [], exclude_sgg)

    scored = []
    for r in rows:
        c_vecs = parse_vectors(r)
        score = calc_lifestyle(c_vecs, req.nudge_weights)
        scored.append(_format_result(r, score, "preference_score"))

    scored.sort(key=lambda x: x["preference_score"], reverse=True)
    results = scored[:req.top_n]

    _add_sigungu_names(results, conn)
    conn.close()

    return {
        "pnu": pnu,
        "mode": "lifestyle",
        "nudge_weights_applied": req.nudge_weights,
        "results": results,
    }
```

- [ ] **Step 2: Commit**

```bash
git add web/backend/routers/similar.py
git commit -m "feat: similar.py 4개 추천 모드 라우터 (location/price/lifestyle/combined)"
```

---

### Task 4: tools.py 챗봇 tool 업데이트

**Files:**
- Modify: `web/backend/services/tools.py:188-211` (tool definition)
- Modify: `web/backend/services/tools.py:961-1037` (executor function + mapping)

- [ ] **Step 1: Update tool definition (line 188-211)**

기존 `get_similar_apartments` Tool 정의를 다음으로 교체:

```python
    Tool(
        name="get_similar_apartments",
        description=(
            "선택한 아파트와 유사한 아파트를 추천합니다. "
            "4가지 모드: location(입지 유사), price(가격대 유사), "
            "lifestyle(선호 인프라 랭킹), combined(종합 유사). "
            "사용자 의도에 맞는 mode를 선택하세요. "
            "lifestyle은 유사도가 아닌 선호도 랭킹입니다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "아파트명 또는 PNU 코드",
                },
                "mode": {
                    "type": "string",
                    "description": "추천 모드: location(입지), price(가격대), lifestyle(선호도), combined(종합)",
                    "enum": ["location", "price", "lifestyle", "combined"],
                    "default": "combined",
                },
                "top_n": {
                    "type": "integer",
                    "description": "추천할 아파트 수 (기본 5)",
                    "default": 5,
                },
                "nudge_weights": {
                    "type": "object",
                    "description": "lifestyle 모드 전용. 카테고리별 가중치 (예: {\"교통\": 0.9, \"교육\": 0.7})",
                },
                "exclude_same_area": {
                    "type": "boolean",
                    "description": "같은 시군구 제외 여부 (기본 false)",
                    "default": False,
                },
            },
            "required": ["query"],
        },
    ),
```

- [ ] **Step 2: Update executor function (line 961-1025)**

기존 `get_similar_apartments` 함수를 다음으로 교체:

```python
async def get_similar_apartments(
    query: str, mode: str = "combined", top_n: int = 5,
    nudge_weights: dict | None = None, exclude_same_area: bool = False,
) -> str:
    """유사 아파트 추천 (4개 모드)."""
    import numpy as np
    import re as _re
    from services.similarity import (
        calc_location, calc_price, calc_lifestyle, calc_combined,
        parse_vectors,
    )

    conn = _get_conn()

    # 아파트 검색
    apt = conn.execute("SELECT pnu FROM apartments WHERE pnu = %s", [query]).fetchone()
    if not apt:
        norm = _re.sub(r'[\s()\-·]', '', query)
        rows = conn.execute(
            "SELECT pnu, bld_nm FROM apartments WHERE group_pnu = pnu AND (bld_nm LIKE %s OR bld_nm_norm LIKE %s) LIMIT 1",
            [f"%{query}%", f"%{norm}%"]
        ).fetchall()
        if not rows:
            conn.close()
            return json.dumps({"error": f"'{query}' 아파트를 찾을 수 없습니다."}, ensure_ascii=False)
        apt = rows[0]

    pnu = apt["pnu"]

    # 대상 벡터
    target_row = conn.execute("""
        SELECT v.vec_basic, v.vec_price, v.vec_facility, v.vec_safety,
               a.bld_nm, a.sigungu_code
        FROM apt_vectors v
        JOIN apartments a ON v.pnu = a.pnu
        WHERE v.pnu = %s
    """, [pnu]).fetchone()

    if not target_row:
        conn.close()
        return json.dumps({"error": "해당 아파트의 유사도 벡터가 없습니다."}, ensure_ascii=False)

    target_vecs = parse_vectors(target_row)
    target_sgg = (target_row["sigungu_code"] or "")[:5] if exclude_same_area else ""

    # 후보 조회
    rows = conn.execute("""
        SELECT v.pnu, v.vec_basic, v.vec_price, v.vec_facility, v.vec_safety,
               a.bld_nm, a.sigungu_code, p.price_per_m2
        FROM apt_vectors v
        JOIN apartments a ON v.pnu = a.pnu
        LEFT JOIN apt_price_score p ON v.pnu = p.pnu
        WHERE v.pnu != %s AND a.group_pnu = a.pnu
    """, [pnu]).fetchall()
    conn.close()

    results = []
    for r in rows:
        if target_sgg and (r["sigungu_code"] or "")[:5] == target_sgg:
            continue
        c_vecs = parse_vectors(r)

        if mode == "location":
            score = calc_location(target_vecs, c_vecs)
            score_str = f"{score * 100:.1f}%"
        elif mode == "price":
            score = calc_price(target_vecs, c_vecs)
            score_str = f"{score * 100:.1f}%"
        elif mode == "lifestyle":
            nw = nudge_weights or {"생활편의": 0.5, "교통": 0.5}
            score = calc_lifestyle(c_vecs, nw)
            score_str = f"{score:.2f}점"
        else:
            score = calc_combined(target_vecs, c_vecs)
            score_str = f"{score * 100:.1f}%"

        results.append({
            "name": r["bld_nm"],
            "pnu": r["pnu"],
            "score": score_str,
            "price_m2": f"{round(float(r['price_per_m2'])):,}만원/m2" if r["price_per_m2"] else "가격정보 없음",
            "_sort": score,
        })

    results.sort(key=lambda x: x["_sort"], reverse=True)
    for r in results:
        del r["_sort"]

    return json.dumps({
        "target": target_row["bld_nm"],
        "mode": mode,
        "similar_apartments": results[:top_n],
    }, ensure_ascii=False)
```

- [ ] **Step 3: Commit**

```bash
git add web/backend/services/tools.py
git commit -m "feat: tools.py 유사 아파트 tool 4개 모드 지원"
```

---

### Task 5: 통합 테스트 추가

**Files:**
- Modify: `web/backend/tests/test_core.py` (append)

- [ ] **Step 1: Append test cases**

test_core.py 파일 끝(마지막 `run_all()` 호출 직전)에 다음을 추가:

```python
# ============================================================
# 유사 아파트 추천 테스트
# ============================================================

@test("유사추천: apt_vectors 서브벡터 구조 확인")
def test_vectors_schema():
    conn = DictConnection()
    row = conn.execute("""
        SELECT vec_basic, vec_price, vec_facility, vec_safety, vector_version
        FROM apt_vectors LIMIT 1
    """).fetchone()
    conn.close()
    assert row is not None, "apt_vectors 테이블이 비어있음"
    assert len(row["vec_basic"]) == 4, f"basic 차원: {len(row['vec_basic'])} != 4"
    assert len(row["vec_price"]) == 3, f"price 차원: {len(row['vec_price'])} != 3"
    assert len(row["vec_facility"]) == 20, f"facility 차원: {len(row['vec_facility'])} != 20"
    assert len(row["vec_safety"]) == 3, f"safety 차원: {len(row['vec_safety'])} != 3"
    assert row["vector_version"] >= 1, "vector_version이 1 미만"


@test("유사추천: location 모드 코사인 유사도 0~1 범위")
def test_similar_location():
    conn = DictConnection()
    pnu = conn.execute("SELECT pnu FROM apt_vectors LIMIT 1").fetchone()["pnu"]
    conn.close()

    from services.similarity import calc_location, parse_vectors
    conn2 = DictConnection()
    rows = conn2.execute("""
        SELECT vec_basic, vec_price, vec_facility, vec_safety FROM apt_vectors LIMIT 2
    """).fetchall()
    conn2.close()
    if len(rows) < 2:
        return
    t = parse_vectors(rows[0])
    c = parse_vectors(rows[1])
    score = calc_location(t, c)
    assert -1 <= score <= 1, f"코사인 유사도 범위 초과: {score}"


@test("유사추천: price 모드 유클리디안 유사도 0~1 범위")
def test_similar_price():
    from services.similarity import calc_price, parse_vectors
    conn = DictConnection()
    rows = conn.execute("SELECT vec_basic, vec_price, vec_facility, vec_safety FROM apt_vectors LIMIT 2").fetchall()
    conn.close()
    if len(rows) < 2:
        return
    t = parse_vectors(rows[0])
    c = parse_vectors(rows[1])
    score = calc_price(t, c)
    assert 0 <= score <= 1, f"유클리디안 유사도 범위 초과: {score}"


@test("유사추천: lifestyle 모드 선호도 점수 반환")
def test_similar_lifestyle():
    from services.similarity import calc_lifestyle, parse_vectors
    conn = DictConnection()
    row = conn.execute("SELECT vec_basic, vec_price, vec_facility, vec_safety FROM apt_vectors LIMIT 1").fetchone()
    conn.close()
    c = parse_vectors(row)
    score = calc_lifestyle(c, {"교통": 0.9, "교육": 0.7})
    assert isinstance(score, float), f"점수 타입 오류: {type(score)}"


@test("유사추천: combined 모드 include_price 옵션")
def test_similar_combined_price():
    from services.similarity import calc_combined, parse_vectors
    conn = DictConnection()
    rows = conn.execute("SELECT vec_basic, vec_price, vec_facility, vec_safety FROM apt_vectors LIMIT 2").fetchall()
    conn.close()
    if len(rows) < 2:
        return
    t = parse_vectors(rows[0])
    c = parse_vectors(rows[1])
    score_no_price = calc_combined(t, c, include_price=False)
    score_with_price = calc_combined(t, c, include_price=True)
    assert score_no_price != score_with_price, "include_price 옵션이 결과에 영향을 주지 않음"
```

- [ ] **Step 2: Run tests**

Run: `uv run python web/backend/tests/test_core.py`
Expected: 새로 추가한 5개 테스트 모두 PASS

- [ ] **Step 3: Commit**

```bash
git add web/backend/tests/test_core.py
git commit -m "test: 유사 아파트 추천 4개 모드 통합 테스트"
```

---

### Task 6: ml-features.md 문서 재작성

**Files:**
- Rewrite: `docs/ml-features.md`

- [ ] **Step 1: Rewrite ml-features.md**

`docs/superpowers/specs/2026-04-06-vector-redesign.md`의 섹션 1~2, 8을 기반으로
`docs/ml-features.md`를 재작성한다. 핵심 내용:

- 30차원 피처 그룹 (basic 4 + price 3 + facility 20 + safety 3)
- 4개 추천 모드 (location/price/lifestyle/combined) 표
- API 엔드포인트 (GET + POST)
- 벡터 재생성 명령어: `uv run python -m batch.ml.build_vectors`
- 넛지 스코어링 모델 섹션은 기존 유지 (XGBoost R2, feature importance 등)

기존 문서의 "향후 개선 방향"은 스펙에서 별도 작업으로 분리된 거리 곡선 보정만 남김.

- [ ] **Step 2: Commit**

```bash
git add docs/ml-features.md
git commit -m "docs: ml-features.md 30차원 피처 그룹 + 4개 모드로 재작성"
```

---

### Task 7: 최종 검증

- [ ] **Step 1: 배치 재실행 + API 테스트**

```bash
# 벡터 재생성
uv run python -m batch.ml.build_vectors

# 통합 테스트
uv run python web/backend/tests/test_core.py
```

- [ ] **Step 2: API 수동 테스트**

백엔드 서버 기동 후 (`cd web/backend && ../../.venv/bin/uvicorn main:app --reload --port 8000`):

```bash
# location 모드
curl -s "http://localhost:8000/api/apartment/$(uv run python -c "from batch.db import get_connection; c=get_connection(); cur=c.cursor(); cur.execute('SELECT pnu FROM apt_vectors LIMIT 1'); print(cur.fetchone()[0]); c.close()")/similar?mode=location&top_n=3" | python -m json.tool

# lifestyle 모드 (POST)
curl -s -X POST "http://localhost:8000/api/apartment/$(uv run python -c "from batch.db import get_connection; c=get_connection(); cur=c.cursor(); cur.execute('SELECT pnu FROM apt_vectors LIMIT 1'); print(cur.fetchone()[0]); c.close()")/similar/lifestyle" \
  -H "Content-Type: application/json" \
  -d '{"nudge_weights": {"교통": 0.9, "교육": 0.7}, "top_n": 3}' | python -m json.tool
```

Expected:
- location: `similarity_pct` 필드가 0~100 범위, top_n개 결과
- lifestyle: `preference_score` 필드, `nudge_weights_applied` 포함

- [ ] **Step 3: Commit all remaining changes**

```bash
git add -A
git commit -m "feat: 유사 아파트 추천 벡터 재설계 완료 (30차원 4그룹, 4개 모드)"
```
