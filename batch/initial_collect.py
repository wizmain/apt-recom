"""비수도권 과거 3년치 거래 데이터 초기 수집.

일일 API 한도(1000콜)를 고려하여 분할 실행.
실행할 때마다 체크포인트에서 이어서 수집.

사용법:
  python -m batch.initial_collect [--max-calls 900]
"""

import argparse
import json
import time
from pathlib import Path
from datetime import datetime

from batch.config import DATA_GO_KR_RATE, TRADE_URL, RENT_URL
from batch.weekly.collect_trades import _call_api, _parse_xml, TRADE_COL_MAP, RENT_COL_MAP
from batch.weekly.load_trades import load_trades
from batch.nationwide_codes import get_nonmetro_codes
from batch.db import get_connection
from batch.logger import setup_logger

CHECKPOINT_FILE = Path(__file__).parent / "data" / "initial_collect_checkpoint.json"


def generate_months(start="202301", end=None):
    if end is None:
        now = datetime.now()
        end = f"{now.year}{now.month:02d}"
    months = []
    y, m = int(start[:4]), int(start[4:])
    ey, em = int(end[:4]), int(end[4:])
    while (y, m) <= (ey, em):
        months.append(f"{y}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text())
    return {"completed": []}  # list of "sgg_cd:YYYYMM"


def save_checkpoint(ckpt):
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.write_text(json.dumps(ckpt, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="비수도권 과거 3년 거래 데이터 초기 수집")
    parser.add_argument("--max-calls", type=int, default=900, help="이번 실행 최대 API 호출 수 (일 한도 고려)")
    args = parser.parse_args()

    logger = setup_logger("initial")
    codes = get_nonmetro_codes()
    months = generate_months("202301")

    ckpt = load_checkpoint()
    completed = set(ckpt["completed"])

    total_pairs = len(codes) * len(months)
    remaining = [(c, m) for c in codes for m in months if f"{c}:{m}" not in completed]

    logger.info(f"전체: {total_pairs}쌍, 완료: {len(completed)}쌍, 남은: {len(remaining)}쌍")
    logger.info(f"이번 실행 최대: {args.max_calls}콜 ({args.max_calls // 2}쌍)")

    conn = get_connection()
    call_count = 0
    pair_count = 0

    for code, month in remaining:
        if call_count >= args.max_calls:
            logger.info(f"일일 한도 도달 ({call_count}콜). 내일 이어서 실행하세요.")
            break

        # 매매 수집
        xml = _call_api(TRADE_URL, code, month)
        trade_rows = _parse_xml(xml, TRADE_COL_MAP)
        call_count += 1
        time.sleep(DATA_GO_KR_RATE)

        # 전월세 수집
        xml = _call_api(RENT_URL, code, month)
        rent_rows = _parse_xml(xml, RENT_COL_MAP)
        call_count += 1
        time.sleep(DATA_GO_KR_RATE)

        # DB 적재
        if trade_rows or rent_rows:
            load_trades(conn, trade_rows, rent_rows, logger)

        # 체크포인트
        completed.add(f"{code}:{month}")
        pair_count += 1

        if pair_count % 50 == 0:
            save_checkpoint({"completed": list(completed)})
            logger.info(f"  진행: {pair_count}쌍 완료 ({call_count}콜), 매매 {len(trade_rows)}건, 전월세 {len(rent_rows)}건")

    # 최종 체크포인트 저장
    save_checkpoint({"completed": list(completed)})

    logger.info(f"이번 실행 완료: {pair_count}쌍, {call_count}콜")
    logger.info(f"전체 진행: {len(completed)}/{total_pairs}쌍 ({len(completed) * 100 // total_pairs}%)")

    conn.close()


if __name__ == "__main__":
    main()
