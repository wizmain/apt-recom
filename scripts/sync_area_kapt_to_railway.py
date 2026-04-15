"""로컬 DB → Railway DB 동기화 — apt_area_info + apt_kapt_info.

전체 재수집 완료 후 Railway에 반영할 때 사용.
각 테이블별로 로컬 전체 레코드를 읽어 Railway에 UPSERT.

사용법:
  .venv/bin/python -m scripts.sync_area_kapt_to_railway
  .venv/bin/python -m scripts.sync_area_kapt_to_railway --table apt_area_info
  .venv/bin/python -m scripts.sync_area_kapt_to_railway --dry-run
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from batch.logger import setup_logger

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BATCH_SIZE = 1000


def _columns(conn, table: str) -> list[str]:
    """정보 스키마에서 컬럼 순서대로 이름 목록 반환."""
    cur = conn.cursor()
    cur.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s
           ORDER BY ordinal_position""",
        [table],
    )
    return [r[0] for r in cur.fetchall()]


def _pk(conn, table: str) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        """SELECT a.attname FROM pg_index i
           JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
           WHERE i.indrelid = %s::regclass AND i.indisprimary""",
        [table],
    )
    return [r[0] for r in cur.fetchall()]


def sync_table(local_url: str, railway_url: str, table: str, dry_run: bool, logger) -> int:
    local = psycopg2.connect(local_url)
    railway = psycopg2.connect(railway_url)
    railway.autocommit = False
    try:
        cols = _columns(local, table)
        pk = _pk(local, table)
        if not cols or not pk:
            logger.error(f"  {table}: 컬럼 또는 PK 조회 실패")
            return 0

        non_pk = [c for c in cols if c not in pk]
        col_list = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        conflict_target = ", ".join(pk)
        update_set = ", ".join([f"{c} = EXCLUDED.{c}" for c in non_pk]) or None

        if update_set:
            upsert_sql = (
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_target}) DO UPDATE SET {update_set}"
            )
        else:
            upsert_sql = (
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_target}) DO NOTHING"
            )

        # 로컬에서 읽기 (서버 사이드 커서로 메모리 효율)
        lcur = local.cursor(name=f"sync_{table}", cursor_factory=psycopg2.extras.DictCursor)
        lcur.itersize = BATCH_SIZE
        lcur.execute(f"SELECT {col_list} FROM {table}")

        rcur = railway.cursor()
        total = 0
        buffer: list[tuple] = []
        for row in lcur:
            buffer.append(tuple(row[c] for c in cols))
            if len(buffer) >= BATCH_SIZE:
                if not dry_run:
                    psycopg2.extras.execute_batch(rcur, upsert_sql, buffer, page_size=200)
                total += len(buffer)
                buffer.clear()
                if total % (BATCH_SIZE * 5) == 0:
                    logger.info(f"  {table}: {total:,}건 처리")
        if buffer:
            if not dry_run:
                psycopg2.extras.execute_batch(rcur, upsert_sql, buffer, page_size=200)
            total += len(buffer)

        if not dry_run:
            railway.commit()
            logger.info(f"  {table}: ✓ {total:,}건 커밋")
        else:
            logger.info(f"  {table}: dry-run {total:,}건 (커밋 안 함)")
        return total
    except Exception as e:
        railway.rollback()
        logger.error(f"  {table}: 실패, 롤백: {e}")
        return 0
    finally:
        local.close()
        railway.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="로컬 → Railway: apt_area_info + apt_kapt_info 동기화")
    parser.add_argument("--table", choices=["apt_area_info", "apt_kapt_info", "all"],
                        default="all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logger = setup_logger("sync_area_kapt")
    local_url = os.getenv("DATABASE_URL")
    railway_url = os.getenv("RAILWAY_DATABASE_URL")
    if not local_url or not railway_url:
        logger.error("DATABASE_URL / RAILWAY_DATABASE_URL 미설정")
        return 1

    if "localhost" not in local_url and "127.0.0.1" not in local_url:
        logger.error(f"DATABASE_URL이 로컬이 아닙니다 — 실수 방지로 중단")
        return 1

    tables = ["apt_area_info", "apt_kapt_info"] if args.table == "all" else [args.table]
    logger.info(f"동기화 시작: {tables} (dry_run={args.dry_run})")

    for t in tables:
        sync_table(local_url, railway_url, t, args.dry_run, logger)

    logger.info("완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
