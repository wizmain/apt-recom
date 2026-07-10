"""대시보드 API — 수도권 아파트 거래 동향."""

import time

from fastapi import APIRouter, HTTPException, Query
from database import DictConnection
from datetime import datetime, timedelta
from routers.apartments import APARTMENT_VISIBLE_CONDITIONS

router = APIRouter()

# ---------------------------------------------------------------------------
# /dashboard/regions 전체 목록 TTL 캐시
# ---------------------------------------------------------------------------
# 발동 조건: 지역검색 입력창이 타이핑마다(프론트 debounce 200ms) q 파라미터만
# 바꿔 이 엔드포인트를 재호출하는데, apt_count 집계는 apartments 31k 행을
# GROUP BY 하는 쿼리(약 44ms)라 검색어를 한 글자씩 칠 때마다 반복 실행됐다.
# apt_count 는 수집 배치(batch.run 등)에서만 바뀌고 요청 트래픽과는 무관하므로
# 프로세스 메모리에 "필터 없는 전체 목록"을 캐시하고, q 필터는 기존과 동일하게
# 캐시된 목록에 파이썬 레벨로 적용한다.
# TTL 3600s 근거: 배치 수집은 일 단위 스케줄이라 1시간 지연은 사용자 체감에
# 영향이 없고, 서버 재기동 없이도 배치 반영을 다음 시간 내로 픽업한다.
_REGIONS_CACHE_TTL_SECONDS = 3600
_regions_cache: dict | None = None  # {"data": list[dict], "ts": float}


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


def _load_all_regions() -> list[dict]:
    """전체 시군구 목록 + apt_count 조회 (q 필터 없음) — TTL 캐시 대상.

    캐시가 유효하면 DB 조회 없이 즉시 반환. 만료/최초 호출 시에만 GROUP BY
    쿼리를 실행해 캐시를 갱신한다. 반환값은 이름순 정렬까지 마친 상태.
    """
    global _regions_cache
    now = time.time()
    if (
        _regions_cache is not None
        and (now - _regions_cache["ts"]) < _REGIONS_CACHE_TTL_SECONDS
    ):
        return _regions_cache["data"]

    visible_where = " AND ".join(APARTMENT_VISIBLE_CONDITIONS)
    conn = DictConnection()
    rows = conn.execute(
        f"""
        SELECT c.code, c.name, c.extra, COALESCE(ac.apt_count, 0) AS apt_count
        FROM common_code c
        LEFT JOIN (
            SELECT a.sigungu_code, COUNT(*) AS apt_count
            FROM apartments a
            LEFT JOIN apt_kapt_info k ON a.pnu = k.pnu
            WHERE {visible_where}
            GROUP BY a.sigungu_code
        ) ac ON ac.sigungu_code = c.code
        WHERE c.group_id = %s
        """,
        ["sigungu"],
    ).fetchall()
    conn.close()
    data = [
        {
            "code": r["code"],
            "name": f"{r['name']}({r['extra']})"
            if r["extra"] and r["extra"] != r["name"]
            else r["name"],
            "apt_count": r["apt_count"],
        }
        for r in rows
    ]
    data.sort(key=lambda x: x["name"])
    _regions_cache = {"data": data, "ts": now}
    return data


@router.get("/dashboard/regions")
def dashboard_regions(q: str = Query("", description="검색어")):
    """시군구 목록 검색.

    apt_count: 노출 가능한 단지 수 (/apartments 목록과 동일 기준 —
    APARTMENT_VISIBLE_CONDITIONS 공유). 강원·전북 행정코드 개편으로 신구 코드가
    공존하는 시군구(구코드는 단지 0)가 있어, 프론트(/region)가 빈 지역을
    목록에서 거를 수 있도록 함께 반환한다.

    q 필터는 TTL 캐시된 전체 목록(_load_all_regions)에 파이썬 레벨로 적용 —
    타이핑마다 재요청돼도 DB 재조회 없이 캐시 히트로 처리된다.
    """
    results = _load_all_regions()
    if q.strip():
        results = [r for r in results if q.strip() in r["name"]]
    return results


