"""오르는 단지 조회 — 배치(batch/trade/refresh_band_trend.py)가 채운 사전 집계 테이블만 읽는다.

테이블: apt_band_trend(단지×면적대 스냅샷), region_band_trend(시군구×면적대 스냅샷),
apt_band_monthly_price(상세 60개월 시계열), apt_band_trend_excluded_key(혼입 제외 키).
상세의 최근 실거래만 trade_history 를 직접 읽고, 배치와 같은 혼입 제외 규칙을 적용한다.

web/backend 는 batch 를 import 할 수 없으므로(배포 제약) 배치와 공유하는 규칙은
아래 상수에 복제하고 출처를 주석으로 남긴다 — 한쪽을 바꾸면 다른 쪽도 함께 바꾼다.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

from services.rising_signals import get_signals

logger = logging.getLogger(__name__)

AREA_BAND_GROUP = "rising_area_band"
SIGUNGU_GROUP = "sigungu"
SCOPE_SIDO_GROUP = (
    "rising_scope_sido"  # batch.trade.band_trend_source.SCOPE_SIDO_GROUP 과 같은 값
)
# 주의 표시 코드 → 배지 문구(name)·툴팁 설명(extra). 판정은 배치(band_trend_calc.caution_codes)가 하고
# API 는 코드를 표시명으로 바꾸기만 한다. batch.trade.band_trend_source.CAUTION_GROUP 과 같은 값.
CAUTION_GROUP = "rising_caution"

PAGE_SIZE = 20
MANWON_PER_EOK = 10_000  # 예산 파라미터(억) → 집계 금액(만원)
MONTHLY_SERIES_MONTHS = 60  # 상세 차트 기간(기준월 포함 5년)
RECENT_WINDOW_MONTHS = (
    3  # 최근 실거래 창 = 기준월로 끝나는 3개월 (median_price_3m 과 같은 창)
)

# 국토부 원문 직거래 표기. batch.trade.band_trend_calc.EXCLUDED_DEALING_GBN 과 같은 값.
DIRECT_DEAL_GBN = "직거래"

# 키 단위 혼입 제외 사유. 건축년도 불일치(build_year_mismatch)는 키 전체가 아니라
# 거래 단위 규칙이므로 아래 허용 오차로 직접 판정한다(배치와 같은 방식).
MAPPING_VIOLATION_REASON = "mapping_violation"

# 거래 신고 건축년도와 매핑 단지 준공연도의 허용 오차(년).
# batch.trade.name_matching._BUILD_YEAR_TOLERANCE 를 복제한 값 — 반드시 함께 바꾼다.
BUILD_YEAR_TOLERANCE_YEARS = 3

# 단지 등급 순위의 기본 창. 12개월 창은 순위 없이 등급만 있는 "참고" 행이라 뒤로 보낸다.
PRIMARY_GRADE_WINDOW_MONTHS = 6

# 정렬 키 → ORDER BY 조각. 사용자 입력은 키 선택에만 쓰이고 SQL 에 결합되지 않는다.
# 값 칼럼 NULL 은 항상 뒤. 마지막 t.pnu 는 페이지 경계가 흔들리지 않게 하는 결정적 동순위 처리.
SORT_ORDER_SQL: dict[str, str] = {
    "change_6m": "t.change_6m_pct DESC NULLS LAST",
    "change_12m": "t.change_12m_pct DESC NULLS LAST",
    "relative_6m": "t.relative_change_6m_pct DESC NULLS LAST",
    # 지역 가격대 = 시군구 3개월 중위가 높은 지역 먼저, 지역 안에서는 단지 가격 높은 순
    "region_price": "r.median_price_3m DESC NULLS LAST, t.median_price_3m DESC NULLS LAST",
    "complex_rank": (
        f"CASE WHEN t.grade_window_months = {PRIMARY_GRADE_WINDOW_MONTHS} THEN 0 ELSE 1 END, "
        "t.complex_rank::DOUBLE PRECISION / NULLIF(t.complex_rank_total, 0) ASC NULLS LAST, "
        "t.median_price_3m DESC NULLS LAST"
    ),
    "price_asc": "t.median_price_3m ASC NULLS LAST",
    "budget_near": "t.median_price_3m DESC NULLS LAST",
}
DEFAULT_SORT = "change_6m"

_ADDRESS_SQL = "COALESCE(a.new_plat_plc, a.plat_plc)"  # 단지 상세 기본정보와 같은 주소

_ITEM_COLUMNS_SQL = f"""
    t.pnu, a.display_name AS name, {_ADDRESS_SQL} AS address, t.sigungu_code,
    t.median_price_3m, t.trade_count_3m, t.change_6m_pct, t.change_12m_pct,
    t.matched_type_count_6m, t.matched_type_count_12m, t.relative_change_6m_pct,
    t.complex_grade, t.complex_rank, t.complex_rank_total, t.grade_window_months,
    t.avg_floor_3m, t.avg_floor_past_6m, t.caution_codes,
    r.region_grade
