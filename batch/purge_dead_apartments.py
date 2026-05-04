"""사장된 아파트(zombie 단지) 삭제 배치.

식별 조건 (둘 다 충족해야 삭제):
  1. 최근 N년(``--inactive-years``, 기본 7) 이내 거래/임대 0건
     (via ``trade_apt_mapping`` → ``trade_history`` / ``rent_history``)
  2. ``apt_kapt_info`` 매핑 없음

추가 제외:
  - ``pnu`` prefix ``TRADE_`` (거래내역에서 자동 생성된 임시 PNU — 별도 정리 대상)
  - ``pnu`` prefix ``KAPT_`` (K-APT 등록 진행 중 임시 PNU)

식별된 PNU 에 대해 ``apartments`` + 12 개 부속 테이블에서 cascade delete.
chunk(기본 500 PNU) 별 단일 transaction. 마지막에 영향 13 개 테이블 모두
``VACUUM (ANALYZE)``.

목적: zombie 데이터로 인한 검색·추천 품질 저하 + 디스크/캐시 효율 개선.
실제 메모리 절감은 작지만(<50 MB) 데이터 위생 효과가 큼.

사용:
    python -m batch.purge_dead_apartments --target local --dry-run
    python -m batch.purge_dead_apartments --target both --inactive-years 10 --dry-run
    python -m batch.purge_dead_apartments --target local --inactive-years 7 --confirm

검증·운영 절차는 plan 문서(/Users/wizmain/.claude/plans/foamy-swimming-book.md) 참고.
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

from batch.logger import setup_logger

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


DEFAULT_INACTIVE_YEARS = 7
DEFAULT_CHUNK_SIZE = 500
DEFAULT_MAX_DELETIONS = 5000

# cascade delete 순서 — 의존성 역순 (master 마지막).
DEPENDENT_TABLES: tuple[str, ...] = (
    "trade_apt_mapping",
    "apt_facility_summary",
    "apt_safety_score",
    "apt_price_score",
    "apt_coord_candidates",
    "apt_coord_history",
    "apt_kapt_info",
    "apt_mgmt_cost",
    "school_zones",
    "apt_area_info",
    "apt_area_type",
    "apt_vectors",
)
MASTER_TABLE = "apartments"


def _db_url(target: str) -> str:
    if target == "local":
        url = os.getenv("DATABASE_URL")
    elif target == "railway":
        url = os.getenv("RAILWAY_DATABASE_URL")
    else:
        raise ValueError(f"unknown target: {target}")
    if not url:
        raise ValueError(f"{target} DB URL 미설정")
    return url


def _cutoff_tuple(years: int) -> tuple[int, int, int]:
    today = date.today()
    cutoff = today.replace(year=today.year - years)
    return cutoff.year, cutoff.month, cutoff.day


# 식별 SQL — TEMP TABLE materialize 후 ARRAY 로 fetch.
DEAD_PNU_SQL = """
    WITH active_seq AS (
        SELECT DISTINCT apt_seq FROM trade_history
        WHERE (deal_year, deal_month, deal_day) >= (%s, %s, %s)
        UNION
        SELECT DISTINCT apt_seq FROM rent_history
        WHERE (deal_year, deal_month, deal_day) >= (%s, %s, %s)
    ),
    active_pnu AS (
        SELECT DISTINCT m.pnu FROM trade_apt_mapping m
        JOIN active_seq s ON s.apt_seq = m.apt_seq
        WHERE m.pnu IS NOT NULL
    )
    SELECT a.pnu, a.bld_nm, a.sigungu_code, a.use_apr_day
    FROM apartments a
    LEFT JOIN apt_kapt_info k ON k.pnu = a.pnu
    WHERE k.pnu IS NULL
      AND a.pnu NOT IN (SELECT pnu FROM active_pnu)
      AND a.pnu NOT LIKE 'TRADE_%%'
      AND a.pnu NOT LIKE 'KAPT_%%'
    ORDER BY a.pnu
