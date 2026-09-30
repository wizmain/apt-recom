"""분양·임대 교체(ADR-014)가 끝난 단지 중 이름이 임대 레코드명으로 남은 곳을 분양 레코드명으로 고친다.

교체 도구가 이름을 바꾸지 않던 때(2026-09-20 로컬, 09-30 Railway) 교체된 단지가 대상이다.
`금호대우임대`·`독립문극동임대` 처럼 분양 단지가 임대 이름으로 노출된다. 이후의 교체는
`companion_records.swap_records` 와 적재 Phase C 가 같은 연산(`adopt_record_name`)을 호출하므로
이 스크립트는 기존 교체분을 위한 일회성이다.

대상: 동반 레코드(`apt_kapt_info.parent_pnu`)가 가리키는 실제 PNU. 그 단지의 `bld_nm`·
`display_name` 이 동반(임대) 레코드명과 같을 때만, 같은 쪽만 바꾼다. 재실행해도 결과가 같다.
합산 no 로 연결되지 않은 교체(래미안월곡 등)는 밀려난 이름을 DB 에서 알 수 없어 다루지 않는다.

⚠️ `--target railway --apply` 는 production 쓰기 — 사용자가 직접 실행한다.

사용 (기본 dry-run):
  .venv/bin/python -m scripts.fix_swapped_apartment_names --target local
  .venv/bin/python -m scripts.fix_swapped_apartment_names --target local --apply
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

from batch.kapt.companion_records import PARENT_PNU_COLUMN, adopt_record_name

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

RAILWAY_URL_MARKER = "railway"

COMPANIONS_SQL = f"""
SELECT {PARENT_PNU_COLUMN}, kapt_name
  FROM apt_kapt_info
 WHERE {PARENT_PNU_COLUMN} IS NOT NULL AND COALESCE(kapt_name, '') <> ''
 ORDER BY {PARENT_PNU_COLUMN}, kapt_code
"""

NAMES_SQL = "SELECT bld_nm, display_name FROM apartments WHERE pnu = %s"


def _db_url(target: str) -> str:
    if target == "local":
        url = os.getenv("DATABASE_URL")
    else:
        url = os.getenv("RAILWAY_DATABASE_URL")
        if url and RAILWAY_URL_MARKER not in url:
            raise SystemExit(
                "RAILWAY_DATABASE_URL 이 Railway 형태가 아님 — 안전상 중단"
            )
    if not url:
        raise SystemExit(f"{target} DB URL 미설정")
    return url


def _names(cur, pnu: str) -> tuple | None:
    cur.execute(NAMES_SQL, [pnu])
    return cur.fetchone()


def rename_swapped(cur) -> list[tuple[str, tuple, tuple]]:
    """동반 레코드명으로 남은 단지 이름을 고치고 (pnu, 변경 전, 변경 후) 목록을 돌려준다."""
    cur.execute(COMPANIONS_SQL)
    changed = []
    for parent_pnu, companion_name in cur.fetchall():
        before = _names(cur, parent_pnu)
        if adopt_record_name(cur, parent_pnu, companion_name):
            changed.append((parent_pnu, before, _names(cur, parent_pnu)))
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=("local", "railway"), required=True)
    parser.add_argument(
        "--apply", action="store_true", help="반영 (기본 dry-run — 롤백)"
    )
    args = parser.parse_args()

    conn = psycopg2.connect(_db_url(args.target))
    try:
        changed = rename_swapped(conn.cursor())
        for pnu, before, after in changed:
            print(f"  {pnu} (bld_nm, display_name): {before} → {after}")
        print(f"[{args.target}] 이름 교정 {len(changed)}건")
        if args.apply:
            conn.commit()
            print("✅ 반영 완료")
        else:
            conn.rollback()
            print("dry-run — 롤백했습니다 (--apply 로 반영)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
