"""배치 데이터 수집/갱신 CLI 진입점.

사용법:
  python batch/run.py --type weekly
  python batch/run.py --type quarterly
  python batch/run.py --type annual
  python batch/run.py --type weekly --dry-run
"""

import sys
import argparse
import time
from batch.logger import setup_logger, BatchResult
from batch.db import get_connection


def run_weekly(args, logger, result):
    from batch.weekly.collect_trades import collect_trades
    from batch.weekly.load_trades import load_trades
    from batch.weekly.recalc_price import recalc_price
    from batch.weekly.enrich_apartments import enrich_new_apartments

    conn = get_connection()
    try:
        # 1. 수집
        t0 = time.time()
        trade_rows, rent_rows = collect_trades(conn, logger, dry_run=args.dry_run)
        result.record("거래 데이터 수집", "success", rows=len(trade_rows) + len(rent_rows), duration=time.time() - t0)

        if args.dry_run:
            logger.info("Dry-run 모드: DB 적재 생략")
            return

        # 2. 적재
        t0 = time.time()
        inserted = load_trades(conn, trade_rows, rent_rows, logger)
        result.record("거래 데이터 적재", "success", rows=inserted, duration=time.time() - t0)

        # 3. 가격 점수 재계산
        t0 = time.time()
        updated = recalc_price(conn, logger)
        result.record("가격 점수 재계산", "success", rows=updated, duration=time.time() - t0)

        # 4. 신규 아파트 등록 + 건물정보 보충
        t0 = time.time()
        enriched = enrich_new_apartments(conn, logger)
        result.record("신규 아파트 보충", "success", rows=enriched, duration=time.time() - t0)

    except Exception as e:
        logger.error(f"Weekly 배치 실패: {e}")
        result.record("Weekly 배치", "critical", error=str(e))
    finally:
        conn.close()


def run_quarterly(args, logger, result):
    from batch.quarterly.collect_facilities import collect_all_facilities
    from batch.quarterly.update_facilities import update_facilities
    from batch.quarterly.recalc_summary import recalc_summary

    conn = get_connection()
    try:
        # 1. 수집
        t0 = time.time()
        facility_rows = collect_all_facilities(logger, dry_run=args.dry_run)
        result.record("시설 데이터 수집", "success", rows=len(facility_rows), duration=time.time() - t0)

        if args.dry_run:
            logger.info("Dry-run 모드: DB 갱신 생략")
            return

        # 2. DB 갱신
        t0 = time.time()
        upserted = update_facilities(conn, facility_rows, logger)
        result.record("시설 DB 갱신", "success", rows=upserted, duration=time.time() - t0)

        # 3. 집계 재계산
        t0 = time.time()
        recalc_summary(conn, logger)
        result.record("시설 집계 재계산", "success", duration=time.time() - t0)

    except Exception as e:
        logger.error(f"Quarterly 배치 실패: {e}")
        result.record("Quarterly 배치", "critical", error=str(e))
    finally:
        conn.close()


def run_annual(args, logger, result):
    from batch.annual.collect_stats import collect_population, collect_crime
    from batch.annual.update_stats import update_population, update_crime

    conn = get_connection()
    try:
        # 1. 인구 수집 + 갱신
        t0 = time.time()
        pop_rows = collect_population(logger, dry_run=args.dry_run)
        result.record("인구 데이터 수집", "success", rows=len(pop_rows), duration=time.time() - t0)

        if not args.dry_run and pop_rows:
            t0 = time.time()
            updated = update_population(conn, pop_rows, logger)
            result.record("인구 DB 갱신", "success", rows=updated, duration=time.time() - t0)

        # 2. 범죄 수집 + 갱신
        t0 = time.time()
        crime_rows = collect_crime(logger, dry_run=args.dry_run)
        result.record("범죄 데이터 수집", "success", rows=len(crime_rows), duration=time.time() - t0)

        if not args.dry_run and crime_rows:
            t0 = time.time()
            updated = update_crime(conn, crime_rows, logger)
            result.record("범죄 DB 갱신", "success", rows=updated, duration=time.time() - t0)

    except Exception as e:
        logger.error(f"Annual 배치 실패: {e}")
        result.record("Annual 배치", "critical", error=str(e))
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="집토리 배치 데이터 수집/갱신")
    parser.add_argument("--type", choices=["weekly", "quarterly", "annual"], required=True,
                        help="배치 유형: weekly(거래), quarterly(시설), annual(인구/범죄)")
    parser.add_argument("--dry-run", action="store_true", help="수집만 하고 DB 적재 생략")
    args = parser.parse_args()

    logger = setup_logger()
    result = BatchResult()

    logger.info(f"배치 시작: {args.type} {'(dry-run)' if args.dry_run else ''}")

    if args.type == "weekly":
        run_weekly(args, logger, result)
    elif args.type == "quarterly":
        run_quarterly(args, logger, result)
    elif args.type == "annual":
        run_annual(args, logger, result)

    result.summary(logger)
    sys.exit(result.exit_code())


if __name__ == "__main__":
    main()
