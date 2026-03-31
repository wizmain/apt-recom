"""대시보드 API — 수도권 아파트 거래 동향."""

from fastapi import APIRouter, Query
from database import DictConnection
from datetime import datetime

router = APIRouter()


def _get_sgg_names(conn=None):
    """common_code 테이블에서 시군구 코드→이름 매핑 조회."""
    close = False
    if conn is None:
        conn = DictConnection()
        close = True
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s", ["sigungu"]
    ).fetchall()
    if close:
        conn.close()
    return {r["code"]: f"{r['name']}({r['extra']})" if r["extra"] and r["extra"] != r["name"] else r["name"] for r in rows}


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


@router.get("/dashboard/summary")
def dashboard_summary(
    sigungu: str = Query("", description="시군구 코드 필터"),
):
    """최근 30일 + 이전 30일 비교 요약 통계 + 갱신 정보."""
    conn = DictConnection()
    from datetime import timedelta
    now = datetime.now()

    # 최근 30일: today-29 ~ today, 이전 30일: today-59 ~ today-30
    cur_start = now - timedelta(days=29)
    prev_start = now - timedelta(days=59)
    prev_end = now - timedelta(days=30)

    sgg_filter = ""
    sgg_params: list = []
    if sigungu:
        sgg_filter = "AND sgg_cd = %s"
        sgg_params = [sigungu]

    # 날짜 범위 SQL: deal_year*10000 + deal_month*100 + deal_day 로 비교
    date_expr = "(deal_year * 10000 + deal_month * 100 + deal_day)"
    cur_start_val = cur_start.year * 10000 + cur_start.month * 100 + cur_start.day
    cur_end_val = now.year * 10000 + now.month * 100 + now.day
    prev_start_val = prev_start.year * 10000 + prev_start.month * 100 + prev_start.day
    prev_end_val = prev_end.year * 10000 + prev_end.month * 100 + prev_end.day

    # 매매 — 최근 30일
    trade_cur = conn.execute(
        f"SELECT COUNT(*) as volume, "
        f"COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deal_amount / NULLIF(exclu_use_ar, 0)), 0) as median_price_m2 "
        f"FROM trade_history WHERE {date_expr} BETWEEN %s AND %s AND exclu_use_ar > 0 {sgg_filter}",
        [cur_start_val, cur_end_val] + sgg_params
    ).fetchone()

    # 매매 — 이전 30일
    trade_prev = conn.execute(
        f"SELECT COUNT(*) as volume, "
        f"COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deal_amount / NULLIF(exclu_use_ar, 0)), 0) as median_price_m2 "
        f"FROM trade_history WHERE {date_expr} BETWEEN %s AND %s AND exclu_use_ar > 0 {sgg_filter}",
        [prev_start_val, prev_end_val] + sgg_params
    ).fetchone()

    # 전월세 — 최근 30일
    rent_cur = conn.execute(
        f"SELECT COUNT(*) as volume, "
        f"COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit / NULLIF(exclu_use_ar, 0)), 0) as median_deposit_m2 "
        f"FROM rent_history WHERE {date_expr} BETWEEN %s AND %s AND exclu_use_ar > 0 {sgg_filter}",
        [cur_start_val, cur_end_val] + sgg_params
    ).fetchone()

    # 전월세 — 이전 30일
    rent_prev = conn.execute(
        f"SELECT COUNT(*) as volume, "
        f"COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit / NULLIF(exclu_use_ar, 0)), 0) as median_deposit_m2 "
        f"FROM rent_history WHERE {date_expr} BETWEEN %s AND %s AND exclu_use_ar > 0 {sgg_filter}",
        [prev_start_val, prev_end_val] + sgg_params
    ).fetchone()

    # 갱신 정보
    last_updated_row = conn.execute(
        "SELECT MAX(created_at) as last_updated FROM trade_history WHERE created_at IS NOT NULL"
    ).fetchone()
    last_updated = last_updated_row["last_updated"].isoformat() if last_updated_row and last_updated_row["last_updated"] else None

    new_today = conn.execute(
        "SELECT COUNT(*) as cnt FROM trade_history WHERE created_at >= NOW() - INTERVAL '24 hours'"
    ).fetchone()

    conn.close()

    return {
        "current_period": f"{cur_start.month}/{cur_start.day}~{now.month}/{now.day}",
        "prev_period": f"{prev_start.month}/{prev_start.day}~{prev_end.month}/{prev_end.day}",
        "last_updated": last_updated,
        "new_today": (new_today["cnt"] or 0) if new_today else 0,
        "trade": {
            "volume": trade_cur["volume"],
            "median_price_m2": round(float(trade_cur["median_price_m2"]), 1),
            "prev_volume": trade_prev["volume"],
            "prev_median_price_m2": round(float(trade_prev["median_price_m2"]), 1),
        },
        "rent": {
            "volume": rent_cur["volume"],
            "median_deposit_m2": round(float(rent_cur["median_deposit_m2"]), 1),
            "prev_volume": rent_prev["volume"],
            "prev_median_deposit_m2": round(float(rent_prev["median_deposit_m2"]), 1),
        },
    }


