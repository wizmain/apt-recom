"""Hedonic 검증 배치 — 실거래가 회귀로 라이프점수 지표의 시장 타당성 측정 (Phase 1-3).

ln(㎡당가격) ~ 시설 접근성(ln 거리, 1km 밀도) + 통제(연식/세대/층/면적),
시군구 고정효과(within demean). 결과는 리포트 파일로만 출력 (DB 쓰기 없음).

산출물:
- models/hedonic_report.json          — 계수/t/R²/가중치 비교 (기계용)
- docs/analysis/hedonic-validation-latest.md — 사람용 요약 (재실행 시 갱신)

해석 가이드:
- dist_* 계수 음수 = 해당 시설에 가까울수록 ㎡당 가격이 높음 (시장이 프리미엄 지불)
- market_importance = |t| 정규화 — 현행 nudge_weight 와 나란히 비교해
  가중치 조정(1-2 대체)의 근거로 사용한다.

사용법:
  .venv/bin/python -m batch.ml.hedonic_validation
  .venv/bin/python -m batch.ml.hedonic_validation --self-test   # 합성 데이터 OLS 검증
"""

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from batch.db import get_connection
from batch.logger import setup_logger

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = REPO_ROOT / "models" / "hedonic_report.json"
REPORT_MD = REPO_ROOT / "docs" / "analysis" / "hedonic-validation-latest.md"

# 접근성 피처로 쓸 subtype (apt_facility_summary 실보유 기준)
FEATURE_SUBTYPES = [
    "subway",
    "bus",
    "school",
    "assigned_elementary",
    "kindergarten",
    "hospital",
    "pharmacy",
    "mart",
    "convenience_store",
    "park",
    "library",
    "pet_facility",
    "animal_hospital",
    "cctv",
    "police",
    "fire_station",
    # 상가정보 유래 4종 (Phase 2-2) — 시장 계수 측정용 (가중치는 별도 결정)
    "cafe",
    "kids_cafe",
    "pet_shop",
    "fitness",
    # 심평원 병원 세분화 3종 (Phase 2-3) — 시장 계수 측정용
    "pediatric_clinic",
    "obgyn_clinic",
    "general_hospital",
]
MIN_SAMPLES = 3000  # 이보다 적으면 회귀 신뢰 불가로 중단


