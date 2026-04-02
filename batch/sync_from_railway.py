"""Railway DB → 로컬 DB 동기화.

모드:
  --mode incremental (기본): created_at 기반 신규 건만 동기화 (수 초)
  --mode full: pg_dump/pg_restore 전체 교체 (수 분)

사용법:
  python -m batch.sync_from_railway
  python -m batch.sync_from_railway --mode full
"""

import os
import argparse
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from batch.logger import setup_logger

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

SYNC_CHECKPOINT_GROUP = "sync_checkpoint"
SYNC_TABLES = [
    ("trade_history", "apt_seq, sgg_cd, apt_nm, deal_amount, exclu_use_ar, floor, deal_year, deal_month, deal_day, build_year, created_at"),
    ("rent_history", "apt_seq, sgg_cd, apt_nm, deposit, monthly_rent, exclu_use_ar, floor, deal_year, deal_month, deal_day, created_at"),
]


def _get_last_sync(local_conn):
    """로컬 DB에서 마지막 동기화 시각 조회."""
    cur = local_conn.cursor()
    cur.execute(
        "SELECT name FROM common_code WHERE group_id = %s AND code = %s",
        [SYNC_CHECKPOINT_GROUP, "last_sync"]
    )
    row = cur.fetchone()
    return row[0] if row else None


def _save_last_sync(local_conn, timestamp):
    """로컬 DB에 마지막 동기화 시각 저장."""
    cur = local_conn.cursor()
    cur.execute(
        """INSERT INTO common_code (group_id, code, name, extra, sort_order)
           VALUES (%s, %s, %s, %s, 0)
           ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name""",
        [SYNC_CHECKPOINT_GROUP, "last_sync", timestamp, ""]
    )
    local_conn.commit()


def incremental_sync(logger):
    """created_at 기반 증분 동기화."""
    local_url = os.getenv("DATABASE_URL")
    railway_url = os.getenv("RAILWAY_DATABASE_URL")

    local = psycopg2.connect(local_url)
    railway = psycopg2.connect(railway_url)

    last_sync = _get_last_sync(local)
    if not last_sync:
        logger.info("마지막 동기화 시각 없음 → full 모드로 전환")
        local.close()
        railway.close()
        return full_sync(logger)

    logger.info(f"증분 동기화 시작 (기준: {last_sync})")
    total = 0
    max_created = last_sync

    for table, cols in SYNC_TABLES:
        # Railway에서 신규 건 조회
        rcur = railway.cursor()
        rcur.execute(f"SELECT {cols} FROM {table} WHERE created_at > %s", [last_sync])
        new_rows = rcur.fetchall()

        if new_rows:
            # 로컬에 INSERT
            lcur = local.cursor()
            col_count = len(cols.split(","))
            placeholders = ",".join(["%s"] * col_count)
            for row in new_rows:
                try:
                    lcur.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", row)
                except psycopg2.errors.UniqueViolation:
                    local.rollback()
                    continue
            local.commit()

            # 최대 created_at 갱신
            for row in new_rows:
                ct = row[-1]  # created_at은 마지막 컬럼
                if ct and str(ct) > max_created:
                    max_created = str(ct)

            logger.info(f"  {table}: {len(new_rows):,}건 동기화")
            total += len(new_rows)
        else:
            logger.info(f"  {table}: 신규 없음")

    # 동기화 시각 갱신
    _save_last_sync(local, max_created)

    # 검증
    logger.info("정합성 검증:")
    for table in ["trade_history", "rent_history"]:
        lcur = local.cursor()
        rcur = railway.cursor()
        lcur.execute(f"SELECT COUNT(*) FROM {table}")
        l = lcur.fetchone()[0]
        rcur.execute(f"SELECT COUNT(*) FROM {table}")
        r = rcur.fetchone()[0]
        ok = "OK" if l == r else f"차이 {r - l:+,}"
        logger.info(f"  {table}: 로컬 {l:,} / Railway {r:,} [{ok}]")

    local.close()
    railway.close()
    logger.info(f"증분 동기화 완료: {total:,}건")


