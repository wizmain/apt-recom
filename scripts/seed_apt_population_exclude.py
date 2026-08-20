"""추천 모집단 제외 정책(apt_population_exclude) common_code 시드.

넛지 추천에서 제외할 K-APT 분양형태를 DB 에 둔다. 하드코딩 금지 원칙에 따라
정책값은 코드가 아닌 common_code 에 있고, 이 스크립트가 유일한 시드 경로다.

- apt_population_exclude / sale_type: name=콤마 구분 분양형태 목록

소비처: web/backend/services/apartment_eligibility.py (모듈 캐시로 1회 로드).
제외 근거·실측치는 그 모듈 docstring 에 있다.

DB 에 행이 없으면 소비처가 기본값('임대')을 쓰므로, 시드 전에 배포돼도 가드는
동작한다. 이 스크립트는 정책값을 코드 밖에서 조정 가능하게 만드는 용도다.

사용 (기본 dry-run):
  .venv/bin/python scripts/seed_apt_population_exclude.py
  .venv/bin/python scripts/seed_apt_population_exclude.py --apply
  .venv/bin/python scripts/seed_apt_population_exclude.py --target railway --apply
    ⚠️ production 쓰기 — CLAUDE.md 정책상 railway 는 사용자가 직접 실행한다.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

GROUP_ID = "apt_population_exclude"

# 제외할 분양형태. K-APT sale_type 실측 분포: 분양 18,808 / 임대 1,964 / 혼합 1,069 /
# 사택 및 관사 등 62.
# - 임대: 매수 불가 + 임대차도 자격 요건 → 추천 대상 아님
# - 혼합: 분양 세대가 있어 유지
# - 사택 및 관사 등: 일반인 대상이 아니지만 62곳뿐이고 실제 노출 사례가 확인되지
#   않아 이번 범위에서 제외하지 않는다. 노출이 확인되면 여기에 추가한다.
EXCLUDED_SALE_TYPES = ["임대"]

UPSERT_SQL = """
INSERT INTO common_code (group_id, code, name, extra, sort_order)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (group_id, code) DO UPDATE SET
    name = EXCLUDED.name,
    extra = EXCLUDED.extra,
    sort_order = EXCLUDED.sort_order
"""


def get_conn(target: str):
    if target == "railway":
        url = os.getenv("RAILWAY_DATABASE_URL")
        if not url:
            raise SystemExit("RAILWAY_DATABASE_URL 미설정 (.env 확인)")
    else:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise SystemExit("DATABASE_URL 미설정 (.env 확인)")
    return psycopg2.connect(url)


def count_excluded(cur, sale_types: list[str]) -> int:
    """제외 대상 단지 수 — 시드 전에 영향 규모를 눈으로 확인한다."""
    placeholders = ", ".join(["%s"] * len(sale_types))
    cur.execute(
        f"""
        SELECT COUNT(*) FROM apartments a
        JOIN apt_kapt_info k ON k.pnu = a.pnu
        WHERE a.lat IS NOT NULL AND a.pnu NOT LIKE 'TRADE_%%'
          AND a.total_hhld_cnt > 0
          AND a.use_apr_day IS NOT NULL AND a.use_apr_day != ''
          AND k.sale_type IN ({placeholders})
        """,
        sale_types,
    )
    return cur.fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["local", "railway"], default="local")
    parser.add_argument("--apply", action="store_true", help="실제 반영 (기본 dry-run)")
    args = parser.parse_args()

    conn = get_conn(args.target)
    conn.autocommit = False
    cur = conn.cursor()

    affected = count_excluded(cur, EXCLUDED_SALE_TYPES)
    print(
        f"제외 대상: {', '.join(EXCLUDED_SALE_TYPES)} → {affected:,}곳이 추천 모집단에서 빠짐"
    )

    row = (GROUP_ID, "sale_type", ",".join(EXCLUDED_SALE_TYPES), "", 1)
    print(
        f"{'APPLY' if args.apply else 'DRY-RUN'} upsert: {row[0]}/{row[1]} — {row[2]}"
    )

    if args.apply:
        cur.execute(UPSERT_SQL, list(row))
        conn.commit()
        print(f"✅ {args.target} 반영 완료")
    else:
        conn.rollback()
        print("dry-run 종료 — 반영하려면 --apply")

    conn.close()


if __name__ == "__main__":
    main()
