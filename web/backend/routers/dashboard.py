"""대시보드 API — 수도권 아파트 거래 동향."""

from fastapi import APIRouter, Query
from database import DictConnection
from datetime import datetime

router = APIRouter()

import sys
from pathlib import Path
# batch 모듈을 프로젝트 루트에서 import
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
from batch.nationwide_codes import ALL_SGG as SGG_NAMES


@router.get("/dashboard/regions")
def dashboard_regions(q: str = Query("", description="검색어")):
    """시군구 목록 검색."""
    results = [{"code": k, "name": v} for k, v in SGG_NAMES.items()]
    if q.strip():
        results = [r for r in results if q.strip() in r["name"]]
    results.sort(key=lambda x: x["name"])
    return results


@router.get("/dashboard/summary")
def dashboard_summary():
    """이번 달 + 전월 요약 통계 + 갱신 정보."""
    conn = DictConnection()
    now = datetime.now()
    cur_year, cur_month = now.year, now.month
    prev_month = cur_month - 1 if cur_month > 1 else 12
    prev_year = cur_year if cur_month > 1 else cur_year - 1

    # 매매 — 이번 달
    trade_cur = conn.execute(
        "SELECT COUNT(*) as volume, COALESCE(AVG(deal_amount), 0) as avg_price "
        "FROM trade_history WHERE deal_year = %s AND deal_month = %s",
        [cur_year, cur_month]
    ).fetchone()

    # 매매 — 전월
    trade_prev = conn.execute(
        "SELECT COUNT(*) as volume, COALESCE(AVG(deal_amount), 0) as avg_price "
        "FROM trade_history WHERE deal_year = %s AND deal_month = %s",
        [prev_year, prev_month]
    ).fetchone()

    # 전월세 — 이번 달
    rent_cur = conn.execute(
        "SELECT COUNT(*) as volume, COALESCE(AVG(deposit), 0) as avg_deposit "
        "FROM rent_history WHERE deal_year = %s AND deal_month = %s",
        [cur_year, cur_month]
    ).fetchone()

    # 전월세 — 전월
    rent_prev = conn.execute(
        "SELECT COUNT(*) as volume, COALESCE(AVG(deposit), 0) as avg_deposit "
        "FROM rent_history WHERE deal_year = %s AND deal_month = %s",
        [prev_year, prev_month]
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
        "current_month": f"{cur_year}-{cur_month:02d}",
        "last_updated": last_updated,
        "new_today": (new_today["cnt"] or 0) if new_today else 0,
        "trade": {
            "volume": trade_cur["volume"],
            "avg_price": round(float(trade_cur["avg_price"])),
            "prev_volume": trade_prev["volume"],
            "prev_avg_price": round(float(trade_prev["avg_price"])),
        },
        "rent": {
            "volume": rent_cur["volume"],
            "avg_deposit": round(float(rent_cur["avg_deposit"])),
            "prev_volume": rent_prev["volume"],
            "prev_avg_deposit": round(float(rent_prev["avg_deposit"])),
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
        name = SGG_NAMES.get(sgg, sgg)
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
            ORDER BY t.deal_year DESC, t.deal_month DESC, t.deal_day DESC, t.deal_amount DESC
            LIMIT %s
        """, params + [limit]).fetchall()

    conn.close()

    result = []
    for r in rows:
        sgg = r.get("sgg_cd", "")
        entry = {
            "apt_nm": r["apt_nm"],
            "sigungu": SGG_NAMES.get(sgg, sgg),
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
