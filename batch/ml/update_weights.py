"""ML Feature Importance 기반 넛지 가중치 재조정.

ML 가중치(가격 기여도)를 참고하되, 넛지별 목적을 유지한 조정안을 산출.
조정 방식: (기존 가중치 × 0.5) + (ML 가중치 × 0.5) → 정규화

사용법:
  python -m batch.ml.update_weights [--dry-run]
"""

import argparse
import json
from pathlib import Path
from batch.db import get_connection
from batch.logger import setup_logger

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"


def main():
    parser = argparse.ArgumentParser(description="넛지 가중치 ML 기반 업데이트")
    parser.add_argument("--dry-run", action="store_true", help="DB 반영 없이 결과만 출력")
    parser.add_argument("--ml-ratio", type=float, default=0.4, help="ML 가중치 반영 비율 (기본 0.4)")
    args = parser.parse_args()

    logger = setup_logger("update_weights")

    # ML 학습된 가중치 로드
    weights_path = MODEL_DIR / "learned_weights.json"
    if not weights_path.exists():
        logger.error(f"학습된 가중치 파일 없음: {weights_path}")
        logger.error("먼저 python -m batch.ml.train_scoring 실행")
        return
    ml_weights = json.loads(weights_path.read_text())
    logger.info(f"ML 가중치 로드: {len(ml_weights)}개 시설")

    # 현재 넛지 가중치 로드 (DB)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT code, name, extra FROM common_code WHERE group_id = %s", ["nudge_weight"])
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
        logger.info(f"\n{'='*50}")
        logger.info(f"넛지: {nudge_id}")
        logger.info(f"{'시설':20s} | {'현재':>6s} | {'ML':>6s} | {'조정':>6s}")
        logger.info("-" * 50)

        new_weights = {}
        for subtype, cur_w in subtypes.items():
            ml_w = ml_weights.get(subtype, 0.02)  # ML에 없는 시설(score_* 등)은 기본 0.02
            blended = cur_w * cur_ratio + ml_w * ml_ratio
            new_weights[subtype] = blended

        # 정규화 (합이 1.0이 되도록)
        total = sum(new_weights.values()) or 1
        for subtype in new_weights:
            new_weights[subtype] = round(new_weights[subtype] / total, 4)

        for subtype in subtypes:
            cur_w = subtypes[subtype]
            new_w = new_weights[subtype]
            ml_w = ml_weights.get(subtype, 0.02)
            change = "↑" if new_w > cur_w + 0.005 else "↓" if new_w < cur_w - 0.005 else "="
            logger.info(f"  {subtype:18s} | {cur_w:>5.3f} | {ml_w:>5.3f} | {new_w:>5.3f} {change}")

        # DB 업데이트
        if not args.dry_run:
            for subtype, new_w in new_weights.items():
                code = f"{nudge_id}:{subtype}"
                cur.execute(
                    "UPDATE common_code SET extra = %s WHERE group_id = %s AND code = %s",
                    [str(new_w), "nudge_weight", code]
                )
                updated_count += 1

    if not args.dry_run:
        conn.commit()
        logger.info(f"\nDB 업데이트 완료: {updated_count}건")
    else:
        logger.info(f"\nDry-run: DB 반영 안 함 (--dry-run 제거 시 적용)")

    conn.close()


if __name__ == "__main__":
    main()
