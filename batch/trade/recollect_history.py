"""지정한 API 조회 코드·기간의 매매·전월세 과거 거래 재수집.

배경 (2026-11-26 실측)
  국토부 실거래 API 는 개편 지역을 신코드로만 응답하고 과거 월 거래까지 신코드로 옮겼다.
  - 화성 병점구(41595)·동탄구(41597): 2026년 이전 거래를 한 번도 수집하지 못했다.
  - 인천 중구·동구·서구: 구코드(28110·28140·28260) 조회가 0건이라 2026.07 이후가 비었다.
    API 조회 코드는 28125(제물포)·28155(영종)·28275(서해)·28290(검단).
  정기 배치는 최근 몇 달만 다시 보므로 빈 과거 구간은 이 도구로 채운다.

동작
  조회 코드 × 계약월(최근 월부터)마다 매매·전월세 API 를 1회씩 부르고 load_trades 로 적재한다.
  load_trades 가 응답 시군구 코드를 내부 구코드로 정규화하고 기존 고유키와 겹치는 행을 거르므로,
  이미 있는 거래는 다시 들어가지 않는다. 새 거래 키의 단지 매핑·가격 점수·오르는 단지 집계는
  다음 정기 거래 배치가 처리한다.

사용
  python -m batch.trade.recollect_history --target local --dry-run --codes 41595,41597 --from-ym 202110 --to-ym 202512
  python -m batch.trade.recollect_history --target local --apply  --codes 41595,41597 --from-ym 202110 --to-ym 202512
  운영(--target railway)은 사용자 허락 후 실행한다.

이 모듈 상단은 DB 드라이버를 import 하지 않는다(scripts/tests CI 대상). DB·API 의존은
실행 함수 안에서 import 한다.
"""

from __future__ import annotations

import argparse
import json
import re

CHECKPOINT_GROUP = "recollect_history_checkpoint"
CHECKPOINT_CODE = "completed"
DEFAULT_MAX_CALLS = 900  # 기본 키 일 한도 안에서 정기 배치 몫을 남기는 1회 실행 상한


# ── 순수 함수 (CI 테스트 대상) ──────────────────────────────────────────────


