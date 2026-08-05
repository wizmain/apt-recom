"""investment 넛지 가중치 교체 — score_price → score_undervalue.

기존 score_price(시군구 평균 대비 저렴함)는 "저평가"와 "저급 단지"를 구분하지
못해 투자 넛지의 축으로 부적합하다. hedonic 잔차 기반 score_undervalue
(batch/ml/build_undervalue, 특성 통제 후 가격 괴리 백분위)로 동일 가중치 스왑.
타 축(subway/score_jeonse/hospital/bus/school/park)은 기존 값 유지.
cost 넛지의 score_price 는 변경하지 않는다 (가성비 = 저렴함이 맞는 축).

사용법:
  .venv/bin/python scripts/update_investment_weights.py                    # dry-run
  .venv/bin/python scripts/update_investment_weights.py --apply            # 로컬 반영
  .venv/bin/python scripts/update_investment_weights.py --target railway --apply
"""

from weight_update_lib import run_set_cli

# 2026-08-05 라이브 DB 값 기준 — score_price(0.2099)만 score_undervalue 로 스왑.
# 합 1.0001 은 기존 적재값의 반올림 잔차 (FULL_REPLACE_SUM_TOLERANCE ±0.001 이내).
INVESTMENT_WEIGHTS = {
    "subway": 0.2208,
    "score_undervalue": 0.2099,
    "score_jeonse": 0.1701,
    "hospital": 0.1090,
    "bus": 0.1009,
    "school": 0.0962,
    "park": 0.0932,
}

if __name__ == "__main__":
    run_set_cli(
        "investment",
        INVESTMENT_WEIGHTS,
        "investment 넛지: score_price → score_undervalue 스왑 (hedonic 저평가 축)",
    )
