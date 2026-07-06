"""newlywed/senior 가중치 재배분 — 심평원 병원 세분화 반영 (Phase 2-3).

| 넛지     | 신규 subtype (가중치)                          | 기존 subtype 처리 |
|----------|--------------------------------------------------|--------------------|
| newlywed | pediatric_clinic (0.08) + obgyn_clinic (0.03)     | 기존 전체 × 0.89   |
| senior   | general_hospital (0.08)                           | 기존 전체 × 0.92   |

근거: 심평원 병원정보(getHospBasisList) 로 진료과목(소아청소년과/산부인과)·
병원급(상급종합+종합병원) 세분화를 `facilities` 에 적재(Task 1). 기존
`hospital`(전체 병의원) 은 유지하고, 신혼 넛지에는 소아과/산부인과 접근성,
시니어 넛지에는 종합병원(응급/중증 대응) 접근성을 신규 축으로 추가한다.

재배분/가드/CLI 로직은 weight_update_lib 공통 모듈 사용
(shrink 재배분, all-or-nothing 가드, 합 검증, 누적 희석 floor 가드).
적용 후 백엔드 재기동 필요 (_load_nudge_weights 캐시).

사용 (기본 dry-run):
  .venv/bin/python scripts/update_hospital_weights.py
  .venv/bin/python scripts/update_hospital_weights.py --apply
  .venv/bin/python scripts/update_hospital_weights.py --target railway --apply  # 사용자 직접
"""

from __future__ import annotations

from weight_update_lib import run_cli

# 넛지별 {신규 subtype: 신규 가중치}
HOSPITAL_ADDITIONS: dict[str, dict[str, float]] = {
    "newlywed": {"pediatric_clinic": 0.08, "obgyn_clinic": 0.03},
    "senior": {"general_hospital": 0.08},
}


if __name__ == "__main__":
    run_cli(HOSPITAL_ADDITIONS, description=__doc__)
