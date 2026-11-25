"""면적대 추세 집계의 입력 조회 — 코드값·범위 거래·매핑 위반 키 (읽기 전용).

refresh_band_trend 가 이 모듈로 입력을 읽고, 계산·적재는 그쪽에서 한다.
여기서는 아무것도 쓰지 않는다.
"""

from __future__ import annotations

from typing import NamedTuple

from batch.db import query_all
from batch.trade.audit_mappings import find_violations
from batch.trade.band_trend_aggregate import MemberApt, SourceTrade, attach_trades
from batch.trade.band_trend_calc import EXCLUDED_DEALING_GBN, BandDef, parse_band_extra

# "목록에 노출 가능한 단지" 조건 — web/backend/routers/apartments.py 의
# APARTMENT_VISIBLE_CONDITIONS 와 같은 5개 조건이다. batch 는 web/backend 를 import
# 하지 않으므로 복제했다. 한쪽을 바꾸면 반드시 다른 쪽도 함께 바꾼다(오르는 단지 목록과
# 단지 목록·지역 허브의 노출 기준이 갈리면 안 된다).
# 전제 alias: FROM apartments a LEFT JOIN apt_kapt_info k ON a.pnu = k.pnu
# 파라미터와 함께 실행되므로 퍼센트 기호는 두 번 쓴다(psycopg2 이스케이프).
VISIBLE_APARTMENT_CONDITIONS: list[str] = [
    "a.pnu NOT LIKE 'TRADE_%%'",
    "a.lat IS NOT NULL",
    "COALESCE(k.ho_cnt, a.total_hhld_cnt) > 0",
    "COALESCE(NULLIF(k.use_date, ''), a.use_apr_day) IS NOT NULL",
    "COALESCE(NULLIF(k.use_date, ''), a.use_apr_day) != ''",
]

AREA_BAND_GROUP = "rising_area_band"
REGION_GRADE_GROUP = "rising_region_grade"
COMPLEX_GRADE_GROUP = "rising_complex_grade"
SCOPE_SIDO_GROUP = "rising_scope_sido"

# 서버 측 커서 한 번에 받는 행 수 (메모리와 왕복 횟수의 절충)
_FETCH_BATCH_ROWS = 50_000


class BandCodes(NamedTuple):
    bands: list[BandDef]
    region_labels: list[str]
    complex_labels: list[str]
    scope_sido: list[str]


def load_codes(conn) -> BandCodes:
    rows = query_all(
        conn,
        """
        SELECT group_id, code, extra FROM common_code
        WHERE group_id = ANY(%s)
        ORDER BY group_id, sort_order
        """,
        [[AREA_BAND_GROUP, REGION_GRADE_GROUP, COMPLEX_GRADE_GROUP, SCOPE_SIDO_GROUP]],
    )
    by_group: dict[str, list[dict]] = {}
    for row in rows:
        by_group.setdefault(row["group_id"], []).append(row)
    missing = [
        g
        for g in (
            AREA_BAND_GROUP,
            REGION_GRADE_GROUP,
            COMPLEX_GRADE_GROUP,
            SCOPE_SIDO_GROUP,
        )
        if not by_group.get(g)
    ]
    if missing:
        raise RuntimeError(
            f"common_code 그룹 누락: {missing} — create_tables() 실행 필요"
        )
    return BandCodes(
        bands=[
            parse_band_extra(r["code"], r["extra"]) for r in by_group[AREA_BAND_GROUP]
        ],
        region_labels=[r["code"] for r in by_group[REGION_GRADE_GROUP]],
        complex_labels=[r["code"] for r in by_group[COMPLEX_GRADE_GROUP]],
        scope_sido=[r["code"] for r in by_group[SCOPE_SIDO_GROUP]],
    )


# 범위 내 노출 대표 단지. 이 CTE 를 쓰는 SQL 은 %(scope_sido)s 파라미터를 받는다.
_SCOPE_APT_CTE = f"""
scope_apt AS (
    SELECT a.pnu, a.sigungu_code
    FROM apartments a
    LEFT JOIN apt_kapt_info k ON a.pnu = k.pnu
    WHERE a.group_pnu = a.pnu
      AND LEFT(a.sigungu_code, 2) = ANY(%(scope_sido)s)
      AND {" AND ".join(VISIBLE_APARTMENT_CONDITIONS)}
)"""

_COMPLETION_DATE = "COALESCE(NULLIF(mk.use_date, ''), ma.use_apr_day)"