_DATA_LAG_NOTICE = (
    "실거래 신고 지연(30일 이내 신고 의무)을 피하기 위해 현재 구간은 '30~60일 전' 30일 윈도우로 집계합니다. "
    "전국 거래 데이터 수집이 진행 중이라 전년 동기 구간의 일부 지역(비수도권 등) 데이터가 아직 누락되어 있어 "
    "전년 대비 비교 수치는 부정확할 수 있습니다."
)

_DATA_LAG_NOTICE_RECENT = (
    "오늘 기준 직전 30일간 실거래 데이터입니다. 실거래 신고 의무가 30일 이내라 "
    "최근 며칠 거래는 아직 신고되지 않아 일부 누락될 수 있습니다(과소집계)."
)


def _format_period(period_start, period_end) -> str:
    """2026-02-18 ~ 2026-03-19 → '2/18~3/19' 포맷."""
    return (
        f"{period_start.month}/{period_start.day}~{period_end.month}/{period_end.day}"
    )


def _format_prev_period(period_start, period_end) -> str:
    return f"{period_start.year}.{period_start.month}/{period_start.day}~{period_end.month}/{period_end.day}"


def _summary_from_aggregate(conn, scope: str):
    """집계 테이블 기반 summary 조회. 빈 결과 시 None 반환."""
    rows = conn.execute(
        """
        SELECT window_kind, period_start, period_end,
               trade_volume, trade_median_price_m2,
               rent_volume, rent_median_deposit_m2
        FROM dashboard_window_stats
        WHERE scope = %s
    """,
        [scope],
    ).fetchall()
    if not rows:
        return None
    by_kind = {r["window_kind"]: r for r in rows}
    cur_row = by_kind.get("current")
    prev_row = by_kind.get("prev_year")
    if not cur_row:
        return None
    if not prev_row:
        # refresh 집계는 거래가 존재하는 (윈도우×시군구)만 행을 만들므로,
        # 전년동기 거래 0건인 시군구는 prev_year 행이 없다. 이를 None(집계 미존재)으로
        # 처리하면 raw fallback 으로 우회해 집계 경로가 무효화됨 — 0건으로 간주가 정답.
        prev_row = {
            "period_start": cur_row["period_start"] - timedelta(days=365),
            "period_end": cur_row["period_end"] - timedelta(days=365),
            "trade_volume": 0,
            "trade_median_price_m2": 0,
            "rent_volume": 0,
            "rent_median_deposit_m2": 0,
        }
    return {
        "current_period": _format_period(
            cur_row["period_start"], cur_row["period_end"]
        ),
        "prev_period": _format_prev_period(
            prev_row["period_start"], prev_row["period_end"]
        ),
        "trade_cur": {
            "volume": cur_row["trade_volume"],
            "median_price_m2": cur_row["trade_median_price_m2"],
        },
        "trade_prev": {
            "volume": prev_row["trade_volume"],
            "median_price_m2": prev_row["trade_median_price_m2"],
        },
        "rent_cur": {
            "volume": cur_row["rent_volume"],
            "median_deposit_m2": cur_row["rent_median_deposit_m2"],
        },
        "rent_prev": {
            "volume": prev_row["rent_volume"],
            "median_deposit_m2": prev_row["rent_median_deposit_m2"],
        },
    }


