"""Railway DB → 로컬 DB 동기화.

Railway에 수집된 비수도권 거래 데이터를 로컬 DB로 복사.
중복 체크 후 신규 건만 INSERT.

사용법:
  python -m batch.sync_from_railway
"""

import os
import psycopg2
import psycopg2.extras
from pathlib import Path
from dotenv import load_dotenv
from batch.logger import setup_logger

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def sync_table(table, cols, key_cols, local, railway, logger):
    """Railway → 로컬: 신규 건만 복사."""
    rcur = railway.cursor()
    rcur.execute(f"SELECT {cols} FROM {table}")
    rw_rows = rcur.fetchall()

    lcur = local.cursor()
    lcur.execute(f"SELECT {key_cols} FROM {table}")
    local_keys = set(tuple(str(v) for v in r) for r in lcur.fetchall())

    col_list = [c.strip() for c in cols.split(",")]
    kc_list = [c.strip() for c in key_cols.split(",")]
    key_indices = [col_list.index(k) for k in kc_list]

    new_rows = [r for r in rw_rows if tuple(str(r[i]) for i in key_indices) not in local_keys]

    if new_rows:
        lcur2 = local.cursor()
        psycopg2.extras.execute_values(
            lcur2, f"INSERT INTO {table} ({cols}) VALUES %s", new_rows, page_size=5000
        )
        local.commit()
        logger.info(f"  {table}: {len(new_rows):,}건 복사 (기존 {len(local_keys):,}건)")
    else:
        logger.info(f"  {table}: 신규 없음 (양쪽 동일)")

    return len(new_rows)


def main():
    logger = setup_logger("sync")
    local_url = os.getenv("DATABASE_URL")
    railway_url = os.getenv("RAILWAY_DATABASE_URL")

    if not local_url or not railway_url:
        logger.error("DATABASE_URL 또는 RAILWAY_DATABASE_URL이 .env에 없습니다.")
        return

    local = psycopg2.connect(local_url)
    railway = psycopg2.connect(railway_url)

    logger.info("Railway → 로컬 동기화 시작")

    total = 0
    total += sync_table(
        "trade_history",
        "apt_seq, sgg_cd, apt_nm, deal_amount, exclu_use_ar, floor, deal_year, deal_month, deal_day, build_year",
        "sgg_cd, apt_nm, deal_year, deal_month, deal_day, deal_amount",
        local, railway, logger,
    )
    total += sync_table(
        "rent_history",
        "apt_seq, sgg_cd, apt_nm, deposit, monthly_rent, exclu_use_ar, floor, deal_year, deal_month, deal_day",
        "sgg_cd, apt_nm, deal_year, deal_month, deal_day, deposit",
        local, railway, logger,
    )

    # 검증
    logger.info("정합성 검증:")
    for table in ["trade_history", "rent_history"]:
        lcur = local.cursor()
        rcur = railway.cursor()
        lcur.execute(f"SELECT COUNT(*) FROM {table}")
        l = lcur.fetchone()[0]
        rcur.execute(f"SELECT COUNT(*) FROM {table}")
        r = rcur.fetchone()[0]
        ok = "OK" if l == r else "MISMATCH"
        logger.info(f"  {table}: 로컬 {l:,} / Railway {r:,} [{ok}]")

    local.close()
    railway.close()
    logger.info(f"동기화 완료: {total:,}건 복사")


if __name__ == "__main__":
    main()