def full_sync(logger):
    """pg_dump/pg_restore 전체 동기화."""
    railway_url = os.getenv("RAILWAY_DATABASE_URL")
    local_url = os.getenv("DATABASE_URL")
    dump_file = os.path.join(tempfile.gettempdir(), "railway_backup.dump")

    pg_dump = "/opt/homebrew/opt/postgresql@18/bin/pg_dump"
    pg_restore = "/opt/homebrew/opt/postgresql@18/bin/pg_restore"
    if not os.path.exists(pg_dump):
        pg_dump = "pg_dump"
        pg_restore = "pg_restore"

    try:
        logger.info("1/3 Railway DB dump 시작...")
        result = subprocess.run(
            [pg_dump, railway_url, "--format=custom", "--no-owner", "--no-acl", f"--file={dump_file}"],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            logger.error(f"pg_dump 실패: {result.stderr}")
            return

        size_mb = os.path.getsize(dump_file) / 1024 / 1024
        logger.info(f"   dump 완료: {size_mb:.1f}MB")

        logger.info("2/3 로컬 DB restore 시작...")
        result = subprocess.run(
            [pg_restore, "--clean", "--if-exists", "--no-owner", "--no-acl", f"--dbname={local_url}", dump_file],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0 and "error" in result.stderr.lower():
            logger.warning(f"pg_restore 경고: {result.stderr[:500]}")
        logger.info("   restore 완료")

        logger.info("3/3 정합성 검증...")
        import psycopg2
        local = psycopg2.connect(local_url)
        railway = psycopg2.connect(railway_url)

        tables = ["apartments", "trade_history", "rent_history", "common_code",
                   "facilities", "apt_facility_summary", "apt_safety_score"]
        for table in tables:
            lcur = local.cursor()
            rcur = railway.cursor()
            lcur.execute(f"SELECT COUNT(*) FROM {table}")
            l = lcur.fetchone()[0]
            rcur.execute(f"SELECT COUNT(*) FROM {table}")
            r = rcur.fetchone()[0]
            ok = "OK" if l == r else "MISMATCH"
            logger.info(f"  {table:25s} 로컬: {l:>10,}  Railway: {r:>10,}  [{ok}]")

        # 동기화 시각 갱신
        now_str = datetime.now(timezone.utc).isoformat()
        _save_last_sync(local, now_str)

        local.close()
        railway.close()
        logger.info("전체 동기화 완료")

    finally:
        if os.path.exists(dump_file):
            os.remove(dump_file)


def push_to_railway(logger):
    """로컬 DB → Railway DB 전체 동기화 (pg_dump/pg_restore)."""
    local_url = os.getenv("DATABASE_URL")
    railway_url = os.getenv("RAILWAY_DATABASE_URL")
    dump_file = os.path.join(tempfile.gettempdir(), "local_backup.dump")

    pg_dump = "/opt/homebrew/opt/postgresql@18/bin/pg_dump"
    pg_restore = "/opt/homebrew/opt/postgresql@18/bin/pg_restore"
    if not os.path.exists(pg_dump):
        pg_dump = "pg_dump"
        pg_restore = "pg_restore"

    try:
        logger.info("1/3 로컬 DB dump 시작...")
        result = subprocess.run(
            [pg_dump, local_url, "--format=custom", "--no-owner", "--no-acl", f"--file={dump_file}"],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            logger.error(f"pg_dump 실패: {result.stderr}")
            return

        size_mb = os.path.getsize(dump_file) / 1024 / 1024
        logger.info(f"   dump 완료: {size_mb:.1f}MB")

        logger.info("2/3 Railway DB restore 시작...")
        result = subprocess.run(
            [pg_restore, "--clean", "--if-exists", "--no-owner", "--no-acl", f"--dbname={railway_url}", dump_file],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0 and "error" in result.stderr.lower():
            logger.warning(f"pg_restore 경고: {result.stderr[:500]}")
        logger.info("   restore 완료")

        logger.info("3/3 정합성 검증...")
        local = psycopg2.connect(local_url)
        railway = psycopg2.connect(railway_url)

        tables = ["apartments", "trade_history", "rent_history", "common_code",
                   "facilities", "apt_facility_summary", "apt_safety_score",
                   "trade_apt_mapping", "apt_price_score"]
        for table in tables:
            lcur = local.cursor()
            rcur = railway.cursor()
            lcur.execute(f"SELECT COUNT(*) FROM {table}")
            l = lcur.fetchone()[0]
            rcur.execute(f"SELECT COUNT(*) FROM {table}")
            r = rcur.fetchone()[0]
            ok = "OK" if l == r else "MISMATCH"
            logger.info(f"  {table:25s} 로컬: {l:>10,}  Railway: {r:>10,}  [{ok}]")

        local.close()
        railway.close()
        logger.info("로컬 → Railway 동기화 완료")

    finally:
        if os.path.exists(dump_file):
            os.remove(dump_file)


def main():
    parser = argparse.ArgumentParser(description="DB 동기화 (Railway ↔ 로컬)")
    parser.add_argument("--mode", choices=["incremental", "full", "push"], default="incremental",
                        help="incremental: Railway→로컬 신규 건 (기본) / full: Railway→로컬 전체 / push: 로컬→Railway 전체")
    args = parser.parse_args()

    logger = setup_logger("sync")

    local_url = os.getenv("DATABASE_URL")
    railway_url = os.getenv("RAILWAY_DATABASE_URL")
    if not local_url or not railway_url:
        logger.error("DATABASE_URL 또는 RAILWAY_DATABASE_URL이 .env에 없습니다.")
        return

    if args.mode == "full":
        full_sync(logger)
    elif args.mode == "push":
        push_to_railway(logger)
    else:
        incremental_sync(logger)


if __name__ == "__main__":
    main()
