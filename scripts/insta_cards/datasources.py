"""데이터 소스 — 운영 공개 API + 로컬 DB(batch.db) 접근을 한 곳에 모은다.

- API 실패·필수 키 누락은 DataSourceError 로 발행 중단 (재시도·fallback 없음).
- 로컬 DB 는 거래 테이블만 사용 — 증분 sync(batch.sync_from_railway)로 충분.
- 단지 단위 지표(지하철·배정초·안전·관리비)는 공개 detail API 로 취득 —
  서비스 화면과 동일 값 보장 (spec §5-4).
"""

from __future__ import annotations

import math

import requests

from scripts.insta_cards.publication import Metric

PROD_API_BASE = "https://api.apt-recom.kr"
API_TIMEOUT_SECONDS = 15
ELIGIBLE_TRADE_DAYS = 90  # "최근 실거래" 적격 기간 (계약일 기준)
STALE_TRADE_WARN_HOURS = 24

NUDGE_SCORE_REQUIRED_KEYS = {
    "pnu",
    "bld_nm",
    "score",
    "total_hhld_cnt",
    "top_contributors",
}
DETAIL_REQUIRED_KEYS = {
    "basic",
    "scores",
    "facility_summary",
    "school",
    "safety",
    "mgmt_cost",
}


class DataSourceError(RuntimeError):
    pass


def open_local_db():
    """batch.db 커넥션 — cwd 가 프로젝트 루트여야 import 가능 (실행 정책)."""
    from batch.db import get_connection

    return get_connection()


def query_all(conn, sql, params=None):
    from batch.db import query_all as batch_query_all

    return batch_query_all(conn, sql, params)


def post_nudge_score(payload: dict) -> list[dict]:
    resp = requests.post(
        f"{PROD_API_BASE}/api/nudge/score", json=payload, timeout=API_TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list):
        raise DataSourceError(f"nudge/score 응답이 목록이 아님: {type(rows)}")
    for i, row in enumerate(rows):
        missing = NUDGE_SCORE_REQUIRED_KEYS - set(row)
        if missing:
            raise DataSourceError(
                f"nudge/score 응답 [{i}] 필수 키 누락: {sorted(missing)}"
            )
    return rows


def get_region_name(sigungu_code: str) -> str:
    resp = requests.get(
        f"{PROD_API_BASE}/api/dashboard/regions", timeout=API_TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    for region in resp.json():
        if region.get("code") == sigungu_code:
            return region["name"]
    raise DataSourceError(f"dashboard/regions 에 없는 시군구 코드: {sigungu_code}")


def get_apartment_detail(pnu: str) -> dict:
    resp = requests.get(
        f"{PROD_API_BASE}/api/apartment/{pnu}", timeout=API_TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    detail = resp.json()
    missing = DETAIL_REQUIRED_KEYS - set(detail)
    if missing:
        raise DataSourceError(f"apartment/{pnu} 응답 필수 키 누락: {sorted(missing)}")
    return detail


INFO_NONE = "정보 없음"  # 결측 표기 — 값 생략이지 fallback 아님 (숨김 금지)


def extract_candidate_metrics(detail: dict, target_area: float | None) -> list[Metric]:
    """detail API 응답 → 후보 공통 지표 4개 (순서 고정)."""
    facility = detail.get("facility_summary") or {}
    subway = facility.get("subway") or {}
    subway_value = (
        f"{round(subway['nearest_distance_m']):,}m"
        if subway.get("nearest_distance_m") is not None
        else INFO_NONE
    )

    school = detail.get("school") or {}
    school_name = school.get("elementary_school_name")
    if school_name and school.get("estimated"):
        school_value = f"{school_name}(추정)"
    elif school_name:
        school_value = school_name
    else:
        school_value = INFO_NONE

    safety = detail.get("safety") or {}
    safety_value = (
        f"{safety['safety_score']:.0f}점"
        if safety.get("safety_score") is not None
        else INFO_NONE
    )

    mgmt = detail.get("mgmt_cost") or {}
    by_area = mgmt.get("by_area") or []
    mgmt_value = INFO_NONE
    if by_area:
        if target_area is not None:
            entry = min(by_area, key=lambda r: abs(r["exclusive_area"] - target_area))
        else:
            entry = max(by_area, key=lambda r: r.get("unit_count") or 0)
        monthly = entry.get("per_unit_cost")
        # per_unit_cost 0원은 미보고 데이터로 간주 → "정보 없음" 처리 (의도된 truthy 검사)
        if monthly:
            # 내장 round()는 은행가 반올림(round(24.5)=24)이라 round-half-up 을 사용
            monthly_man = math.floor(monthly / 10000 + 0.5)
            annual_man = math.floor(monthly * 12 / 10000 + 0.5)
            mgmt_value = f"{monthly_man}만원 (연 {annual_man}만원)"

    return [
        Metric("지하철", subway_value, ""),
        Metric("배정 초등학교", school_value, ""),
        Metric("안전점수", safety_value, ""),
        Metric("월 관리비", mgmt_value, ""),
    ]


def fetch_recent_trades(
    conn,
    sigungu_code: str,
    *,
    max_amount: int | None = None,
    min_area: float | None = None,
    max_area: float | None = None,
    days: int = ELIGIBLE_TRADE_DAYS,
) -> dict[str, dict]:
    """지역 내 최근 계약일 기준 대표 거래(단지당 1건, 결정적 tie-break).

    반환: pnu → {pnu, deal_amount, exclu_use_ar, deal_date, bld_nm, use_apr_day}
    """
    conditions = [
        "a.sigungu_code = %s",
        "make_date(t.deal_year, t.deal_month, t.deal_day) >= CURRENT_DATE - (%s || ' days')::interval",
    ]
    params: list = [sigungu_code, days]
    if max_amount is not None:
        conditions.append("t.deal_amount <= %s")
        params.append(max_amount)
    if min_area is not None and max_area is not None:
        conditions.append("t.exclu_use_ar BETWEEN %s AND %s")
        params.extend([min_area, max_area])

    sql = f"""
        SELECT DISTINCT ON (m.pnu)
            m.pnu,
            t.deal_amount,
            t.exclu_use_ar,
            make_date(t.deal_year, t.deal_month, t.deal_day) AS deal_date,
            COALESCE(a.display_name, a.bld_nm) AS bld_nm,
            a.use_apr_day
        FROM trade_history t
        JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        JOIN apartments a ON a.pnu = m.pnu
        WHERE {" AND ".join(conditions)}
        ORDER BY m.pnu,
                 make_date(t.deal_year, t.deal_month, t.deal_day) DESC,
                 t.deal_amount DESC
    """
    rows = query_all(conn, sql, params)
    return {r["pnu"]: dict(r) for r in rows}


def stale_trade_warning(conn) -> str | None:
    rows = query_all(
        conn,
        "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 3600.0 AS age_hours "
        "FROM trade_history",
    )
    age = rows[0]["age_hours"] if rows else None
    if age is None or age > STALE_TRADE_WARN_HOURS:
        return (
            f"경고: 로컬 trade_history 최신 적재가 {round(age) if age is not None else '?'}시간 전입니다. "
            "batch.sync_from_railway 실행을 권장합니다."
        )
    return None
