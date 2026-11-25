"""오르는 단지 — 면적대 가격 추세 사전 집계 4개 테이블 재생성 (trade 배치 체인).

  apt_band_monthly_price      단지×면적대 60개월 월별 중위가 (상세 차트)
  apt_band_trend              단지×면적대 스냅샷 (목록)
  region_band_trend           시군구×면적대 스냅샷 (지역 등급)
  apt_band_trend_excluded_key 혼입 의심으로 뺀 거래 키 (감사·상세 API 제외 근거)

모듈 분담
  band_trend_source     입력 조회(코드값·범위 거래·매핑 위반 키) — 읽기 전용 SQL
  band_trend_aggregate  혼입 제외·지표 계산·행 생성 — 순수 계산
  이 모듈               흐름 조립·적재(한 트랜잭션 DELETE + INSERT)·결과 로그

별도 커넥션에서 수행해 run_trade 선행 단계 트랜잭션과 격리한다(refresh_dashboard 와 같은 방식).
호출자는 이 시점 이전에 선행 단계를 commit 해야 한다.
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import date

import psycopg2.extras

from batch.db import get_connection
from batch.trade.band_trend_aggregate import (
    BandTables,
    ExclusionResult,
    apply_exclusions,
    build_tables,
)
from batch.trade.band_trend_calc import HISTORY_MONTHS, base_month, shift_month
from batch.trade.band_trend_source import (
    find_mapping_violations,
    load_codes,
    load_trades,
)

# 면적대별 혼입 제외 비율 경고선. 넘으면 판정 규칙 오작동(대량 오탐)을 의심한다.
# 2026-11-25 로컬 실측(기준월 202609, 60개월) 면적대별 2.3~3.8% — 최댓값의 약 2배로 잡았다.
EXCLUSION_RATIO_WARN = 0.08
EXCLUDED_KEY_LOG_LIMIT = 10
_INSERT_PAGE_ROWS = 5_000

_TABLE_INSERTS = (
    (
        "apt_band_monthly_price",
        "INSERT INTO apt_band_monthly_price (pnu, area_band, deal_ym, median_price, trade_count, refreshed_at) "
        "VALUES %s",
        "(%s, %s, %s, %s, %s, NOW())",
    ),
    (
        "apt_band_trend",
        "INSERT INTO apt_band_trend (pnu, area_band, sigungu_code, base_ym, median_price_3m, trade_count_3m, "
        "trade_count_6m, change_6m_pct, change_12m_pct, matched_type_count_6m, matched_type_count_12m, "
        "relative_change_6m_pct, complex_grade, complex_rank, complex_rank_total, grade_window_months, "
        "refreshed_at) VALUES %s",
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())",
    ),
    (
        "region_band_trend",
        "INSERT INTO region_band_trend (sigungu_code, area_band, base_ym, median_price_3m, trade_count_3m, "
        "change_6m_pct, change_12m_pct, region_grade, region_rank, region_rank_total, refreshed_at) VALUES %s",
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())",
    ),
    (
        "apt_band_trend_excluded_key",
        "INSERT INTO apt_band_trend_excluded_key (apt_seq, pnu, reason, refreshed_at) VALUES %s",
        "(%s, %s, %s, NOW())",
    ),
)


def refresh_band_trend(logger, today: date | None = None) -> dict[str, int]:
    """4개 테이블 재생성. 반환 키: monthly_rows, trend_rows, region_rows, excluded_keys, excluded_trades."""
    started = time.time()
    base_ym = base_month(today or date.today())
    start_ym = shift_month(base_ym, -(HISTORY_MONTHS - 1))
    logger.info(f"  면적대 추세 집계 시작: 기준월 {base_ym}, 기간 {start_ym}~{base_ym}")

    conn = get_connection()
    try:
        codes = load_codes(conn)

        t0 = time.time()
        trades = load_trades(conn, codes.scope_sido, start_ym, base_ym)
        logger.info(
            f"    거래 로드: {len(trades):,}건 (시도 {codes.scope_sido}, {time.time() - t0:.1f}s)"
        )

        t0 = time.time()
        violations = find_mapping_violations(conn, codes.scope_sido)
        logger.info(
            f"    매핑 정합성 위반 키: {len(violations):,}개 ({time.time() - t0:.1f}s)"
        )

        exclusion = apply_exclusions(
            trades, codes.bands, {v["apt_seq"]: v["pnu"] for v in violations}
        )
        key_names = {
            t.apt_seq: t.apt_nm for t in trades if t.apt_seq in exclusion.excluded_keys
        }
        del trades
        _log_exclusions(logger, exclusion, key_names)

        t0 = time.time()
        tables = build_tables(
            exclusion.kept, base_ym, codes.region_labels, codes.complex_labels
        )
        logger.info(f"    지표 계산: {time.time() - t0:.1f}s")
        _log_coverage(logger, tables, [b.code for b in codes.bands])

        excluded_rows = [
            (seq, pnu, reason) for seq, (pnu, reason) in exclusion.excluded_keys.items()
        ]
        _replace_tables(
            conn,
            (tables.monthly_rows, tables.trend_rows, tables.region_rows, excluded_rows),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    counts = {
        "monthly_rows": len(tables.monthly_rows),
        "trend_rows": len(tables.trend_rows),
        "region_rows": len(tables.region_rows),
        "excluded_keys": len(excluded_rows),
        "excluded_trades": sum(exclusion.excluded_trades_by_key.values()),
    }
    logger.info(f"  면적대 추세 집계 완료: {counts} ({time.time() - started:.1f}s)")
    return counts


def _replace_tables(conn, rows_per_table: tuple[list[tuple], ...]) -> None:
    """4개 테이블을 같은 트랜잭션에서 비우고 다시 채운다 (커밋은 호출자)."""
    cur = conn.cursor()
    for table, _sql, _template in _TABLE_INSERTS:
        cur.execute(f"DELETE FROM {table}")
    for (table, sql, template), rows in zip(
        _TABLE_INSERTS, rows_per_table, strict=True
    ):
        psycopg2.extras.execute_values(
            cur, sql, rows, template=template, page_size=_INSERT_PAGE_ROWS
        )


def _log_exclusions(
    logger, exclusion: ExclusionResult, key_names: dict[str, str | None]
) -> None:
    reasons = Counter(reason for _pnu, reason in exclusion.excluded_keys.values())
    excluded_total = sum(exclusion.excluded_trades_by_key.values())
    logger.info(
        f"    혼입 제외: 키 {len(exclusion.excluded_keys):,}개 {dict(reasons)}, "
        f"거래 {excluded_total:,}건 / 면적대 거래 {sum(exclusion.trades_by_band.values()):,}건"
    )
    for band, total in sorted(
        exclusion.trades_by_band.items(), key=lambda item: float(item[0])
    ):
        excluded = exclusion.excluded_by_band[band]
        ratio = excluded / total if total else 0.0
        line = f"      {band}: {excluded:,}/{total:,} ({ratio:.1%})"
        if ratio > EXCLUSION_RATIO_WARN:
            logger.warning(
                f"{line} — 제외 비율이 경고선 {EXCLUSION_RATIO_WARN:.0%} 초과, 판정 규칙 점검 필요"
            )
        else:
            logger.info(line)
    for seq, count in exclusion.excluded_trades_by_key.most_common(
        EXCLUDED_KEY_LOG_LIMIT
    ):
        pnu, reason = exclusion.excluded_keys[seq]
        logger.info(
            f"      제외 키 {seq} ({key_names.get(seq)}) → {pnu} [{reason}] {count:,}건"
        )


def _log_coverage(logger, tables: BandTables, band_codes: list[str]) -> None:
    """면적대별 노출 단지 수·변화값 NULL 비율·지역 등급 부여 수 (MIN_* 조정 근거)."""
    for band in band_codes:
        trend = [r for r in tables.trend_rows if r.area_band == band]
        regions = [r for r in tables.region_rows if r.area_band == band]
        null_6m = sum(1 for r in trend if r.change_6m_pct is None)
        graded_regions = sum(1 for r in regions if r.region_grade is not None)
        null_ratio = null_6m / len(trend) if trend else 0.0
        logger.info(
            f"      {band}: 단지 {len(trend):,} (6개월 변화 NULL {null_6m:,}, {null_ratio:.1%}), "
            f"지역 {len(regions)} (등급 {graded_regions}, 미부여 {len(regions) - graded_regions})"
        )
