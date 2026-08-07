"""Hedonic t값 기반 넛지 가중치 재조정.

블렌딩 입력을 XGB feature importance(learned_weights.json)에서 hedonic 회귀
(models/hedonic_report.json)의 t값으로 교체했다 (2026-08-07). XGB importance 는
시군구 고정효과 없이 학습되어 지역 가격 효과가 혼입된 "가격 상관"이고,
hedonic t 는 시군구 within 회귀라 지역 효과를 통제한 시설 가치 신호다.

방향 가드 (필수 — 실측 근거):
    dist 계수가 양수(가까울수록 싸다)인데 유의한 subtype 이 실재한다
    (2026-08-07 리포트: cctv t=+15.2, hospital +7.5, cafe +7.2, bus +5.4).
    |t| 만 정규화하면 cctv 가 최상위 중요도로 잡혀 가중치를 올리게 된다 —
    시장이 프리미엄을 주지 않는 방향으로의 증폭은 오류이므로,
    ML 신호는 "beta < 0 (가까울수록 비쌈) AND |t| >= T_SIGNIFICANT" 인
    subtype 에만 부여하고 나머지는 블렌딩 없이 현재 가중치를 유지한다.
    (방향 역전 subtype 의 가중치를 0 쪽으로 깎지 않는 이유: 넛지 축은
    가격 가치만이 아니라 목적 가치(예: safety 넛지의 cctv)를 담는다 —
    시장 신호가 없거나 반대인 축은 목적 기반 현행값을 존중한다.)

조정 방식: new = 기존 × (1 − ml_ratio) + hedonic신호 × ml_ratio → 넛지별 정규화
유지 정책: score_* pseudo-subtype / 리포트 미포함 / 방향역전 / 유의미하지 않은
subtype 은 블렌딩하지 않고 유지 (사유를 로그에 표기). 정규화는 전체에 적용.

선행 조건: batch.ml.hedonic_validation 실행으로 hedonic_report.json 생성
(batch/run.py --type ml 체인은 hedonic_validation → update_weights 순서 보장).

사용법:
  python -m batch.ml.update_weights [--dry-run] [--ml-ratio 0.4]
"""

import argparse
import json
from pathlib import Path

from batch.db import get_connection
from batch.logger import setup_logger

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"

# 유의성 임계 |t| — 통상적 5% 양측 기준(≈1.96)의 관례값.
T_SIGNIFICANT = 2.0


def hedonic_signal(
    coefficients: dict[str, dict], t_threshold: float = T_SIGNIFICANT
) -> tuple[dict[str, float], dict[str, str]]:
    """hedonic 계수 → subtype 별 블렌딩 신호.

    반환: (signal, excluded)
    - signal: {subtype: 정규화 |t|} — beta < 0 이고 |t| >= t_threshold 인
      dist_* subtype 만 포함, 합 1.0 으로 정규화.
    - excluded: {subtype: 제외 사유} — "방향역전(beta>0)" | "유의X(|t|<임계)"
      (리포트에 dist_ 항목 자체가 없는 subtype 은 여기에도 없다 — 호출측에서
      "미학습" 처리)
    """
    raw: dict[str, float] = {}
    excluded: dict[str, str] = {}
    for name, c in coefficients.items():
        if not name.startswith("dist_"):
            continue
        subtype = name.removeprefix("dist_")
        beta, t = float(c.get("beta", 0.0)), float(c.get("t", 0.0))
        if abs(t) < t_threshold:
            excluded[subtype] = f"유의X(|t|={abs(t):.1f}<{t_threshold})"
        elif beta > 0:
            excluded[subtype] = f"방향역전(beta>0, t={t:+.1f})"
        else:
            raw[subtype] = abs(t)
    total = sum(raw.values())
    signal = {s: v / total for s, v in raw.items()} if total else {}
    return signal, excluded


