"""대시보드 API — 수도권 아파트 거래 동향."""

from fastapi import APIRouter, Query
from database import DictConnection
from datetime import datetime

router = APIRouter()


def _get_sgg_names(conn):
    """common_code 테이블에서 시군구 코드→이름 매핑 조회.

    호출자가 반드시 conn 을 전달해야 한다. pool 기반으로 전환된 뒤에는
    dead branch(함수 내부에서 DictConnection 생성) 제거 — 잉여 conn 획득 방지.
    """
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s", ["sigungu"]
    ).fetchall()
    return {
        r["code"]: f"{r['name']}({r['extra']})"
        if r["extra"] and r["extra"] != r["name"]
        else r["name"]
        for r in rows
    }


@router.get("/dashboard/regions")
def dashboard_regions(q: str = Query("", description="검색어")):
    """시군구 목록 검색."""
    conn = DictConnection()
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s", ["sigungu"]
    ).fetchall()
    conn.close()
    results = [{"code": r["code"], "name": f"{r['name']}({r['extra']})" if r["extra"] and r["extra"] != r["name"] else r["name"]} for r in rows]
    if q.strip():
        results = [r for r in results if q.strip() in r["name"]]
    results.sort(key=lambda x: x["name"])
    return results


_DATA_LAG_NOTICE = (
    "실거래 신고 지연(30일 이내 신고 의무)을 피하기 위해 현재 구간은 '30~60일 전' 30일 윈도우로 집계합니다. "
    "전국 거래 데이터 수집이 진행 중이라 전년 동기 구간의 일부 지역(비수도권 등) 데이터가 아직 누락되어 있어 "
    "전년 대비 비교 수치는 부정확할 수 있습니다."
)


def _format_period(period_start, period_end) -> str:
    """2026-02-18 ~ 2026-03-19 → '2/18~3/19' 포맷."""
    return f"{period_start.month}/{period_start.day}~{period_end.month}/{period_end.day}"


def _format_prev_period(period_start, period_end) -> str:
    return f"{period_start.year}.{period_start.month}/{period_start.day}~{period_end.month}/{period_end.day}"


def _summary_from_aggregate(conn, scope: str):
    """집계 테이블 기반 summary 조회. 빈 결과 시 None 반환."""
    rows = conn.execute("""
        SELECT window_kind, period_start, period_end,
               trade_volume, trade_median_price_m2,
               rent_volume, rent_median_deposit_m2
        FROM dashboard_window_stats
        WHERE scope = %s
    """, [scope]).fetchall()
    if not rows:
        return None
    by_kind = {r["window_kind"]: r for r in rows}
    cur_row = by_kind.get("current")
    prev_row = by_kind.get("prev_year")
    if not cur_row or not prev_row:
        return None
    return {
        "current_period": _format_period(cur_row["period_start"], cur_row["period_end"]),
        "prev_period": _format_prev_period(prev_row["period_start"], prev_row["period_end"]),
        "trade_cur": {"volume": cur_row["trade_volume"], "median_price_m2": cur_row["trade_median_price_m2"]},
        "trade_prev": {"volume": prev_row["trade_volume"], "median_price_m2": prev_row["trade_median_price_m2"]},
        "rent_cur": {"volume": cur_row["rent_volume"], "median_deposit_m2": cur_row["rent_median_deposit_m2"]},
        "rent_prev": {"volume": prev_row["rent_volume"], "median_deposit_m2": prev_row["rent_median_deposit_m2"]},
    }


