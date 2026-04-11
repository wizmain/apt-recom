"""Nudge scoring engine for apartment recommendations.

가중치/최대거리를 common_code 테이블에서 로드하고 캐시.
거리→점수 변환: 로그 감쇠 비선형 함수 (ML Feature Importance 기반 decay 파라미터)
밀도 반영: count_1km 기반 밀도 점수를 거리 점수와 블렌딩
프로필별 파라미터: metro / major_city / provincial 3단계 지역 프로필
"""

import math

from database import DictConnection

# ---------------------------------------------------------------------------
# 지역 프로필 매핑 (시도코드 → profile)
# ---------------------------------------------------------------------------
_region_profiles: dict[str, str] | None = None

_DEFAULT_REGION_PROFILES: dict[str, str] = {
    "11": "metro", "28": "metro", "41": "metro",
    "26": "major_city", "27": "major_city", "29": "major_city",
    "30": "major_city", "31": "major_city", "36": "major_city",
    "42": "provincial", "43": "provincial", "44": "provincial",
    "45": "provincial", "46": "provincial", "47": "provincial",
    "48": "provincial", "50": "provincial",
}


def _load_region_profiles() -> dict[str, str]:
    global _region_profiles
    if _region_profiles is not None:
        return _region_profiles
    conn = DictConnection()
    rows = conn.execute(
        "SELECT code, name FROM common_code WHERE group_id = %s",
        ["region_profile"],
    ).fetchall()
    conn.close()
    if rows:
        _region_profiles = {r["code"]: r["name"] for r in rows}
    else:
        _region_profiles = _DEFAULT_REGION_PROFILES.copy()
    return _region_profiles


def get_region_profile(sigungu_code: str | None) -> str:
    """시군구코드 → 프로필(metro/major_city/provincial) 반환."""
    profiles = _load_region_profiles()
    sido = (sigungu_code or "")[:2]
    return profiles.get(sido, "provincial")


# ---------------------------------------------------------------------------
# 모듈 레벨 캐시 (서버 프로세스 내 1회 로드)
# ---------------------------------------------------------------------------
_max_distances: dict[str, float] | None = None
_max_distances_by_profile: dict[str, dict[str, float]] | None = None
_nudge_weights: dict[str, dict[str, float]] | None = None
_facility_decay_by_profile: dict[str, dict[str, float]] | None = None
_density_factor_by_profile: dict[str, dict[str, float]] | None = None


# ---------------------------------------------------------------------------
# 기본값 (metro 프로필 기준, DB에 데이터 없을 때 fallback)
# ---------------------------------------------------------------------------

# 시설별 로그 감쇠 파라미터 (ML Feature Importance 기반)
_DEFAULT_FACILITY_DECAY: dict[str, float] = {
    "mart": 800,
    "hospital": 700,
    "subway": 500,
    "pharmacy": 400,
    "animal_hospital": 350,
    "convenience_store": 350,
    "bus": 300,
    "kindergarten": 400,
    "library": 350,
    "pet_facility": 300,
    "cctv": 300,
    "school": 400,
    "fire_station": 250,
    "park": 300,
    "police": 250,
}

# 시설별 밀도 환산 계수 (count_1km × factor → 0~100 점수)
_DEFAULT_DENSITY_FACTOR: dict[str, float] = {
    "convenience_store": 5,
    "bus": 5,
    "cctv": 3,
    "pharmacy": 8,
    "hospital": 8,
    "mart": 15,
    "school": 15,
    "kindergarten": 10,
    "park": 10,
    "library": 25,
    "subway": 25,
    "pet_facility": 15,
    "animal_hospital": 15,
    "police": 50,
    "fire_station": 50,
}

# 프로필별 배율 (metro=1.0 기준)
_DECAY_MULTIPLIER = {"metro": 1.0, "major_city": 1.3, "provincial": 1.8}
_DENSITY_MULTIPLIER = {"metro": 1.0, "major_city": 1.5, "provincial": 2.0}
_MAX_DIST_MULTIPLIER = {"metro": 1.0, "major_city": 1.3, "provincial": 1.6}


# ---------------------------------------------------------------------------
# 로더 함수들
# ---------------------------------------------------------------------------

def _load_max_distances() -> dict[str, float]:
    """기존 호환: 글로벌 max_distance (facility_distance group)."""
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


def _load_max_distances_by_profile() -> dict[str, dict[str, float]]:
    """프로필별 max_distance 로드. 프로필별 group 없으면 글로벌에 배율 적용."""
    global _max_distances_by_profile
    if _max_distances_by_profile is not None:
        return _max_distances_by_profile

    base = _load_max_distances()
    conn = DictConnection()
    result: dict[str, dict[str, float]] = {}

    for profile in ("metro", "major_city", "provincial"):
        rows = conn.execute(
            "SELECT code, name FROM common_code WHERE group_id = %s",
            [f"facility_distance_{profile}"],
        ).fetchall()
        if rows:
            result[profile] = {r["code"]: float(r["name"]) for r in rows}
        else:
            mult = _MAX_DIST_MULTIPLIER.get(profile, 1.0)
            result[profile] = {k: round(v * mult, 1) for k, v in base.items()}

    conn.close()
    _max_distances_by_profile = result
    return result


