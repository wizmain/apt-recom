"""모드별 유사도/선호도 계산 서비스.

추천 모드 4가지(location, price, lifestyle, combined)에 대해
유사도/선호도 점수를 계산하는 순수 계산 모듈.
DB 접근이나 HTTP 레이어 의존 없이 numpy 연산만 수행한다.
"""

import numpy as np

# ---------------------------------------------------------------------------
# 상수 정의
# ---------------------------------------------------------------------------

# 모드별 그룹 가중치
GROUP_WEIGHTS: dict[str, dict[str, float]] = {
    "location": {"facility": 0.75, "safety": 0.25},
    "combined": {"basic": 0.25, "facility": 0.50, "safety": 0.25},
    "combined_with_price": {
        "basic": 0.2125,
        "facility": 0.425,
        "safety": 0.2125,
        "price": 0.15,
    },
}

# 모드별 기본 hard filter
DEFAULT_FILTERS: dict[str, dict[str, float]] = {
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
NUDGE_FACILITY_MAP: dict[str, dict[str, list[int]]] = {
    "교통": {"count": [0, 1], "dist": [15]},
    "교육": {"count": [2, 3, 8], "dist": [16]},
    "의료": {"count": [4, 9], "dist": [19]},
    "생활편의": {"count": [6, 7], "dist": [18]},
    "자연환경": {"count": [5], "dist": [17]},
    "반려동물": {"count": [10, 11], "dist": []},
    "안전": {"count": [12, 13, 14], "dist": []},
}

FACILITY_VECTOR_DIM = 20
DEFAULT_NUDGE_WEIGHT = 0.1

# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """코사인 유사도. norm이 0이면 0.0 반환."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _euclidean_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """유클리드 거리 기반 유사도. 1 / (1 + distance)."""
    dist = np.linalg.norm(a - b)
    return float(1.0 / (1.0 + dist))


def _apply_group_weights(
    vectors: dict[str, np.ndarray],
    weights: dict[str, float],
) -> np.ndarray:
    """그룹별 가중치를 곱한 뒤 연결(concatenate)하여 단일 벡터 반환.

    weights에 포함된 그룹만 사용한다.
    vectors에 해당 그룹이 없으면 건너뛴다.
    """
    parts: list[np.ndarray] = []
    for group, weight in weights.items():
        if group in vectors:
            parts.append(vectors[group] * weight)
    if not parts:
        return np.array([], dtype=np.float64)
    return np.concatenate(parts)


def _build_nudge_weights_vector(nudge_weights: dict[str, float]) -> np.ndarray:
    """넛지 카테고리 가중치를 20차원 facility 가중치 벡터로 변환.

    규칙:
    - 카테고리 가중치를 해당 카테고리의 피처 수로 나누어 균등 분배
    - dist 피처는 음수 가중치 (StandardScaler 적용 후 큰 값 = 먼 거리이므로)
    - 매핑되지 않은 피처는 DEFAULT_NUDGE_WEIGHT 적용
    """
    weights = np.full(FACILITY_VECTOR_DIM, DEFAULT_NUDGE_WEIGHT, dtype=np.float64)

    # 매핑된 인덱스 추적 (나중에 기본값 유지 여부 판단)
    mapped_indices: set[int] = set()

    for category, category_weight in nudge_weights.items():
        mapping = NUDGE_FACILITY_MAP.get(category)
        if mapping is None:
            continue

        count_indices = mapping["count"]
        dist_indices = mapping["dist"]
        total_features = len(count_indices) + len(dist_indices)
        if total_features == 0:
            continue

        per_feature = category_weight / total_features

        for idx in count_indices:
            weights[idx] = per_feature
            mapped_indices.add(idx)

        for idx in dist_indices:
            # dist는 음수 (가까울수록 좋음 -> 스케일된 값이 작을수록 좋음)
            weights[idx] = -per_feature
            mapped_indices.add(idx)

    return weights


# ---------------------------------------------------------------------------
# DB row 파싱
# ---------------------------------------------------------------------------


def parse_vectors(row: dict) -> dict[str, np.ndarray]:
    """DB 행(dict)에서 서브벡터를 numpy 배열 dict로 변환.

    DB 컬럼: vec_basic, vec_price, vec_facility, vec_safety
    """
    return {
        "basic": np.array(row["vec_basic"], dtype=np.float64),
        "price": np.array(row["vec_price"], dtype=np.float64),
        "facility": np.array(row["vec_facility"], dtype=np.float64),
        "safety": np.array(row["vec_safety"], dtype=np.float64),
    }


# ---------------------------------------------------------------------------
# 모드별 유사도 계산
# ---------------------------------------------------------------------------


def calc_location(
    target: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
) -> float:
    """위치/환경 유사도 — facility + safety 가중 코사인 유사도."""
    weights = GROUP_WEIGHTS["location"]
    vec_t = _apply_group_weights(target, weights)
    vec_c = _apply_group_weights(candidate, weights)
    return _cosine_similarity(vec_t, vec_c)


def calc_price(
    target: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
) -> float:
    """가격 유사도 — price 서브벡터 유클리드 유사도."""
    return _euclidean_similarity(target["price"], candidate["price"])


def calc_lifestyle(
    candidate: dict[str, np.ndarray],
    nudge_weights: dict[str, float],
) -> float:
    """라이프스타일 선호도 — facility 벡터와 넛지 가중치의 내적."""
    weight_vec = _build_nudge_weights_vector(nudge_weights)
    return float(np.dot(candidate["facility"], weight_vec))


def calc_combined(
    target: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
    include_price: bool = False,
) -> float:
    """종합 유사도 — basic + facility + safety (+ price) 가중 코사인 유사도."""
    weight_key = "combined_with_price" if include_price else "combined"
    weights = GROUP_WEIGHTS[weight_key]
    vec_t = _apply_group_weights(target, weights)
    vec_c = _apply_group_weights(candidate, weights)
    return _cosine_similarity(vec_t, vec_c)
