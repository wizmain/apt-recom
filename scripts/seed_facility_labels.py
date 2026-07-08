"""common_code(facility_label) 누락 라벨 시드 — Phase 1~2 신규 subtype 9종.

아파트 상세 주변시설/가중치 UI 는 common_code('facility_label') 로 표시명을
매핑하는데(useCodes), Phase 1(배정초교)·Phase 2(상가/병원/학원) subtype 은
라벨이 누락되어 영문 subtype 이 그대로 노출된다. 관례: code=subtype, name=한글
표시명, extra=facility_type (facilities 테이블의 실제 type 과 일치).

멱등: ON CONFLICT (group_id, code) DO UPDATE — 재실행 안전.

사용 (기본 dry-run):
  .venv/bin/python scripts/seed_facility_labels.py [--target local|railway] --apply
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

# (subtype, 표시명, facility_type)
FACILITY_LABELS = [
    ("assigned_elementary", "배정 초등학교", "education"),
    ("cafe", "카페", "living"),
    ("kids_cafe", "키즈카페", "living"),
    ("pet_shop", "반려용품점", "pet"),
    ("fitness", "피트니스", "culture"),
    ("pediatric_clinic", "소아청소년과", "medical"),
    ("obgyn_clinic", "산부인과", "medical"),
    ("general_hospital", "종합병원", "medical"),
    ("academy", "학원", "education"),
]

UPSERT_SQL = (
    "INSERT INTO common_code (group_id, code, name, extra, sort_order) "
    "VALUES ('facility_label', %s, %s, %s, 0) "
    "ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name, extra = EXCLUDED.extra"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["local", "railway"], default="local")
    parser.add_argument("--apply", action="store_true", help="반영 (기본 dry-run)")
    args = parser.parse_args()

    url_env = "DATABASE_URL" if args.target == "local" else "RAILWAY_DATABASE_URL"
    db_url = os.getenv(url_env)
    if not db_url:
        raise SystemExit(f"{url_env} 확인 필요 (.env)")
    if args.target == "railway" and "railway" not in db_url and "rlwy" not in db_url:
        raise SystemExit("RAILWAY_DATABASE_URL 이 Railway 형태가 아님 — 안전상 중단")

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT code FROM common_code WHERE group_id = 'facility_label' AND code = ANY(%s)",
            [[c for c, _, _ in FACILITY_LABELS]],
        )
        existing = {r[0] for r in cur.fetchall()}
        for code, name, ftype in FACILITY_LABELS:
            state = "갱신" if code in existing else "신규"
            print(f"  [{state}] {code} = {name} (extra={ftype})")
        if not args.apply:
            print(f"dry-run 종료 ({args.target}) — 반영하려면 --apply")
            return
        for code, name, ftype in FACILITY_LABELS:
            cur.execute(UPSERT_SQL, (code, name, ftype))
        conn.commit()
        print(f"✅ {args.target} 반영 완료: {len(FACILITY_LABELS)}건")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