# 범위 내 대표 단지에 속한 구성원 단지(매핑 대상 PNU)와 그 대표 단지·준공연도. 약 1.8만 행.
_MEMBERS_SQL = f"""
WITH {_SCOPE_APT_CTE}
SELECT ma.pnu AS member_pnu, s.pnu, s.sigungu_code,
       CASE WHEN LEFT({_COMPLETION_DATE}, 4) ~ '^[0-9]{{4}}$'
            THEN LEFT({_COMPLETION_DATE}, 4)::INTEGER END AS completion_year
FROM apartments ma
LEFT JOIN apt_kapt_info mk ON mk.pnu = ma.pnu
JOIN scope_apt s ON s.pnu = ma.group_pnu
"""

# 구성원 단지에 매핑된 거래 키. 약 3.4만 행.
_MAPPING_SQL = (
    "SELECT apt_seq, pnu FROM trade_apt_mapping WHERE pnu = ANY(%(member_pnus)s)"
)

# 거래는 조인 없이 trade_history 하나만 읽는다. 시도 접두는 사전 필터일 뿐이고 최종 범위는
# attach_trades 가 매핑·구성원 단지로 정한다(거래 sgg_cd 와 단지 sigungu_code 는 같은 구코드 체계).
# deal_year 범위는 계약월 식과 같은 조건이지만 인덱스·계획 추정을 돕기 위해 함께 둔다.
_RAW_TRADES_SQL = """
SELECT apt_seq, apt_nm, exclu_use_ar AS area, deal_year * 100 + deal_month AS deal_ym,
       deal_amount AS price, build_year
FROM trade_history
WHERE deal_year BETWEEN %(start_year)s AND %(end_year)s
  AND deal_year * 100 + deal_month BETWEEN %(start_ym)s AND %(end_ym)s
  AND LEFT(sgg_cd, 2) = ANY(%(scope_sido)s)
  AND dealing_gbn IS DISTINCT FROM %(excluded_dealing_gbn)s
  AND deal_amount > 0
  AND exclu_use_ar > 0
"""

_MEMBER_PNUS_SQL = f"""
WITH {_SCOPE_APT_CTE}
SELECT a.pnu FROM apartments a JOIN scope_apt s ON s.pnu = a.group_pnu
"""


def load_trades(
    conn, scope_sido: list[str], start_ym: int, end_ym: int
) -> list[SourceTrade]:
    """범위 시도·기간의 매매 거래(직거래 제외)를 대표 단지에 귀속해 읽는다.

    dealing_gbn NULL(미분류)은 유지한다 — 스펙 §5.3. 매핑 단지가 노출 대표 단지에
    속하지 않으면 버린다.

    거래·매핑·단지를 한 SQL 로 조인하면 플래너가 대상 단지 수를 1~2건으로 잘못 추정해
    단지마다 거래 인덱스를 찾는 중첩 루프를 고른다. 메모리 1GB 인 운영 DB 에서는
    trade_history 를 디스크에서 무작위로 읽게 되어 이 조회만 503초가 걸렸다(2026-11-25
    운영 배치, 로컬 5.6초). 그래서 작은 표 두 개(구성원 단지·매핑)와 거래 단일 스캔으로
    나눠 읽고 attach_trades 로 붙인다(로컬 0.8초, 결과 행 동일).
    """
    members = {
        r["member_pnu"]: MemberApt(r["pnu"], r["sigungu_code"], r["completion_year"])
        for r in query_all(conn, _MEMBERS_SQL, {"scope_sido": scope_sido})
    }
    if not members:
        return []
    mapping = {
        r["apt_seq"]: r["pnu"]
        for r in query_all(conn, _MAPPING_SQL, {"member_pnus": list(members)})
    }
    params = {
        "scope_sido": scope_sido,
        "start_year": start_ym // 100,
        "end_year": end_ym // 100,
        "start_ym": start_ym,
        "end_ym": end_ym,
        "excluded_dealing_gbn": EXCLUDED_DEALING_GBN,
    }
    # 수도권 60개월이 80만 행 수준이라 서버 측 커서로 나눠 받는다.
    with conn.cursor(name="band_trend_trades") as cur:
        cur.itersize = _FETCH_BATCH_ROWS
        cur.execute(_RAW_TRADES_SQL, params)
        return attach_trades(cur, mapping, members)


def find_mapping_violations(conn, scope_sido: list[str]) -> list[dict]:
    """범위 내 대표 단지와 그 그룹 구성원에 매핑된 키 중 물리 정합성 위반(audit_mappings)."""
    pnus = [
        r["pnu"] for r in query_all(conn, _MEMBER_PNUS_SQL, {"scope_sido": scope_sido})
    ]
    if not pnus:
        return []
    violations, _checked = find_violations(conn, pnus=pnus)
    return violations
