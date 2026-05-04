"""거래/임대 이력 N년 보관 주기 삭제 배치.

대상 테이블: ``trade_history``, ``rent_history`` — N년 이상 오래된 행 삭제.
부수 정리: ``trade_apt_mapping`` 의 orphan apt_seq (양쪽 history 어디에도 없는) 자동 제거.
마지막에 영향 받은 테이블 ``VACUUM (ANALYZE)`` 실행.

목적: Railway Postgres 메모리 압박 감소. ``trade_history``(982 MB) +
``rent_history``(1.9 GB) + 인덱스 21개 가 DB 의 ~80% 차지.

사용:
    python -m batch.purge_old_trades --target local --dry-run         # 기본 7년
    python -m batch.purge_old_trades --target both --years 5          # cutoff 변경
    python -m batch.purge_old_trades --target railway --years 7       # 본격 실행
    python -m batch.purge_old_trades --target local --years 5 --confirm  # 7 미만은 confirm 필요

검증·운영 절차는 plan 문서(/Users/wizmain/.claude/plans/foamy-swimming-book.md) 참고.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import date
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

from batch.logger import setup_logger

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


DEFAULT_YEARS = 7
DEFAULT_BATCH_SIZE = 50000
DEFAULT_MAX_ROWS = 5_000_000
SLEEP_BETWEEN_BATCHES = (
    0.5  # 초 — 다른 트랜잭션에게 I/O 양보 (인덱스 11개로 WAL 폭증 큼)
)

HISTORY_TABLES: tuple[tuple[str, str], ...] = (
    # (table, sample_value_column)
    ("trade_history", "deal_amount"),
    ("rent_history", "deposit"),
)


def _db_url(target: str) -> str:
    if target == "local":
        url = os.getenv("DATABASE_URL")
    elif target == "railway":
        url = os.getenv("RAILWAY_DATABASE_URL")
    else:
        raise ValueError(f"unknown target: {target}")
    if not url:
        raise ValueError(f"{target} DB URL 미설정")
    return url


def _cutoff_tuple(years: int) -> tuple[int, int, int]:
    today = date.today()
    cutoff = today.replace(year=today.year - years)
    return cutoff.year, cutoff.month, cutoff.day


def _count_old(cur, table: str, cutoff: tuple[int, int, int]) -> int:
    cur.execute(
        f"SELECT COUNT(*) FROM {table} "
        f"WHERE (deal_year, deal_month, deal_day) < (%s, %s, %s)",
        list(cutoff),
    )
    return cur.fetchone()[0]


def _sample_old(
    cur, table: str, sample_col: str, cutoff: tuple[int, int, int], limit: int = 10
) -> list[tuple]:
    cur.execute(
        f"SELECT id, sgg_cd, apt_nm, deal_year, deal_month, deal_day, {sample_col} "
        f"FROM {table} "
        f"WHERE (deal_year, deal_month, deal_day) < (%s, %s, %s) "
        f"ORDER BY id LIMIT %s",
        [*cutoff, limit],
    )
    return cur.fetchall()


def _delete_old_chunked(
    conn, table: str, cutoff: tuple[int, int, int], batch_size: int, logger
) -> int:
    """LIMIT 루프 chunk DELETE. chunk 별 commit. 누적 삭제 수 반환."""
    total = 0
    cur = conn.cursor()
    while True:
        cur.execute(
            f"DELETE FROM {table} WHERE id IN ("
            f"  SELECT id FROM {table} "
            f"  WHERE (deal_year, deal_month, deal_day) < (%s, %s, %s) "
            f"  LIMIT %s"
            f")",
            [*cutoff, batch_size],
        )
        deleted = cur.rowcount
        conn.commit()
        if deleted == 0:
            break
        total += deleted
        logger.info(f"  {table}: {deleted:,}건 삭제 (누적 {total:,})")
        time.sleep(SLEEP_BETWEEN_BATCHES)
    return total


def _delete_orphan_mappings(conn, logger) -> int:
    """trade/rent history 어디에도 매칭 안 되는 trade_apt_mapping 제거."""
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM trade_apt_mapping m
        WHERE NOT EXISTS (SELECT 1 FROM trade_history t WHERE t.apt_seq = m.apt_seq)
          AND NOT EXISTS (SELECT 1 FROM rent_history  r WHERE r.apt_seq = m.apt_seq)
        """
    )
    deleted = cur.rowcount
    conn.commit()
    logger.info(f"  trade_apt_mapping orphan: {deleted:,}건 삭제")
    return deleted


