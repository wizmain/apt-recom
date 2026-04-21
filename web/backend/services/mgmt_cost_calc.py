"""관리비 안분 계산 유틸.

K-APT 관리비 부과 원칙:
  - 공용관리비·장충금: 관리비부과면적 비례 부과 (세대별 전용면적으로 근사)
  - 개별사용료: 세대별 실사용(평균으로 근사)

공식:
    per_unit(주택형) =
        (common_cost + repair_fund) × (exclusive_area / priv_area_total)
      + (individual_cost / total_unit_count)

표시 단위:
  - K-APT 엑셀은 주택형을 소수점 3자리(예: 84.813, 84.891, 84.947, 84.990 등
    동일 "84타입" 아래 다수의 세부 타입)로 제공.
  - UI 는 한국 부동산 관행대로 "전용면적 정수(=평형 기준)"로 묶어 표시.
    59.981 → 59, 84.813~84.990 → 84, 114.844~114.977 → 114, 141.979 → 141.
"""


def compute_by_area(latest_cost: dict, area_types: list[dict]) -> list[dict] | None:
    """주택형별 월 관리비 계산 + 정수 면적(평형) 기준 그룹화.

    Args:
        latest_cost: apt_mgmt_cost 최신월 row. common_cost/individual_cost/repair_fund 필요.
        area_types: apt_area_type row 목록. exclusive_area/unit_count/priv_area_total 필요.

    Returns:
        평형별 집계 목록. 각 항목:
          exclusive_area: int (그룹 대표 면적 = floor)
          unit_count:     세대수 합
          per_unit_cost:  세대수 가중 평균
          area_min/max:   그룹 내 세부 전용면적 범위(소수 2자리)
          subtype_count:  그룹 내 세부 주택형 개수
        계산 불가(데이터 결측) 시 None.
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

    # 1) 세부 주택형별 per_unit 계산
    subtypes = [
        {
            "exclusive_area": float(r["exclusive_area"]),
            "unit_count": int(r["unit_count"]),
            "per_unit_cost": common_repair * (float(r["exclusive_area"]) / priv_total) + indiv_per_unit,
        }
        for r in area_types
    ]

    # 2) 정수 면적(=평형) 기준으로 그룹화. 59.xx → 59, 84.xx → 84 ...
    groups: dict[int, dict] = {}
    for s in subtypes:
        key = int(s["exclusive_area"])  # Python int() = floor for positive
        g = groups.setdefault(
            key,
            {
                "exclusive_area": key,
                "unit_count": 0,
                "cost_sum": 0.0,
                "area_min": s["exclusive_area"],
                "area_max": s["exclusive_area"],
                "subtype_count": 0,
            },
        )
        g["unit_count"] += s["unit_count"]
        g["cost_sum"] += s["per_unit_cost"] * s["unit_count"]
        g["area_min"] = min(g["area_min"], s["exclusive_area"])
        g["area_max"] = max(g["area_max"], s["exclusive_area"])
        g["subtype_count"] += 1

    return [
        {
            "exclusive_area": g["exclusive_area"],
            "unit_count": g["unit_count"],
            "per_unit_cost": round(g["cost_sum"] / g["unit_count"]) if g["unit_count"] else 0,
            "area_min": round(g["area_min"], 2),
            "area_max": round(g["area_max"], 2),
            "subtype_count": g["subtype_count"],
        }
        for key in sorted(groups)
        for g in [groups[key]]
    ]