def _load_facility_decay_by_profile() -> dict[str, dict[str, float]]:
    """프로필별 decay 로드. DB에 없으면 기본값에 배율 적용."""
    global _facility_decay_by_profile
    if _facility_decay_by_profile is not None:
        return _facility_decay_by_profile

    conn = DictConnection()
    result: dict[str, dict[str, float]] = {}

    for profile in ("metro", "major_city", "provincial"):
        rows = conn.execute(
            "SELECT code, name FROM common_code WHERE group_id = %s",
            [f"facility_decay_{profile}"],
        ).fetchall()
        if rows:
            result[profile] = {r["code"]: float(r["name"]) for r in rows}
        else:
            mult = _DECAY_MULTIPLIER.get(profile, 1.0)
            result[profile] = {k: round(v * mult) for k, v in _DEFAULT_FACILITY_DECAY.items()}

    conn.close()
    _facility_decay_by_profile = result
    return result


def _load_density_factor_by_profile() -> dict[str, dict[str, float]]:
    """프로필별 density factor 로드. DB에 없으면 기본값에 배율 적용."""
    global _density_factor_by_profile
    if _density_factor_by_profile is not None:
        return _density_factor_by_profile

    conn = DictConnection()
    result: dict[str, dict[str, float]] = {}

    for profile in ("metro", "major_city", "provincial"):
        rows = conn.execute(
            "SELECT code, name FROM common_code WHERE group_id = %s",
            [f"density_factor_{profile}"],
        ).fetchall()
        if rows:
            result[profile] = {r["code"]: float(r["name"]) for r in rows}
        else:
            mult = _DENSITY_MULTIPLIER.get(profile, 1.0)
            result[profile] = {k: round(v * mult, 1) for k, v in _DEFAULT_DENSITY_FACTOR.items()}

    conn.close()
    _density_factor_by_profile = result
    return result


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
        parts = r["code"].split(":", 1)
        if len(parts) == 2:
            nudge_id, _ = parts
            if nudge_id not in _nudge_weights:
                _nudge_weights[nudge_id] = {}
            _nudge_weights[nudge_id][r["name"]] = float(r["extra"])
    return _nudge_weights


# ---------------------------------------------------------------------------
# 공개 API: 캐시 접근 + 무효화
# ---------------------------------------------------------------------------

def get_max_distances() -> dict[str, float]:
    return _load_max_distances()


def get_nudge_weights() -> dict[str, dict[str, float]]:
    return _load_nudge_weights()


def invalidate_cache() -> None:
    """모듈 레벨 캐시 리셋. 가중치/거리기준 수정 후 호출."""
    global _nudge_weights, _max_distances, _max_distances_by_profile
    global _region_profiles, _facility_decay_by_profile, _density_factor_by_profile
    _nudge_weights = None
    _max_distances = None
    _max_distances_by_profile = None
    _region_profiles = None
    _facility_decay_by_profile = None
    _density_factor_by_profile = None


# ---------------------------------------------------------------------------
# 점수 계산 함수
# ---------------------------------------------------------------------------

def distance_to_score(
    distance_m: float | None,
    facility_subtype: str,
    profile: str = "metro",
) -> float:
    """거리 → 0~100 점수 (로그 감쇠 비선형, 프로필별 파라미터)."""
    if distance_m is None:
        return 0.0
    max_d_map = _load_max_distances_by_profile()
    max_d = max_d_map.get(profile, {}).get(facility_subtype, 3000)
    if distance_m >= max_d:
        return 0.0
    decay_map = _load_facility_decay_by_profile()
    decay = decay_map.get(profile, _DEFAULT_FACILITY_DECAY).get(facility_subtype, 400)
    score = 100.0 * max(
        0.0, 1.0 - math.log(1 + distance_m / decay) / math.log(1 + max_d / decay)
    )
    return round(score, 2)


def density_to_score(
    count_1km: int | None,
    facility_subtype: str,
    profile: str = "metro",
) -> float:
    """1km 내 시설 수 → 0~100 점수 (프로필별 factor)."""
    if not count_1km:
        return 0.0
    factor_map = _load_density_factor_by_profile()
    factor = factor_map.get(profile, _DEFAULT_DENSITY_FACTOR).get(facility_subtype, 10)
    return round(min(100.0, count_1km * factor), 2)


def facility_score(
    distance_m: float | None,
    count_1km: int | None,
    facility_subtype: str,
    distance_ratio: float = 0.7,
    profile: str = "metro",
) -> float:
    """거리(70%) + 밀도(30%) 블렌딩 점수 (프로필별 파라미터).

    지하철 인프라가 없는 비수도권 아파트는 중립 점수 50점 반환.
    """
    # 지하철 인프라가 없는 비수도권: 중립 점수 50점
    # distance=None 또는 max_distance 초과 + 1km 내 0개 → 인프라 부재로 판단
    if facility_subtype == "subway" and profile != "metro" and not count_1km:
        if distance_m is None:
            return 50.0
        max_d_map = _load_max_distances_by_profile()
        max_d = max_d_map.get(profile, {}).get("subway", 3000)
        if distance_m >= max_d:
            return 50.0

    d_score = distance_to_score(distance_m, facility_subtype, profile)
    n_score = density_to_score(count_1km, facility_subtype, profile)
    return round(d_score * distance_ratio + n_score * (1.0 - distance_ratio), 2)


def calculate_nudge_score(
    facility_scores: dict[str, float],
    nudge_id: str,
    custom_weights: dict[str, float] | None = None,
) -> float:
    """단일 넛지의 가중 평균 점수."""
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
    """복수 넛지의 평균 점수."""
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