"""


def _identify_dead_pnus(cur, cutoff: tuple[int, int, int]) -> list[tuple]:
    """(pnu, bld_nm, sigungu_code, use_apr_day) 튜플 리스트 반환."""
    cur.execute(DEAD_PNU_SQL, [*cutoff, *cutoff])
    return cur.fetchall()


def _delete_chunk(conn, pnu_chunk: list[str]) -> dict[str, int]:
    """단일 transaction 안에서 13 개 테이블 cascade delete. 테이블별 삭제 수 반환."""
    cur = conn.cursor()
    counts: dict[str, int] = {}
    try:
        for table in DEPENDENT_TABLES:
            cur.execute(f"DELETE FROM {table} WHERE pnu = ANY(%s)", [pnu_chunk])
            counts[table] = cur.rowcount
        cur.execute(f"DELETE FROM {MASTER_TABLE} WHERE pnu = ANY(%s)", [pnu_chunk])
        counts[MASTER_TABLE] = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return counts


def _vacuum(url: str, logger) -> None:
    """VACUUM 은 transaction 안에서 못 돌리므로 별도 autocommit connection."""
    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        for table in (*DEPENDENT_TABLES, MASTER_TABLE):
            logger.info(f"  VACUUM (ANALYZE) {table}")
            cur.execute(f"VACUUM (ANALYZE) {table}")
    finally:
        conn.close()


def _process_target(target: str, args, logger) -> None:
    cutoff = _cutoff_tuple(args.inactive_years)
    logger.info(
        f"[{target}] cutoff={cutoff} (inactive_years={args.inactive_years}) "
        f"dry_run={args.dry_run} chunk_size={args.chunk_size}"
    )

    url = _db_url(target)
    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        cur = conn.cursor()

        # 1) 식별
        dead_rows = _identify_dead_pnus(cur, cutoff)
        total = len(dead_rows)
        logger.info(f"  [{target}] 사장 단지 식별: {total:,}건")

        if total == 0:
            logger.info(f"  [{target}] 삭제 대상 없음 — 종료")
            return

        # 2) 안전 캡 검사
        if total > args.max_deletions:
            logger.error(
                f"  [{target}] 식별 {total:,}건이 --max-deletions={args.max_deletions:,} 초과 — abort"
            )
            return

        # 3) sample 출력
        logger.info(f"  [{target}] sample (최대 10건):")
        for r in dead_rows[:10]:
            logger.info(f"    {r}")

        # 4) dry-run 종료
        if args.dry_run:
            logger.info(f"  [{target}] DRY-RUN 종료 — 실제 삭제 없음")
            return

        # 5) confirm 검사 (실행 시 필수)
        if not args.confirm:
            logger.error(
                f"  [{target}] cascade delete 는 위험 — --confirm 없이 실행 불가"
            )
            return

        # 6) chunk 별 cascade delete
        pnus = [r[0] for r in dead_rows]
        cumulative: dict[str, int] = {}
        for i in range(0, len(pnus), args.chunk_size):
            chunk = pnus[i : i + args.chunk_size]
            counts = _delete_chunk(conn, chunk)
            for k, v in counts.items():
                cumulative[k] = cumulative.get(k, 0) + v
            logger.info(
                f"  [{target}] chunk {i // args.chunk_size + 1}: "
                f"PNU {len(chunk)}건 삭제 (apartments={counts.get(MASTER_TABLE, 0)})"
            )

        logger.info(f"  [{target}] 합계 (테이블별):")
        for table, count in cumulative.items():
            logger.info(f"    {table}: {count:,}건")
    finally:
        conn.close()

    # 7) VACUUM (별도 autocommit connection)
    if not args.dry_run and not args.no_vacuum:
        _vacuum(url, logger)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="사장된 아파트(zombie 단지) cascade delete 배치"
    )
    parser.add_argument(
        "--inactive-years",
        type=int,
        default=DEFAULT_INACTIVE_YEARS,
        help=f"비활성 기준 N년. 기본 {DEFAULT_INACTIVE_YEARS}",
    )
    parser.add_argument(
        "--target", choices=["local", "railway", "both"], default="local"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"PNU/transaction 묶음. 기본 {DEFAULT_CHUNK_SIZE}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 삭제 없이 식별 카운트 + 10 건 sample 출력",
    )
    parser.add_argument(
        "--no-vacuum", action="store_true", help="실행 후 VACUUM (ANALYZE) 단계 건너뜀"
    )
    parser.add_argument(
        "--max-deletions",
        type=int,
        default=DEFAULT_MAX_DELETIONS,
        help=f"식별 PNU 수가 이 값 초과 시 abort. 기본 {DEFAULT_MAX_DELETIONS}",
    )
    parser.add_argument(
        "--confirm", action="store_true", help="실제 삭제 시 필수 — cascade 는 비가역"
    )
    args = parser.parse_args()

    if args.inactive_years <= 0:
        parser.error("--inactive-years must be positive")
    if args.chunk_size <= 0:
        parser.error("--chunk-size must be positive")

    logger = setup_logger("purge_dead_apartments")
    targets = ["local", "railway"] if args.target == "both" else [args.target]
    for t in targets:
        _process_target(t, args, logger)


if __name__ == "__main__":
    main()
