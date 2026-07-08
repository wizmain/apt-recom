"""apt_mgmt_cost 로컬 → Railway 벌크 upsert (월별 정기 관리비 반영).

K-APT 관리비는 자료실 엑셀을 로컬에 적재(collect_mgmt_cost --source xlsx)한 뒤
이 스크립트로 Railway 에 반영한다 — collect_mgmt_cost 의 --target railway 는
행 단위 원격 upsert 라 10만 행 기준 1시간 이상 걸려 부적합(벌크 복사 관례).

방식: DELETE 없이 **execute_values + ON CONFLICT (pnu, year_month) DO UPDATE**.
Railway 에만 존재하는 (pnu,월) 행(API 수집분 등)을 보존하기 위해 교체가 아닌
upsert 를 쓴다 — 2026-07 실측에서 Railway 전용 키 70건 확인됨.

트랜잭션 1개 — 실패 시 전체 롤백.

⚠️ production 쓰기 — 사용자 승인 하에 실행.

사용 (기본 dry-run):
  .venv/bin/python scripts/push_mgmt_cost_to_railway.py --since 202601
  .venv/bin/python scripts/push_mgmt_cost_to_railway.py --since 202601 --apply
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json, execute_values

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

COLS = (
    "pnu, year_month, common_cost, individual_cost, repair_fund, "
    "total_cost, cost_per_unit, detail"
)

UPSERT_SQL = (
    f"INSERT INTO apt_mgmt_cost ({COLS}) VALUES %s "
    "ON CONFLICT (pnu, year_month) DO UPDATE SET "
    "common_cost=EXCLUDED.common_cost, individual_cost=EXCLUDED.individual_cost, "
    "repair_fund=EXCLUDED.repair_fund, total_cost=EXCLUDED.total_cost, "
    "cost_per_unit=EXCLUDED.cost_per_unit, detail=EXCLUDED.detail"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, help="반영 시작 년월 YYYYMM (포함)")
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
        f"SELECT {COLS} FROM apt_mgmt_cost WHERE year_month >= %s", [args.since]
    )
    rows = [(*r[:7], Json(r[7])) for r in lcur.fetchall()]
    local.close()
    print(f"로컬 apt_mgmt_cost (>= {args.since}): {len(rows):,}행")
    if not rows:
        raise SystemExit("반영 대상 없음 — --since 확인")

    if not args.apply:
        print("dry-run 종료 (Railway 미접속) — 반영하려면 --apply")
        return

    railway = psycopg2.connect(railway_url)
    railway.autocommit = False
    try:
        rcur = railway.cursor()
        execute_values(rcur, UPSERT_SQL, rows, page_size=2000)
        railway.commit()
        rcur.execute(
            "SELECT year_month, COUNT(*) FROM apt_mgmt_cost "
            "WHERE year_month >= %s GROUP BY 1 ORDER BY 1",
            [args.since],
        )
        print("✅ Railway 월별 행수:", rcur.fetchall())
    except Exception:
        railway.rollback()
        raise
    finally:
        railway.close()


if __name__ == "__main__":
    main()
