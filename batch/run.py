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
        result.record(
            "거래 데이터 수집",
            "success",
            rows=len(trade_rows) + len(rent_rows),
            duration=time.time() - t0,
        )

        if args.dry_run:
            logger.info("Dry-run 모드: DB 적재 생략")
            return

        # 2. 적재
        t0 = time.time()
        inserted = load_trades(conn, trade_rows, rent_rows, logger)
        result.record(
            "거래 데이터 적재", "success", rows=inserted, duration=time.time() - t0
        )

        # 3. 가격 점수 재계산
        t0 = time.time()
        updated = recalc_price(conn, logger)
        result.record(
            "가격 점수 재계산", "success", rows=updated, duration=time.time() - t0
        )

        # 4. 신규 아파트 등록 + 건물정보 보충
        t0 = time.time()
        enriched, new_pnus = enrich_new_apartments(conn, logger)
        result.record(
            "신규 아파트 보충", "success", rows=enriched, duration=time.time() - t0
        )

        # 4.5. 대시보드 집계 갱신 — 별도 커넥션에서 수행하여 선행 단계와 격리.
        #      선행 단계(load_trades/recalc_price/enrich)가 내부 commit 하지만 안전망으로 commit 재호출.
        #      집계 갱신 실패는 배치 전체 critical 오탐을 피하기 위해 warning record로 분리.
        conn.commit()
        try:
            from batch.trade.refresh_dashboard import refresh_dashboard_stats

            t0 = time.time()
            counts = refresh_dashboard_stats(logger)
            result.record(
                "대시보드 집계 갱신",
                "success",
                rows=sum(counts.values()),
                duration=time.time() - t0,
            )
        except Exception as e:
            logger.error(f"대시보드 집계 갱신 실패: {e}")
            result.record("대시보드 집계 갱신", "warning", error=str(e))

        # 5. K-APT 보완은 enrich_new_apartments 내부 Phase 3에서 처리됨

        # 6. 시설 집계 + 안전점수 + 유사도 벡터 (모든 데이터 반영 후 계산)
        if new_pnus:
            from batch.quarterly.recalc_summary import recalc_for_new_apartments

            t0 = time.time()
            recalc_for_new_apartments(conn, logger, new_pnus)
            result.record(
                "시설집계/안전점수",
                "success",
                rows=len(new_pnus),
                duration=time.time() - t0,
            )

            # 6b. 신규 아파트의 파생/외부 데이터 축 즉시 등록 (2026-07-05 감사).
            # 방치 시 배정초교는 다음 quarterly(최대 3개월), 건축물대장(승강기/주차)은
            # 무기한 중립 50 상태로 남는다. 배정초교는 위 시설 집계의 school 최근접
            # 거리를 프록시로 쓰므로 반드시 6단계 이후 실행. 실패는 거래 배치 본연
            # 기능을 해치지 않도록 warning 으로 격리.
            try:
                from batch.quarterly.assigned_school import recalc_assigned_school

                t0 = time.time()
                stats = recalc_assigned_school(conn, logger, pnu_list=new_pnus)
                result.record(
                    "신규 배정초교 등록",
                    "success",
                    rows=stats["total"],
                    duration=time.time() - t0,
                )
            except Exception as e:
                logger.warning(f"신규 배정초교 등록 실패: {e}")
                result.record("신규 배정초교 등록", "warning", error=str(e))

            try:
                from batch.annual.collect_building_register import (
                    collect_building_register,
                )

                t0 = time.time()
                stats = collect_building_register(conn, logger, pnu_list=new_pnus)
                result.record(
                    "신규 건축물대장 수집",
                    "success",
                    rows=stats["upserted"],
                    duration=time.time() - t0,
                )
            except Exception as e:
                logger.warning(f"신규 건축물대장 수집 실패: {e}")
                result.record("신규 건축물대장 수집", "warning", error=str(e))

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
        region = getattr(args, "region", "metro")
        facility_rows = collect_all_facilities(
            logger, dry_run=args.dry_run, region=region
        )
        result.record(
            "시설 데이터 수집",
            "success",
            rows=len(facility_rows),
            duration=time.time() - t0,
        )

        if args.dry_run:
            logger.info("Dry-run 모드: DB 갱신 생략")
            return

        # 2. DB 갱신
        t0 = time.time()
        upserted = update_facilities(conn, facility_rows, logger, region=region)
        result.record(
            "시설 DB 갱신", "success", rows=upserted, duration=time.time() - t0
        )

        # 3. 집계 재계산
        t0 = time.time()
        recalc_summary(conn, logger)
        result.record("시설 집계 재계산", "success", duration=time.time() - t0)

        # 4. 배정초교 거리 재계산 (education 넛지 1급 지표 — recalc_summary 의
        #    school 최근접 거리를 fallback 프록시로 쓰므로 반드시 3단계 이후 실행)
        from batch.quarterly.assigned_school import recalc_assigned_school

        t0 = time.time()
        stats = recalc_assigned_school(conn, logger)
        result.record(
            "배정초교 거리 재계산",
            "success",
            rows=stats["total"],
            duration=time.time() - t0,
        )

    except Exception as e:
        logger.error(f"Quarterly 배치 실패: {e}")
        result.record("Quarterly 배치", "critical", error=str(e))
    finally:
        conn.close()