"""

_ITEM_FROM_SQL = """
    FROM apt_band_trend t
    JOIN apartments a ON a.pnu = t.pnu
    LEFT JOIN region_band_trend r
        ON r.sigungu_code = t.sigungu_code AND r.area_band = t.area_band
"""


# region_band_trend 응답 칼럼 — 메타 지역 목록과 단지 요약이 같은 모양을 쓴다(_to_region).
_REGION_COLUMNS_SQL = """
    sigungu_code, median_price_3m, trade_count_3m, change_6m_pct, change_12m_pct,
    region_grade, region_rank, region_rank_total
"""


class AreaBand(NamedTuple):
    code: str
    name: str
    min_area: float
    max_area: float | None  # None = 상한 없음


class ListFilters(NamedTuple):
    area_band: str
    budget_min_eok: float | None
    budget_max_eok: float | None
    sido: str | None
    sgg_codes: list[str]
    query: str


def _parse_band_extra(extra: str) -> tuple[float, float | None]:
    """rising_area_band.extra "하한,상한" 파싱 — 빈 상한("175,")은 무제한.

    batch.trade.band_trend_calc.parse_band_extra 와 같은 규칙(배포 제약으로 복제).
    """
    lower_text, _, upper_text = extra.partition(",")
    upper_text = upper_text.strip()
    return float(lower_text), float(upper_text) if upper_text else None


def load_area_bands(conn) -> dict[str, AreaBand]:
    """면적대 코드 → 정의 (sort_order 순서 유지)."""
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s ORDER BY sort_order",
        [AREA_BAND_GROUP],
    ).fetchall()
    bands: dict[str, AreaBand] = {}
    for row in rows:
        min_area, max_area = _parse_band_extra(row["extra"])
        bands[row["code"]] = AreaBand(row["code"], row["name"], min_area, max_area)
    return bands


def load_scope_sidos(conn) -> list[dict]:
    """계산 범위 시도 목록 (common_code rising_scope_sido, sort_order 순) — 지역 패널 탭 라벨."""
    rows = conn.execute(
        "SELECT code, name FROM common_code WHERE group_id = %s ORDER BY sort_order",
        [SCOPE_SIDO_GROUP],
    ).fetchall()
    return [{"code": row["code"], "name": row["name"]} for row in rows]


def load_caution_labels(conn) -> dict[str, dict]:
    """주의 코드 → {code, name, description} (common_code rising_caution, sort_order 순)."""
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s ORDER BY sort_order",
        [CAUTION_GROUP],
    ).fetchall()
    return {
        row["code"]: {
            "code": row["code"],
            "name": row["name"],
            "description": row["extra"],
        }
        for row in rows
    }


def _to_item(row: dict, caution_labels: dict[str, dict]) -> dict:
    """apt_band_trend 행(_ITEM_COLUMNS_SQL) → 응답 item. 주의 코드를 표시명 목록(cautions)으로 바꾼다.

    배치가 적재 전에 코드-표시명 짝을 검증하므로(band_trend_source.load_codes) 표시명 없는 코드는
    정상 경로에선 없다. 생기면 배치·common_code 불일치이므로 경고 로그를 남기고 그 코드만 뺀다.
    """
    item = dict(row)
    codes = item.pop("caution_codes") or []
    unknown = [code for code in codes if code not in caution_labels]
    if unknown:
        logger.warning(
            "rising caution 표시명 없음 %s (pnu=%s) — common_code %s 확인",
            unknown,
            item.get("pnu"),
            CAUTION_GROUP,
        )
    item["cautions"] = [
        caution_labels[code] for code in codes if code in caution_labels
    ]
    return item


def _sigungu_names(conn) -> dict[str, str]:
    """시군구 코드 → 표시명. routers/dashboard.py 의 _get_sgg_names 와 같은 표기
    (extra 가 이름과 다르면 "이름(extra)", 예: 장안구(수원))."""
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s",
        [SIGUNGU_GROUP],
    ).fetchall()
    return {
        r["code"]: f"{r['name']}({r['extra']})"
        if r["extra"] and r["extra"] != r["name"]
        else r["name"]
        for r in rows
    }


def _latest_base_ym(conn) -> int | None:
    row = conn.execute("SELECT MAX(base_ym) AS base_ym FROM apt_band_trend").fetchone()
    return row["base_ym"]


def _to_region(row: dict, sgg_names: dict[str, str]) -> dict:
    """region_band_trend 행 → 지역 응답 모양(시군구 표시명·시도 코드 부여). 메타·단지 요약 공용."""
    region = dict(row)
    region["sigungu_name"] = sgg_names.get(
        region["sigungu_code"], region["sigungu_code"]
    )
    region["sido_code"] = region["sigungu_code"][:2]
    return region


# ── 메타 ─────────────────────────────────────────────────────────────


def get_meta(conn) -> dict:
    """기준월 + 면적대 목록 + 면적대별 지역 목록(지역 가격 순위 순)."""
    bands = load_area_bands(conn)
    sgg_names = _sigungu_names(conn)
    rows = conn.execute(
        f"""
        SELECT area_band, {_REGION_COLUMNS_SQL}
        FROM region_band_trend
        ORDER BY area_band, region_rank ASC NULLS LAST, sigungu_code
        """
    ).fetchall()
    regions: dict[str, list[dict]] = {code: [] for code in bands}
    for row in rows:
        region = dict(row)
        band_code = region.pop("area_band")
        regions.setdefault(band_code, []).append(_to_region(region, sgg_names))
    return {
        "base_ym": _latest_base_ym(conn),
        "bands": [band._asdict() for band in bands.values()],
        "sidos": load_scope_sidos(conn),
        "regions": regions,
    }


# ── 목록 ─────────────────────────────────────────────────────────────


def _escape_like(text: str) -> str:
    """ILIKE 패턴 메타문자를 리터럴로 (ESCAPE '\\' 와 짝)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _list_where(filters: ListFilters, include_selection: bool) -> tuple[str, dict]:
    """목록 WHERE 절과 파라미터. include_selection=False 면 시군구 선택·검색어를 뺀다
    (지역별 단지 수는 면적대·예산·시도 조건으로만 센다)."""
    clauses = ["t.area_band = %(area_band)s"]
    params: dict = {"area_band": filters.area_band}
    if filters.budget_min_eok is not None:
        clauses.append("t.median_price_3m >= %(budget_min)s")
        params["budget_min"] = round(filters.budget_min_eok * MANWON_PER_EOK)
    if filters.budget_max_eok is not None:
        clauses.append("t.median_price_3m <= %(budget_max)s")
        params["budget_max"] = round(filters.budget_max_eok * MANWON_PER_EOK)
    if filters.sido:
        clauses.append("LEFT(t.sigungu_code, 2) = %(sido)s")
        params["sido"] = filters.sido
    if include_selection:
        if filters.sgg_codes:
            clauses.append("t.sigungu_code = ANY(%(sgg_codes)s)")
            params["sgg_codes"] = filters.sgg_codes
        query = filters.query.strip()
        if query:
            clauses.append(
                "(a.display_name ILIKE %(pattern)s ESCAPE '\\'"
                " OR a.new_plat_plc ILIKE %(pattern)s ESCAPE '\\'"
                " OR a.plat_plc ILIKE %(pattern)s ESCAPE '\\')"
            )
            params["pattern"] = f"%{_escape_like(query)}%"
    return " AND ".join(clauses), params


