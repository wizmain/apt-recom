"""관리비 안분 계산 유틸.

K-APT 관리비 부과 원칙:
  - 공용관리비·장충금: 관리비부과면적 비례 부과 (세대별 전용면적으로 근사)
  - 개별사용료: 세대별 실사용(평균으로 근사)

공식:
    per_unit(주택형) =
        (common_cost + repair_fund) × (exclusive_area / priv_area_total)
      + (individual_cost / total_unit_count)

- 공용+장충금 항은 단지 총액을 "세대 전용면적 ÷ 단지 전체 전용면적" 으로 분할.
- priv_area_total 자체가 단지 전체 전용면적 합이므로 세대 개수로 다시 나눌 필요 없음.
"""


def compute_by_area(latest_cost: dict, area_types: list[dict]) -> list[dict] | None:
    """주택형별 월 관리비 계산.

    Args:
        latest_cost: apt_mgmt_cost 최신월 row. common_cost/individual_cost/repair_fund 필요.
        area_types: apt_area_type row 목록. exclusive_area/unit_count/priv_area_total 필요.

    Returns:
        주택형별 per_unit_cost 목록. 계산 불가(데이터 결측)시 None.
    """
    if not area_types or not latest_cost:
        return None

    total_units = sum(int(r.get("unit_count") or 0) for r in area_types)
    if total_units <= 0:
        return None

    priv_total = float(area_types[0].get("priv_area_total") or 0)
    if priv_total <= 0:
        return None

    common_repair = int(latest_cost.get("common_cost") or 0) + int(latest_cost.get("repair_fund") or 0)
    individual = int(latest_cost.get("individual_cost") or 0)
    indiv_per_unit = individual / total_units

    return [
        {
            "exclusive_area": float(r["exclusive_area"]),
            "unit_count": int(r["unit_count"]),
            "per_unit_cost": round(
                common_repair * (float(r["exclusive_area"]) / priv_total) + indiv_per_unit
            ),
        }
        for r in area_types
    ]
