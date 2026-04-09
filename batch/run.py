"""배치 데이터 수집/갱신 CLI 진입점.

사용법:
  python batch/run.py --type trade
  python batch/run.py --type quarterly
  python batch/run.py --type annual
  python batch/run.py --type trade --dry-run
"""

import sys
import argparse
import time
from batch.logger import setup_logger, BatchResult
from batch.db import get_connection


def run_trade(args, logger, result):
    from batch.trade.collect_trades import collect_trades
    from batch.trade.load_trades import load_trades
    from batch.trade.recalc_price import recalc_price
    from batch.trade.enrich_apartments import enrich_new_apartments

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
        enriched, new_pnus = enrich_new_apartments(conn, logger)
        result.record("신규 아파트 보충", "success", rows=enriched, duration=time.time() - t0)

        # 5. K-APT 정보 수집 (점수 계산 전에 실행)
        if enriched > 0:
            from batch.kapt.collect_kapt_info import enrich_kapt_for_new
            t0 = time.time()
            kapt_cnt = enrich_kapt_for_new(conn, logger, new_pnus)
            result.record("K-APT 정보 수집", "success", rows=kapt_cnt, duration=time.time() - t0)

        # 6. 시설 집계 + 안전점수 + 유사도 벡터 (모든 데이터 반영 후 계산)
        if new_pnus:
            from batch.quarterly.recalc_summary import recalc_for_new_apartments
            t0 = time.time()
            recalc_for_new_apartments(conn, logger, new_pnus)
            result.record("시설집계/안전점수", "success", rows=len(new_pnus), duration=time.time() - t0)

        if enriched > 0:
            from batch.ml.build_vectors import build_all_vectors
            t0 = time.time()
            build_all_vectors(conn, logger)
            result.record("벡터 재생성", "success", duration=time.time() - t0)

    except Exception as e:
        logger.error(f"거래 배치 실패: {e}")
        result.record("거래 배치", "critical", error=str(e))
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


def run_mgmt_cost(args, logger, result):
    from batch.kapt.collect_mgmt_cost import collect_from_api

    conn = get_connection()
    try:
        t0 = time.time()
        count = collect_from_api(conn=conn, logger=logger, dry_run=args.dry_run)
        result.record("관리비 API 수집", "success", rows=count, duration=time.time() - t0)
    except Exception as e:
        logger.error(f"관리비 배치 실패: {e}")
        result.record("관리비 배치", "critical", error=str(e))
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="집토리 배치 데이터 수집/갱신")
    parser.add_argument("--type", choices=["trade", "quarterly", "annual", "mgmt_cost"], required=True,
                        help="배치 유형: trade(거래), quarterly(시설), annual(인구/범죄), mgmt_cost(관리비)")
    parser.add_argument("--dry-run", action="store_true", help="수집만 하고 DB 적재 생략")
    args = parser.parse_args()

    logger = setup_logger()
    result = BatchResult()

    logger.info(f"배치 시작: {args.type} {'(dry-run)' if args.dry_run else ''}")

    if args.type == "trade":
        run_trade(args, logger, result)
    elif args.type == "quarterly":
        run_quarterly(args, logger, result)
    elif args.type == "annual":
        run_annual(args, logger, result)
    elif args.type == "mgmt_cost":
        run_mgmt_cost(args, logger, result)

    result.summary(logger)
    sys.exit(result.exit_code())


if __name__ == "__main__":
    main()