def ols(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """OLS 폐형해. 반환: (beta, t_stats, r2)."""
    xtx = x.T @ x
    xtx_inv = np.linalg.pinv(xtx)
    beta = xtx_inv @ x.T @ y
    resid = y - x @ beta
    dof = max(len(y) - x.shape[1], 1)
    sigma2 = float(resid @ resid) / dof
    se = np.sqrt(np.clip(np.diag(xtx_inv) * sigma2, 1e-12, None))
    t_stats = beta / se
    ss_tot = float(((y - y.mean()) ** 2).sum()) or 1.0
    r2 = 1.0 - float(resid @ resid) / ss_tot
    return beta, t_stats, r2


def top_correlated_pairs(
    x: np.ndarray, names: list[str], top_n: int = 10
) -> list[dict]:
    """피처 간 피어슨 상관 상위 쌍 (다중공선성 진단용). |r| 내림차순."""
    std = x.std(axis=0)
    valid = std > 1e-12  # 상수 컬럼 제외 (상관 정의 불가)
    corr = np.corrcoef(x[:, valid], rowvar=False)
    valid_names = [n for n, v in zip(names, valid) if v]
    pairs = []
    for i in range(len(valid_names)):
        for j in range(i + 1, len(valid_names)):
            pairs.append((valid_names[i], valid_names[j], float(corr[i, j])))
    pairs.sort(key=lambda p: abs(p[2]), reverse=True)
    return [
        {"feature_a": a, "feature_b": b, "pearson_r": round(r, 4)}
        for a, b, r in pairs[:top_n]
    ]


def self_test() -> None:
    """합성 데이터로 OLS + 고정효과(demean) 경로가 알려진 계수를 복원하는지 검증."""
    rng = np.random.default_rng(42)
    n = 5000
    x = rng.normal(size=(n, 3))
    true_beta = np.array([0.5, -1.2, 0.0])
    y = x @ true_beta + rng.normal(scale=0.1, size=n)
    beta, t_stats, r2 = ols(y, x)
    assert np.allclose(beta, true_beta, atol=0.02), f"계수 복원 실패: {beta}"
    assert abs(t_stats[2]) < 3, f"무효 피처의 t 가 과대: {t_stats[2]}"
    assert r2 > 0.95, f"R² 과소: {r2}"
    print("self-test PASS: beta=", np.round(beta, 3), "r2=", round(r2, 4))

    # 고정효과 검증: 그룹별 상이한 절편(고정효과)을 y 에 주입 후
    # demean_by_group → ols 경로가 원래 β 를 복원해야 한다.
    groups = rng.choice(np.array(["g1", "g2", "g3"]), size=n)
    group_effects = {"g1": 3.0, "g2": -2.0, "g3": 7.5}
    y_fe = y + np.array([group_effects[g] for g in groups])
    y_d, x_d = demean_by_group(y_fe, x, groups)
    beta_fe, _, r2_fe = ols(y_d, x_d)
    assert np.allclose(beta_fe, true_beta, atol=0.02), f"FE 계수 복원 실패: {beta_fe}"
    assert r2_fe > 0.95, f"FE within R² 과소: {r2_fe}"
    # demean 이 실제로 그룹 평균을 제거했는지 확인
    for g in group_effects:
        assert abs(y_d[groups == g].mean()) < 1e-9, f"그룹 {g} demean 실패"
    print("self-test PASS (FE): beta=", np.round(beta_fe, 3), "r2=", round(r2_fe, 4))


def load_dataset(conn, logger):
    """라벨/피처/통제/시군구 로드. 반환: (y, X, feature_names, sgg_codes)."""
    cur = conn.cursor()

    cur.execute(
        """
        SELECT m.pnu, AVG(t.deal_amount / NULLIF(t.exclu_use_ar, 0)) AS price_m2
        FROM trade_history t
        JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        WHERE t.deal_amount > 0 AND t.exclu_use_ar > 0
          AND make_date(t.deal_year, t.deal_month, 1) >= CURRENT_DATE - INTERVAL '2 years'
        GROUP BY m.pnu
        """
    )
    price_map = {r[0]: float(r[1]) for r in cur.fetchall() if r[1] and r[1] > 0}
    logger.info(f"가격 라벨(최근 2년): {len(price_map):,}건")

    cur.execute(
        """
        SELECT a.pnu, a.sigungu_code, a.total_hhld_cnt, a.max_floor, a.use_apr_day,
               COALESCE(ai.avg_area, 60)
        FROM apartments a
        LEFT JOIN apt_area_info ai ON a.pnu = ai.pnu
        WHERE a.lat IS NOT NULL
        """
    )
    controls = {}
    for pnu, sgg, hhld, floor, apr, area in cur.fetchall():
        try:
            age = datetime.now().year - int(str(apr)[:4]) if apr else 20
        except (ValueError, TypeError):
            age = 20
        controls[pnu] = (sgg or "", age, hhld or 100, floor or 15, float(area or 60))

    cur.execute(
        "SELECT pnu, facility_subtype, nearest_distance_m, count_1km "
        "FROM apt_facility_summary WHERE facility_subtype = ANY(%s)",
        [FEATURE_SUBTYPES],
    )
    feats: dict[str, dict[str, tuple]] = {}
    for pnu, subtype, dist, cnt in cur.fetchall():
        feats.setdefault(pnu, {})[subtype] = (dist, cnt)

    # 건축물대장 품질 축 (Phase 2-1) — 세대당 주차, 승강기 밀도(대당 담당 세대의
    # 역수 스케일). 결측(미수집/미등재)은 표본 중앙값으로 대체해 계수 편향을 줄인다
    # (0 대체는 "품질 최악"과 혼동되어 계수를 왜곡).
    cur.execute(
        "SELECT pnu, parking_per_hhld, elevator_count, register_hhld_cnt "
        "FROM apt_building_register"
    )
    bldg: dict[str, tuple] = {}
    for pnu, ratio, elv, reg_hhld in cur.fetchall():
        elevator_ratio = (
            float(elv) / reg_hhld
            if elv is not None and reg_hhld and reg_hhld > 0
            else None
        )
        bldg[pnu] = (float(ratio) if ratio is not None else None, elevator_ratio)

    feature_names = []
    for s in FEATURE_SUBTYPES:
        feature_names += [f"dist_{s}", f"cnt1km_{s}"]
    feature_names += ["bldg_parking_ratio", "bldg_elevator_ratio"]
    feature_names += ["age", "hhld", "floor", "area"]

    rows_y, rows_x, sggs = [], [], []
    for pnu, price in price_map.items():
        if pnu not in controls:
            continue
        sgg, age, hhld, floor, area = controls[pnu]
        f = feats.get(pnu, {})
        xrow = []
        for s in FEATURE_SUBTYPES:
            dist, cnt = f.get(s, (None, 0))
            # 결측 거리 = max 취급(멀다) — ln(1+20km). 결측 편향은 Phase 0 정책과
            # 별개로, 회귀에서는 "없음=매우 멂"이 보수적.
            xrow.append(math.log1p(dist if dist is not None else 20000.0))
            xrow.append(float(cnt or 0))
        parking_ratio, elevator_ratio = bldg.get(pnu, (None, None))
        xrow += [parking_ratio, elevator_ratio]  # None 은 아래에서 중앙값 대체
        xrow += [float(age), float(hhld), float(floor), float(area)]
        rows_y.append(math.log(price))
        rows_x.append(xrow)
        sggs.append(sgg[:5])

    x_arr = np.array(rows_x, dtype=float)  # None → np.nan
    for col_name in ("bldg_parking_ratio", "bldg_elevator_ratio"):
        idx = feature_names.index(col_name)
        col = x_arr[:, idx]
        median = float(np.nanmedian(col)) if not np.all(np.isnan(col)) else 0.0
        col[np.isnan(col)] = median

    return np.array(rows_y), x_arr, feature_names, np.array(sggs)


def demean_by_group(y: np.ndarray, x: np.ndarray, groups: np.ndarray):
    """시군구 within demean (고정효과)."""
    y_out = y.astype(float).copy()
    x_out = x.astype(float).copy()
    for g in np.unique(groups):
        idx = groups == g
        y_out[idx] -= y_out[idx].mean()
        x_out[idx] -= x_out[idx].mean(axis=0)
    return y_out, x_out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    logger = setup_logger("hedonic_validation")
    conn = get_connection()
    try:
        y, x, names, sggs = load_dataset(conn, logger)
    finally:
        conn.close()

    if len(y) < MIN_SAMPLES:
        raise SystemExit(f"표본 부족: {len(y)} < {MIN_SAMPLES}")
    logger.info(f"회귀 표본: {len(y):,}건, 피처 {len(names)}개")

    y_d, x_d = demean_by_group(y, x, sggs)
    beta, t_stats, r2 = ols(y_d, x_d)

    dist_idx = [i for i, n in enumerate(names) if n.startswith("dist_")]
    # 다중공선성 진단: 회귀에 실제 투입된 (demean 후) dist_* 피처 간 상관 상위쌍
    collinearity = top_correlated_pairs(
        x_d[:, dist_idx], [names[i] for i in dist_idx], top_n=10
    )
    importance_raw = {names[i]: abs(float(t_stats[i])) for i in dist_idx}
    total_imp = sum(importance_raw.values()) or 1.0
    market_importance = {
        k.removeprefix("dist_"): round(v / total_imp, 4)
        for k, v in importance_raw.items()
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "samples": int(len(y)),
        "r2_within": round(r2, 4),
        "coefficients": {
            names[i]: {
                "beta": round(float(beta[i]), 6),
                "t": round(float(t_stats[i]), 2),
            }
            for i in range(len(names))
        },
        "market_importance_by_subtype": market_importance,
        "collinearity_top_pairs": collinearity,
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    logger.info(f"리포트 저장: {REPORT_JSON}")

    md = [
        "# Hedonic 검증 리포트 (자동 생성)",
        "",
        f"- 생성: {report['generated_at']}",
        f"- 표본: {report['samples']:,} (아파트 단위, 최근 2년 평균 ㎡당가)",
        f"- within R² (시군구 고정효과): {report['r2_within']}",
        "",
        "## 거리 계수 (음수 = 가까울수록 비쌈)",
        "",
        "| subtype | beta(ln거리) | t | 시장 중요도(|t| 정규화) |",
        "|---|---|---|---|",
    ]
    for s in FEATURE_SUBTYPES:
        c = report["coefficients"].get(f"dist_{s}")
        if c:
            md.append(
                f"| {s} | {c['beta']} | {c['t']} | {market_importance.get(s, 0)} |"
            )
    md += [
        "",
        "> 해석: |t|≥2 면 유의. 시장 중요도는 넛지 가중치 조정의 참고 근거 (1-2 대체).",
        "",
        "## 다중공선성 진단 — dist_* 피처 간 피어슨 상관 상위 10쌍 (demean 후)",
        "",
        "| feature_a | feature_b | r |",
        "|---|---|---|",
    ]
    for p in collinearity:
        md.append(f"| {p['feature_a']} | {p['feature_b']} | {p['pearson_r']} |")
    md += [
        "",
        "> |r| 이 높은 쌍은 개별 계수 해석 주의 (부호 왜곡 가능).",
        "",
    ]
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(md))
    logger.info(f"요약 저장: {REPORT_MD}")


if __name__ == "__main__":
    main()
