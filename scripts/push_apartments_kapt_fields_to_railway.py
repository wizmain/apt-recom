"""로컬 → Railway: K-APT 매핑 단지의 apartments 동기화 (신규 INSERT + K-APT 컬럼 UPDATE).

`batch.kapt.ingest_full_kapt` 결과를 Railway 에 반영한다.
  - Phase C(--register-new) 가 새로 만든 단지 → Railway 에 없는 pnu 를 전 컬럼 INSERT
  - Phase A 가 덮어쓴 total_hhld_cnt / dong_count / max_floor / use_apr_day → 기존 행은
    이 4개 컬럼만 UPDATE (Railway 전용 행·다른 컬럼은 건드리지 않음)

대상: 로컬 apt_kapt_info 에 매핑된 pnu (K-APT 공개의무단지) 로 한정.

사용법:
  .venv/bin/python -m scripts.push_apartments_kapt_fields_to_railway            # dry-run (건수만)
  .venv/bin/python -m scripts.push_apartments_kapt_fields_to_railway --apply    # 실제 반영
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from batch.logger import setup_logger

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

KAPT_FIELDS = ["total_hhld_cnt", "dong_count", "max_floor", "use_apr_day"]
STAGING_TABLE = "tmp_apartments_kapt_sync"
INSERT_PAGE_SIZE = 5000


def _railway_url() -> str:
    url = os.getenv("RAILWAY_DATABASE_URL")
    if not url or "railway" not in url:
        raise SystemExit("RAILWAY_DATABASE_URL 이 Railway 형태가 아님 — 안전상 중단")
    return url


def _table_columns(cur, table: str) -> list[str]:
    cur.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s
           ORDER BY ordinal_position""",
        [table],
    )
    return [r[0] for r in cur.fetchall()]


def fetch_local_rows(local_url: str) -> tuple[list[str], list[tuple]]:
    """K-APT 매핑 단지의 apartments 전 컬럼 행을 반환."""
    conn = psycopg2.connect(local_url)
    try:
        cur = conn.cursor()
        columns = _table_columns(cur, "apartments")
        cur.execute(
            f"""
            SELECT {", ".join("a." + c for c in columns)}
            FROM apartments a
            JOIN apt_kapt_info k ON k.pnu = a.pnu
            """
        )
        return columns, cur.fetchall()
    finally:
        conn.close()


def push(
    railway_url: str, columns: list[str], rows: list[tuple], apply: bool, logger
) -> None:
    conn = psycopg2.connect(railway_url)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        remote_columns = _table_columns(cur, "apartments")
        if set(columns) != set(remote_columns):
            raise SystemExit(
                f"apartments 컬럼 불일치 — 로컬 전용 {set(columns) - set(remote_columns)}, "
                f"Railway 전용 {set(remote_columns) - set(columns)}"
            )

        col_list = ", ".join(columns)
        cur.execute(
            f"CREATE TEMP TABLE {STAGING_TABLE} (LIKE apartments INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        psycopg2.extras.execute_values(
            cur,
            f"INSERT INTO {STAGING_TABLE} ({col_list}) VALUES %s",
            rows,
            page_size=INSERT_PAGE_SIZE,
        )

        cur.execute(
            f"""
            SELECT COUNT(*) FROM {STAGING_TABLE} s
            WHERE NOT EXISTS (SELECT 1 FROM apartments a WHERE a.pnu = s.pnu)
            """
        )
        missing_count = cur.fetchone()[0]

        diff_cond = " OR ".join(f"a.{c} IS DISTINCT FROM s.{c}" for c in KAPT_FIELDS)
        cur.execute(
            f"""
            SELECT COUNT(*) FROM apartments a
            JOIN {STAGING_TABLE} s ON s.pnu = a.pnu
            WHERE {diff_cond}
            """
        )
        diff_count = cur.fetchone()[0]
        logger.info(
            f"스테이징 {len(rows):,}건 → Railway 미존재(INSERT 대상) {missing_count:,}건, "
            f"K-APT 컬럼 상이(UPDATE 대상) {diff_count:,}건"
        )

        if not apply:
            conn.rollback()
            logger.info("dry-run: 반영 안 함 (--apply 로 실행)")
            return

        cur.execute(
            f"""
            INSERT INTO apartments ({col_list})
            SELECT {col_list} FROM {STAGING_TABLE} s
            WHERE NOT EXISTS (SELECT 1 FROM apartments a WHERE a.pnu = s.pnu)
            """
        )
        inserted = cur.rowcount

        set_clause = ", ".join(f"{c} = s.{c}" for c in KAPT_FIELDS)
        cur.execute(
            f"""
            UPDATE apartments a SET {set_clause}
            FROM {STAGING_TABLE} s
            WHERE s.pnu = a.pnu AND ({diff_cond})
            """
        )
        updated = cur.rowcount
        conn.commit()
        logger.info(f"✅ 완료: INSERT {inserted:,}건, UPDATE {updated:,}건")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="K-APT 매핑 단지 apartments Railway 동기화"
    )
    parser.add_argument("--apply", action="store_true", help="실제 반영 (기본 dry-run)")
    args = parser.parse_args()

    logger = setup_logger("push_apartments_kapt_fields")
    local_url = os.getenv("DATABASE_URL")
    if not local_url:
        raise SystemExit("DATABASE_URL 확인 필요 (.env)")

    columns, rows = fetch_local_rows(local_url)
    logger.info(f"로컬 apartments ⋈ apt_kapt_info: {len(rows):,}건")
    push(_railway_url(), columns, rows, args.apply, logger)


if __name__ == "__main__":
    main()