def run_annual(args, logger, result):
    from batch.annual.collect_stats import collect_population
    from batch.annual.update_stats import update_population

    conn = get_connection()
    try:
        # 1. 인구 수집 + 갱신
        t0 = time.time()
        pop_rows = collect_population(logger, dry_run=args.dry_run)
        result.record(
            "인구 데이터 수집", "success", rows=len(pop_rows), duration=time.time() - t0
        )

        if not args.dry_run and pop_rows:
            t0 = time.time()
            updated = update_population(conn, pop_rows, logger)
            result.record(
                "인구 DB 갱신", "success", rows=updated, duration=time.time() - t0
            )

        # 범죄 갱신은 batch/safety/load_safety_data.py (KOSIS 경찰청 통계 →
        # sigungu_crime_detail, 전국 268 시군구 백분위) 경로로 일원화됨.
        # 구 경로(collect_crime → sigungu_crime_score 77행)는 커버리지가 좁고
        # 스코어링에서 더 이상 참조하지 않아 제거 (2026-07-04, 라이프점수 Phase 0 후속).

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
        result.record(
            "관리비 API 수집", "success", rows=count, duration=time.time() - t0
        )
    except Exception as e:
        logger.error(f"관리비 배치 실패: {e}")
        result.record("관리비 배치", "critical", error=str(e))
    finally:
        conn.close()


def run_kapt_refresh(args, logger, result):
    from batch.kapt.collect_kapt_info import phase2_refresh

    conn = get_connection()
    try:
        t0 = time.time()
        count = phase2_refresh(conn, logger)
        result.record(
            "K-APT 정보 갱신", "success", rows=count, duration=time.time() - t0
        )
    except Exception as e:
        logger.error(f"K-APT 갱신 실패: {e}")
        result.record("K-APT 갱신", "critical", error=str(e))
    finally:
        conn.close()


def run_backfill(args, logger, result):
    from batch.trade.backfill_trades import backfill_trades

    conn = get_connection()
    try:
        t0 = time.time()
        max_calls = args.max_calls if args.max_calls is not None else 900
        updated = backfill_trades(
            conn, logger, max_calls=max_calls, dry_run=args.dry_run
        )
        result.record("거래 백필", "success", rows=updated, duration=time.time() - t0)
    except Exception as e:
        logger.error(f"백필 배치 실패: {e}")
        result.record("백필 배치", "critical", error=str(e))
    finally:
        conn.close()


