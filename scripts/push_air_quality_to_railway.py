"""에어코리아 대기질 3테이블(측정소/월평균/apt 점수)을 로컬 → Railway 벌크 동기화.

라이프점수 Phase 2-4 배포 단계 (nature 재설계 — score_air 축).

신규 facility(facilities+apt_facility_summary 형태) 배포는 범용 스크립트
`push_facilities_to_railway.py --prefix ... --subtypes ...`를 사용할 것 — 본 파일은
facilities 형태가 아닌 전용 테이블 3개를 다뤄 범용화 대상에서 제외, 완료 기록물로 유지.

방식: push_hira_facilities_to_railway.py 골격 준용 — 로컬 최종 상태가 이미
UNIQUE 제약(air_quality_monthly)/PK(air_quality_station, apt_air_score) 을
통과한 자기정합 집합이므로, **전체 DELETE 후 execute_values 일괄 INSERT** 로
복사한다. 대상 테이블이 3개뿐이고 subtype 필터가 없는 전용 테이블이라
범위 조건 없이 전체 교체한다.

⚠️ Railway 에 create_tables() 가 아직 실행되지 않아 3개 테이블이 존재하지
않을 수 있다 — 이 스크립트는 INSERT 전 database.py 와 동일한 DDL 을
인라인으로 CREATE TABLE IF NOT EXISTS 실행한다(멱등, 기존 데이터 무영향).

트랜잭션 1개로 수행 — 실패 시 전체 롤백 (prod 부분 상태 없음).

⚠️ production 쓰기 — 사용자 승인 하에 실행.

사용 (기본 dry-run, Railway 미접속 — 로컬 조회만 수행):
  .venv/bin/python scripts/push_air_quality_to_railway.py
  .venv/bin/python scripts/push_air_quality_to_railway.py --apply
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

# database.py create_tables() 의 대기질 3테이블 DDL 과 동일 (Phase 2-4).
# Railway 에 아직 반영되지 않았을 수 있어 이 스크립트에서 인라인 실행한다.
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS air_quality_station (
    station_name TEXT PRIMARY KEY,
    addr TEXT,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    mang_name TEXT,
    measured_items TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS air_quality_monthly (
    id SERIAL PRIMARY KEY,
    station_name TEXT NOT NULL,
    measure_month CHAR(7) NOT NULL,
    pm25 DOUBLE PRECISION,
    pm10 DOUBLE PRECISION,
    o3 DOUBLE PRECISION,
    no2 DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (station_name, measure_month)
);
CREATE INDEX IF NOT EXISTS idx_air_monthly_station ON air_quality_monthly (station_name);

CREATE TABLE IF NOT EXISTS apt_air_score (
    pnu TEXT PRIMARY KEY,
    station_name TEXT,
    station_distance_m DOUBLE PRECISION,
    avg_pm25 DOUBLE PRECISION,
    month_count INTEGER,
    score_air DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
-- 최초 배포 시 VARCHAR(19)로 생성된 환경 보정용 — 이미 TEXT 인 경우 no-op, 멱등.
ALTER TABLE apt_air_score ALTER COLUMN pnu TYPE TEXT;
"""

STATION_COLS = "station_name, addr, lat, lng, mang_name, measured_items, is_active"
MONTHLY_COLS = "station_name, measure_month, pm25, pm10, o3, no2"
SCORE_COLS = "pnu, station_name, station_distance_m, avg_pm25, month_count, score_air"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Railway 반영 (기본 dry-run)"
    )
    args = parser.parse_args()

    local_url = os.getenv("DATABASE_URL")
    railway_url = os.getenv("RAILWAY_DATABASE_URL")
    if not local_url or not railway_url:
        raise SystemExit("DATABASE_URL / RAILWAY_DATABASE_URL 확인 필요 (.env)")
    if "railway" not in railway_url and "rlwy" not in railway_url:
        raise SystemExit("RAILWAY_DATABASE_URL 이 Railway 형태가 아님 — 안전상 중단")

    local = psycopg2.connect(local_url)
    lcur = local.cursor()
    lcur.execute(f"SELECT {STATION_COLS} FROM air_quality_station")
    station_rows = lcur.fetchall()
    lcur.execute(f"SELECT {MONTHLY_COLS} FROM air_quality_monthly")
    monthly_rows = lcur.fetchall()
    lcur.execute(f"SELECT {SCORE_COLS} FROM apt_air_score")
    score_rows = lcur.fetchall()
    local.close()
    print(
        f"로컬: air_quality_station {len(station_rows):,}행 / "
        f"air_quality_monthly {len(monthly_rows):,}행 / "
        f"apt_air_score {len(score_rows):,}행"
    )

    if not station_rows or not monthly_rows or not score_rows:
        raise SystemExit(
            "로컬 데이터 없음 — batch/quarterly/collect_air_quality.py 먼저 실행"
        )

    if not args.apply:
        print("dry-run 종료 (Railway 미접속) — 반영하려면 --apply")
        return

    railway = psycopg2.connect(railway_url)
    railway.autocommit = False
    try:
        rcur = railway.cursor()
        rcur.execute(CREATE_TABLES_SQL)
        print("Railway 테이블 확인/생성 완료 (CREATE TABLE IF NOT EXISTS)")

        rcur.execute("DELETE FROM apt_air_score")
        print(f"Railway apt_air_score 기존 삭제: {rcur.rowcount:,}행")
        rcur.execute("DELETE FROM air_quality_monthly")
        print(f"Railway air_quality_monthly 기존 삭제: {rcur.rowcount:,}행")
        rcur.execute("DELETE FROM air_quality_station")
        print(f"Railway air_quality_station 기존 삭제: {rcur.rowcount:,}행")

        execute_values(
            rcur,
            f"INSERT INTO air_quality_station ({STATION_COLS}) VALUES %s",
            station_rows,
            page_size=2000,
        )
        execute_values(
            rcur,
            f"INSERT INTO air_quality_monthly ({MONTHLY_COLS}) VALUES %s",
            monthly_rows,
            page_size=2000,
        )
        execute_values(
            rcur,
            f"INSERT INTO apt_air_score ({SCORE_COLS}) VALUES %s",
            score_rows,
            page_size=2000,
        )
        railway.commit()

        rcur.execute("SELECT COUNT(*) FROM air_quality_station")
        print("✅ Railway air_quality_station:", rcur.fetchone()[0], "행")
        rcur.execute("SELECT COUNT(DISTINCT measure_month) FROM air_quality_monthly")
        print("✅ Railway air_quality_monthly 월수:", rcur.fetchone()[0])
        rcur.execute(
            "SELECT COUNT(*), AVG(score_air) FROM apt_air_score WHERE score_air IS NOT NULL"
        )
        print("✅ Railway apt_air_score:", rcur.fetchone())
    except Exception:
        railway.rollback()
        raise
    finally:
        railway.close()


if __name__ == "__main__":
    main()
