"""Nudge scoring engine for apartment recommendations.

가중치/최대거리를 common_code 테이블에서 로드하고 캐시.
거리→점수 변환: 로그 감쇠 비선형 함수 (ML Feature Importance 기반 decay 파라미터)
밀도 반영: count_1km 기반 밀도 점수를 거리 점수와 블렌딩
"""

import math

from database import DictConnection

# 모듈 레벨 캐시 (서버 프로세스 내 1회 로드)
_max_distances: dict[str, float] | None = None
_nudge_weights: dict[str, dict[str, float]] | None = None


def _load_max_distances() -> dict[str, float]:
    global _max_distances
    if _max_distances is not None:
        return _max_distances
    conn = DictConnection()
    rows = conn.execute(
        "SELECT code, name FROM common_code WHERE group_id = %s", ["facility_distance"]
    ).fetchall()
    conn.close()
    _max_distances = {r["code"]: float(r["name"]) for r in rows}
    return _max_distances


def _load_nudge_weights() -> dict[str, dict[str, float]]:
    global _nudge_weights
    if _nudge_weights is not None:
        return _nudge_weights
    conn = DictConnection()
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s",
        ["nudge_weight"],
    ).fetchall()
    conn.close()
    _nudge_weights = {}
    for r in rows:
        # code = "nudge_id:subtype", name = subtype, extra = weight
        parts = r["code"].split(":", 1)
        if len(parts) == 2:
            nudge_id, _ = parts
            if nudge_id not in _nudge_weights:
                _nudge_weights[nudge_id] = {}
            _nudge_weights[nudge_id][r["name"]] = float(r["extra"])
    return _nudge_weights


def get_max_distances() -> dict[str, float]:
    return _load_max_distances()


def get_nudge_weights() -> dict[str, dict[str, float]]:
    return _load_nudge_weights()


def invalidate_cache() -> None:
    """모듈 레벨 캐시 리셋. 가중치/거리기준 수정 후 호출."""
    global _nudge_weights, _max_distances
    _nudge_weights = None
    _max_distances = None


# 시설별 로그 감쇠 파라미터 (ML Feature Importance 기반)
# decay 값이 클수록 먼 거리에서도 점수가 천천히 감소 (중요 시설)
# decay 값이 작을수록 가까운 거리에서만 높은 점수 (덜 중요한 시설)
FACILITY_DECAY: dict[str, float] = {
    "mart": 800,  # ML 가중치 29.3% — 가장 중요, 넓은 유효 범위
    "hospital": 700,  # ML 13.2% — 의료 접근성 중요
    "subway": 500,  # ML 11.5% — 교통 핵심
    "pharmacy": 400,  # ML 7.8%
    "animal_hospital": 350,  # ML 5.2%
    "convenience_store": 350,  # ML 4.8%
    "bus": 300,  # ML 4.2%
    "kindergarten": 400,  # ML 3.7%
    "library": 350,  # ML 3.4%
    "pet_facility": 300,  # ML 3.3%
    "cctv": 300,  # ML 3.2%
    "school": 400,  # ML 3.1%
    "fire_station": 250,  # ML 2.7%
    "park": 300,  # ML 2.5%
    "police": 250,  # ML 2.5%
}

# 시설별 밀도 환산 계수 (count_1km × factor → 0~100 점수)
# 평균 밀도가 높은 시설은 factor가 낮고, 희소한 시설은 factor가 높음
DENSITY_FACTOR: dict[str, float] = {
    "convenience_store": 5,  # 평균 ~15개/1km, 5×15=75
    "bus": 5,  # 평균 ~12개/1km
    "cctv": 3,  # 평균 ~20개/1km
    "pharmacy": 8,  # 평균 ~8개/1km
    "hospital": 8,  # 평균 ~6개/1km
    "mart": 15,  # 평균 ~3개/1km
    "school": 15,  # 평균 ~3개/1km
    "kindergarten": 10,  # 평균 ~5개/1km
    "park": 10,  # 평균 ~5개/1km
    "library": 25,  # 평균 ~2개/1km
    "subway": 25,  # 평균 ~2개/1km
    "pet_facility": 15,  # 평균 ~3개/1km
    "animal_hospital": 15,  # 평균 ~3개/1km
    "police": 50,  # 평균 ~1개/1km
    "fire_station": 50,  # 평균 ~1개/1km
}


def distance_to_score(distance_m: float | None, facility_subtype: str) -> float:
    """Convert a distance in meters to a 0-100 score (log-decay nonlinear).

    가까운 거리에서 점수가 급격히 높고, 먼 거리에서는 차이가 미미한 비선형 곡선.
    decay 파라미터로 시설별 유효 범위를 조절.
    """
    if distance_m is None:
        return 0.0
    max_d = _load_max_distances().get(facility_subtype, 3000)
    if distance_m >= max_d:
        return 0.0
    decay = FACILITY_DECAY.get(facility_subtype, 400)
    score = 100.0 * max(
        0.0, 1.0 - math.log(1 + distance_m / decay) / math.log(1 + max_d / decay)
    )
    return round(score, 2)


def density_to_score(count_1km: int | None, facility_subtype: str) -> float:
    """Convert facility count within 1km to a 0-100 score."""
    if not count_1km:
        return 0.0
    factor = DENSITY_FACTOR.get(facility_subtype, 10)
    return round(min(100.0, count_1km * factor), 2)


def facility_score(
    distance_m: float | None,
    count_1km: int | None,
    facility_subtype: str,
    distance_ratio: float = 0.7,
) -> float:
    """Calculate blended facility score: distance (70%) + density (30%)."""
    d_score = distance_to_score(distance_m, facility_subtype)
    n_score = density_to_score(count_1km, facility_subtype)
    return round(d_score * distance_ratio + n_score * (1.0 - distance_ratio), 2)


def calculate_nudge_score(
    facility_scores: dict[str, float],
    nudge_id: str,
    custom_weights: dict[str, float] | None = None,
) -> float:
    """Calculate weighted average score for a single nudge."""
    weights = (
        custom_weights if custom_weights else _load_nudge_weights().get(nudge_id, {})
    )
    if not weights:
        return 0.0

    total_weight = 0.0
    total_score = 0.0
    for subtype, w in weights.items():
        total_score += facility_scores.get(subtype, 0.0) * w
        total_weight += w

    if total_weight == 0:
        return 0.0
    return round(total_score / total_weight, 2)


def calculate_multi_nudge_score(
    facility_scores: dict[str, float],
    nudge_ids: list[str],
    custom_weights_map: dict[str, dict[str, float]] | None = None,
) -> float:
    """Calculate the mean score across multiple nudges."""
    if not nudge_ids:
        return 0.0
    scores = [
        calculate_nudge_score(
            facility_scores,
            nid,
            (custom_weights_map or {}).get(nid),
        )
        for nid in nudge_ids
    ]
    return round(sum(scores) / len(scores), 2)