def run_ml(args, logger, result):
    """ML 재학습 파이프라인 (Phase 1-4).

    기본 dry-run: 학습·리포트만 수행하고 common_code 는 건드리지 않는다.
    --apply 명시 시에만 감쇠(decay)·넛지 가중치를 DB 에 반영한다 —
    점수 체계의 무단 변동을 막기 위한 안전장치.
    """
    import subprocess

    steps = [
        ("ML 학습 (train_scoring)", [sys.executable, "-m", "batch.ml.train_scoring"]),
        ("Hedonic 검증", [sys.executable, "-m", "batch.ml.hedonic_validation"]),
    ]
    apply_flag = getattr(args, "apply", False)
    curves_cmd = [sys.executable, "-m", "batch.ml.apply_curves"]
    weights_cmd = [sys.executable, "-m", "batch.ml.update_weights"]
    if apply_flag:
        curves_cmd.append("--apply")
    else:
        weights_cmd.append("--dry-run")
    steps.append(("감쇠 곡선 반영", curves_cmd))
    steps.append(("넛지 가중치 갱신", weights_cmd))

    try:
        for name, cmd in steps:
            t0 = time.time()
            proc = subprocess.run(cmd, capture_output=False)
            if proc.returncode != 0:
                result.record(name, "critical", error=f"exit {proc.returncode}")
                logger.error(f"{name} 실패 — 이후 단계 중단")
                return
            result.record(name, "success", duration=time.time() - t0)
    except Exception as e:
        # subprocess 스폰 실패 등 returncode 로 잡히지 않는 예외 — 다른 run_* 와 동일하게 구조화 보고
        logger.error(f"ML 파이프라인 실패: {e}")
        result.record("ML 파이프라인", "critical", error=str(e))


def run_building_register(args, logger, result):
    """건축물대장 표제부 수집 (라이프점수 Phase 2-1). 체크포인트 재개형."""
    from batch.annual.collect_building_register import collect_building_register

    conn = get_connection()
    try:
        t0 = time.time()
        # 기본 0 = 무제한 전수 수집. backfill 과 달리 900 캡을 두지 않음.
        max_calls = args.max_calls if args.max_calls is not None else 0
        stats = collect_building_register(conn, logger, max_calls=max_calls)
        result.record(
            "건축물대장 수집",
            "success",
            rows=stats["upserted"],
            duration=time.time() - t0,
        )
    except Exception as e:
        logger.error(f"건축물대장 배치 실패: {e}")
        result.record("건축물대장 배치", "critical", error=str(e))
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="집토리 배치 데이터 수집/갱신")
    parser.add_argument(
        "--type",
        choices=[
            "trade",
            "quarterly",
            "annual",
            "mgmt_cost",
            "kapt_refresh",
            "backfill",
            "ml",
            "building_register",
        ],
        required=True,
        help="배치 유형: trade(거래), quarterly(시설), annual(인구/범죄), mgmt_cost(관리비), kapt_refresh(K-APT 갱신), backfill(거래 백필), ml(재학습 파이프라인), building_register(건축물대장 표제부 수집)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="수집만 하고 DB 적재 생략"
    )
    parser.add_argument(
        "--region",
        default="metro",
        help="시설 수집 지역 (metro/all/시도명). quarterly 전용",
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=None,
        help="최대 API 호출 수. backfill(거래 백필)/building_register(건축물대장 표제부) 공용. "
        "타입별 기본: backfill 900, building_register 0(무제한)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="ml 전용: 학습 결과(decay/가중치)를 common_code 에 반영 (기본 dry-run)",
    )
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
    elif args.type == "kapt_refresh":
        run_kapt_refresh(args, logger, result)
    elif args.type == "backfill":
        run_backfill(args, logger, result)
    elif args.type == "ml":
        run_ml(args, logger, result)
    elif args.type == "building_register":
        run_building_register(args, logger, result)

    result.summary(logger)
    sys.exit(result.exit_code())


if __name__ == "__main__":
    main()