def _summary_from_raw(conn, sigungu: str, recent: bool = False):
    """집계 테이블 fallback 또는 0-30일(recent=True) 윈도우 모드 raw 쿼리.

    recent=False: 신고 지연 보정용 30~60일 전 30일 윈도우 (기본, 집계 테이블 fallback)
    recent=True : 오늘 기준 직전 30일 윈도우 (집계 테이블 미존재 — 항상 raw 경로)
    """
    from datetime import timedelta

    # date 단위로 계산해야 함 — datetime(시각 포함)을 make_date(자정) BETWEEN
    # 하한과 비교하면 시작일 하루가 통째로 빠진다 (집계 테이블과 45건 불일치 원인).
    now = datetime.now().date()
    if recent:
        cur_end = now
        cur_start = cur_end - timedelta(days=29)
    else:
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
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS volume,
                   COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {value_expr}), 0) AS median
            FROM {table}
            WHERE exclu_use_ar > 0
              AND make_date(deal_year, deal_month, deal_day) BETWEEN %s AND %s
              {sgg_filter}
        """,
            [start, end] + sgg_params,
        ).fetchone()
        return {"volume": row["volume"] or 0, "median": float(row["median"] or 0)}

    trade_cur = _agg(
        "trade_history", "deal_amount / NULLIF(exclu_use_ar, 0)", cur_start, cur_end
    )
    trade_prev = _agg(
        "trade_history", "deal_amount / NULLIF(exclu_use_ar, 0)", prev_start, prev_end
    )
    rent_cur = _agg(
        "rent_history", "deposit / NULLIF(exclu_use_ar, 0)", cur_start, cur_end
    )
    rent_prev = _agg(
        "rent_history", "deposit / NULLIF(exclu_use_ar, 0)", prev_start, prev_end
    )

    return {
        "current_period": _format_period(cur_start, cur_end),
        "prev_period": _format_prev_period(prev_start, prev_end),
        "trade_cur": {
            "volume": trade_cur["volume"],
            "median_price_m2": trade_cur["median"],
        },
        "trade_prev": {
            "volume": trade_prev["volume"],
            "median_price_m2": trade_prev["median"],
        },
        "rent_cur": {
            "volume": rent_cur["volume"],
            "median_deposit_m2": rent_cur["median"],
        },
        "rent_prev": {
            "volume": rent_prev["volume"],
            "median_deposit_m2": rent_prev["median"],
        },
    }


@router.get("/dashboard/summary")
def dashboard_summary(
    sigungu: str = Query("", description="시군구 코드 필터"),
    recent: bool = False,
):
    """매매·전월세 30일 윈도우 요약 + 갱신 정보.

    기본은 신고 지연 보정용 '30~60일 전' 윈도우 (집계 테이블 사용).
    recent=True 시 '오늘 기준 직전 30일' 윈도우 — 집계 테이블에 없으므로 raw 쿼리 강제.
    """
    conn = DictConnection()
    scope = sigungu or "ALL"
    if recent:
        stats = _summary_from_raw(conn, sigungu, recent=True)
    else:
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
        if last_updated_row and last_updated_row["last_updated"]
        else None
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
        "data_lag_notice": _DATA_LAG_NOTICE_RECENT if recent else _DATA_LAG_NOTICE,
        "last_updated": last_updated,
        "new_today": (new_today_row["cnt"] or 0) if new_today_row else 0,
        "trade": {
            "volume": stats["trade_cur"]["volume"],
            "median_price_m2": round(float(stats["trade_cur"]["median_price_m2"]), 1),
            "prev_volume": stats["trade_prev"]["volume"],
            "prev_median_price_m2": round(
                float(stats["trade_prev"]["median_price_m2"]), 1
            ),
        },
        "rent": {
            "volume": stats["rent_cur"]["volume"],
            "median_deposit_m2": round(
                float(stats["rent_cur"]["median_deposit_m2"]), 1
            ),
            "prev_volume": stats["rent_prev"]["volume"],
            "prev_median_deposit_m2": round(
                float(stats["rent_prev"]["median_deposit_m2"]), 1
            ),
        },
    }


def _trend_from_aggregate(conn, scope: str, start_ym: int):
    """dashboard_monthly_stats에서 월별 추이 조회."""
    rows = conn.execute(
        """
        SELECT deal_year, deal_month,
               trade_volume, trade_avg_price, trade_avg_price_m2,
               rent_volume, rent_avg_deposit
        FROM dashboard_monthly_stats
        WHERE scope = %s AND deal_year * 100 + deal_month >= %s
        ORDER BY deal_year, deal_month
    """,
        [scope, start_ym],
    ).fetchall()
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

    trade = conn.execute(
        f"""
        SELECT deal_year, deal_month, COUNT(*) AS trade_volume,
               COALESCE(AVG(deal_amount), 0) AS trade_avg_price,
               COALESCE(AVG(CASE WHEN exclu_use_ar > 0 THEN deal_amount / exclu_use_ar END), 0) AS trade_avg_price_m2
        FROM trade_history
        WHERE deal_year * 100 + deal_month >= %s {sgg_filter}
        GROUP BY deal_year, deal_month
    """,
        params,
    ).fetchall()

    rent = conn.execute(
        f"""
        SELECT deal_year, deal_month, COUNT(*) AS rent_volume,
               COALESCE(AVG(deposit), 0) AS rent_avg_deposit
        FROM rent_history
        WHERE deal_year * 100 + deal_month >= %s {sgg_filter}
        GROUP BY deal_year, deal_month
    """,
        params,
    ).fetchall()

    key = lambda r: (r["deal_year"], r["deal_month"])  # noqa: E731
    tmap = {key(r): r for r in trade}
    rmap = {key(r): r for r in rent}
    merged = []
    for k in sorted(set(tmap.keys()) | set(rmap.keys())):
        t = tmap.get(k, {})
        r = rmap.get(k, {})
        merged.append(
            {
                "deal_year": k[0],
                "deal_month": k[1],
                "trade_volume": t.get("trade_volume", 0),
                "trade_avg_price": t.get("trade_avg_price", 0),
                "trade_avg_price_m2": t.get("trade_avg_price_m2", 0),
                "rent_volume": r.get("rent_volume", 0),
                "rent_avg_deposit": r.get("rent_avg_deposit", 0),
            }
        )
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
        jeonse_ratio = (
            round(rent_avg / trade_avg * 100, 1)
            if trade_avg > 0 and rent_avg > 0
            else 0
        )
        result.append(
            {
                "month": f"{r['deal_year']}-{r['deal_month']:02d}",
                "trade_volume": r["trade_volume"] or 0,
                "trade_avg_price": round(trade_avg),
                "trade_avg_price_m2": round(float(r["trade_avg_price_m2"] or 0)),
                "rent_volume": r["rent_volume"] or 0,
                "rent_avg_deposit": round(rent_avg),
                "jeonse_ratio": jeonse_ratio,
            }
        )

    return result


def _ranking_from_aggregate(conn, type_: str, year: int, month: int):
    """dashboard_ranking_stats에서 현재월 Top 10 조회."""
    return conn.execute(
        """
        SELECT sgg_cd, volume, avg_value
        FROM dashboard_ranking_stats
        WHERE type = %s AND deal_year = %s AND deal_month = %s
        ORDER BY volume DESC
        LIMIT 10
    """,
        [type_, year, month],
    ).fetchall()


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
        entry = {
            "sigungu_code": sgg,
            "sigungu_name": sgg_names.get(sgg, sgg),
            "volume": r["volume"],
        }
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
    from_date: str = Query(
        "", pattern=r"^(\d{8})?$", description="시작일 YYYYMMDD (포함, 선택)"
    ),
    to_date: str = Query(
        "", pattern=r"^(\d{8})?$", description="종료일 YYYYMMDD (포함, 선택)"
    ),
):
    """최근 거래 내역 목록.

    선택 필터:
    - sigungu: 시군구 코드 5자리
    - from_date / to_date: 거래일 기준 날짜 범위 (포함). 둘 중 하나만 지정 가능.
      범위 366일 초과 시 400.
    """
    from_d = datetime.strptime(from_date, "%Y%m%d").date() if from_date else None
    to_d = datetime.strptime(to_date, "%Y%m%d").date() if to_date else None
    if from_d and to_d:
        if from_d > to_d:
            raise HTTPException(status_code=400, detail="from_date must be <= to_date")
        if (to_d - from_d).days > 366:
            raise HTTPException(
                status_code=400, detail="date range must be within 366 days"
            )

    where_parts: list[str] = []
    params: list = []
    if sigungu:
        where_parts.append("t.sgg_cd = %s")
        params.append(sigungu)
    if from_d is not None:
        where_parts.append("make_date(t.deal_year, t.deal_month, t.deal_day) >= %s")
        params.append(from_d)
    if to_d is not None:
        where_parts.append("make_date(t.deal_year, t.deal_month, t.deal_day) <= %s")
        params.append(to_d)
    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    conn = DictConnection()

    # apartments JOIN — 프론트의 "지도로 이동" 즉시 focus 를 위해 좌표(lat/lng)
    # 와 표시명(bld_nm) 을 함께 반환. 좌표가 없는 단지는 프론트에서 버튼을
    # 비활성화 처리하므로, 조용한 실패(전환만 되고 panTo 미발동) 가 방지된다.
    if type == "trade":
        rows = conn.execute(
            f"""
            SELECT t.apt_nm, t.sgg_cd, t.deal_amount, t.exclu_use_ar, t.floor,
                   t.deal_year, t.deal_month, t.deal_day, m.pnu,
                   a.lat, a.lng, a.bld_nm
            FROM trade_history t
            LEFT JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
            LEFT JOIN apartments a ON a.pnu = m.pnu
            {where_sql}
            ORDER BY t.deal_year DESC, t.deal_month DESC, t.deal_day DESC, t.deal_amount DESC
            LIMIT %s
        """,
            params + [limit],
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT t.apt_nm, t.sgg_cd, t.deposit, t.monthly_rent, t.exclu_use_ar, t.floor,
                   t.deal_year, t.deal_month, t.deal_day, m.pnu,
                   a.lat, a.lng, a.bld_nm
            FROM rent_history t
            LEFT JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
            LEFT JOIN apartments a ON a.pnu = m.pnu
            {where_sql}
            ORDER BY t.deal_year DESC, t.deal_month DESC, t.deal_day DESC, t.deposit DESC
            LIMIT %s
        """,
            params + [limit],
        ).fetchall()

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
            "date": f"{r['deal_year']}.{r['deal_month']:02d}.{r['deal_day']:02d}"
            if r.get("deal_day")
            else f"{r['deal_year']}.{r['deal_month']:02d}",
            "pnu": r.get("pnu"),
            "lat": r.get("lat"),
            "lng": r.get("lng"),
            "bld_nm": r.get("bld_nm"),
        }
        if type == "trade":
            entry["price"] = r["deal_amount"]
        else:
            entry["deposit"] = r.get("deposit")
            entry["monthly_rent"] = r.get("monthly_rent")
        result.append(entry)

    return result


