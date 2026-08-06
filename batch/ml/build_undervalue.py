"""저평가 점수(apt_price_score.undervalue_score) 배치 — hedonic 잔차 기반.

investment 넛지의 가격 축 재설계: 기존 score_price(시군구 평균 대비 저렴함)는
"저평가"와 "저급 단지"를 구분하지 못한다. 이 배치는 특성을 통제한 뒤 남는
가격 괴리(잔차)로 저평가를 측정한다.

정의:
    ln(㎡당가, 최근 2년 평균) ~ 시설 접근성(24종 ln거리+밀도) + 건물품질 +
                                대기질 + 통제(연식·세대·층·면적),
                                시군구 고정효과(within demean) OLS
    잔차 r = 실제 − 예측  (r < 0 = 특성 대비 싸다 = 저평가)
    undervalue_score = percentile_rank(−r) × 100   (전국 백분위, 높을수록 저평가)

한계 (docs/nudge-scoring-system.md 와 공유): 잔차에는 미관측 요인이 섞인다 —
고평가(잔차+)에는 재건축 기대 등 선반영 가치가, 저평가(잔차−)에는 미관측
결함이 포함될 수 있다. 절대적 투자 판단이 아니라 상대 지표로만 쓴다.

갱신 주기: batch/run.py trade 체인에서 recalc_price 직후 (12h) — 가격 라벨이
갱신된 시점과 정합. 라벨 없는 아파트(최근 2년 거래 없음)는 NULL 로 재설정되어
조립(facility_scores 4e)이 중립 50 으로 처리한다.

사용법:
  .venv/bin/python -m batch.ml.build_undervalue              # 계산 + DB 반영
  .venv/bin/python -m batch.ml.build_undervalue --self-test  # 합성 데이터 검증 (DB 불필요)
"""

import argparse

import numpy as np
import psycopg2.extras

from batch.db import get_connection
from batch.logger import setup_logger
from batch.ml.hedonic_validation import (
    MIN_SAMPLES,
    demean_by_group,
    load_dataset,
    ols,
)


def residual_to_score(residuals: np.ndarray) -> np.ndarray:
    """잔차 → 전국 백분위 점수 (0~100, 잔차가 작을수록(싸다) 높은 점수)."""
    neg = -residuals
    sorted_neg = np.sort(neg)
    ranks = np.searchsorted(sorted_neg, neg, side="right")
    return ranks / len(neg) * 100.0


def build_undervalue(conn, logger) -> int:
    """hedonic 잔차 기반 undervalue_score 계산 + upsert. 반환: 반영 행수."""
    y, x, names, sggs, pnus = load_dataset(conn, logger)
    if len(y) < MIN_SAMPLES:
        logger.warning(f"표본 부족: {len(y)} < {MIN_SAMPLES} — 저평가 점수 갱신 생략")
        return 0

    y_d, x_d = demean_by_group(y, x, sggs)
    beta, _t, r2 = ols(y_d, x_d)
    residuals = y_d - x_d @ beta
    scores = residual_to_score(residuals)
    logger.info(
        f"  hedonic 잔차: 표본 {len(y):,}, within R² {r2:.4f}, "
        f"잔차 std {residuals.std():.4f}"
    )

    cur = conn.cursor()
    # 라벨 윈도(최근 2년)에서 빠진 아파트의 구 점수가 남지 않도록 전체 NULL 후 반영.
    cur.execute("UPDATE apt_price_score SET undervalue_score = NULL")
    # 라벨은 있으나 apt_price_score 행이 아직 없는 아파트도 수용 (upsert) —
    # 나머지 컬럼은 recalc_price 가 다음 실행에서 채운다.
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO apt_price_score (pnu, undervalue_score)
        VALUES %s
        ON CONFLICT (pnu) DO UPDATE SET undervalue_score = EXCLUDED.undervalue_score
        """,
        [(pnu, round(float(s), 2)) for pnu, s in zip(pnus, scores)],
        page_size=5000,
    )
    conn.commit()
    logger.info(f"  저평가 점수 반영: {len(pnus):,}건")
    return len(pnus)


def self_test() -> None:
    """합성 데이터 검증 (DB 불필요): 알려진 할인 그룹이 고득점을 복원하는지.

    y = x·β + 시군구 고정효과 + noise 에서 일부 아파트에만 가격 할인(-0.2)을
    주입 — 잔차 경로가 그 할인을 복원해 할인 그룹의 점수가 상위로 몰려야 한다.
    """
    rng = np.random.default_rng(42)
    n = 6000
    x = rng.normal(size=(n, 4))
    beta_true = np.array([0.3, -0.8, 0.5, 0.0])
    groups = rng.choice(np.array(["g1", "g2", "g3", "g4"]), size=n)
    fe = {"g1": 2.0, "g2": -1.0, "g3": 4.0, "g4": 0.5}
    y = x @ beta_true + np.array([fe[g] for g in groups]) + rng.normal(scale=0.05, size=n)

    discounted = rng.choice(n, size=300, replace=False)
    y[discounted] -= 0.2  # 특성 대비 20% 저렴 (ln 스케일)

    y_d, x_d = demean_by_group(y, x, groups)
    beta, _t, r2 = ols(y_d, x_d)
    scores = residual_to_score(y_d - x_d @ beta)

    mean_disc = scores[discounted].mean()
    mask = np.ones(n, dtype=bool)
    mask[discounted] = False
    mean_rest = scores[mask].mean()
    assert mean_disc > 95.0, f"할인 그룹 점수 과소: {mean_disc:.1f}"
    assert 45.0 < mean_rest < 55.0, f"비할인 그룹이 중립을 벗어남: {mean_rest:.1f}"
    assert r2 > 0.9, f"R² 과소: {r2}"
    # 백분위 성질: 전체 평균 ≈ 50, 범위 (0, 100]
    assert 49.0 < scores.mean() < 51.0 and scores.max() <= 100.0 and scores.min() > 0.0
    print(
        f"self-test PASS: 할인그룹 평균 {mean_disc:.1f} / 비할인 {mean_rest:.1f} / r2 {r2:.4f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test", action="store_true", help="합성 데이터 검증 (DB 불필요)"
    )
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    logger = setup_logger("build_undervalue")
    conn = get_connection()
    try:
        build_undervalue(conn, logger)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