def _summary_from_raw(conn, sigungu: str):
    """집계 테이블이 아직 비어있을 때의 fallback 경로. 배치 최초 실행 전 브릿지용.

    TODO(remove-after-batch-run): 배치가 최소 1회 실행되어 dashboard_window_stats가
    채워진 이후에는 이 경로가 더 이상 호출되지 않는다. 다음 PR에서 제거.
    """
    from datetime import timedelta
    now = datetime.now()
    cur_end = now - timedelta(days=30)
    cur_start = cur_end - timedelta(days=29)
    prev_start = cur_start - timedelta(days=365)
    prev_end = cur_end - timedelta(days=365)

    sgg_filter = ""
    sgg_params: list = []
    if sigungu:
        sgg_filter = "AND sgg_cd = %s"
        sgg_params = [sigungu]

    def _agg(table, value_expr, start, end):
        row = conn.execute(f"""
            SELECT COUNT(*) AS volume,
                   COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {value_expr}), 0) AS median
            FROM {table}
            WHERE exclu_use_ar > 0
              AND make_date(deal_year, deal_month, deal_day) BETWEEN %s AND %s
              {sgg_filter}
        """, [start, end] + sgg_params).fetchone()
        return {"volume": row["volume"] or 0, "median": float(row["median"] or 0)}

    trade_cur = _agg("trade_history", "deal_amount / NULLIF(exclu_use_ar, 0)", cur_start, cur_end)
    trade_prev = _agg("trade_history", "deal_amount / NULLIF(exclu_use_ar, 0)", prev_start, prev_end)
    rent_cur = _agg("rent_history", "deposit / NULLIF(exclu_use_ar, 0)", cur_start, cur_end)
    rent_prev = _agg("rent_history", "deposit / NULLIF(exclu_use_ar, 0)", prev_start, prev_end)

    return {
        "current_period": _format_period(cur_start, cur_end),
        "prev_period": _format_prev_period(prev_start, prev_end),
        "trade_cur": {"volume": trade_cur["volume"], "median_price_m2": trade_cur["median"]},
        "trade_prev": {"volume": trade_prev["volume"], "median_price_m2": trade_prev["median"]},
        "rent_cur": {"volume": rent_cur["volume"], "median_deposit_m2": rent_cur["median"]},
        "rent_prev": {"volume": rent_prev["volume"], "median_deposit_m2": rent_prev["median"]},
    }


@router.get("/dashboard/summary")
def dashboard_summary(
    sigungu: str = Query("", description="시군구 코드 필터"),
):
    """30~60일 전 30일 구간 vs 전년 동기 30일(YoY) 비교 요약 통계 + 갱신 정보.

    부동산 실거래가는 계약 후 30일 이내 신고 의무가 있어 최근 30일 구간은
    신고 지연으로 과소집계된다. 이를 피하기 위해 "30~60일 전"의 30일 윈도우를
    현재 구간으로 사용한다. 계절성을 상쇄하기 위해 전년 동기(365일 전)와
    비교한다. 단, 전국 거래 데이터 수집이 진행 중이라 전년 동기 구간의 일부
    지역이 누락될 수 있어 비교 수치는 부정확할 수 있다(UI에서 안내).

    데이터는 dashboard_window_stats 집계 테이블에서 조회한다.
    집계가 아직 없으면 raw 쿼리로 fallback (브릿지 경로).
    """
    conn = DictConnection()
    scope = sigungu or "ALL"
    stats = _summary_from_aggregate(conn, scope)
    if stats is None:
        stats = _summary_from_raw(conn, sigungu)

    # 갱신 정보는 실시간성이 중요해 집계 테이블이 아닌 trade_history 직접 조회.
    # EXPLAIN: 합치면 Parallel Seq Scan (235ms), 분리하면 Index Only Scan 각 2ms.
    last_updated_row = conn.execute(
        "SELECT MAX(created_at) as last_updated FROM trade_history"
    ).fetchone()
    last_updated = (
        last_updated_row["last_updated"].isoformat()
        if last_updated_row and last_updated_row["last_updated"] else None
    )

    new_today_row = conn.execute(
        "SELECT COUNT(*) as cnt FROM trade_history WHERE created_at >= NOW() - INTERVAL '24 hours'"
    ).fetchone()

    conn.close()

    return {
        "current_period": stats["current_period"],
        "prev_period": stats["prev_period"],
        "prev_label": "전년 동기",
        "comparison_mode": "yoy",
        "data_lag_notice": _DATA_LAG_NOTICE,
        "last_updated": last_updated,
        "new_today": (new_today_row["cnt"] or 0) if new_today_row else 0,
        "trade": {
            "volume": stats["trade_cur"]["volume"],
            "median_price_m2": round(float(stats["trade_cur"]["median_price_m2"]), 1),
            "prev_volume": stats["trade_prev"]["volume"],
            "prev_median_price_m2": round(float(stats["trade_prev"]["median_price_m2"]), 1),
        },
        "rent": {
            "volume": stats["rent_cur"]["volume"],
            "median_deposit_m2": round(float(stats["rent_cur"]["median_deposit_m2"]), 1),
            "prev_volume": stats["rent_prev"]["volume"],
            "prev_median_deposit_m2": round(float(stats["rent_prev"]["median_deposit_m2"]), 1),
        },
    }