def main():
    parser = argparse.ArgumentParser(description="넛지 가중치 hedonic 기반 업데이트")
    parser.add_argument(
        "--dry-run", action="store_true", help="DB 반영 없이 결과만 출력"
    )
    parser.add_argument(
        "--ml-ratio", type=float, default=0.4, help="hedonic 신호 반영 비율 (기본 0.4)"
    )
    args = parser.parse_args()

    logger = setup_logger("update_weights")

    report_path = MODEL_DIR / "hedonic_report.json"
    if not report_path.exists():
        logger.error(f"hedonic 리포트 없음: {report_path}")
        logger.error("먼저 python -m batch.ml.hedonic_validation 실행")
        return
    report = json.loads(report_path.read_text())
    ml_weights, excluded = hedonic_signal(report["coefficients"])
    logger.info(
        f"hedonic 신호 로드: 유효 {len(ml_weights)}개 / 제외 {len(excluded)}개 "
        f"(표본 {report.get('samples'):,}, within R² {report.get('r2_within')})"
    )
    for s, reason in sorted(excluded.items()):
        logger.info(f"  제외 {s:20s} — {reason}")

    # 현재 넛지 가중치 로드 (DB)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s",
        ["nudge_weight"],
    )
    rows = cur.fetchall()

    current_weights: dict[str, dict[str, float]] = {}
    for row in rows:
        parts = row[0].split(":", 1)
        if len(parts) == 2:
            nudge_id = parts[0]
            subtype = row[1]
            weight = float(row[2])
            if nudge_id not in current_weights:
                current_weights[nudge_id] = {}
            current_weights[nudge_id][subtype] = weight

    logger.info(f"현재 넛지: {len(current_weights)}개")

    # 각 넛지별 가중치 조정
    ml_ratio = args.ml_ratio
    cur_ratio = 1.0 - ml_ratio
    updated_count = 0

    for nudge_id, subtypes in current_weights.items():
        logger.info(f"\n{'=' * 60}")
        logger.info(f"넛지: {nudge_id}")
        logger.info(f"{'시설':20s} | {'현재':>6s} | {'신호':>6s} | {'조정':>6s}")
        logger.info("-" * 60)

        new_weights = {}
        # 블렌딩 없이 유지되는 subtype: {subtype: 사유}
        kept: dict[str, str] = {}
        for subtype, cur_w in subtypes.items():
            ml_w = ml_weights.get(subtype)
            if ml_w is None:
                new_weights[subtype] = cur_w
                kept[subtype] = excluded.get(subtype, "미학습")
            else:
                new_weights[subtype] = cur_w * cur_ratio + ml_w * ml_ratio

        # 정규화 (합이 1.0이 되도록) — 유지된 subtype 포함 전체에 적용
        total = sum(new_weights.values()) or 1
        for subtype in new_weights:
            new_weights[subtype] = round(new_weights[subtype] / total, 4)

        for subtype in subtypes:
            cur_w = subtypes[subtype]
            new_w = new_weights[subtype]
            ml_w = ml_weights.get(subtype)
            ml_w_display = f"{ml_w:>5.3f}" if ml_w is not None else "  N/A"
            if subtype in kept:
                note = f"유지({kept[subtype]})"
            else:
                note = (
                    "↑"
                    if new_w > cur_w + 0.005
                    else "↓"
                    if new_w < cur_w - 0.005
                    else "="
                )
            logger.info(
                f"  {subtype:18s} | {cur_w:>5.3f} | {ml_w_display} | {new_w:>5.3f} {note}"
            )

        # DB 업데이트
        if not args.dry_run:
            for subtype, new_w in new_weights.items():
                code = f"{nudge_id}:{subtype}"
                cur.execute(
                    "UPDATE common_code SET extra = %s WHERE group_id = %s AND code = %s",
                    [str(new_w), "nudge_weight", code],
                )
                updated_count += 1

    if not args.dry_run:
        conn.commit()
        logger.info(f"\nDB 업데이트 완료: {updated_count}건 — 백엔드 재기동 필요")
    else:
        logger.info("\nDry-run: DB 반영 안 함 (--dry-run 제거 시 적용)")

    conn.close()


if __name__ == "__main__":
    main()