def month_range(from_ym: int, to_ym: int) -> list[str]:
    """from_ym~to_ym 계약월(YYYYMM 문자열)을 최근 월부터. 범위가 뒤집히면 ValueError."""
    if from_ym > to_ym:
        raise ValueError(f"기간이 뒤집혔다: {from_ym} > {to_ym}")
    months = []
    year, month = divmod(to_ym, 100)
    while year * 100 + month >= from_ym:
        months.append(f"{year}{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return months


def parse_codes(value: str) -> list[str]:
    """'41595,41597' → ['41595', '41597']. 다섯 자리 숫자만 허용."""
    codes = [c.strip() for c in value.split(",") if c.strip()]
    if not codes:
        raise ValueError("조회 코드를 하나 이상 지정해야 한다")
    for code in codes:
        if not re.fullmatch(r"\d{5}", code):
            raise ValueError(f"조회 코드는 다섯 자리 숫자여야 한다: {code!r}")
    return codes


def pair_key(code: str, month: str) -> str:
    return f"{code}:{month}"


# ── DB·API (실행 경로) ─────────────────────────────────────────────────────


def _db_url(target: str) -> str:
    import os

    url = os.getenv("DATABASE_URL" if target == "local" else "RAILWAY_DATABASE_URL")
    if not url:
        raise SystemExit(f"{target} DB URL 미설정 (.env 확인)")
    return url


def _load_checkpoint(conn) -> set[str]:
    from batch.db import query_one

    row = query_one(
        conn,
        "SELECT name FROM common_code WHERE group_id = %s AND code = %s",
        [CHECKPOINT_GROUP, CHECKPOINT_CODE],
    )
    return set(json.loads(row["name"])) if row and row["name"] else set()


def _save_checkpoint(conn, completed: set[str]) -> None:
    conn.cursor().execute(
        """INSERT INTO common_code (group_id, code, name, extra, sort_order)
           VALUES (%s, %s, %s, %s, 0)
           ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name, extra = EXCLUDED.extra""",
        [
            CHECKPOINT_GROUP,
            CHECKPOINT_CODE,
            json.dumps(sorted(completed)),
            str(len(completed)),
        ],
    )
    conn.commit()


def recollect(
    conn, logger, *, codes: list[str], months: list[str], max_calls: int, dry_run: bool
) -> dict:
    """조회 코드 × 계약월을 최근 월부터 재수집한다. 반환: 집계 dict."""
    import time

    from batch.config import DATA_GO_KR_RATE, RENT_URL, TRADE_URL
    from batch.trade.collect_trades import (
        RENT_COL_MAP,
        TRADE_COL_MAP,
        _call_api,
        _parse_xml,
    )
    from batch.trade.load_trades import load_trades

    completed = _load_checkpoint(conn)
    pairs = [(m, c) for m in months for c in codes if pair_key(c, m) not in completed]
    logger.info(
        f"재수집 대상 {len(months) * len(codes)}쌍 (코드 {codes}, {months[-1]}~{months[0]}), "
        f"체크포인트 완료 {len(completed)}, 남은 {len(pairs)}, 이번 최대 {max_calls}콜"
        + (" [dry-run]" if dry_run else "")
    )
    stats = {
        "pairs": 0,
        "calls": 0,
        "failed_pairs": 0,
        "trade_rows": 0,
        "rent_rows": 0,
        "new_rows": 0,
    }
    for month, code in pairs:
        if stats["calls"] + 2 > max_calls:
            logger.info(
                f"호출 한도 도달 ({stats['calls']}콜) — 다음 실행에서 이어서 처리"
            )
            break
        trade_xml = _call_api(TRADE_URL, code, month, logger)
        time.sleep(DATA_GO_KR_RATE)
        rent_xml = _call_api(RENT_URL, code, month, logger)
        time.sleep(DATA_GO_KR_RATE)
        stats["calls"] += 2
        if trade_xml is None or rent_xml is None:
            # 호출 실패는 완료로 남기지 않는다(다음 실행에서 재시도). 사유는 _call_api 가 로그한다.
            stats["failed_pairs"] += 1
            continue
        trade_rows = _parse_xml(trade_xml, TRADE_COL_MAP)
        rent_rows = _parse_xml(rent_xml, RENT_COL_MAP)
        new_rows = load_trades(conn, trade_rows, rent_rows, logger, dry_run=dry_run)
        stats["pairs"] += 1
        stats["trade_rows"] += len(trade_rows)
        stats["rent_rows"] += len(rent_rows)
        stats["new_rows"] += new_rows
        logger.info(
            f"  {code} {month}: 매매 {len(trade_rows)}, 전월세 {len(rent_rows)} → "
            f"{'신규 후보' if dry_run else '적재'} {new_rows}"
        )
        if not dry_run:
            completed.add(pair_key(code, month))
            _save_checkpoint(conn, completed)
    logger.info(f"완료: {stats}")
    return stats


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    p = argparse.ArgumentParser(description="국토부 실거래 과거 구간 재수집")
    p.add_argument("--target", choices=["local", "railway"], required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run", action="store_true", help="조회·대조만, 쓰기·체크포인트 없음"
    )
    mode.add_argument("--apply", action="store_true")
    p.add_argument(
        "--codes", required=True, help="API 조회 코드, 쉼표 구분 (예: 41595,41597)"
    )
    p.add_argument("--from-ym", type=int, required=True)
    p.add_argument("--to-ym", type=int, required=True)
    p.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    args = p.parse_args()

    import psycopg2

    from batch.logger import setup_logger
    from batch.trade.trade_keys import try_trade_write_lock

    logger = setup_logger(f"recollect_history_{args.target}")
    conn = psycopg2.connect(_db_url(args.target))
    try:
        # 거래 배치·키 변경과 동시에 거래 테이블을 쓰지 않는다(ADR-015). 세션 잠금은 연결 종료 시 풀린다.
        if args.apply and not try_trade_write_lock(conn):
            logger.error(
                "거래 쓰기 잠금 점유 중(거래 배치 또는 키 변경 실행 중) — 중단"
            )
            return
        recollect(
            conn,
            logger,
            codes=parse_codes(args.codes),
            months=month_range(args.from_ym, args.to_ym),
            max_calls=args.max_calls,
            dry_run=args.dry_run,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