@router.get("/dashboard/trend")
def dashboard_trend(
    months: int = Query(12, ge=1, le=60),
    sigungu: str = Query("", description="시군구 코드 (5자리). 비어있으면 전체"),
):
    """월별 거래 추이."""
    conn = DictConnection()
    now = datetime.now()

    # 시작 연월 계산
    start_month = now.month - months
    start_year = now.year
    while start_month <= 0:
        start_month += 12
        start_year -= 1

    sgg_filter = ""
    params_base: list = [start_year * 100 + start_month]
    if sigungu:
        sgg_filter = "AND sgg_cd = %s"
        params_base.append(sigungu)

    # 매매 월별 집계
    trade_rows = conn.execute(f"""
        SELECT deal_year, deal_month, COUNT(*) as volume,
               COALESCE(AVG(deal_amount), 0) as avg_price,
               COALESCE(AVG(CASE WHEN exclu_use_ar > 0 THEN deal_amount / exclu_use_ar END), 0) as avg_price_m2
        FROM trade_history
        WHERE deal_year * 100 + deal_month >= %s {sgg_filter}
        GROUP BY deal_year, deal_month
        ORDER BY deal_year, deal_month
    """, params_base).fetchall()

    # 전월세 월별 집계
    rent_params: list = [start_year * 100 + start_month]
    rent_sgg = ""
    if sigungu:
        rent_sgg = "AND sgg_cd = %s"
        rent_params.append(sigungu)

    rent_rows = conn.execute(f"""
        SELECT deal_year, deal_month, COUNT(*) as volume,
               COALESCE(AVG(deposit), 0) as avg_deposit
        FROM rent_history
        WHERE deal_year * 100 + deal_month >= %s {rent_sgg}
        GROUP BY deal_year, deal_month
        ORDER BY deal_year, deal_month
    """, rent_params).fetchall()

    conn.close()

    # 병합
    trade_map = {f"{r['deal_year']}-{r['deal_month']:02d}": r for r in trade_rows}
    rent_map = {f"{r['deal_year']}-{r['deal_month']:02d}": r for r in rent_rows}
    all_months = sorted(set(trade_map.keys()) | set(rent_map.keys()))

    result = []
    for month in all_months:
        t = trade_map.get(month)
        r = rent_map.get(month)
        trade_avg = float(t["avg_price"]) if t else 0
        rent_avg = float(r["avg_deposit"]) if r else 0
        jeonse_ratio = round(rent_avg / trade_avg * 100, 1) if trade_avg > 0 and rent_avg > 0 else 0

        result.append({
            "month": month,
            "trade_volume": t["volume"] if t else 0,
            "trade_avg_price": round(trade_avg),
            "trade_avg_price_m2": round(float(t["avg_price_m2"])) if t else 0,
            "rent_volume": r["volume"] if r else 0,
            "rent_avg_deposit": round(rent_avg),
            "jeonse_ratio": jeonse_ratio,
        })

    return result


@router.get("/dashboard/ranking")
def dashboard_ranking(
    type: str = Query("trade", regex="^(trade|rent)$"),
):
    """이번 달 시군구별 거래량 랭킹 Top 10."""
    conn = DictConnection()
    now = datetime.now()

    if type == "trade":
        rows = conn.execute("""
            SELECT t.sgg_cd, a.sigungu_name, COUNT(*) as volume,
                   COALESCE(AVG(t.deal_amount), 0) as avg_price
            FROM trade_history t
            LEFT JOIN (
                SELECT DISTINCT LEFT(sigungu_code, 5) as sgg_cd, sigungu_code as sigungu_name
                FROM apartments
            ) a ON t.sgg_cd = a.sgg_cd
            WHERE t.deal_year = %s AND t.deal_month = %s
            GROUP BY t.sgg_cd, a.sigungu_name
            ORDER BY volume DESC
            LIMIT 10
        """, [now.year, now.month]).fetchall()
    else:
        rows = conn.execute("""
            SELECT r.sgg_cd, a.sigungu_name, COUNT(*) as volume,
                   COALESCE(AVG(r.deposit), 0) as avg_deposit
            FROM rent_history r
            LEFT JOIN (
                SELECT DISTINCT LEFT(sigungu_code, 5) as sgg_cd, sigungu_code as sigungu_name
                FROM apartments
            ) a ON r.sgg_cd = a.sgg_cd
            WHERE r.deal_year = %s AND r.deal_month = %s
            GROUP BY r.sgg_cd, a.sigungu_name
            ORDER BY volume DESC
            LIMIT 10
        """, [now.year, now.month]).fetchall()

    conn.close()

    result = []
    for r in rows:
        sgg = r["sgg_cd"]
        sgg_names = _get_sgg_names()
        name = sgg_names.get(sgg, sgg)
        entry = {"sigungu_code": sgg, "sigungu_name": name, "volume": r["volume"]}
        if type == "trade":
            entry["avg_price"] = round(float(r["avg_price"]))
        else:
            entry["avg_deposit"] = round(float(r.get("avg_deposit", 0)))
        result.append(entry)

    return result


@router.get("/dashboard/recent")
def dashboard_recent(
    type: str = Query("trade", regex="^(trade|rent)$"),
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
                   t.deal_year, t.deal_month, t.deal_day
            FROM trade_history t
            {sgg_filter}
            ORDER BY t.deal_year DESC, t.deal_month DESC, t.deal_day DESC, t.deal_amount DESC
            LIMIT %s
        """, params + [limit]).fetchall()
    else:
        rows = conn.execute(f"""
            SELECT t.apt_nm, t.sgg_cd, t.deposit, t.monthly_rent, t.exclu_use_ar, t.floor,
                   t.deal_year, t.deal_month, t.deal_day
            FROM rent_history t
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