def _trend_from_aggregate(conn, scope: str, start_ym: int):
    """dashboard_monthly_stats에서 월별 추이 조회."""
    rows = conn.execute("""
        SELECT deal_year, deal_month,
               trade_volume, trade_avg_price, trade_avg_price_m2,
               rent_volume, rent_avg_deposit
        FROM dashboard_monthly_stats
        WHERE scope = %s AND deal_year * 100 + deal_month >= %s
        ORDER BY deal_year, deal_month
    """, [scope, start_ym]).fetchall()
    return rows


def _trend_from_raw(conn, sigungu: str, start_ym: int):
    """집계 테이블이 비어있을 때의 fallback.

    TODO(remove-after-batch-run): 다음 PR에서 제거.
    """
    sgg_filter = ""
    params: list = [start_ym]
    if sigungu:
        sgg_filter = "AND sgg_cd = %s"
        params.append(sigungu)

    trade = conn.execute(f"""
        SELECT deal_year, deal_month, COUNT(*) AS trade_volume,
               COALESCE(AVG(deal_amount), 0) AS trade_avg_price,
               COALESCE(AVG(CASE WHEN exclu_use_ar > 0 THEN deal_amount / exclu_use_ar END), 0) AS trade_avg_price_m2
        FROM trade_history
        WHERE deal_year * 100 + deal_month >= %s {sgg_filter}
        GROUP BY deal_year, deal_month
    """, params).fetchall()

    rent = conn.execute(f"""
        SELECT deal_year, deal_month, COUNT(*) AS rent_volume,
               COALESCE(AVG(deposit), 0) AS rent_avg_deposit
        FROM rent_history
        WHERE deal_year * 100 + deal_month >= %s {sgg_filter}
        GROUP BY deal_year, deal_month
    """, params).fetchall()

    key = lambda r: (r["deal_year"], r["deal_month"])  # noqa: E731
    tmap = {key(r): r for r in trade}
    rmap = {key(r): r for r in rent}
    merged = []
    for k in sorted(set(tmap.keys()) | set(rmap.keys())):
        t = tmap.get(k, {})
        r = rmap.get(k, {})
        merged.append({
            "deal_year": k[0],
            "deal_month": k[1],
            "trade_volume": t.get("trade_volume", 0),
            "trade_avg_price": t.get("trade_avg_price", 0),
            "trade_avg_price_m2": t.get("trade_avg_price_m2", 0),
            "rent_volume": r.get("rent_volume", 0),
            "rent_avg_deposit": r.get("rent_avg_deposit", 0),
        })
    return merged


