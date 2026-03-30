"""배치 후 검증 쿼리."""

from batch.db import query_one, query_all


def verify_weekly(conn, logger):
    """Weekly 배치 검증."""
    logger.info("Weekly 검증 시작...")
    ok = True

    r = query_one(conn, "SELECT COUNT(*) as cnt FROM trade_history")
    logger.info(f"  trade_history: {r['cnt']:,}건")

    r = query_one(conn, "SELECT COUNT(*) as cnt FROM rent_history")
    logger.info(f"  rent_history: {r['cnt']:,}건")

    r = query_one(conn, "SELECT MAX(deal_year * 100 + deal_month) as last_ym FROM trade_history")
    logger.info(f"  최신 거래월: {r['last_ym']}")

    r = query_one(conn, "SELECT COUNT(*) as cnt FROM apt_price_score")
    logger.info(f"  apt_price_score: {r['cnt']:,}건")

    r = query_one(conn, "SELECT AVG(price_score) as avg, MIN(price_score) as mn, MAX(price_score) as mx FROM apt_price_score")
    if r["avg"] is None:
        logger.error("  price_score가 비어있음!")
        ok = False
    else:
        logger.info(f"  price_score 범위: {r['mn']:.1f} ~ {r['mx']:.1f} (평균 {r['avg']:.1f})")

    return ok


def verify_quarterly(conn, logger):
    """Quarterly 배치 검증."""
    logger.info("Quarterly 검증 시작...")
    ok = True

    rows = query_all(conn, "SELECT facility_subtype, COUNT(*) as cnt FROM facilities GROUP BY facility_subtype ORDER BY cnt DESC")
    logger.info("  시설 유형별:")
    for r in rows:
        logger.info(f"    {r['facility_subtype']:20s} {r['cnt']:>8,}건")

    r = query_one(conn, "SELECT COUNT(*) as cnt FROM apt_facility_summary")
    logger.info(f"  apt_facility_summary: {r['cnt']:,}건")

    r = query_one(conn, "SELECT AVG(safety_score) as avg FROM apt_safety_score")
    if r["avg"]:
        logger.info(f"  safety_score 평균: {r['avg']:.1f}")
    else:
        logger.error("  safety_score가 비어있음!")
        ok = False

    return ok


def verify_annual(conn, logger):
    """Annual 배치 검증."""
    logger.info("Annual 검증 시작...")
    ok = True

    r = query_one(conn, "SELECT COUNT(*) as cnt, SUM(total_pop) as total FROM population_by_district WHERE age_group = %s", ["계"])
    if r["cnt"] and r["cnt"] > 0:
        logger.info(f"  인구: {r['cnt']:,}개 시군구, 총 {r['total']:,}명")
    else:
        logger.error("  인구 데이터 없음!")
        ok = False

    r = query_one(conn, "SELECT COUNT(*) as cnt, AVG(crime_safety_score) as avg FROM sigungu_crime_score")
    if r["cnt"] and r["cnt"] > 0:
        logger.info(f"  범죄: {r['cnt']:,}개 시군구, 평균 점수 {r['avg']:.1f}")
    else:
        logger.error("  범죄 데이터 없음!")
        ok = False

    return ok
