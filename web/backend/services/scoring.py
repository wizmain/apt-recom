"""Nudge scoring engine for apartment recommendations."""

# Maximum expected distance (meters) per facility subtype, used for score normalization.
# A facility at 0m scores 100; at MAX_DISTANCE or beyond scores 0.
MAX_DISTANCES: dict[str, float] = {
    "subway": 3000,
    "bus": 1500,
    "park": 2000,
    "hospital": 3000,
    "pharmacy": 1500,
    "school": 2000,
    "kindergarten": 2000,
    "library": 3000,
    "mart": 2000,
    "convenience_store": 1000,
    "police": 3000,
    "fire_station": 5000,
    "pet_facility": 3000,
    "animal_hospital": 3000,
    "cctv": 1000,
}

# Each nudge maps facility_subtypes to weights (must sum to ~1.0 per nudge).
NUDGE_WEIGHTS: dict[str, dict[str, float]] = {
    "cost": {
        "_price": 0.30,
        "_jeonse": 0.15,
        "_safety": 0.05,
        "subway": 0.15,
        "bus": 0.10,
        "mart": 0.10,
        "convenience_store": 0.10,
        "pharmacy": 0.05,
    },
    "pet": {
        "pet_facility": 0.35,
        "animal_hospital": 0.30,
        "park": 0.35,
    },
    "commute": {
        "subway": 0.45,
        "bus": 0.35,
        "convenience_store": 0.20,
    },
    "newlywed": {
        "_safety": 0.10,
        "subway": 0.10,
        "mart": 0.10,
        "hospital": 0.15,
        "park": 0.15,
        "kindergarten": 0.20,
        "school": 0.20,
    },
    "education": {
        "school": 0.30,
        "kindergarten": 0.25,
        "library": 0.25,
        "park": 0.20,
    },
    "senior": {
        "_safety": 0.10,
        "hospital": 0.25,
        "pharmacy": 0.20,
        "park": 0.15,
        "bus": 0.10,
        "convenience_store": 0.20,
    },
    "investment": {
        "_price": 0.25,
        "_jeonse": 0.20,
        "subway": 0.20,
        "bus": 0.10,
        "park": 0.10,
        "school": 0.10,
        "hospital": 0.05,
    },
    "nature": {
        "park": 0.50,
        "library": 0.25,
        "pet_facility": 0.25,
    },
    "safety": {
        "_safety": 0.25,
        "_crime": 0.25,
        "police": 0.15,
        "fire_station": 0.10,
        "cctv": 0.15,
        "convenience_store": 0.05,
        "park": 0.05,
    },
}


def distance_to_score(distance_m: float | None, facility_subtype: str) -> float:
    """Convert a distance in meters to a 0-100 score.

    Closer is better. Returns 0 if distance is None or >= MAX_DISTANCE.
    """
    if distance_m is None:
        return 0.0
    max_d = MAX_DISTANCES.get(facility_subtype, 3000)
    if distance_m >= max_d:
        return 0.0
    return round(100.0 * (1.0 - distance_m / max_d), 2)


def calculate_nudge_score(
    facility_scores: dict[str, float],
    nudge_id: str,
    custom_weights: dict[str, float] | None = None,
) -> float:
    """Calculate weighted average score for a single nudge.

    Args:
        facility_scores: {facility_subtype: score_0_to_100}
        nudge_id: one of the NUDGE_WEIGHTS keys
        custom_weights: optional override for the weights of this nudge
    """
    weights = custom_weights if custom_weights else NUDGE_WEIGHTS.get(nudge_id, {})
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