@router.get("/dashboard/trend")
def dashboard_trend(
    months: int = Query(12, ge=1, le=60),
    sigungu: str = Query("", description="시군구 코드 (5자리). 비어있으면 전체"),
):
    """월별 거래 추이. dashboard_monthly_stats 집계 테이블 기반."""
    conn = DictConnection()
    now = datetime.now()

    # 시작 연월 계산
    start_month = now.month - months + 1
    start_year = now.year
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start_ym = start_year * 100 + start_month

    scope = sigungu or "ALL"
    rows = _trend_from_aggregate(conn, scope, start_ym)
    if not rows:
        rows = _trend_from_raw(conn, sigungu, start_ym)

    conn.close()

    result = []
    for r in rows:
        trade_avg = float(r["trade_avg_price"] or 0)
        rent_avg = float(r["rent_avg_deposit"] or 0)
        jeonse_ratio = round(rent_avg / trade_avg * 100, 1) if trade_avg > 0 and rent_avg > 0 else 0
        result.append({
            "month": f"{r['deal_year']}-{r['deal_month']:02d}",
            "trade_volume": r["trade_volume"] or 0,
            "trade_avg_price": round(trade_avg),
            "trade_avg_price_m2": round(float(r["trade_avg_price_m2"] or 0)),
            "rent_volume": r["rent_volume"] or 0,
            "rent_avg_deposit": round(rent_avg),
            "jeonse_ratio": jeonse_ratio,
        })

    return result


def _ranking_from_aggregate(conn, type_: str, year: int, month: int):
    """dashboard_ranking_stats에서 현재월 Top 10 조회."""
    return conn.execute("""
        SELECT sgg_cd, volume, avg_value
        FROM dashboard_ranking_stats
        WHERE type = %s AND deal_year = %s AND deal_month = %s
        ORDER BY volume DESC
        LIMIT 10
    """, [type_, year, month]).fetchall()


def _ranking_from_raw(conn, type_: str, year: int, month: int):
    """집계 테이블이 비어있을 때의 fallback.

    TODO(remove-after-batch-run): 다음 PR에서 제거.
    """
    if type_ == "trade":
        sql = """
            SELECT sgg_cd, COUNT(*) AS volume, COALESCE(AVG(deal_amount), 0) AS avg_value
            FROM trade_history
            WHERE deal_year = %s AND deal_month = %s AND sgg_cd IS NOT NULL
            GROUP BY sgg_cd
            ORDER BY volume DESC
            LIMIT 10
        """
    else:
        sql = """
            SELECT sgg_cd, COUNT(*) AS volume, COALESCE(AVG(deposit), 0) AS avg_value
            FROM rent_history
            WHERE deal_year = %s AND deal_month = %s AND sgg_cd IS NOT NULL
            GROUP BY sgg_cd
            ORDER BY volume DESC
            LIMIT 10
        """
    return conn.execute(sql, [year, month]).fetchall()


@router.get("/dashboard/ranking")
def dashboard_ranking(
    type: str = Query("trade", pattern="^(trade|rent)$"),
):
    """이번 달 시군구별 거래량 랭킹 Top 10. dashboard_ranking_stats 기반."""
    conn = DictConnection()
    now = datetime.now()

    rows = _ranking_from_aggregate(conn, type, now.year, now.month)
    if not rows:
        rows = _ranking_from_raw(conn, type, now.year, now.month)

    sgg_names = _get_sgg_names(conn)
    conn.close()

    result = []
    for r in rows:
        sgg = r["sgg_cd"]
        entry = {"sigungu_code": sgg, "sigungu_name": sgg_names.get(sgg, sgg), "volume": r["volume"]}
        if type == "trade":
            entry["avg_price"] = round(float(r["avg_value"] or 0))
        else:
            entry["avg_deposit"] = round(float(r["avg_value"] or 0))
        result.append(entry)

    return result