def _resolve_pnu_to_apt_keys(
    conn, pnu: str
) -> tuple[list[int], str | None, str | None]:
    """pnu → 같은 group_pnu 단지의 apt_seq 목록 + 표시용 (bld_nm, sigungu_code).

    apartments.bld_nm 과 trade_history.apt_nm 의 표기 차이가 약 60% 에 달해
    PNU 기반 진입은 apt_seq 매핑을 통해 거래내역을 특정한다. group_pnu 단위로
    묶어 분리 등록된 동의 거래까지 포함.
    """
    rows = conn.execute(
        """
        WITH target AS (
            SELECT pnu FROM apartments
            WHERE group_pnu = (SELECT group_pnu FROM apartments WHERE pnu = %s)
        )
        SELECT DISTINCT m.apt_seq
        FROM trade_apt_mapping m
        WHERE m.pnu IN (SELECT pnu FROM target)
        """,
        [pnu],
    ).fetchall()
    seqs = [r["apt_seq"] for r in rows]

    label = conn.execute(
        "SELECT COALESCE(display_name, bld_nm) AS bld_nm, sigungu_code FROM apartments WHERE pnu = %s",
        [pnu],
    ).fetchone()
    bld_nm = label["bld_nm"] if label else None
    sigungu_code = label["sigungu_code"] if label else None
    return seqs, bld_nm, sigungu_code


