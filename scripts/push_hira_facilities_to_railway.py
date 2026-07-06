"""심평원 병원 시설(facilities HIRA_*) + summary 3 subtype 을 로컬 → Railway 벌크 동기화.

라이프점수 Phase 2-3 배포 단계 (병원정보서비스 세분화).

방식: Railway 에서 재수집(행 단위 원격 upsert)은 WAN RTT 로 수 시간이 걸려 부적합.
로컬 최종 상태가 이미 unique 제약(idx_facility_unique)을 통과한 자기정합 집합이므로,
**대상 범위 DELETE 후 execute_values 일괄 INSERT** 로 복사한다 — 재수집 시
대표 기관 선정이 로컬/prod 간 어긋나는 충돌도 원천 회피된다.

트랜잭션 1개로 수행 — 실패 시 전체 롤백 (prod 부분 상태 없음).

⚠️ production 쓰기 — 사용자 승인 하에 실행.

사용 (기본 dry-run):
  .venv/bin/python scripts/push_hira_facilities_to_railway.py
  .venv/bin/python scripts/push_hira_facilities_to_railway.py --apply
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

HIRA_SUBTYPES = ["pediatric_clinic", "obgyn_clinic", "general_hospital"]

FACILITY_COLS = (
    "facility_id, facility_type, facility_subtype, name, lat, lng, address, is_active"
)
SUMMARY_COLS = (
    "pnu, facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km"
)


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
    lcur.execute(
        f"SELECT {FACILITY_COLS} FROM facilities "
        "WHERE facility_subtype = ANY(%s) AND facility_id LIKE 'HIRA\\_%%'",
        [HIRA_SUBTYPES],
    )
    fac_rows = lcur.fetchall()
    lcur.execute(
        f"SELECT {SUMMARY_COLS} FROM apt_facility_summary WHERE facility_subtype = ANY(%s)",
        [HIRA_SUBTYPES],
    )
    sum_rows = lcur.fetchall()
    local.close()
    print(f"로컬: facilities {len(fac_rows):,}행 / summary {len(sum_rows):,}행")

    if not fac_rows or not sum_rows:
        raise SystemExit("로컬 데이터 없음 — 수집/집계 먼저 실행")

    if not args.apply:
        print("dry-run 종료 (Railway 미접속) — 반영하려면 --apply")
        return

    railway = psycopg2.connect(railway_url)
    railway.autocommit = False
    try:
        rcur = railway.cursor()
        rcur.execute(
            "DELETE FROM facilities WHERE facility_subtype = ANY(%s)", [HIRA_SUBTYPES]
        )
        print(f"Railway facilities 기존 삭제: {rcur.rowcount:,}행")
        execute_values(
            rcur,
            f"INSERT INTO facilities ({FACILITY_COLS}) VALUES %s",
            fac_rows,
            page_size=2000,
        )
        rcur.execute(
            "DELETE FROM apt_facility_summary WHERE facility_subtype = ANY(%s)",
            [HIRA_SUBTYPES],
        )
        print(f"Railway summary 기존 삭제: {rcur.rowcount:,}행")
        execute_values(
            rcur,
            f"INSERT INTO apt_facility_summary ({SUMMARY_COLS}) VALUES %s",
            sum_rows,
            page_size=2000,
        )
        railway.commit()
        rcur.execute(
            "SELECT facility_subtype, COUNT(*) FROM facilities "
            "WHERE facility_subtype = ANY(%s) GROUP BY 1 ORDER BY 1",
            [HIRA_SUBTYPES],
        )
        print("✅ Railway facilities:", rcur.fetchall())
        rcur.execute(
            "SELECT COUNT(*) FROM apt_facility_summary WHERE facility_subtype = ANY(%s)",
            [HIRA_SUBTYPES],
        )
        print("✅ Railway summary:", rcur.fetchone()[0], "행")
    except Exception:
        railway.rollback()
        raise
    finally:
        railway.close()


if __name__ == "__main__":
    main()
