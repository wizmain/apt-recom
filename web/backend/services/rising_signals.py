"""가격흐름 상세의 "상승과 함께 보이는 정보" — 상승 단지에서 같은 시기 확인된 사실 신호.

원인을 단정하지 않는다. 2026-11-28 검증(reports/rising_signals/FINDINGS.md, 84㎡급 기준월 202609)에서
6개월 상승 상위 50곳이 전체보다 뚜렷이 많이 가진 특성만 고른다.
  - 지역 대비 변화(지역 동반 / 지역보다 더 오름): 모든 상승 단지를 두 갈래로 나눠 해석을 돕는다.
  - 준공 30년 이상: 상위 50 28% vs 전체 15% (1.9배)
  - 역 500m 이내: 상위 50 38% vs 전체 22% (1.7배)
신고가(상승의 동어반복)·전세 상승(구분력 약함)·거래 증가(오히려 낮음)는 뺐다.

판정은 이미 저장된 값(apt_band_trend·apartments·apt_facility_summary)만 쓰므로 배치가 아니라 여기서 한다.
문구는 common_code rising_signal(name = 제목, extra = 설명)에서 읽는다.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)

SIGNAL_GROUP = "rising_signal"

SIGNAL_REGION_WIDE = "region_wide"
SIGNAL_OUTPACING_REGION = "outpacing_region"
SIGNAL_REBUILD_AGE = "rebuild_age"
SIGNAL_NEAR_SUBWAY = "near_subway"

# 시군구 같은 면적대 6개월 변화가 단지 변화의 이 비율 이상이면 "지역 동반", 아니면 "지역보다 더 오름".
REGION_DRIVEN_MIN_SHARE = 0.5
# 기준월 연도 - 준공연도가 이 값 이상이면 재건축 연한 신호.
REBUILD_AGE_YEARS = 30
# 가장 가까운 지하철역 거리(m)가 이 값 이하면 역 가까움 신호.
NEAR_SUBWAY_MAX_METERS = 500

_SUBWAY_FACILITY_SUBTYPE = "subway"
# 단지 목록·배치와 같은 준공일 우선순위(K-APT 사용승인일 → 건축물대장 사용승인일).
_COMPLETION_DATE_SQL = "COALESCE(NULLIF(k.use_date, ''), a.use_apr_day)"


class ComplexFacts(NamedTuple):
    """신호 판정에 쓰는 단지 고정 사실. 없으면 None."""

    completion_year: int | None
    nearest_subway_m: float | None


class SignalMatch(NamedTuple):
    code: str
    evidence: str  # 이 단지의 근거 수치 문구


def _format_pct(value: float) -> str:
    return f"{value:+.1f}%"


def match_signals(
    change_6m_pct: float | None,
    relative_change_6m_pct: float | None,
    sigungu_name: str,
    base_ym: int,
    facts: ComplexFacts,
) -> list[SignalMatch]:
    """6개월 변화가 플러스인 단지의 신호(지역 → 연식 → 역 순). 하락·보합·비교 부족이면 빈 목록."""
    if change_6m_pct is None or change_6m_pct <= 0:
        return []
    matches: list[SignalMatch] = []

    if relative_change_6m_pct is not None:
        # 배치 정의: relative = 단지 변화 - 지역 변화
        region_change = change_6m_pct - relative_change_6m_pct
        region_text = f"{sigungu_name} 같은 면적대 {_format_pct(region_change)}"
        if region_change >= change_6m_pct * REGION_DRIVEN_MIN_SHARE:
            matches.append(SignalMatch(SIGNAL_REGION_WIDE, region_text))
        else:
            matches.append(
                SignalMatch(
                    SIGNAL_OUTPACING_REGION,
                    f"{region_text}보다 {relative_change_6m_pct:+.1f}%p",
                )
            )

    if facts.completion_year is not None:
        age = base_ym // 100 - facts.completion_year
        if age >= REBUILD_AGE_YEARS:
            matches.append(
                SignalMatch(
                    SIGNAL_REBUILD_AGE, f"{facts.completion_year}년 준공 · {age}년"
                )
            )

    if (
        facts.nearest_subway_m is not None
        and facts.nearest_subway_m <= NEAR_SUBWAY_MAX_METERS
    ):
        matches.append(
            SignalMatch(
                SIGNAL_NEAR_SUBWAY, f"가장 가까운 역 {round(facts.nearest_subway_m)}m"
            )
        )
    return matches


def load_complex_facts(conn, pnu: str) -> ComplexFacts:
    """단지 준공연도(앞 4자리가 연도일 때만)와 가장 가까운 지하철역 거리."""
    row = conn.execute(
        f"""
        SELECT {_COMPLETION_DATE_SQL} AS completion_date, f.nearest_distance_m
        FROM apartments a
        LEFT JOIN apt_kapt_info k ON k.pnu = a.pnu
        LEFT JOIN apt_facility_summary f
            ON f.pnu = a.pnu AND f.facility_subtype = %s
        WHERE a.pnu = %s
        """,
        [_SUBWAY_FACILITY_SUBTYPE, pnu],
    ).fetchone()
    if row is None:
        return ComplexFacts(None, None)
    completion = row["completion_date"] or ""
    year_text = completion[:4]
    return ComplexFacts(
        int(year_text) if year_text.isdigit() else None,
        row["nearest_distance_m"],
    )


def load_signal_labels(conn) -> dict[str, dict]:
    """신호 코드 → {code, name, description} (common_code rising_signal)."""
    rows = conn.execute(
        "SELECT code, name, extra FROM common_code WHERE group_id = %s",
        [SIGNAL_GROUP],
    ).fetchall()
    return {
        row["code"]: {
            "code": row["code"],
            "name": row["name"],
            "description": row["extra"],
        }
        for row in rows
    }


def to_signal_items(
    matches: list[SignalMatch], labels: dict[str, dict], pnu: str
) -> list[dict]:
    """판정 결과 → 응답 목록 [{code, name, description, evidence}].

    문구가 없는 코드는 create_tables() 미실행 등 설정 불일치다 — 경고를 남기고 그 신호만 뺀다.
    """
    items: list[dict] = []
    for match in matches:
        label = labels.get(match.code)
        if label is None:
            logger.warning(
                "rising signal 문구 없음 %s (pnu=%s) — common_code %s 확인",
                match.code,
                pnu,
                SIGNAL_GROUP,
            )
            continue
        items.append({**label, "evidence": match.evidence})
    return items


def get_signals(conn, item: dict, sigungu_name: str, base_ym: int) -> list[dict]:
    """가격흐름 상세 item(apt_band_trend 행)의 신호 목록."""
    if item["change_6m_pct"] is None or item["change_6m_pct"] <= 0:
        return []  # 판정 대상이 아니면 사실 조회를 하지 않는다
    matches = match_signals(
        item["change_6m_pct"],
        item["relative_change_6m_pct"],
        sigungu_name,
        base_ym,
        load_complex_facts(conn, item["pnu"]),
    )
    return to_signal_items(matches, load_signal_labels(conn), item["pnu"])
