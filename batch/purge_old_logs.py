"""사용자 행동 로그 · 챗봇 대화 로그 90일 보관 주기 삭제 배치.

대상 테이블: `user_event`, `chat_log`.
정책:
- `created_at < NOW() - INTERVAL '{days} days'` 조건의 행을 삭제
- WAL 폭증과 락 지속 시간을 줄이기 위해 `LIMIT {batch_size}` 루프 + 짧은 sleep
- `--dry-run` 은 실제 삭제 없이 대상 건수만 출력

사용:
  python -m batch.purge_old_logs                  # 기본 90일
  python -m batch.purge_old_logs --days 30        # 보관 기간 변경
  python -m batch.purge_old_logs --dry-run        # 삭제 없이 대상 건수만
  python -m batch.purge_old_logs --batch-size 5000

GitHub Actions 주간 실행 워크플로우에서 호출한다.
"""

from __future__ import annotations

import argparse
import logging
import time

from batch.db import get_connection

logger = logging.getLogger("purge_old_logs")

# 처리 대상 테이블. 새 로그 테이블 추가 시 이 튜플에 포함.
TARGET_TABLES: tuple[str, ...] = ("user_event", "chat_log")

DEFAULT_DAYS = 90
DEFAULT_BATCH_SIZE = 10000
SLEEP_BETWEEN_BATCHES = 0.2  # 초 — 다른 트랜잭션에게 I/O 양보


def _count_expired(cur, table: str, days: int) -> int:
    """삭제 대상 건수 반환."""
    cur.execute(
        f"SELECT COUNT(*) FROM {table} "
        f"WHERE created_at < NOW() - (%s || ' days')::INTERVAL",
        [str(days)],
    )
    row = cur.fetchone()
    return row[0] if row else 0


def purge_table(
    conn,
    table: str,
    *,
    days: int,
    batch_size: int,
    dry_run: bool,
) -> int:
    """단일 테이블 LIMIT 루프 삭제. 반환값은 삭제(또는 대상) 건수."""
    cur = conn.cursor()

    if dry_run:
        count = _count_expired(cur, table, days)
        logger.info(f"[DRY-RUN] {table}: {count:,}건 삭제 대상 (기준 {days}일)")
        return count

    total = 0
    while True:
        cur.execute(
            f"DELETE FROM {table} WHERE id IN ("
            f"  SELECT id FROM {table} "
            f"  WHERE created_at < NOW() - (%s || ' days')::INTERVAL "
            f"  LIMIT %s"
            f")",
            [str(days), batch_size],
        )
        deleted = cur.rowcount
        conn.commit()
        total += deleted

        if deleted == 0:
            break

        logger.info(f"  {table}: {deleted:,}건 삭제 (누적 {total:,})")
        time.sleep(SLEEP_BETWEEN_BATCHES)

    logger.info(f"{table}: 최종 {total:,}건 삭제 완료")
    return total


def run(*, days: int, batch_size: int, dry_run: bool) -> dict[str, int]:
    """모든 TARGET_TABLES 에 대해 purge 실행. 결과 dict 반환."""
    conn = get_connection()
    conn.autocommit = False
    try:
        results: dict[str, int] = {}
        for table in TARGET_TABLES:
            results[table] = purge_table(
                conn, table, days=days, batch_size=batch_size, dry_run=dry_run
            )
        return results
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="사용자 로그 90일 보관 삭제 배치")
    parser.add_argument(
        "--days", type=int, default=DEFAULT_DAYS,
        help=f"보관 기간(일). 이 일수 이전 생성 행을 삭제. 기본: {DEFAULT_DAYS}",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"1회 DELETE 당 최대 행 수. 기본: {DEFAULT_BATCH_SIZE}",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="실제 삭제 없이 대상 건수만 조회·출력",
    )
    args = parser.parse_args()

    if args.days <= 0:
        parser.error("--days must be positive")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    mode = "DRY-RUN" if args.dry_run else "EXECUTE"
    logger.info(
        f"purge_old_logs start — days={args.days} batch_size={args.batch_size} mode={mode}"
    )
    results = run(days=args.days, batch_size=args.batch_size, dry_run=args.dry_run)
    total = sum(results.values())
    logger.info(f"완료: 합계 {total:,}건 ({results})")


if __name__ == "__main__":
    main()