def list_complexes(conn, filters: ListFilters, sort: str, page: int) -> dict:
    """필터·정렬·페이지에 맞는 단지 목록 + 지역별 단지 수."""
    order_sql = SORT_ORDER_SQL[sort]
    where_sql, params = _list_where(filters, include_selection=True)

    totals = conn.execute(
        f"""
        SELECT COUNT(*) AS total_count, COUNT(DISTINCT t.sigungu_code) AS region_count
        {_ITEM_FROM_SQL}
        WHERE {where_sql}
        """,
        params,
    ).fetchone()

    items = conn.execute(
        f"""
        SELECT {_ITEM_COLUMNS_SQL}
        {_ITEM_FROM_SQL}
        WHERE {where_sql}
        ORDER BY {order_sql}, t.pnu
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {**params, "limit": PAGE_SIZE, "offset": (page - 1) * PAGE_SIZE},
    ).fetchall()

    caution_labels = load_caution_labels(conn)
    region_where_sql, region_params = _list_where(filters, include_selection=False)
    region_rows = conn.execute(
        f"""
        SELECT t.sigungu_code, COUNT(*) AS complex_count
        FROM apt_band_trend t
        WHERE {region_where_sql}
        GROUP BY t.sigungu_code
        """,
        region_params,
    ).fetchall()

    return {
        "base_ym": _latest_base_ym(conn),
        "total_count": totals["total_count"],
        "region_count": totals["region_count"],
        "page": page,
        "page_size": PAGE_SIZE,
        "items": [_to_item(row, caution_labels) for row in items],
        "region_counts": {
            row["sigungu_code"]: row["complex_count"] for row in region_rows
        },
    }


# ── 상세 ─────────────────────────────────────────────────────────────


def _shift_ym(ym: int, months: int) -> int:
    """YYYYMM 에 months 개월을 더한다(음수 가능)."""
    index = (ym // 100) * 12 + (ym % 100 - 1) + months
    return (index // 12) * 100 + index % 12 + 1


def _monthly_series(conn, pnu: str, area_band: str, base_ym: int) -> list[dict]:
    """기준월로 끝나는 60개월. 거래 없는 달은 median_price null, trade_count 0."""
    start_ym = _shift_ym(base_ym, -(MONTHLY_SERIES_MONTHS - 1))
    rows = conn.execute(
        """
        SELECT deal_ym, median_price, trade_count FROM apt_band_monthly_price
        WHERE pnu = %s AND area_band = %s AND deal_ym BETWEEN %s AND %s
        """,
        [pnu, area_band, start_ym, base_ym],
    ).fetchall()
    by_ym = {row["deal_ym"]: row for row in rows}
    series = []
    for offset in range(MONTHLY_SERIES_MONTHS):
        ym = _shift_ym(start_ym, offset)
        row = by_ym.get(ym)
        series.append(
            {
                "ym": ym,
                "median_price": row["median_price"] if row else None,
                "trade_count": row["trade_count"] if row else 0,
            }
        )
    return series


# 거래 → 매핑 단지 → 대표 단지(group_pnu) 귀속은 batch/trade/band_trend_source.py 의
# _TRADES_SQL 과 같다. 준공연도 = 매핑 단지의 K-APT 사용승인일, 없으면 건축물대장 사용승인일.
_COMPLETION_DATE_SQL = "COALESCE(NULLIF(mk.use_date, ''), ma.use_apr_day)"

_RECENT_TRADES_SQL = f"""
SELECT
    t.deal_year || '-' || LPAD(t.deal_month::TEXT, 2, '0')
        || '-' || LPAD(t.deal_day::TEXT, 2, '0') AS deal_date,
    t.exclu_use_ar, t.floor, t.deal_amount,
    COALESCE(t.dealing_gbn = %(direct_deal_gbn)s, FALSE) AS is_direct_deal
FROM trade_history t
JOIN trade_apt_mapping m ON m.apt_seq = t.apt_seq
JOIN apartments ma ON ma.pnu = m.pnu
LEFT JOIN apt_kapt_info mk ON mk.pnu = ma.pnu
WHERE ma.group_pnu = %(pnu)s
  AND t.deal_year * 100 + t.deal_month BETWEEN %(start_ym)s AND %(end_ym)s
  AND t.deal_amount > 0
  AND t.exclu_use_ar >= %(min_area)s
  AND (%(max_area)s IS NULL OR t.exclu_use_ar < %(max_area)s)
  AND NOT EXISTS (
      SELECT 1 FROM apt_band_trend_excluded_key x
      WHERE x.apt_seq = t.apt_seq AND x.reason = %(mapping_violation)s
  )
  AND NOT (
      t.build_year IS NOT NULL
      AND LEFT({_COMPLETION_DATE_SQL}, 4) ~ '^[0-9]{{4}}$'
      AND ABS(t.build_year - LEFT({_COMPLETION_DATE_SQL}, 4)::INTEGER)
          > %(build_year_tolerance)s
  )
ORDER BY t.deal_year DESC, t.deal_month DESC, t.deal_day DESC NULLS LAST, t.id DESC
"""


def _recent_trades(conn, pnu: str, band: AreaBand, base_ym: int) -> list[dict]:
    """기준월로 끝나는 3개월·면적대 범위 실거래. 혼입 제외는 배치와 같고 직거래는 표시만 한다."""
    rows = conn.execute(
        _RECENT_TRADES_SQL,
        {
            "pnu": pnu,
            "start_ym": _shift_ym(base_ym, -(RECENT_WINDOW_MONTHS - 1)),
            "end_ym": base_ym,
            "min_area": band.min_area,
            "max_area": band.max_area,
            "direct_deal_gbn": DIRECT_DEAL_GBN,
            "mapping_violation": MAPPING_VIOLATION_REASON,
            "build_year_tolerance": BUILD_YEAR_TOLERANCE_YEARS,
        },
    ).fetchall()
    return [dict(row) for row in rows]


def get_detail(conn, pnu: str, band: AreaBand) -> dict | None:
    """단지×면적대 상세. 해당 면적대 집계 행이 없으면 None."""
    item = conn.execute(
        f"""
        SELECT {_ITEM_COLUMNS_SQL}, t.base_ym
        {_ITEM_FROM_SQL}
        WHERE t.pnu = %s AND t.area_band = %s
        """,
        [pnu, band.code],
    ).fetchone()
    if item is None:
        return None
    item = _to_item(item, load_caution_labels(conn))
    base_ym = item.pop("base_ym")
    sigungu_name = _sigungu_names(conn).get(item["sigungu_code"], item["sigungu_code"])
    return {
        "pnu": item["pnu"],
        "name": item["name"],
        "address": item["address"],
        "item": item,
        # 상승과 함께 보이는 정보 — 상세(가격흐름 패널·홈 가격흐름 탭)에만 싣는다(services/rising_signals.py)
        "signals": get_signals(conn, item, sigungu_name, base_ym),
        "monthly": _monthly_series(conn, pnu, band.code, base_ym),
        "recent_trades": _recent_trades(conn, pnu, band, base_ym),
    }


# ── 지도용 추세 요약 ───────────────────────────────────────────────────

# 한 번에 받는 PNU 상한. 클러스터러 minLevel(5) 이상 줌은 마커가 묶여 개별 화살표가 안 보이므로
# 그 줌의 대량 요청은 받지 않는다. 프론트 hooks/useMapTrends.ts 의 같은 이름 상수와 함께 바꾼다.
MAP_TREND_MAX_PNUS = 2000
# |6개월 변화| 가 이 값 이하면 보합(화살표 없음). 설계 2026-11-26 사용자 확정.
FLAT_THRESHOLD_PCT = 2.0
# 3개월 거래가 이 건수 이하면 지도 화살표를 그리지 않는다(지도 전용 규칙, 노출 하한 2건과 같다).
# frontend-next app/_home/Map/InfoWindowTrend.tsx 의 MAP_THIN_SAMPLE_MAX_TRADES 와 같은 값 — 함께 바꾼다.
# 목록·상세의 "표본 적음" 배지는 배치 주의 코드(low_sample, 3건 이하)로 따로 판정한다.
THIN_SAMPLE_MAX_TRADES = 2


def trend_direction(change_6m_pct: float | None, trade_count_3m: int | None) -> str:
    """마커 방향: up / down / flat(보합) / none(비교 부족·표본 적음)."""
    if change_6m_pct is None or trade_count_3m is None:
        return "none"
    if trade_count_3m <= THIN_SAMPLE_MAX_TRADES:
        return "none"
    if abs(change_6m_pct) <= FLAT_THRESHOLD_PCT:
        return "flat"
    return "up" if change_6m_pct > 0 else "down"


def bands_for_area_filter(
    bands: dict[str, AreaBand], min_area: float | None, max_area: float | None
) -> list[str]:
    """면적 필터와 겹치는 면적대 코드(면적대 [min, max) 기준, bands 순서 유지)."""
    return [
        code
        for code, band in bands.items()
        if (max_area is None or band.min_area <= max_area)
        and (min_area is None or band.max_area is None or band.max_area > min_area)
    ]


# 요청 PNU → 대표 단지(group_pnu) 집계 행 중 선택 면적대의 거래 최다 1행. 응답 키는 요청 PNU.
# 동률이면 면적대 정의 순서(common_code sort_order — 작은 면적대 먼저). area_band 는 TEXT 라
# 문자열 정렬하면 "100" 이 "59" 보다 앞선다.
_MAP_TRENDS_SQL = """
    SELECT DISTINCT ON (req.pnu)
           req.pnu AS request_pnu, t.area_band, t.median_price_3m, t.trade_count_3m,
           t.change_6m_pct, t.change_12m_pct, t.matched_type_count_6m, t.matched_type_count_12m,
           t.complex_grade, t.complex_rank, t.complex_rank_total, t.grade_window_months,
           r.region_grade
    FROM unnest(%(pnus)s::text[]) AS req(pnu)
    JOIN apartments a ON a.pnu = req.pnu
    JOIN apt_band_trend t
        ON t.pnu = COALESCE(a.group_pnu, a.pnu) AND t.area_band = ANY(%(bands)s)
    JOIN common_code bc ON bc.group_id = %(band_group)s AND bc.code = t.area_band
    LEFT JOIN region_band_trend r
        ON r.sigungu_code = t.sigungu_code AND r.area_band = t.area_band
    ORDER BY req.pnu, t.trade_count_3m DESC NULLS LAST, bc.sort_order
"""


def get_map_trends(
    conn, pnus: list[str], min_area: float | None, max_area: float | None
) -> dict:
    """지도 단지들의 추세 요약. 집계 행이 없는 PNU 는 결과에 없다."""
    base_ym = _latest_base_ym(conn)
    bands = load_area_bands(conn)
    selected = bands_for_area_filter(bands, min_area, max_area)
    if not pnus or not selected:
        return {"base_ym": base_ym, "items": {}}
    rows = conn.execute(
        _MAP_TRENDS_SQL,
        {
            "pnus": list(dict.fromkeys(pnus)),
            "bands": selected,
            "band_group": AREA_BAND_GROUP,
        },
    ).fetchall()
    items = {}
    for row in rows:
        item = {k: v for k, v in row.items() if k != "request_pnu"}
        item["area_band_name"] = bands[row["area_band"]].name
        item["direction"] = trend_direction(row["change_6m_pct"], row["trade_count_3m"])
        items[row["request_pnu"]] = item
    return {"base_ym": base_ym, "items": items}


# ── 가격흐름: 상세 팝업 탭용 단지 요약 ─────────────────────────────────


def _representative(conn, pnu: str) -> dict | None:
    """요청 PNU 의 대표 단지(group_pnu) 이름·주소. apartments 에 없으면 None."""
    return conn.execute(
        f"""
        SELECT a.pnu, a.display_name AS name, {_ADDRESS_SQL} AS address
        FROM apartments req
        JOIN apartments a ON a.pnu = COALESCE(req.group_pnu, req.pnu)
        WHERE req.pnu = %s
        """,
        [pnu],
    ).fetchone()


def _regions_by_band(conn, sigungu_code: str, band_codes: list[str]) -> dict[str, dict]:
    """한 시군구의 면적대별 지역 집계 → {면적대: 지역 응답}."""
    rows = conn.execute(
        f"""
        SELECT area_band, {_REGION_COLUMNS_SQL}
        FROM region_band_trend
        WHERE sigungu_code = %s AND area_band = ANY(%s)
        """,
        [sigungu_code, band_codes],
    ).fetchall()
    sgg_names = _sigungu_names(conn)
    regions = {}
    for row in rows:
        region = dict(row)
        regions[region.pop("area_band")] = _to_region(region, sgg_names)
    return regions


def get_complex_summary(
    conn, pnu: str, min_area: float | None = None, max_area: float | None = None
) -> dict | None:
    """단지의 전 면적대 요약(대표 단지 기준). 요청 PNU 가 apartments 에 없으면 None.

    첫 면적대(default_band)는 지도 추세(get_map_trends)에 지도와 같은 면적 필터를 넣어 고른다 —
    지도 배지와 상세 탭 첫 화면이 같은 면적대·같은 숫자를 보이게 하기 위함.
    필터와 겹치는 면적대가 없으면 지도에도 배지가 없으므로, 필터 없는 기준(대표 면적대)으로 연다.
    """
    rep = _representative(conn, pnu)
    if rep is None:
        return None
    bands = load_area_bands(conn)
    # 면적대 정의(common_code)와 조인 — 정의에 없는 집계 행(정의 변경 후 배치 재실행 전)은
    # 지도 추세(_MAP_TRENDS_SQL)와 같이 제외하고, 정렬도 정의 순서(sort_order)를 따른다.
    rows = conn.execute(
        f"""
        SELECT {_ITEM_COLUMNS_SQL}, t.area_band
        {_ITEM_FROM_SQL}
        JOIN common_code bc ON bc.group_id = %s AND bc.code = t.area_band
        WHERE t.pnu = %s
        ORDER BY bc.sort_order
        """,
        [AREA_BAND_GROUP, rep["pnu"]],
    ).fetchall()
    caution_labels = load_caution_labels(conn)
    rows = [_to_item(r, caution_labels) for r in rows]
    regions = (
        _regions_by_band(conn, rows[0]["sigungu_code"], [r["area_band"] for r in rows])
        if rows
        else {}
    )
    band_items = []
    for item in rows:
        code = item.pop("area_band")
        band_items.append(
            {
                "area_band": code,
                "area_band_name": bands[code].name,
                "item": item,
                "region": regions.get(code),
            }
        )
    map_item = get_map_trends(conn, [pnu], min_area, max_area)["items"].get(pnu)
    if map_item is None and (min_area is not None or max_area is not None):
        map_item = get_map_trends(conn, [pnu], None, None)["items"].get(pnu)
    return {
        "base_ym": _latest_base_ym(conn),
        "pnu": rep["pnu"],
        "name": rep["name"],
        "address": rep["address"],
        "default_band": map_item["area_band"] if map_item else None,
        "bands": band_items,
    }
