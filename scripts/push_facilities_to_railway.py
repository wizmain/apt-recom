"""facilities(prefix+subtype 범위) + apt_facility_summary(subtype 범위)를 로컬 → Railway 벌크 동기화.

`push_hira_facilities_to_railway.py`/`push_store_facilities_to_railway.py` 골격을
`--prefix`/`--subtypes` 인자로 범용화한 스크립트 — Phase 2-5(NEIS 학원)부터는
subtype 전용 스크립트를 새로 만들지 않고 이 스크립트를 사용한다(기존
push_store/push_hira/push_air 는 완료 기록물로 유지, 미변경).

방식: Railway 에서 재수집(행 단위 원격 upsert)은 WAN RTT 로 수 시간이 걸려 부적합.
로컬 최종 상태가 이미 unique 제약(idx_facility_unique)을 통과한 자기정합 집합이므로,
**대상 범위 DELETE 후 execute_values 일괄 INSERT** 로 복사한다 — 재수집 시
대표 시설 선정이 로컬/prod 간 어긋나는 충돌도 원천 회피된다.

facilities 는 `facility_subtype = ANY(subtypes) AND facility_id LIKE '{prefix}%'` 로
범위를 좁혀 DELETE 한다(기존 3개 스크립트는 subtype 만으로 DELETE — 이 스크립트는
prefix 까지 함께 걸어 향후 동일 subtype 을 다른 프리픽스가 쓰게 되어도 안전).
apt_facility_summary 는 facility_id 를 갖지 않아 subtype 범위로만 DELETE 한다.

트랜잭션 1개로 수행 — 실패 시 전체 롤백 (prod 부분 상태 없음).

⚠️ production 쓰기 — 사용자 승인 하에 실행.

사용 (기본 dry-run):
  .venv/bin/python scripts/push_facilities_to_railway.py --prefix NEIS_ --subtypes academy
  .venv/bin/python scripts/push_facilities_to_railway.py --prefix NEIS_ --subtypes academy --apply
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

FACILITY_COLS = (
    "facility_id, facility_type, facility_subtype, name, lat, lng, address, is_active"
)
SUMMARY_COLS = (
    "pnu, facility_subtype, nearest_distance_m, count_1km, count_3km, count_5km"
)


def _escape_like_prefix(prefix: str) -> str:
    """LIKE 패턴의 와일드카드(%, _)와 이스케이프 문자(\\) 자체를 이스케이프.

    facility_id 접두어(예: NEIS_)에 포함된 '_' 는 LIKE 상 단일문자 와일드카드로
    해석되므로, 리터럴 매칭을 위해 반드시 이스케이프해야 한다(기존
    push_hira/push_store 스크립트와 동일한 이유).
    """
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix", required=True, help="facility_id 접두어 (예: NEIS_)"
    )
    parser.add_argument(
        "--subtypes",
        nargs="+",
        required=True,
        help="facility_subtype 목록 (예: academy)",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Railway 반영 (기본 dry-run)"
    )
    args = parser.parse_args()

    like_pattern = f"{_escape_like_prefix(args.prefix)}%"

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
        "WHERE facility_subtype = ANY(%s) AND facility_id LIKE %s",
        [args.subtypes, like_pattern],
    )
    fac_rows = lcur.fetchall()
    lcur.execute(
        f"SELECT {SUMMARY_COLS} FROM apt_facility_summary WHERE facility_subtype = ANY(%s)",
        [args.subtypes],
    )
    sum_rows = lcur.fetchall()
    local.close()
    print(
        f"로컬 (prefix={args.prefix!r}, subtypes={args.subtypes}): "
        f"facilities {len(fac_rows):,}행 / summary {len(sum_rows):,}행"
    )

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
            "DELETE FROM facilities WHERE facility_subtype = ANY(%s) AND facility_id LIKE %s",
            [args.subtypes, like_pattern],
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
            [args.subtypes],
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
            [args.subtypes],
        )
        print("✅ Railway facilities:", rcur.fetchall())
        rcur.execute(
            "SELECT COUNT(*) FROM apt_facility_summary WHERE facility_subtype = ANY(%s)",
            [args.subtypes],
        )
        print("✅ Railway summary:", rcur.fetchone()[0], "행")
    except Exception:
        railway.rollback()
        raise
    finally:
        railway.close()


if __name__ == "__main__":
    main()
