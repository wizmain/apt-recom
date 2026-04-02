"""넛지 스코어링 모델 학습 — 실거래가 기반 비선형 가중치.

거래가(y) ~ 시설 거리/개수(X) 회귀 모델을 학습하여:
1. 비선형 거리→점수 변환 함수 추출 (PDP)
2. 시설별 가격 기여도 기반 가중치 산출

사용법:
  python -m batch.ml.train_scoring
"""

import json
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error
import xgboost as xgb
import joblib

from batch.db import get_connection
from batch.logger import setup_logger
from batch.ml.build_vectors import FACILITY_SUBTYPES

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_DIR.mkdir(exist_ok=True)


def main():
    logger = setup_logger("train_scoring")
    conn = get_connection()
    cur = conn.cursor()

    logger.info("학습 데이터 생성 중...")

    # 아파트별 평균 ㎡당 가격 (label)
    cur.execute("""
        SELECT m.pnu, AVG(t.deal_amount / NULLIF(t.exclu_use_ar, 0)) as price_m2
        FROM trade_history t
        JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        WHERE t.deal_amount > 0 AND t.exclu_use_ar > 0
        GROUP BY m.pnu
    """)
    price_map = {row[0]: row[1] for row in cur.fetchall() if row[1] and row[1] > 0}
    logger.info(f"가격 라벨: {len(price_map):,}건")

    # 아파트 기본 정보
    cur.execute("""
        SELECT a.pnu, a.total_hhld_cnt, a.max_floor, a.use_apr_day,
               COALESCE(ai.avg_area, 60) as avg_area
        FROM apartments a
        LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
        WHERE a.group_pnu = a.pnu AND a.lat IS NOT NULL
    """)
    apt_info = {}
    for row in cur.fetchall():
        pnu = row[0]
        try:
            age = 2026 - int(str(row[3])[:4]) if row[3] else 20
        except (ValueError, TypeError):
            age = 20
        apt_info[pnu] = [age, row[1] or 100, row[2] or 15, row[4] or 60]

    # 시설 거리/개수
    cur.execute("SELECT pnu, facility_subtype, nearest_distance_m, count_1km FROM apt_facility_summary")
    facility_map: dict[str, dict] = {}
    for row in cur.fetchall():
        if row[0] not in facility_map:
            facility_map[row[0]] = {}
        facility_map[row[0]][row[1]] = (row[2] or 5000, row[3] or 0)

    conn.close()

    # 학습 데이터 조합
    feature_names = (
        ["building_age", "total_hhld_cnt", "max_floor", "avg_area"]
        + [f"{s}_dist" for s in FACILITY_SUBTYPES]
        + [f"{s}_count_1km" for s in FACILITY_SUBTYPES]
    )

    X_data = []
    y_data = []
    pnus = []

    for pnu, price in price_map.items():
        if pnu not in apt_info or pnu not in facility_map:
            continue

        basic = apt_info[pnu]
        fac = facility_map[pnu]
        fac_dist = [fac.get(s, (5000, 0))[0] for s in FACILITY_SUBTYPES]
        fac_count = [fac.get(s, (5000, 0))[1] for s in FACILITY_SUBTYPES]

        X_data.append(basic + fac_dist + fac_count)
        y_data.append(price)
        pnus.append(pnu)

    X = np.array(X_data, dtype=np.float64)
    y = np.array(y_data, dtype=np.float64)
    X = np.nan_to_num(X, nan=0.0)

    logger.info(f"학습 데이터: {len(X):,}건 x {len(feature_names)}피처")

    # Train/Val 분할
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
    logger.info(f"Train: {len(X_train):,} / Val: {len(X_val):,}")

    # XGBoost 학습
    logger.info("XGBoost 학습 시작...")
    model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    # 성능 평가
    y_pred = model.predict(X_val)
    r2 = r2_score(y_val, y_pred)
    mae = mean_absolute_error(y_val, y_pred)
    logger.info(f"검증 성능: R² = {r2:.4f}, MAE = {mae:.1f}만원/㎡")

    # Feature Importance
    importances = model.feature_importances_
    feat_imp = sorted(zip(feature_names, importances), key=lambda x: -x[1])
    logger.info("Feature Importance (Top 15):")
    for name, imp in feat_imp[:15]:
        logger.info(f"  {name:25s} {imp:.4f}")

    # 비선형 거리→점수 함수 추출 (PDP 근사)
    logger.info("비선형 거리→점수 함수 추출 중...")
    distance_curves = {}
    for i, subtype in enumerate(FACILITY_SUBTYPES):
        feat_idx = 4 + i  # basic 4개 뒤 distance 시작
        distances = np.linspace(0, 5000, 50)
        X_pdp = np.tile(np.median(X_train, axis=0), (50, 1))
        X_pdp[:, feat_idx] = distances
        predictions = model.predict(X_pdp)
        # 정규화: 0m 예측값 = 100점, 최대 거리 = 0점
        scores = predictions - predictions.min()
        if scores.max() > 0:
            scores = scores / scores.max() * 100
        scores = scores[::-1]  # 가까울수록 높은 점수
        distance_curves[subtype] = {
            "distances": distances.tolist(),
            "scores": scores.tolist(),
        }

    # 모델 + 곡선 저장
    model_path = MODEL_DIR / "scoring_model.joblib"
    joblib.dump(model, model_path)
    logger.info(f"모델 저장: {model_path}")

    curves_path = MODEL_DIR / "distance_curves.json"
    curves_path.write_text(json.dumps(distance_curves, ensure_ascii=False))
    logger.info(f"거리 곡선 저장: {curves_path}")

    # 넛지 가중치 산출 (시설별 importance 기반)
    logger.info("넛지 가중치 산출...")
    facility_importance = {}
    for name, imp in feat_imp:
        for subtype in FACILITY_SUBTYPES:
            if subtype in name:
                facility_importance[subtype] = facility_importance.get(subtype, 0) + imp

    # 정규화
    total_imp = sum(facility_importance.values()) or 1
    for k in facility_importance:
        facility_importance[k] = round(float(facility_importance[k]) / total_imp, 4)

    logger.info("시설별 학습된 가중치:")
    for subtype, weight in sorted(facility_importance.items(), key=lambda x: -x[1]):
        logger.info(f"  {subtype:20s} {weight:.4f}")

    weights_path = MODEL_DIR / "learned_weights.json"
    serializable = {k: float(v) for k, v in facility_importance.items()}
    weights_path.write_text(json.dumps(serializable, ensure_ascii=False))
    logger.info(f"가중치 저장: {weights_path}")


if __name__ == "__main__":
    main()
