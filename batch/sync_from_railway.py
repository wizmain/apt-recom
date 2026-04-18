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

# 아파트 관련 테이블: created_at 부재 → PK 기반 전략
# mode: "missing_only" (Railway에만 있는 PK만 INSERT)
#       "upsert"       (PK 충돌 시 전체 컬럼 UPDATE — 재계산되는 스코어용)
APT_SYNC_TABLES = [
    {
        "name": "apartments",
        "pk": ["pnu"],
        "cols": ["pnu", "bld_nm", "total_hhld_cnt", "dong_count", "max_floor",
                 "use_apr_day", "plat_plc", "new_plat_plc", "bjd_code", "sigungu_code",
                 "lat", "lng", "bld_nm_norm", "coord_source", "group_pnu"],
        "mode": "missing_only",
    },
    {
        "name": "trade_apt_mapping",
        "pk": ["apt_seq"],
        "cols": ["apt_seq", "pnu", "apt_nm", "sgg_cd", "match_method"],
        "mode": "missing_only",
    },
    {
        "name": "apt_facility_summary",
        "pk": ["pnu", "facility_subtype"],
        "cols": ["pnu", "facility_subtype", "nearest_distance_m",
                 "count_1km", "count_3km", "count_5km"],
        "mode": "missing_only",
    },
    {
        "name": "apt_safety_score",
        "pk": ["pnu"],
        "cols": ["pnu", "safety_score", "cctv_count_500m", "cctv_count_1km",
                 "nearest_cctv_m", "crime_safety_score", "micro_score",
                 "access_score", "macro_score", "complex_score", "data_reliability",
                 "crime_hotspot_grade", "score_version", "complex_cctv_score",
                 "complex_security_score", "complex_mgr_score", "complex_parking_score",
                 "regional_safety_score", "crime_adjust_score", "complex_data_source"],
        "mode": "upsert",
    },
    {
        "name": "apt_price_score",
        "pk": ["pnu"],
        "cols": ["pnu", "price_per_m2", "sgg_avg_price_per_m2",
                 "price_score", "jeonse_ratio"],
        "mode": "upsert",
    },
]


def _sync_apt_table(local, railway, cfg, logger):
    """아파트 관련 테이블 단건 동기화."""
    table = cfg["name"]
    pk_cols = cfg["pk"]
    all_cols = cfg["cols"]
    mode = cfg["mode"]

    pk_sql = ", ".join(pk_cols)
    col_sql = ", ".join(all_cols)
    placeholders = ", ".join(["%s"] * len(all_cols))

    if mode == "missing_only":
        # Railway 전체 조회 후 로컬 PK 집합과 비교해 누락 행만 INSERT
        lcur = local.cursor()
        lcur.execute(f"SELECT {pk_sql} FROM {table}")
        local_pks = {tuple(r) for r in lcur.fetchall()}

        rcur = railway.cursor()
        rcur.execute(f"SELECT {col_sql} FROM {table}")
        pk_indices = [all_cols.index(c) for c in pk_cols]
        missing_rows = [
            row for row in rcur.fetchall()
            if tuple(row[i] for i in pk_indices) not in local_pks
        ]

        if not missing_rows:
            logger.info(f"  {table}: 신규 없음")
            return 0

        lcur2 = local.cursor()
        psycopg2.extras.execute_values(
            lcur2,
            f"INSERT INTO {table} ({col_sql}) VALUES %s ON CONFLICT ({pk_sql}) DO NOTHING",
            missing_rows,
            page_size=500,
        )
        local.commit()
        logger.info(f"  {table}: {len(missing_rows):,}건 신규 INSERT")
        return len(missing_rows)

    elif mode == "upsert":
        # Railway 전체를 로컬로 UPSERT (PK 충돌 시 UPDATE)
        rcur = railway.cursor()
        rcur.execute(f"SELECT {col_sql} FROM {table}")
        rows = rcur.fetchall()
        if not rows:
            logger.info(f"  {table}: Railway 데이터 없음")
            return 0

        update_cols = [c for c in all_cols if c not in pk_cols]
        update_sql = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])
        lcur = local.cursor()
        psycopg2.extras.execute_values(
            lcur,
            f"""INSERT INTO {table} ({col_sql}) VALUES %s
                ON CONFLICT ({pk_sql}) DO UPDATE SET {update_sql}""",
            rows,
            page_size=500,
        )
        local.commit()
        logger.info(f"  {table}: {len(rows):,}건 UPSERT")
        return len(rows)

    else:
        logger.warning(f"  {table}: 알 수 없는 모드 '{mode}' — 스킵")
        return 0


def sync_apt_tables(local, railway, logger):
    """아파트 관련 5개 테이블 동기화."""
    logger.info("아파트 관련 테이블 동기화 시작")
    total = 0
    for cfg in APT_SYNC_TABLES:
        try:
            total += _sync_apt_table(local, railway, cfg, logger)
        except Exception as e:
            local.rollback()
            logger.error(f"  {cfg['name']} 동기화 실패: {e}")
    logger.info(f"아파트 관련 테이블 동기화 완료: {total:,}건")
    return total


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

    # 아파트 관련 테이블 동기화 (PK 기반)
    apt_total = sync_apt_tables(local, railway, logger)

    # 검증
    logger.info("정합성 검증:")
    verify_tables = ["trade_history", "rent_history"] + [c["name"] for c in APT_SYNC_TABLES]
    for table in verify_tables:
        lcur = local.cursor()
        rcur = railway.cursor()
        lcur.execute(f"SELECT COUNT(*) FROM {table}")
        l = lcur.fetchone()[0]
        rcur.execute(f"SELECT COUNT(*) FROM {table}")
        r = rcur.fetchone()[0]
        if l == r:
            status = "OK"
        elif l > r:
            status = f"로컬 추가 +{l - r:,}"
        else:
            status = f"부족 {r - l:+,}"
        logger.info(f"  {table:28s} 로컬 {l:>10,} / Railway {r:>10,} [{status}]")

    local.close()
    railway.close()
    logger.info(f"증분 동기화 완료: trade/rent {total:,}건 + apt {apt_total:,}건")


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
            capture_output=True, text=True, timeout=1800,
        )
        if result.returncode != 0:
            logger.error(f"pg_dump 실패: {result.stderr}")
            return

        size_mb = os.path.getsize(dump_file) / 1024 / 1024
        logger.info(f"   dump 완료: {size_mb:.1f}MB")

        logger.info("2/3 로컬 DB restore 시작...")
        result = subprocess.run(
            [pg_restore, "--clean", "--if-exists", "--no-owner", "--no-acl", f"--dbname={local_url}", dump_file],
            capture_output=True, text=True, timeout=1800,
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
            capture_output=True, text=True, timeout=1800,
        )
        if result.returncode != 0:
            logger.error(f"pg_dump 실패: {result.stderr}")
            return

        size_mb = os.path.getsize(dump_file) / 1024 / 1024
        logger.info(f"   dump 완료: {size_mb:.1f}MB")

        logger.info("2/3 Railway DB restore 시작...")
        result = subprocess.run(
            [pg_restore, "--clean", "--if-exists", "--no-owner", "--no-acl", f"--dbname={railway_url}", dump_file],
            capture_output=True, text=True, timeout=1800,
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
