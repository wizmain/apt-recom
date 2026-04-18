"""대시보드 집계 테이블 3종 갱신.

- dashboard_monthly_stats: 최근 60개월 scope(ALL/시군구)별 월간 집계 (trend 전용)
- dashboard_window_stats:  30~60일전 / 전년동기 윈도우 집계 (summary 전용)
- dashboard_ranking_stats: 최근 3개월 시군구별 거래량 (ranking 전용)

별도 커넥션으로 수행하여 run_trade의 선행 단계 트랜잭션과 완전 격리.
실패 시 rollback이 선행 작업에 영향을 주지 않는다.
"""

from datetime import date, timedelta

from batch.db import get_connection


MONTHLY_WINDOW_MONTHS = 60
RANKING_WINDOW_MONTHS = 3


def refresh_dashboard_stats(logger) -> dict:
    """집계 테이블 3종 갱신. 반환: {"monthly": n, "window": n, "ranking": n}.

    별도 커넥션에서 수행 — run_trade 상위 트랜잭션과 격리.
    호출자는 이 시점 이전에 선행 단계를 commit해야 한다.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        logger.info("  대시보드 집계 갱신 시작")
        monthly = _refresh_monthly(cur, logger)
        window = _refresh_window(cur, logger)
        ranking = _refresh_ranking(cur, logger)
        conn.commit()
        logger.info(f"  대시보드 집계 갱신 완료: monthly={monthly}, window={window}, ranking={ranking}")
        return {"monthly": monthly, "window": window, "ranking": ranking}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _start_year_month(months_back: int) -> int:
    """오늘 기준 N개월 전의 year*100+month 값."""
    today = date.today()
    y, m = today.year, today.month - months_back + 1
    while m <= 0:
        m += 12
        y -= 1
    return y * 100 + m


def _refresh_monthly(cur, logger) -> int:
    """최근 60개월, scope=ALL + 시군구별 월간 집계."""
    start_ym = _start_year_month(MONTHLY_WINDOW_MONTHS)
    sql = """
    WITH trade_all AS (
        SELECT 'ALL'::TEXT AS scope, deal_year, deal_month,
               COUNT(*)::INTEGER AS volume,
               COALESCE(AVG(deal_amount), 0)::DOUBLE PRECISION AS avg_price,
               COALESCE(AVG(CASE WHEN exclu_use_ar > 0 THEN deal_amount / exclu_use_ar END), 0)::DOUBLE PRECISION AS avg_price_m2,
               COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (
                   ORDER BY CASE WHEN exclu_use_ar > 0 THEN deal_amount / exclu_use_ar END
               ), 0)::DOUBLE PRECISION AS median_price_m2
        FROM trade_history
        WHERE deal_year * 100 + deal_month >= %s
        GROUP BY deal_year, deal_month
    ),
    trade_sgg AS (
        SELECT sgg_cd AS scope, deal_year, deal_month,
               COUNT(*)::INTEGER AS volume,
               COALESCE(AVG(deal_amount), 0)::DOUBLE PRECISION AS avg_price,
               COALESCE(AVG(CASE WHEN exclu_use_ar > 0 THEN deal_amount / exclu_use_ar END), 0)::DOUBLE PRECISION AS avg_price_m2,
               COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (
                   ORDER BY CASE WHEN exclu_use_ar > 0 THEN deal_amount / exclu_use_ar END
               ), 0)::DOUBLE PRECISION AS median_price_m2
        FROM trade_history
        WHERE deal_year * 100 + deal_month >= %s AND sgg_cd IS NOT NULL
        GROUP BY sgg_cd, deal_year, deal_month
    ),
    trade_agg AS (
        SELECT * FROM trade_all UNION ALL SELECT * FROM trade_sgg
    ),
    rent_all AS (
        SELECT 'ALL'::TEXT AS scope, deal_year, deal_month,
               COUNT(*)::INTEGER AS volume,
               COALESCE(AVG(deposit), 0)::DOUBLE PRECISION AS avg_deposit,
               COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (
                   ORDER BY CASE WHEN exclu_use_ar > 0 THEN deposit / exclu_use_ar END
               ), 0)::DOUBLE PRECISION AS median_deposit_m2
        FROM rent_history
        WHERE deal_year * 100 + deal_month >= %s
        GROUP BY deal_year, deal_month
    ),
    rent_sgg AS (
        SELECT sgg_cd AS scope, deal_year, deal_month,
               COUNT(*)::INTEGER AS volume,
               COALESCE(AVG(deposit), 0)::DOUBLE PRECISION AS avg_deposit,
               COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (
                   ORDER BY CASE WHEN exclu_use_ar > 0 THEN deposit / exclu_use_ar END
               ), 0)::DOUBLE PRECISION AS median_deposit_m2
        FROM rent_history
        WHERE deal_year * 100 + deal_month >= %s AND sgg_cd IS NOT NULL
        GROUP BY sgg_cd, deal_year, deal_month
    ),
    rent_agg AS (
        SELECT * FROM rent_all UNION ALL SELECT * FROM rent_sgg
    ),
    joined AS (
        SELECT COALESCE(t.scope, r.scope) AS scope,
               COALESCE(t.deal_year, r.deal_year) AS deal_year,
               COALESCE(t.deal_month, r.deal_month) AS deal_month,
               COALESCE(t.volume, 0) AS trade_volume,
               COALESCE(t.avg_price, 0) AS trade_avg_price,
               COALESCE(t.avg_price_m2, 0) AS trade_avg_price_m2,
               COALESCE(t.median_price_m2, 0) AS trade_median_price_m2,
               COALESCE(r.volume, 0) AS rent_volume,
               COALESCE(r.avg_deposit, 0) AS rent_avg_deposit,
               COALESCE(r.median_deposit_m2, 0) AS rent_median_deposit_m2
        FROM trade_agg t
        FULL OUTER JOIN rent_agg r USING (scope, deal_year, deal_month)
    )
    INSERT INTO dashboard_monthly_stats (
        scope, deal_year, deal_month,
        trade_volume, trade_avg_price, trade_avg_price_m2, trade_median_price_m2,
        rent_volume, rent_avg_deposit, rent_median_deposit_m2, refreshed_at
    )
    SELECT scope, deal_year, deal_month,
           trade_volume, trade_avg_price, trade_avg_price_m2, trade_median_price_m2,
           rent_volume, rent_avg_deposit, rent_median_deposit_m2, NOW()
    FROM joined
    ON CONFLICT (scope, deal_year, deal_month) DO UPDATE SET
        trade_volume = EXCLUDED.trade_volume,
        trade_avg_price = EXCLUDED.trade_avg_price,
        trade_avg_price_m2 = EXCLUDED.trade_avg_price_m2,
        trade_median_price_m2 = EXCLUDED.trade_median_price_m2,
        rent_volume = EXCLUDED.rent_volume,
        rent_avg_deposit = EXCLUDED.rent_avg_deposit,
        rent_median_deposit_m2 = EXCLUDED.rent_median_deposit_m2,
        refreshed_at = NOW()
    """
    cur.execute(sql, [start_ym, start_ym, start_ym, start_ym])
    rows = cur.rowcount
    logger.info(f"    monthly: {rows}건 upsert")
    return rows


def _refresh_window(cur, logger) -> int:
    """30~60일전 30일(current) vs 전년동기(prev_year) 윈도우, scope=ALL + 시군구별."""
    today = date.today()
    cur_end = today - timedelta(days=30)
    cur_start = cur_end - timedelta(days=29)
    prev_end = cur_end - timedelta(days=365)
    prev_start = cur_start - timedelta(days=365)

    # 두 윈도우 × (ALL + 시군구) 한 번에 집계
    sql = """
    WITH params AS (
        SELECT 'current'::TEXT AS window_kind, %s::DATE AS ps, %s::DATE AS pe
        UNION ALL
        SELECT 'prev_year', %s::DATE, %s::DATE
    ),
    -- trade: 전체 스코프. 원본 /summary 로직과 일관성 위해 exclu_use_ar > 0 필터 적용.
    trade_all AS (
        SELECT p.window_kind, p.ps, p.pe, 'ALL'::TEXT AS scope,
               COUNT(*)::INTEGER AS volume,
               COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (
                   ORDER BY t.deal_amount / t.exclu_use_ar
               ), 0)::DOUBLE PRECISION AS median_price_m2
        FROM params p
        LEFT JOIN trade_history t
            ON make_date(t.deal_year, t.deal_month, t.deal_day) BETWEEN p.ps AND p.pe
            AND t.exclu_use_ar > 0
        GROUP BY p.window_kind, p.ps, p.pe
    ),
    trade_sgg AS (
        SELECT p.window_kind, p.ps, p.pe, t.sgg_cd AS scope,
               COUNT(*)::INTEGER AS volume,
               COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (
                   ORDER BY t.deal_amount / t.exclu_use_ar
               ), 0)::DOUBLE PRECISION AS median_price_m2
        FROM params p
        JOIN trade_history t
            ON make_date(t.deal_year, t.deal_month, t.deal_day) BETWEEN p.ps AND p.pe
        WHERE t.sgg_cd IS NOT NULL AND t.exclu_use_ar > 0
        GROUP BY p.window_kind, p.ps, p.pe, t.sgg_cd
    ),
    trade_agg AS (
        SELECT * FROM trade_all UNION ALL SELECT * FROM trade_sgg
    ),
    rent_all AS (
        SELECT p.window_kind, p.ps, p.pe, 'ALL'::TEXT AS scope,
               COUNT(*)::INTEGER AS volume,
               COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (
                   ORDER BY r.deposit / r.exclu_use_ar
               ), 0)::DOUBLE PRECISION AS median_deposit_m2
        FROM params p
        LEFT JOIN rent_history r
            ON make_date(r.deal_year, r.deal_month, r.deal_day) BETWEEN p.ps AND p.pe
            AND r.exclu_use_ar > 0
        GROUP BY p.window_kind, p.ps, p.pe
    ),
    rent_sgg AS (
        SELECT p.window_kind, p.ps, p.pe, r.sgg_cd AS scope,
               COUNT(*)::INTEGER AS volume,
               COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (
                   ORDER BY r.deposit / r.exclu_use_ar
               ), 0)::DOUBLE PRECISION AS median_deposit_m2
        FROM params p
        JOIN rent_history r
            ON make_date(r.deal_year, r.deal_month, r.deal_day) BETWEEN p.ps AND p.pe
        WHERE r.sgg_cd IS NOT NULL AND r.exclu_use_ar > 0
        GROUP BY p.window_kind, p.ps, p.pe, r.sgg_cd
    ),
    rent_agg AS (
        SELECT * FROM rent_all UNION ALL SELECT * FROM rent_sgg
    ),
    joined AS (
        SELECT COALESCE(t.scope, r.scope) AS scope,
               COALESCE(t.window_kind, r.window_kind) AS window_kind,
               COALESCE(t.ps, r.ps) AS period_start,
               COALESCE(t.pe, r.pe) AS period_end,
               COALESCE(t.volume, 0) AS trade_volume,
               COALESCE(t.median_price_m2, 0) AS trade_median_price_m2,
               COALESCE(r.volume, 0) AS rent_volume,
               COALESCE(r.median_deposit_m2, 0) AS rent_median_deposit_m2
        FROM trade_agg t
        FULL OUTER JOIN rent_agg r USING (scope, window_kind, ps, pe)
    )
    INSERT INTO dashboard_window_stats (
        scope, window_kind, period_start, period_end,
        trade_volume, trade_median_price_m2, rent_volume, rent_median_deposit_m2, refreshed_at
    )
    SELECT scope, window_kind, period_start, period_end,
           trade_volume, trade_median_price_m2, rent_volume, rent_median_deposit_m2, NOW()
    FROM joined
    ON CONFLICT (scope, window_kind) DO UPDATE SET
        period_start = EXCLUDED.period_start,
        period_end = EXCLUDED.period_end,
        trade_volume = EXCLUDED.trade_volume,
        trade_median_price_m2 = EXCLUDED.trade_median_price_m2,
        rent_volume = EXCLUDED.rent_volume,
        rent_median_deposit_m2 = EXCLUDED.rent_median_deposit_m2,
        refreshed_at = NOW()
    """
    cur.execute(sql, [cur_start, cur_end, prev_start, prev_end])
    rows = cur.rowcount
    logger.info(f"    window: {rows}건 upsert (current={cur_start}~{cur_end}, prev={prev_start}~{prev_end})")
    return rows


def _refresh_ranking(cur, logger) -> int:
    """최근 3개월 × type(trade/rent) × 시군구별 거래량/평균."""
    start_ym = _start_year_month(RANKING_WINDOW_MONTHS)

    # 3개월보다 오래된 데이터 정리
    cur.execute(
        "DELETE FROM dashboard_ranking_stats WHERE deal_year * 100 + deal_month < %s",
        [start_ym],
    )
    deleted = cur.rowcount

    sql = """
    WITH trade_agg AS (
        SELECT 'trade'::TEXT AS type, deal_year, deal_month, sgg_cd,
               COUNT(*)::INTEGER AS volume,
               COALESCE(AVG(deal_amount), 0)::DOUBLE PRECISION AS avg_value
        FROM trade_history
        WHERE deal_year * 100 + deal_month >= %s AND sgg_cd IS NOT NULL
        GROUP BY deal_year, deal_month, sgg_cd
    ),
    rent_agg AS (
        SELECT 'rent'::TEXT AS type, deal_year, deal_month, sgg_cd,
               COUNT(*)::INTEGER AS volume,
               COALESCE(AVG(deposit), 0)::DOUBLE PRECISION AS avg_value
        FROM rent_history
        WHERE deal_year * 100 + deal_month >= %s AND sgg_cd IS NOT NULL
        GROUP BY deal_year, deal_month, sgg_cd
    )
    INSERT INTO dashboard_ranking_stats (type, deal_year, deal_month, sgg_cd, volume, avg_value, refreshed_at)
    SELECT type, deal_year, deal_month, sgg_cd, volume, avg_value, NOW()
    FROM (SELECT * FROM trade_agg UNION ALL SELECT * FROM rent_agg) agg
    ON CONFLICT (type, deal_year, deal_month, sgg_cd) DO UPDATE SET
        volume = EXCLUDED.volume,
        avg_value = EXCLUDED.avg_value,
        refreshed_at = NOW()
    """
    cur.execute(sql, [start_ym, start_ym])
    upserted = cur.rowcount
    logger.info(f"    ranking: {upserted}건 upsert, {deleted}건 정리")
    return upserted
