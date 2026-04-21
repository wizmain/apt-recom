"""로컬 DB → Railway DB 테이블 단위 UPSERT 동기화.

지정 테이블의 로컬 데이터를 Railway에 UPSERT한다.
전체 DB를 덮어쓰지 않으므로 다른 테이블에 영향 없음.

사용법:
  python -m batch.push_table_to_railway apt_area_info
  python -m batch.push_table_to_railway apt_area_info --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger("push_table")

# 테이블별 설정: (PK 컬럼, 전체 컬럼 목록)
TABLE_CONFIGS = {
    "apt_area_info": {
        "pk": ["pnu"],
        "columns": [
            "pnu", "min_area", "max_area", "avg_area",
            "min_supply_area", "max_supply_area", "avg_supply_area",
            "unit_count", "area_types",
            "cnt_under_40", "cnt_40_60", "cnt_60_85",
            "cnt_85_115", "cnt_115_135", "cnt_over_135",
            "source", "last_refreshed",
        ],
    },
    "apt_area_type": {
        "pk": ["pnu", "exclusive_area"],
        "columns": [
            "pnu", "exclusive_area", "unit_count",
            "mgmt_area_total", "priv_area_total", "last_refreshed",
        ],
    },
    "apt_mgmt_cost": {
        "pk": ["pnu", "year_month"],
        "columns": [
            "pnu", "year_month",
            "common_cost", "individual_cost", "repair_fund",
            "total_cost", "cost_per_unit", "detail",
        ],
    },
    "apt_kapt_info": {
        "pk": ["pnu"],
        "columns": [
            "pnu", "kapt_code", "kapt_name", "sigungu_code",
            "sale_type", "heat_type", "builder", "developer",
            "apt_type", "mgr_type", "hall_type", "structure",
            "total_area", "priv_area", "mgmt_area",
            "ho_cnt", "dong_cnt", "top_floor", "top_floor_official",
            "base_floor", "use_date",
            "sale_ho_cnt", "rent_ho_cnt", "rent_public_cnt", "rent_private_cnt",
            "area_under_60", "area_60_85", "area_85_135", "area_over_135",
            "mgmt_company", "general_mgmt_type", "general_mgmt_staff",
            "security_type", "security_staff", "security_company",
            "parking_cnt", "parking_ground", "parking_underground",
            "total_car_cnt", "ev_car_cnt", "ev_charger_cnt",
            "ev_charger_ground", "ev_charger_underground",
            "ev_parking_ground", "ev_parking_underground",
            "cctv_cnt", "elevator_cnt",
            "elevator_passenger", "elevator_freight", "elevator_mixed",
            "elevator_disabled", "elevator_emergency",
            "home_network", "welfare", "convenience_facilities",
            "jibun_addr", "road_addr", "tel", "fax", "homepage", "zipcode",
            "subway_info", "bus_time",
            "joined_date", "food_waste_method", "cleaning_staff", "elevator_mgr_type",
            "updated_at",
        ],
    },
}

BATCH_SIZE = 500


def _ensure_remote_schema(remote_conn, table: str) -> None:
    """Railway에 테이블/컬럼이 없으면 생성."""
    cur = remote_conn.cursor()

    if table == "apt_area_info":
        cur.execute("""
            CREATE TABLE IF NOT EXISTS apt_area_info (
                pnu TEXT PRIMARY KEY,
                min_area DOUBLE PRECISION, max_area DOUBLE PRECISION, avg_area DOUBLE PRECISION,
                unit_count INTEGER, area_types INTEGER,
                cnt_under_40 INTEGER, cnt_40_60 INTEGER, cnt_60_85 INTEGER,
                cnt_85_115 INTEGER, cnt_115_135 INTEGER, cnt_over_135 INTEGER
            )
        """)
        for col_ddl in [
            "ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS source TEXT",
            "ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS last_refreshed TIMESTAMPTZ",
            "ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS min_supply_area DOUBLE PRECISION",
            "ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS max_supply_area DOUBLE PRECISION",
            "ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS avg_supply_area DOUBLE PRECISION",
        ]:
            cur.execute(col_ddl)

    elif table == "apt_mgmt_cost":
        cur.execute("""
            CREATE TABLE IF NOT EXISTS apt_mgmt_cost (
                pnu TEXT,
                year_month TEXT,
                common_cost BIGINT,
                individual_cost BIGINT,
                repair_fund BIGINT,
                total_cost BIGINT,
                cost_per_unit BIGINT,
                detail JSONB,
                PRIMARY KEY (pnu, year_month)
            )
        """)

    elif table == "apt_area_type":
        cur.execute("""
            CREATE TABLE IF NOT EXISTS apt_area_type (
                pnu TEXT NOT NULL,
                exclusive_area DOUBLE PRECISION NOT NULL,
                unit_count INTEGER NOT NULL,
                mgmt_area_total DOUBLE PRECISION,
                priv_area_total DOUBLE PRECISION,
                last_refreshed TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (pnu, exclusive_area)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_apt_area_type_pnu ON apt_area_type(pnu)")

    elif table == "apt_kapt_info":
        # 원본 CREATE은 backend/database.py에서 이미 생성됐을 가능성 높음.
        # 누락 컬럼만 ADD.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS apt_kapt_info (
                pnu TEXT PRIMARY KEY,
                kapt_code TEXT, kapt_name TEXT, sigungu_code TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        add_cols = [
            ("sale_type", "TEXT"), ("heat_type", "TEXT"), ("builder", "TEXT"),
            ("developer", "TEXT"), ("apt_type", "TEXT"), ("mgr_type", "TEXT"),
            ("hall_type", "TEXT"), ("structure", "TEXT"),
            ("total_area", "DOUBLE PRECISION"), ("priv_area", "DOUBLE PRECISION"),
            ("mgmt_area", "DOUBLE PRECISION"),
            ("ho_cnt", "INTEGER"), ("dong_cnt", "INTEGER"),
            ("top_floor", "INTEGER"), ("top_floor_official", "INTEGER"),
            ("base_floor", "INTEGER"), ("use_date", "TEXT"),
            ("sale_ho_cnt", "INTEGER"), ("rent_ho_cnt", "INTEGER"),
            ("rent_public_cnt", "INTEGER"), ("rent_private_cnt", "INTEGER"),
            ("area_under_60", "INTEGER"), ("area_60_85", "INTEGER"),
            ("area_85_135", "INTEGER"), ("area_over_135", "INTEGER"),
            ("mgmt_company", "TEXT"), ("general_mgmt_type", "TEXT"),
            ("general_mgmt_staff", "INTEGER"), ("security_type", "TEXT"),
            ("security_staff", "INTEGER"), ("security_company", "TEXT"),
            ("parking_cnt", "INTEGER"), ("parking_ground", "INTEGER"),
            ("parking_underground", "INTEGER"),
            ("total_car_cnt", "INTEGER"), ("ev_car_cnt", "INTEGER"),
            ("ev_charger_cnt", "INTEGER"),
            ("ev_charger_ground", "INTEGER"), ("ev_charger_underground", "INTEGER"),
            ("ev_parking_ground", "INTEGER"), ("ev_parking_underground", "INTEGER"),
            ("cctv_cnt", "INTEGER"), ("elevator_cnt", "INTEGER"),
            ("elevator_passenger", "INTEGER"), ("elevator_freight", "INTEGER"),
            ("elevator_mixed", "INTEGER"), ("elevator_disabled", "INTEGER"),
            ("elevator_emergency", "INTEGER"),
            ("home_network", "TEXT"), ("welfare", "TEXT"),
            ("convenience_facilities", "TEXT"),
            ("jibun_addr", "TEXT"), ("road_addr", "TEXT"),
            ("tel", "TEXT"), ("fax", "TEXT"), ("homepage", "TEXT"),
            ("zipcode", "TEXT"),
            ("subway_info", "TEXT"), ("bus_time", "TEXT"),
            ("joined_date", "TEXT"), ("food_waste_method", "TEXT"),
            ("cleaning_staff", "INTEGER"), ("elevator_mgr_type", "TEXT"),
        ]
        for col, typ in add_cols:
            cur.execute(f"ALTER TABLE apt_kapt_info ADD COLUMN IF NOT EXISTS {col} {typ}")

    remote_conn.commit()


def push_table(table: str, *, dry_run: bool = False) -> None:
    config = TABLE_CONFIGS.get(table)
    if not config:
        logger.error(f"지원하지 않는 테이블: {table}")
        logger.info(f"지원 테이블: {', '.join(TABLE_CONFIGS.keys())}")
        return

    local_url = os.getenv("DATABASE_URL")
    railway_url = os.getenv("RAILWAY_DATABASE_URL")
    if not local_url or not railway_url:
        logger.error("DATABASE_URL 또는 RAILWAY_DATABASE_URL이 .env에 없습니다.")
        return

    local = psycopg2.connect(local_url)
    remote = psycopg2.connect(railway_url)

    pk_cols = config["pk"]
    all_cols = config["columns"]
    non_pk = [c for c in all_cols if c not in pk_cols]

    # Railway 스키마 보장
    _ensure_remote_schema(remote, table)

    # 로컬 데이터 조회
    local_cur = local.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    local_cur.execute(f"SELECT {', '.join(all_cols)} FROM {table}")
    local_rows = local_cur.fetchall()
    logger.info(f"로컬 {table}: {len(local_rows):,}건")

    # Railway 현재 건수
    remote_cur = remote.cursor()
    remote_cur.execute(f"SELECT COUNT(*) FROM {table}")
    remote_before = remote_cur.fetchone()[0]
    logger.info(f"Railway {table} (before): {remote_before:,}건")

    if dry_run:
        logger.info("[DRY-RUN] 실제 UPSERT 생략")
        local.close()
        remote.close()
        return

    # UPSERT 생성
    col_list = ", ".join(all_cols)
    placeholders = ", ".join([f"%({c})s" for c in all_cols])
    conflict_cols = ", ".join(pk_cols)
    update_set = ", ".join([f"{c} = EXCLUDED.{c}" for c in non_pk])

    upsert_sql = f"""
        INSERT INTO {table} ({col_list})
        VALUES ({placeholders})
        ON CONFLICT ({conflict_cols}) DO UPDATE SET {update_set}
    """

    # dict/list 컬럼(JSONB)은 Json 어댑터로 감싸야 psycopg2가 바인딩 가능
    jsonb_cols = {"detail"}

    def _adapt(row: dict) -> dict:
        out = dict(row)
        for c in jsonb_cols:
            if c in out and isinstance(out[c], (dict, list)):
                out[c] = psycopg2.extras.Json(out[c])
        return out

    # 배치 UPSERT — execute_batch 사용(round-trip 수십 배 감소)
    inserted = 0
    for i in range(0, len(local_rows), BATCH_SIZE):
        batch = [_adapt(r) for r in local_rows[i:i + BATCH_SIZE]]
        remote_cur = remote.cursor()
        psycopg2.extras.execute_batch(remote_cur, upsert_sql, batch, page_size=BATCH_SIZE)
        remote.commit()
        inserted += len(batch)
        if inserted % 5000 == 0 or inserted == len(local_rows):
            logger.info(f"  진행: {inserted:,}/{len(local_rows):,}")

    # 검증
    remote_cur = remote.cursor()
    remote_cur.execute(f"SELECT COUNT(*) FROM {table}")
    remote_after = remote_cur.fetchone()[0]

    logger.info(f"Railway {table} (after): {remote_after:,}건 (이전: {remote_before:,})")
    logger.info(f"UPSERT 완료: {len(local_rows):,}건 처리")

    local.close()
    remote.close()


def main():
    parser = argparse.ArgumentParser(description="로컬 → Railway 테이블 UPSERT")
    parser.add_argument("table", help="동기화할 테이블명")
    parser.add_argument("--dry-run", action="store_true", help="실제 쓰기 없이 확인만")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    push_table(args.table, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