@router.get("/dashboard/recent")
def dashboard_recent(
    type: str = Query("trade", pattern="^(trade|rent)$"),
    limit: int = Query(20, ge=1, le=100),
    sigungu: str = Query("", description="시군구 코드 필터"),
):
    """최근 거래 내역 목록."""
    conn = DictConnection()

    sgg_filter = ""
    params: list = []
    if sigungu:
        sgg_filter = "WHERE t.sgg_cd = %s"
        params.append(sigungu)

    if type == "trade":
        rows = conn.execute(f"""
            SELECT t.apt_nm, t.sgg_cd, t.deal_amount, t.exclu_use_ar, t.floor,
                   t.deal_year, t.deal_month, t.deal_day, m.pnu
            FROM trade_history t
            LEFT JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
            {sgg_filter}
            ORDER BY t.deal_year DESC, t.deal_month DESC, t.deal_day DESC, t.deal_amount DESC
            LIMIT %s
        """, params + [limit]).fetchall()
    else:
        rows = conn.execute(f"""
            SELECT t.apt_nm, t.sgg_cd, t.deposit, t.monthly_rent, t.exclu_use_ar, t.floor,
                   t.deal_year, t.deal_month, t.deal_day, m.pnu
            FROM rent_history t
            LEFT JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
            {sgg_filter}
            ORDER BY t.deal_year DESC, t.deal_month DESC, t.deal_day DESC, t.deposit DESC
            LIMIT %s
        """, params + [limit]).fetchall()

    sgg_names = _get_sgg_names(conn)
    conn.close()

    result = []
    for r in rows:
        sgg = r.get("sgg_cd", "")
        entry = {
            "apt_nm": r["apt_nm"],
            "sgg_cd": sgg,
            "sigungu": sgg_names.get(sgg, sgg),
            "area": r.get("exclu_use_ar"),
            "floor": r.get("floor"),
            "date": f"{r['deal_year']}.{r['deal_month']:02d}.{r['deal_day']:02d}" if r.get("deal_day") else f"{r['deal_year']}.{r['deal_month']:02d}",
            "pnu": r.get("pnu"),
        }
        if type == "trade":
            entry["price"] = r["deal_amount"]
        else:
            entry["deposit"] = r.get("deposit")
            entry["monthly_rent"] = r.get("monthly_rent")
        result.append(entry)

    return result


@router.get("/dashboard/trades")
def dashboard_trades(
    apt_nm: str = Query(..., description="아파트명"),
    sgg_cd: str = Query(..., description="시군구 코드"),
    area: float | None = Query(None, description="기준 면적 (±5㎡ 필터)"),
):
    """특정 아파트의 매매 + 전월세 이력 조회. area 지정 시 비슷한 면적만."""
    conn = DictConnection()

    area_filter = ""
    params_trade: list = [apt_nm, sgg_cd]
    params_rent: list = [apt_nm, sgg_cd]
    if area is not None:
        area_filter = "AND exclu_use_ar BETWEEN %s AND %s"
        params_trade.extend([area - 5, area + 5])
        params_rent.extend([area - 5, area + 5])

    trades = conn.execute(f"""
        SELECT deal_amount, exclu_use_ar, floor, deal_year, deal_month, deal_day
        FROM trade_history
        WHERE apt_nm = %s AND sgg_cd = %s {area_filter}
        ORDER BY deal_year DESC, deal_month DESC, deal_day DESC
    """, params_trade).fetchall()

    rents = conn.execute(f"""
        SELECT deposit, monthly_rent, exclu_use_ar, floor, deal_year, deal_month, deal_day
        FROM rent_history
        WHERE apt_nm = %s AND sgg_cd = %s {area_filter}
        ORDER BY deal_year DESC, deal_month DESC, deal_day DESC
    """, params_rent).fetchall()

    sgg_names = _get_sgg_names(conn)
    conn.close()

    return {
        "apt_nm": apt_nm,
        "sigungu": sgg_names.get(sgg_cd, sgg_cd),
        "trades": [
            {
                "date": f"{r['deal_year']}.{r['deal_month']:02d}.{r['deal_day']:02d}",
                "price": r["deal_amount"],
                "area": r.get("exclu_use_ar"),
                "floor": r.get("floor"),
            }
            for r in trades
        ],
        "rents": [
            {
                "date": f"{r['deal_year']}.{r['deal_month']:02d}.{r['deal_day']:02d}",
                "deposit": r.get("deposit"),
                "monthly_rent": r.get("monthly_rent"),
                "area": r.get("exclu_use_ar"),
                "floor": r.get("floor"),
            }
            for r in rents
        ],
    }
