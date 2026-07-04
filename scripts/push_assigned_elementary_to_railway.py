"""assigned_elementary summary 행을 로컬 → Railway 로 UPSERT 동기화.

라이프점수 Phase 1 배포 체크리스트 ①단계 (PR #131 참조).
apt_facility_summary 전체(50만+행)가 아니라 facility_subtype='assigned_elementary'
행(약 3.5만)만 동기화한다 — 다른 subtype 은 Railway 의 quarterly 배치 산출물을
건드리지 않는다.

⚠️ production 쓰기 — CLAUDE.md 정책상 사용자가 직접 실행한다.

사용 (기본 dry-run — Railway 에 접속하지 않고 로컬 행수만 확인):
  .venv/bin/python scripts/push_assigned_elementary_to_railway.py
  .venv/bin/python scripts/push_assigned_elementary_to_railway.py --apply

실행 후: ② scripts/update_education_weights.py --target railway --apply
        ③ Railway 백엔드 재기동 (가중치/summary 캐시 없음 — 재기동은 ②의 가중치 캐시용)
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

SUBTYPE = "assigned_elementary"

UPSERT_SQL = """
    INSERT INTO apt_facility_summary
        (pnu, facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km)
    VALUES %s
    ON CONFLICT (pnu, facility_subtype) DO UPDATE SET
        nearest_distance_m = EXCLUDED.nearest_distance_m,
        count_1km = EXCLUDED.count_1km,
        count_3km = EXCLUDED.count_3km,
        count_5km = EXCLUDED.count_5km
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Railway 에 실제 반영 (기본 dry-run)"
    )
    args = parser.parse_args()

    local_url = os.getenv("DATABASE_URL")
    if not local_url:
        raise SystemExit("DATABASE_URL 미설정 (.env 확인)")

    local = psycopg2.connect(local_url)
    cur = local.cursor()
    cur.execute(
        "SELECT pnu, facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km "
        "FROM apt_facility_summary WHERE facility_subtype = %s",
        [SUBTYPE],
    )
    rows = cur.fetchall()
    local.close()
    print(f"로컬 {SUBTYPE} 행: {len(rows):,}")

    if not rows:
        raise SystemExit(
            "로컬에 동기화할 행이 없음 — batch.quarterly.assigned_school 먼저 실행"
        )

    if not args.apply:
        print("dry-run 종료 (Railway 미접속) — 반영하려면 --apply")
        return

    railway_url = os.getenv("RAILWAY_DATABASE_URL")
    if not railway_url:
        raise SystemExit("RAILWAY_DATABASE_URL 미설정 (.env 확인)")
    if "railway" not in railway_url and "rlwy" not in railway_url:
        raise SystemExit("RAILWAY_DATABASE_URL 이 Railway 형태가 아님 — 안전상 중단")

    railway = psycopg2.connect(railway_url)
    railway.autocommit = False
    try:
        rcur = railway.cursor()
        execute_values(rcur, UPSERT_SQL, rows, page_size=1000)
        railway.commit()
        rcur.execute(
            "SELECT COUNT(*) FROM apt_facility_summary WHERE facility_subtype = %s",
            [SUBTYPE],
        )
        print(f"✅ Railway 반영 완료 — {SUBTYPE} 행: {rcur.fetchone()[0]:,}")
    finally:
        railway.close()


if __name__ == "__main__":
    main()
