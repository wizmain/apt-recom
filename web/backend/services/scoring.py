"""Nudge scoring engine for apartment recommendations.

가중치/최대거리를 common_code 테이블에서 로드하고 캐시.
"""

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
        "SELECT code, name, extra FROM common_code WHERE group_id = %s", ["nudge_weight"]
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


def distance_to_score(distance_m: float | None, facility_subtype: str) -> float:
    """Convert a distance in meters to a 0-100 score."""
    if distance_m is None:
        return 0.0
    max_d = _load_max_distances().get(facility_subtype, 3000)
    if distance_m >= max_d:
        return 0.0
    return round(100.0 * (1.0 - distance_m / max_d), 2)


def calculate_nudge_score(
    facility_scores: dict[str, float],
    nudge_id: str,
    custom_weights: dict[str, float] | None = None,
) -> float:
    """Calculate weighted average score for a single nudge."""
    weights = custom_weights if custom_weights else _load_nudge_weights().get(nudge_id, {})
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
            facility_scores, nid,
            (custom_weights_map or {}).get(nid),
        )
        for nid in nudge_ids
    ]
    return round(sum(scores) / len(scores), 2)