@router.get("/dashboard/trades")
def dashboard_trades(
    pnu: str | None = Query(None, description="PNU (우선) — 정확한 단지 특정"),
    apt_nm: str | None = Query(None, description="아파트명 (pnu 미제공 시 fallback)"),
    sgg_cd: str | None = Query(
        None, description="시군구 코드 (pnu 미제공 시 fallback)"
    ),
    area: float | None = Query(None, description="기준 면적 (±5㎡ 필터)"),
):
    """특정 아파트의 매매 + 전월세 이력 조회.

    조회 키 우선순위:
      1) pnu → group_pnu 단위로 묶어 trade_apt_mapping → apt_seq 기반 정확 매칭
      2) (apt_nm, sgg_cd) → 기존 fallback (Dashboard 거래행 클릭 흐름)

    apartments.bld_nm 과 trade_history.apt_nm 표기가 다른 케이스가 약 60% 에
    달해, PNU 기반 진입은 반드시 1) 경로를 사용해야 한다.
    """
    if not pnu and not (apt_nm and sgg_cd):
        raise HTTPException(
            status_code=400,
            detail="pnu 또는 (apt_nm + sgg_cd) 중 하나는 필수입니다.",
        )

    conn = DictConnection()
    try:
        # 1) PNU 경로 — apt_seq 기반 정확 매칭 (group_pnu 단위)
        if pnu:
            seqs, bld_nm, sigungu_code = _resolve_pnu_to_apt_keys(conn, pnu)
            if not seqs:
                # 단지는 있으나 거래 매핑이 없는 케이스 (신축·미거래 단지 등)
                return {
                    "apt_nm": bld_nm or "",
                    "sigungu": _get_sgg_names(conn).get(
                        sigungu_code, sigungu_code or ""
                    ),
                    "trades": [],
                    "rents": [],
                }

            seq_ph = ",".join(["%s"] * len(seqs))
            area_filter = ""
            extra_params: list = []
            if area is not None:
                area_filter = "AND exclu_use_ar BETWEEN %s AND %s"
                extra_params = [area - 5, area + 5]

            trades = conn.execute(
                f"""
                SELECT DISTINCT ON (id)
                       id, deal_amount, exclu_use_ar, floor, deal_year, deal_month, deal_day
                FROM trade_history
                WHERE apt_seq IN ({seq_ph}) {area_filter}
                ORDER BY id, deal_year DESC, deal_month DESC, deal_day DESC
                """,
                seqs + extra_params,
            ).fetchall()
            rents = conn.execute(
                f"""
                SELECT DISTINCT ON (id)
                       id, deposit, monthly_rent, exclu_use_ar, floor, deal_year, deal_month, deal_day
                FROM rent_history
                WHERE apt_seq IN ({seq_ph}) {area_filter}
                ORDER BY id, deal_year DESC, deal_month DESC, deal_day DESC
                """,
                seqs + extra_params,
            ).fetchall()
            # DISTINCT ON (id) 가 id 순 정렬을 강제하므로 표시용으로 다시 날짜 정렬.
            trades.sort(
                key=lambda r: (r["deal_year"], r["deal_month"], r["deal_day"]),
                reverse=True,
            )
            rents.sort(
                key=lambda r: (r["deal_year"], r["deal_month"], r["deal_day"]),
                reverse=True,
            )
            display_apt_nm = bld_nm or ""
            display_sgg_cd = sigungu_code or ""

        # 2) (apt_nm, sgg_cd) fallback — Dashboard 거래행 클릭 흐름 호환
        else:
            area_filter = ""
            params: list = [apt_nm, sgg_cd]
            if area is not None:
                area_filter = "AND exclu_use_ar BETWEEN %s AND %s"
                params.extend([area - 5, area + 5])

            trades = conn.execute(
                f"""
                SELECT deal_amount, exclu_use_ar, floor, deal_year, deal_month, deal_day
                FROM trade_history
                WHERE apt_nm = %s AND sgg_cd = %s {area_filter}
                ORDER BY deal_year DESC, deal_month DESC, deal_day DESC
                """,
                params,
            ).fetchall()
            rents = conn.execute(
                f"""
                SELECT deposit, monthly_rent, exclu_use_ar, floor, deal_year, deal_month, deal_day
                FROM rent_history
                WHERE apt_nm = %s AND sgg_cd = %s {area_filter}
                ORDER BY deal_year DESC, deal_month DESC, deal_day DESC
                """,
                params,
            ).fetchall()
            display_apt_nm = apt_nm or ""
            display_sgg_cd = sgg_cd or ""

        sgg_names = _get_sgg_names(conn)
    finally:
        conn.close()

    return {
        "apt_nm": display_apt_nm,
        "sigungu": sgg_names.get(display_sgg_cd, display_sgg_cd),
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
