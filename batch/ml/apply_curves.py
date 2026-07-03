"""ML 학습 거리 곡선(distance_curves.json) → common_code facility_decay 반영 (Phase 1-4).

배포 제약: Railway 백엔드는 web/backend/ 만 배포되어 models/ 파일에 접근할 수
없다 → 런타임 반영 경로는 파일이 아니라 common_code(DB). scoring.py 의
_load_facility_decay_by_profile 이 facility_decay_{profile} 그룹을 우선
조회하므로, 여기서 upsert 하면 백엔드 재기동 시 적용된다.

방법: PDP 곡선을 런타임 파라메트릭 로그감쇠(decay 1개)로 최소자승 적합.
- grid search (50~3000, step 25) — 의존성 없이 결정적.
- 적합 RMSE > 20점이면 skip (곡선이 로그감쇠 형태가 아님 — 억지 반영 방지).
- metro 적합값에 기존 프로필 배율(×1.3 / ×1.8)을 적용해 3개 프로필 산출.

사용법:
  .venv/bin/python -m batch.ml.apply_curves            # dry-run
  .venv/bin/python -m batch.ml.apply_curves --apply
  (batch/run.py --type ml 에서도 호출됨)
"""

import argparse
import json
import math
from pathlib import Path

from batch.db import get_connection
from batch.logger import setup_logger

REPO_ROOT = Path(__file__).resolve().parents[2]
CURVES_PATH = REPO_ROOT / "models" / "distance_curves.json"

RMSE_SKIP_THRESHOLD = 20.0
DECAY_GRID = [float(d) for d in range(50, 3001, 25)]
PROFILE_MULTIPLIER = {"metro": 1.0, "major_city": 1.3, "provincial": 1.8}
DEFAULT_MAX_DISTANCE_M = 3000.0


def _log_decay_score(d: float, decay: float, max_d: float) -> float:
    if d >= max_d:
        return 0.0
    return 100.0 * max(0.0, 1.0 - math.log(1 + d / decay) / math.log(1 + max_d / decay))


def fit_decay_from_curve(
    distances: list[float], scores: list[float], max_d: float = DEFAULT_MAX_DISTANCE_M
) -> float:
    """PDP 곡선 → 로그감쇠 decay 최소자승 적합 (RMSE 최소 grid 탐색)."""
    # 곡선 점수를 0~100 으로 정규화 (PDP 원점수는 임의 스케일)
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0
    norm = [(s - lo) / span * 100.0 for s in scores]

    best_decay, best_rmse = DECAY_GRID[0], float("inf")
    for decay in DECAY_GRID:
        se = 0.0
        for d, s in zip(distances, norm):
            se += (_log_decay_score(d, decay, max_d) - s) ** 2
        rmse = math.sqrt(se / len(norm))
        if rmse < best_rmse:
            best_decay, best_rmse = decay, rmse
    fit_decay_from_curve.last_rmse = best_rmse  # 호출부 skip 판단용
    return best_decay


def apply_curves(conn, logger, apply: bool = False) -> dict:
    """곡선 적합 → facility_decay_{profile} upsert. 반환 {"applied": n, "skipped": n}."""
    if not CURVES_PATH.exists():
        logger.error(f"곡선 파일 없음: {CURVES_PATH} — 먼저 train_scoring 실행")
        return {"applied": 0, "skipped": 0}

    curves = json.loads(CURVES_PATH.read_text())
    cur = conn.cursor()
    applied = skipped = 0

    for subtype, curve in curves.items():
        decay = fit_decay_from_curve(curve["distances"], curve["scores"])
        rmse = fit_decay_from_curve.last_rmse
        if rmse > RMSE_SKIP_THRESHOLD:
            logger.warning(
                f"  {subtype:20s} skip — 적합 RMSE {rmse:.1f} > {RMSE_SKIP_THRESHOLD}"
            )
            skipped += 1
            continue
        for profile, mult in PROFILE_MULTIPLIER.items():
            value = round(decay * mult)
            logger.info(
                f"  {'APPLY' if apply else 'DRY-RUN'} facility_decay_{profile}.{subtype} = {value} (rmse {rmse:.1f})"
            )
            if apply:
                cur.execute(
                    """
                    INSERT INTO common_code (group_id, code, name, extra, sort_order)
                    VALUES (%s, %s, %s, '', 0)
                    ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name
                    """,
                    [f"facility_decay_{profile}", subtype, str(value)],
                )
        applied += 1

    if apply:
        conn.commit()
        logger.info(
            f"✅ 반영 완료: {applied} subtype × 3 profiles — 백엔드 재기동 필요 (decay 캐시)"
        )
    else:
        logger.info(f"dry-run: {applied} subtype 반영 예정, {skipped} skip")
    return {"applied": applied, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="common_code 반영 (기본 dry-run)"
    )
    args = parser.parse_args()
    logger = setup_logger("apply_curves")
    conn = get_connection()
    try:
        apply_curves(conn, logger, apply=args.apply)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
