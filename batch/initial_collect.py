"""비수도권 과거 3년치 거래 데이터 초기 수집.

일일 API 한도(1000콜)를 고려하여 분할 실행.
체크포인트를 DB(common_code 테이블)에 저장하여 GitHub Actions에서도 이어서 수집.

사용법:
  python -m batch.initial_collect [--max-calls 900] [--skip-enrich]
"""

import argparse
import json
import time
from datetime import datetime

from batch.config import DATA_GO_KR_RATE, TRADE_URL, RENT_URL
from batch.trade.collect_trades import _call_api, _parse_xml, TRADE_COL_MAP, RENT_COL_MAP
from batch.trade.load_trades import load_trades
from batch.nationwide_codes import get_nonmetro_codes
from batch.db import get_connection
from batch.logger import setup_logger

CHECKPOINT_GROUP = "initial_collect_checkpoint"


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


def load_checkpoint(conn):
    """DB에서 체크포인트 로드."""
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM common_code WHERE group_id = %s AND code = %s",
        [CHECKPOINT_GROUP, "completed"]
    )
    row = cur.fetchone()
    if row:
        return set(json.loads(row[0]))
    return set()


def save_checkpoint(conn, completed):
    """DB에 체크포인트 저장."""
    data = json.dumps(sorted(completed), ensure_ascii=False)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO common_code (group_id, code, name, extra, sort_order)
           VALUES (%s, %s, %s, %s, 0)
           ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name""",
        [CHECKPOINT_GROUP, "completed", data, str(len(completed))]
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="비수도권 과거 3년 거래 데이터 초기 수집")
    parser.add_argument("--max-calls", type=int, default=900, help="이번 실행 최대 API 호출 수")
    parser.add_argument("--skip-enrich", action="store_true", help="신규 아파트 보충 생략 (별도 워크플로에서 실행)")
    args = parser.parse_args()

    logger = setup_logger("initial")
    codes = get_nonmetro_codes()
    months = generate_months("202301")

    conn = get_connection()
    completed = load_checkpoint(conn)

    total_pairs = len(codes) * len(months)
    remaining = [(c, m) for c in codes for m in months if f"{c}:{m}" not in completed]

    logger.info(f"전체: {total_pairs}쌍, 완료: {len(completed)}쌍, 남은: {len(remaining)}쌍")
    logger.info(f"이번 실행 최대: {args.max_calls}콜 ({args.max_calls // 2}쌍)")

    call_count = 0
    pair_count = 0

    for code, month in remaining:
        if call_count >= args.max_calls:
            logger.info(f"한도 도달 ({call_count}콜). 다음 실행에서 이어서 수집.")
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
            save_checkpoint(conn, completed)
            logger.info(f"  진행: {pair_count}쌍 완료 ({call_count}콜), 매매 {len(trade_rows)}건, 전월세 {len(rent_rows)}건")

    # 최종 체크포인트 저장
    save_checkpoint(conn, completed)

    logger.info(f"이번 실행 완료: {pair_count}쌍, {call_count}콜")
    logger.info(f"전체 진행: {len(completed)}/{total_pairs}쌍 ({len(completed) * 100 // total_pairs}%)")

    # ── 신규 아파트 등록 + 건축물대장/전유부(공급면적)/K-APT 보충 ──
    # CI에서는 --skip-enrich로 별도 워크플로(batch-enrich-apartments)에서 실행.
    # 로컬 실행 시에는 기본적으로 enrich까지 수행.
    if args.skip_enrich:
        logger.info("--skip-enrich: 신규 아파트 보충 생략 (별도 워크플로에서 실행)")
    else:
        try:
            from batch.trade.enrich_apartments import enrich_new_apartments
            logger.info("신규 아파트 보충 시작...")
            enriched, new_pnus = enrich_new_apartments(conn, logger)
            logger.info(f"신규 아파트 등록: {enriched}건 (신규 PNU {len(new_pnus)})")
        except Exception as e:
            logger.error(f"신규 아파트 보충 실패: {e}")

    conn.close()


if __name__ == "__main__":
    main()
