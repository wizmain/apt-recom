"""시군구·월별 관리비 median 캐시 테이블(`sigungu_mgmt_cost_stats`) 일괄 갱신.

매 detail 핸들러 호출마다 시군구 전체 단지를 percentile_cont 로 집계하던 비용을
사전 계산된 lookup 으로 대체하기 위함. K-APT 관리비 데이터는 월 단위로만
갱신되므로 이 테이블도 일배치(또는 K-APT 관리비 수집 직후) 한 번 돌리면 충분.

사용:
    .venv/bin/python -m batch.compute_mgmt_cost_stats              # local
    .venv/bin/python -m batch.compute_mgmt_cost_stats --target railway
    .venv/bin/python -m batch.compute_mgmt_cost_stats --target both
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

from batch.logger import setup_logger

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


# detail.py 의 _mgmt_percentiles 와 동일한 eligible 필터:
#   - cost_per_unit < 10,000 또는 total_cost < 100,000: K-APT 엑셀 오입력
#   - cost_per_unit = total_cost: 분모=1 fallback 오류
COMPUTE_SQL = """
    WITH eligible AS (
        SELECT a.sigungu_code, m.year_month, m.pnu, m.total_cost, m.cost_per_unit
        FROM apt_mgmt_cost m
        JOIN apartments a ON m.pnu = a.pnu
        WHERE m.cost_per_unit >= 10000
          AND m.total_cost >= 100000
          AND m.cost_per_unit != m.total_cost
          AND a.sigungu_code IS NOT NULL
    ),
    apt_area AS (
        SELECT pnu, MAX(mgmt_area_total) AS mgmt_area_total
        FROM apt_area_type
        WHERE mgmt_area_total > 0
        GROUP BY pnu
    ),
    eligible_with_area AS (
        SELECT e.sigungu_code, e.year_month,
               e.total_cost::float / aa.mgmt_area_total AS per_m2
        FROM eligible e
        JOIN apt_area aa ON e.pnu = aa.pnu
    )
    INSERT INTO sigungu_mgmt_cost_stats
        (sigungu_code, year_month, median_per_unit, median_per_m2, sample_size, computed_at)
    SELECT
        s.sigungu_code,
        s.year_month,
        s.median_per_unit,
        m.median_per_m2,
        s.sample_size,
        NOW()
    FROM (
        SELECT sigungu_code, year_month,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY cost_per_unit) AS median_per_unit,
               COUNT(*) AS sample_size
        FROM eligible
        GROUP BY sigungu_code, year_month
    ) s
    LEFT JOIN (
        SELECT sigungu_code, year_month,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY per_m2) AS median_per_m2
        FROM eligible_with_area
        GROUP BY sigungu_code, year_month
    ) m USING (sigungu_code, year_month)
    ON CONFLICT (sigungu_code, year_month)
    DO UPDATE SET
        median_per_unit = EXCLUDED.median_per_unit,
        median_per_m2 = EXCLUDED.median_per_m2,
        sample_size = EXCLUDED.sample_size,
        computed_at = EXCLUDED.computed_at
"""


def _db_url(target: str) -> str:
    if target == "local":
        url = os.getenv("DATABASE_URL")
    elif target == "railway":
        url = os.getenv("RAILWAY_DATABASE_URL")
    else:
        raise ValueError("single DB target expected")
    if not url:
        raise ValueError(f"{target} DB URL 미설정")
    return url


def compute(target: str, logger) -> None:
    conn = psycopg2.connect(_db_url(target))
    conn.autocommit = False
    try:
        cur = conn.cursor()
        # 테이블이 없을 수 있으므로 안전 보장. database.create_tables 에 정의돼 있으나
        # 신규 환경에서 fresh DB 가 아닐 수 있어 IF NOT EXISTS 로 한 번 더.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sigungu_mgmt_cost_stats (
                sigungu_code TEXT NOT NULL,
                year_month TEXT NOT NULL,
                median_per_unit DOUBLE PRECISION,
                median_per_m2 DOUBLE PRECISION,
                sample_size INTEGER NOT NULL DEFAULT 0,
                computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (sigungu_code, year_month)
            )
            """
        )
        t0 = time.perf_counter()
        cur.execute(COMPUTE_SQL)
        rows = cur.rowcount
        conn.commit()
        elapsed = time.perf_counter() - t0
        cur.execute("SELECT COUNT(*) FROM sigungu_mgmt_cost_stats")
        total = cur.fetchone()[0]
        logger.info(
            f"[{target}] upsert={rows}건  total={total}건  elapsed={elapsed:.1f}s"
        )
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target", choices=["local", "railway", "both"], default="local"
    )
    args = parser.parse_args()

    logger = setup_logger("compute_mgmt_cost_stats")
    targets = ["local", "railway"] if args.target == "both" else [args.target]
    for t in targets:
        compute(t, logger)


if __name__ == "__main__":
    main()
