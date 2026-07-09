"""education 가중치 재배분 — NEIS 학원(입시.검정 및 보습) 밀도 반영 (Phase 2-5).

| 넛지      | 신규 subtype (가중치) | 기존 subtype 처리 |
|-----------|------------------------|--------------------|
| education | academy (0.12)         | 기존 5축 × 0.88    |

근거: NEIS 학원·교습소 API 로 전국 입시.검정 및 보습 학원을 수집·적재(Task 1-2,
facilities.facility_subtype='academy', 39,458건 — 좌표 UNIQUE 로 같은 건물
학원을 대표 1건 압축). education 넛지는 "학군을 거리(assigned_elementary/
school)에서 질(kindergarten/park/library)+사교육 밀도로" 확장하는 마지막 축으로
academy 를 추가한다. shrink 후 기존 최소 축(school/library 0.15 → 0.132)이
MIN_AXIS_WEIGHT(0.05) 를 상회해 floor 가드는 미발동.

재배분/가드/CLI 로직은 weight_update_lib 공통 모듈 사용
(shrink 재배분, all-or-nothing 가드, 합 검증, 누적 희석 floor 가드).
적용 후 백엔드 재기동 필요 (_load_nudge_weights 캐시).

사용 (기본 dry-run):
  .venv/bin/python scripts/update_academy_weights.py
  .venv/bin/python scripts/update_academy_weights.py --apply
  .venv/bin/python scripts/update_academy_weights.py --target railway --apply  # 사용자 직접
"""

from __future__ import annotations

from weight_update_lib import run_cli

# 넛지별 {신규 subtype: 신규 가중치}
ACADEMY_ADDITIONS: dict[str, dict[str, float]] = {
    "education": {"academy": 0.12},
}


if __name__ == "__main__":
    run_cli(ACADEMY_ADDITIONS, description=__doc__)
