"""nature 가중치 전면 재설계 — park + 에어코리아 대기질 (Phase 2-4).

| 넛지   | 기존 축 (제거)                              | 신규 축 (교체 후)             |
|--------|----------------------------------------------|---------------------------------|
| nature | park(.4868) / library(.2569) / pet_facility(.2563) | park(0.60) / score_air(0.40) |

근거: 진단 문서 §3.4 — nature 가 근접 시설(공원/도서관/반려동물시설) 밀도로만
평가되어 도시밀도가 높은 지역(강남 등)이 구조적으로 유리했다(§2.1 편향).
에어코리아 월평균 PM2.5 기반 `score_air`(백분위, apt_air_score — Phase 2-4
Task 1) 를 대기질 지표로 도입하고, library/pet_facility 는 nature 축에서만
제거한다 — 두 시설 데이터 자체와 다른 넛지(pet 넛지의 pet_facility 등)는
그대로 유지되며 영향받지 않는다 (사용자 승인 (a)안).

기존 additions+shrink 방식(update_hospital_weights.py 등)이 아니라 축 구성
자체를 다시 짜는 전면 교체이므로 weight_update_lib.set_nudge_weights() 를
사용한다 (floor 가드 미적용 — 재설정 자체가 의도된 재검토, lib docstring 참고).

사용 (기본 dry-run):
  .venv/bin/python scripts/update_nature_weights.py
  .venv/bin/python scripts/update_nature_weights.py --apply
  .venv/bin/python scripts/update_nature_weights.py --target railway --apply  # 사용자 직접 실행 전용, 이번 작업에서는 미실행
"""

from __future__ import annotations

from weight_update_lib import run_set_cli

NUDGE_ID = "nature"
NATURE_WEIGHTS: dict[str, float] = {"park": 0.60, "score_air": 0.40}


if __name__ == "__main__":
    run_set_cli(NUDGE_ID, NATURE_WEIGHTS, description=__doc__)