def _vacuum(url: str, tables: list[str], logger) -> None:
    """VACUUM 은 transaction 안에서 못 돌리므로 별도 autocommit connection."""
    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        for t in tables:
            logger.info(f"  VACUUM (ANALYZE) {t}")
            cur.execute(f"VACUUM (ANALYZE) {t}")
    finally:
        conn.close()


def _process_target(target: str, args, logger) -> None:
    cutoff = _cutoff_tuple(args.years)
    logger.info(
        f"[{target}] cutoff={cutoff} (years={args.years}) "
        f"dry_run={args.dry_run} batch_size={args.batch_size}"
    )

    url = _db_url(target)
    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        cur = conn.cursor()

        # 1) 카운트 + 안전 캡 검사
        counts: dict[str, int] = {}
        for table, sample_col in HISTORY_TABLES:
            counts[table] = _count_old(cur, table, cutoff)
            logger.info(f"  [{target}] {table}: 삭제 대상 {counts[table]:,}건")

        total_target = sum(counts.values())
        if total_target > args.max_rows:
            logger.error(
                f"  [{target}] 삭제 대상 {total_target:,}건이 --max-rows={args.max_rows:,} 초과 — abort"
            )
            return

        # 2) dry-run 이면 sample 출력 후 종료
        if args.dry_run:
            for table, sample_col in HISTORY_TABLES:
                if counts[table] == 0:
                    continue
                rows = _sample_old(cur, table, sample_col, cutoff)
                logger.info(f"  [{target}] {table} sample (최대 10건):")
                for r in rows:
                    logger.info(f"    {r}")
            logger.info(f"  [{target}] DRY-RUN 종료 — 실제 삭제 없음")
            return

        # 3) 실제 chunked DELETE
        total_deleted = 0
        for table, _ in HISTORY_TABLES:
            if counts[table] == 0:
                logger.info(f"  [{target}] {table}: 대상 0 — skip")
                continue
            deleted = _delete_old_chunked(conn, table, cutoff, args.batch_size, logger)
            total_deleted += deleted
            logger.info(f"  [{target}] {table}: 최종 {deleted:,}건 삭제")

        # 4) orphan mapping 정리
        if not args.skip_mapping_cleanup:
            _delete_orphan_mappings(conn, logger)

        logger.info(f"  [{target}] 합계 {total_deleted:,}건 삭제 완료")
    finally:
        conn.close()

    # 5) VACUUM (별도 autocommit connection)
    if not args.dry_run and not args.no_vacuum:
        vacuum_targets = ["trade_history", "rent_history"]
        if not args.skip_mapping_cleanup:
            vacuum_targets.append("trade_apt_mapping")
        _vacuum(url, vacuum_targets, logger)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="trade_history / rent_history N년 이상 오래된 거래 삭제 배치"
    )
    parser.add_argument(
        "--years",
        type=int,
        default=DEFAULT_YEARS,
        help=f"보관 기간(년). 기본 {DEFAULT_YEARS}",
    )
    parser.add_argument(
        "--target", choices=["local", "railway", "both"], default="local"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"chunk 행 수. 기본 {DEFAULT_BATCH_SIZE}",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=DEFAULT_MAX_ROWS,
        help=f"예상 삭제 행 수가 이 값 초과 시 abort. 기본 {DEFAULT_MAX_ROWS}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 삭제 없이 카운트 + 10건 sample 만 출력",
    )
    parser.add_argument(
        "--no-vacuum", action="store_true", help="실행 후 VACUUM (ANALYZE) 단계 건너뜀"
    )
    parser.add_argument(
        "--skip-mapping-cleanup",
        action="store_true",
        help="orphan trade_apt_mapping 정리 건너뜀",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="--years 가 기본값 미만일 때 추가 안전 확인",
    )
    args = parser.parse_args()

    if args.years <= 0:
        parser.error("--years must be positive")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    if args.years < DEFAULT_YEARS and not args.dry_run and not args.confirm:
        parser.error(
            f"--years={args.years} 가 기본 {DEFAULT_YEARS} 미만 — 실행하려면 --confirm 필요"
        )

    logger = setup_logger("purge_old_trades")
    targets = ["local", "railway"] if args.target == "both" else [args.target]
    for t in targets:
        _process_target(t, args, logger)


if __name__ == "__main__":
    main()
