"""오르는 단지 — 면적대 추세 집계의 순수 계산 (DB·네트워크 I/O 없음).

refresh_band_trend 가 읽어 온 거래(band_trend_source)를 받아 혼입 제외를 적용하고,
band_trend_calc 의 함수로 4개 테이블에 넣을 행을 만든다. 지표 정의는
docs/superpowers/specs/2026-11-25-rising-complexes-design.md §5.3~§5.5.

혼입 제외 (스펙 §5.3, 매핑은 고치지 않는다 — 교정은 reflect_* 스크립트)
  - 키 단위: audit_mappings.find_violations 가 물리 정합성 위반으로 판정한 apt_seq 의
    거래 전부 → reason mapping_violation
  - 거래 단위: 거래 신고 건축년도와 매핑 단지 준공연도 차이가 _BUILD_YEAR_TOLERANCE 를
    넘는 거래만 → 그 apt_seq 를 reason build_year_mismatch 로 기록(감사용).
    같은 키가 두 사유에 다 걸리면 mapping_violation 이 우선한다.

이상거래 창(스펙 §5.3 작성자 판단): 지표 창마다 단지·면적대 단위로 독립 판정한다.
지역 지표는 단지 단위로 걸러진 거래를 시군구로 모아 계산한다(지역 전체 중앙값으로
다시 거르면 단지 간 정상 가격차가 이상거래로 잘린다).
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from collections.abc import Hashable, Iterable, Mapping, Sequence
from typing import NamedTuple

from batch.trade.band_trend_calc import (
    CHANGE_OFFSETS,
    HISTORY_MONTHS,
    MIN_COMPLEX_GRADE_POPULATION,
    MIN_GRADE_TRADES,
    MIN_RECENT_TRADES,
    MIN_REGION_TRADES,
    BandDef,
    band_of,
    complex_grade,
    drop_outliers,
    median,
    monthly_series,
    placement_rank,
    region_grade,
    shift_month,
    type_change,
    type_key,
    window,
)
from batch.trade.name_matching import _BUILD_YEAR_TOLERANCE

REASON_MAPPING_VIOLATION = "mapping_violation"
REASON_BUILD_YEAR_MISMATCH = "build_year_mismatch"

# 단지 등급 순위 창(스펙 §5.4): 최근 6개월 중위가 순위, 표본 미달 단지는 12개월 중위가로 대입.
GRADE_WINDOW_MONTHS = 6
GRADE_FALLBACK_WINDOW_MONTHS = 12

_OFFSET_6M, _OFFSET_12M = CHANGE_OFFSETS


class SourceTrade(NamedTuple):
    apt_seq: str
    apt_nm: str | None
    mapped_pnu: str  # trade_apt_mapping.pnu (그룹 구성원일 수 있음)
    pnu: str  # 대표 단지(group_pnu)
    sigungu_code: str
    area: float
    deal_ym: int
    price: int  # 만원
    build_year: int | None  # 거래 신고서 건축년도
    completion_year: int | None  # 매핑 단지 준공연도


class MemberApt(NamedTuple):
    """범위 내 노출 대표 단지에 속한 구성원 단지(매핑 대상 PNU) 정보."""

    pnu: str  # 대표 단지(group_pnu)
    sigungu_code: str
    completion_year: int | None  # 구성원 단지 준공연도


def attach_trades(
    raw_trades: Iterable[tuple],
    mapping: Mapping[str, str],
    members: Mapping[str, MemberApt],
) -> list[SourceTrade]:
    """거래 행에 매핑·대표 단지 정보를 붙인다. 매핑이 없거나 범위 밖 단지인 거래는 버린다.

    raw_trades: (apt_seq, apt_nm, area, deal_ym, price, build_year)
    mapping: apt_seq → 매핑 PNU, members: 매핑 PNU → 대표 단지 정보.
    DB 조인 대신 여기서 붙이는 이유는 band_trend_source.load_trades 주석 참조.
    """
    trades: list[SourceTrade] = []
    for apt_seq, apt_nm, area, deal_ym, price, build_year in raw_trades:
        mapped_pnu = mapping.get(apt_seq)
        member = members.get(mapped_pnu) if mapped_pnu is not None else None
        if member is None:
            continue
        # 키·이름 문자열은 intern 해 80만 행 규모의 메모리를 줄인다.
        trades.append(
            SourceTrade(
                sys.intern(apt_seq),
                sys.intern(apt_nm) if apt_nm else None,
                mapped_pnu,
                member.pnu,
                member.sigungu_code,
                area,
                deal_ym,
                price,
                build_year,
                member.completion_year,
            )
        )
    return trades


class BandTrade(NamedTuple):
    pnu: str
    sigungu_code: str
    band: str
    type_key: float
    deal_ym: int
    price: int


class ExclusionResult(NamedTuple):
    kept: list[BandTrade]
    excluded_keys: dict[str, tuple[str, str]]  # apt_seq -> (매핑 pnu, reason)
    excluded_trades_by_key: Counter[str]
    trades_by_band: Counter[str]
    excluded_by_band: Counter[str]


class Windows(NamedTuple):
    current: frozenset[int]
    past_6m: frozenset[int]
    past_12m: frozenset[int]
    grade: frozenset[int]
    grade_fallback: frozenset[int]


class ComplexStats(NamedTuple):
    pnu: str
    band: str
    sigungu_code: str
    current: list[BandTrade]  # 창별 이상거래 제외 후
    past_6m: list[BandTrade]
    past_12m: list[BandTrade]
    count_6m: int
    median_6m: float | None
    median_12m: float | None


class GradeCandidate(NamedTuple):
    pnu: str
    count_6m: int
    median_6m: float | None
    median_12m: float | None


class ComplexGrade(NamedTuple):
    grade: str
    rank: int | None  # 12개월 대입 등급은 순위를 비운다
    total: int | None
    window_months: int


class RegionGrade(NamedTuple):
    grade: str
    rank: int
    total: int


def build_year_mismatch(build_year: int | None, completion_year: int | None) -> bool:
    """거래 건축년도와 단지 준공연도가 허용 오차를 넘게 다른지. 한쪽이라도 없으면 판단하지 않는다."""
    if build_year is None or completion_year is None:
        return False
    return abs(build_year - completion_year) > _BUILD_YEAR_TOLERANCE


def apply_exclusions(
    trades: Iterable[SourceTrade],
    bands: Sequence[BandDef],
    violation_pnus: Mapping[str, str],
) -> ExclusionResult:
    """면적대를 붙이고 혼입 의심 거래를 뺀다. violation_pnus = {위반 apt_seq: 매핑 pnu}.

    면적대 밖(50㎡ 미만 등) 거래는 집계 대상이 아니므로 제외 통계에도 넣지 않는다.
    """
    excluded_keys = {
        seq: (pnu, REASON_MAPPING_VIOLATION) for seq, pnu in violation_pnus.items()
    }
    kept: list[BandTrade] = []
    excluded_trades_by_key: Counter[str] = Counter()
    trades_by_band: Counter[str] = Counter()
    excluded_by_band: Counter[str] = Counter()
    for t in trades:
        band = band_of(t.area, bands)
        if band is None:
            continue
        trades_by_band[band] += 1
        if t.apt_seq in violation_pnus:
            excluded = True
        elif build_year_mismatch(t.build_year, t.completion_year):
            excluded = True
            excluded_keys.setdefault(
                t.apt_seq, (t.mapped_pnu, REASON_BUILD_YEAR_MISMATCH)
            )
        else:
            excluded = False
        if excluded:
            excluded_trades_by_key[t.apt_seq] += 1
            excluded_by_band[band] += 1
        else:
            kept.append(
                BandTrade(
                    t.pnu, t.sigungu_code, band, type_key(t.area), t.deal_ym, t.price
                )
            )
    return ExclusionResult(
        kept, excluded_keys, excluded_trades_by_key, trades_by_band, excluded_by_band
    )


def excluded_ratio_by_band(exclusion: ExclusionResult) -> dict[str, float]:
    """면적대별 혼입 제외 비율(0~1). 분모는 면적대 안 거래 전체(제외 전)."""
    return {
        band: exclusion.excluded_by_band[band] / total
        for band, total in exclusion.trades_by_band.items()
        if total
    }


def make_windows(base_ym: int) -> Windows:
    return Windows(
        current=frozenset(window(base_ym)),
        past_6m=frozenset(window(shift_month(base_ym, -_OFFSET_6M))),
        past_12m=frozenset(window(shift_month(base_ym, -_OFFSET_12M))),
        grade=frozenset(window(base_ym, GRADE_WINDOW_MONTHS)),
        grade_fallback=frozenset(window(base_ym, GRADE_FALLBACK_WINDOW_MONTHS)),
    )


def trades_in_window(
    trades: Iterable[BandTrade], months: frozenset[int]
) -> list[BandTrade]:
    """창에 든 거래 중 창 중앙값 ±BAND_OUTLIER_MAX_DEVIATION 안의 것만 (창마다 독립 판정).

    판정이 가격 값만으로 정해지므로, drop_outliers 가 남긴 값 집합으로 거래를 거른다.
    """
    in_window = [t for t in trades if t.deal_ym in months]
    kept_prices = set(drop_outliers([t.price for t in in_window]))
    return [t for t in in_window if t.price in kept_prices]


def prices_by_key(trades: Iterable[BandTrade], key) -> dict[Hashable, list[int]]:
    grouped: dict[Hashable, list[int]] = defaultdict(list)
    for t in trades:
        grouped[key(t)].append(t.price)
    return grouped


def _median_or_none(trades: Sequence[BandTrade]) -> float | None:
    return median([t.price for t in trades]) if trades else None


def complex_stats(
    pnu: str, band: str, trades: Sequence[BandTrade], windows: Windows
) -> ComplexStats:
    grade_trades = trades_in_window(trades, windows.grade)
    return ComplexStats(
        pnu=pnu,
        band=band,
        sigungu_code=trades[0].sigungu_code,
        current=trades_in_window(trades, windows.current),
        past_6m=trades_in_window(trades, windows.past_6m),
        past_12m=trades_in_window(trades, windows.past_12m),
        count_6m=len(grade_trades),
        median_6m=_median_or_none(grade_trades),
        median_12m=_median_or_none(trades_in_window(trades, windows.grade_fallback)),
    )


def complex_grades(
    candidates: Sequence[GradeCandidate], labels: Sequence[str]
) -> dict[str, ComplexGrade]:
    """시군구·면적대 안의 단지 등급 (스펙 §5.4 작성자 판단 문단).

    모집단 = 6개월 거래 MIN_GRADE_TRADES 이상 단지, 6개월 중위가 내림차순 순위.
    미달 단지는 12개월 중위가를 모집단에 대입해 등급만 준다(순위 비움). 모집단보다
    싸면 placement_rank 가 total+1 이 되므로 최하위(total)로 맞춘다.
    모집단이 MIN_COMPLEX_GRADE_POPULATION 미만이면 아무 단지에도 등급을 주지 않는다.
    """
    population = [
        c
        for c in candidates
        if c.count_6m >= MIN_GRADE_TRADES and c.median_6m is not None
    ]
    population_desc = sorted((c.median_6m for c in population), reverse=True)
    total = len(population_desc)
    if total < MIN_COMPLEX_GRADE_POPULATION:
        # 등급·순위·grade_window_months 모두 NULL 로 적재된다(호출부가 grades 에 없는 단지를 비움).
        return {}
    grades: dict[str, ComplexGrade] = {}
    for c in population:
        rank = placement_rank(c.median_6m, population_desc)
        grade, _decile = complex_grade(rank, total, labels)
        grades[c.pnu] = ComplexGrade(grade, rank, total, GRADE_WINDOW_MONTHS)
    for c in candidates:
        if c.pnu in grades or c.median_12m is None:
            continue
        placed = min(placement_rank(c.median_12m, population_desc), total)
        grade, _decile = complex_grade(placed, total, labels)
        grades[c.pnu] = ComplexGrade(grade, None, None, GRADE_FALLBACK_WINDOW_MONTHS)
    return grades


def region_grades(
    levels: Mapping[str, tuple[float | None, int]], labels: Sequence[str]
) -> dict[str, RegionGrade]:
    """면적대 안 지역 등급. levels = {시군구: (3개월 중위가, 3개월 거래 수)}.

    모집단 = 거래 MIN_REGION_TRADES 이상 지역, 가격 내림차순 순위를 라벨 수만큼 균등 분할.
    """
    population = {
        sgg: price
        for sgg, (price, count) in levels.items()
        if count >= MIN_REGION_TRADES and price is not None
    }
    population_desc = sorted(population.values(), reverse=True)
    total = len(population_desc)
    grades: dict[str, RegionGrade] = {}
    for sgg, price in population.items():
        rank = placement_rank(price, population_desc)
        grades[sgg] = RegionGrade(region_grade(rank, total, labels), rank, total)
    return grades


class RegionMetrics(NamedTuple):
    median_price_3m: int
    trade_count_3m: int
    change_6m_pct: float | None
    change_12m_pct: float | None


# 적재 행 — 필드 순서는 각 테이블 칼럼 순서(refreshed_at 제외)와 같다.
class MonthlyRow(NamedTuple):
    pnu: str
    area_band: str
    deal_ym: int
    median_price: int
    trade_count: int


class TrendRow(NamedTuple):
    pnu: str
    area_band: str
    sigungu_code: str
    base_ym: int
    median_price_3m: int
    trade_count_3m: int
    trade_count_6m: int
    change_6m_pct: float | None
    change_12m_pct: float | None
    matched_type_count_6m: int
    matched_type_count_12m: int
    relative_change_6m_pct: float | None
    complex_grade: str | None
    complex_rank: int | None
    complex_rank_total: int | None
    grade_window_months: int | None


class RegionRow(NamedTuple):
    sigungu_code: str
    area_band: str
    base_ym: int
    median_price_3m: int
    trade_count_3m: int
    change_6m_pct: float | None
    change_12m_pct: float | None
    region_grade: str | None
    region_rank: int | None
    region_rank_total: int | None


class BandTables(NamedTuple):
    monthly_rows: list[MonthlyRow]
    trend_rows: list[TrendRow]
    region_rows: list[RegionRow]


def _by_type(trades: Iterable[BandTrade]) -> dict[Hashable, list[int]]:
    return prices_by_key(trades, lambda t: t.type_key)


def _by_complex_type(trades: Iterable[BandTrade]) -> dict[Hashable, list[int]]:
    return prices_by_key(trades, lambda t: (t.pnu, t.type_key))


def region_metrics(members: Sequence[ComplexStats]) -> RegionMetrics | None:
    """시군구·면적대 지표. 비교 키는 (단지, 주택형). 최근 창 거래가 없으면 None."""
    current = [t for s in members for t in s.current]
    if not current:
        return None
    past_6m = [t for s in members for t in s.past_6m]
    past_12m = [t for s in members for t in s.past_12m]
    change_6m, _ = type_change(_by_complex_type(current), _by_complex_type(past_6m))
    change_12m, _ = type_change(_by_complex_type(current), _by_complex_type(past_12m))
    return RegionMetrics(
        round(median([t.price for t in current])), len(current), change_6m, change_12m
    )


def build_tables(
    kept: Iterable[BandTrade],
    base_ym: int,
    region_labels: Sequence[str],
    complex_labels: Sequence[str],
) -> BandTables:
    windows = make_windows(base_ym)
    history_months = window(base_ym, HISTORY_MONTHS)

    trades_by_complex: dict[tuple[str, str], list[BandTrade]] = defaultdict(list)
    for t in kept:
        trades_by_complex[(t.pnu, t.band)].append(t)

    members_by_region: dict[tuple[str, str], list[ComplexStats]] = defaultdict(list)
    for (pnu, band), trades in trades_by_complex.items():
        stats = complex_stats(pnu, band, trades, windows)
        members_by_region[(stats.sigungu_code, band)].append(stats)

    metrics_by_region: dict[tuple[str, str], RegionMetrics] = {}
    for region_key, members in members_by_region.items():
        metrics = region_metrics(members)
        if metrics is not None:
            metrics_by_region[region_key] = metrics

    region_rows: list[RegionRow] = []
    for band in {band for _sgg, band in metrics_by_region}:
        levels = {
            sgg: (m.median_price_3m, m.trade_count_3m)
            for (sgg, b), m in metrics_by_region.items()
            if b == band
        }
        grades = region_grades(levels, region_labels)
        for sgg in levels:
            m = metrics_by_region[(sgg, band)]
            g = grades.get(sgg)
            region_rows.append(
                RegionRow(
                    sgg,
                    band,
                    base_ym,
                    m.median_price_3m,
                    m.trade_count_3m,
                    m.change_6m_pct,
                    m.change_12m_pct,
                    g.grade if g else None,
                    g.rank if g else None,
                    g.total if g else None,
                )
            )

    trend_rows: list[TrendRow] = []
    monthly_rows: list[MonthlyRow] = []
    for (sgg, band), members in members_by_region.items():
        grades = complex_grades(
            [
                GradeCandidate(s.pnu, s.count_6m, s.median_6m, s.median_12m)
                for s in members
            ],
            complex_labels,
        )
        region = metrics_by_region.get((sgg, band))
        region_change_6m = region.change_6m_pct if region else None
        for s in members:
            if len(s.current) < MIN_RECENT_TRADES:
                continue
            change_6m, matched_6m = type_change(
                _by_type(s.current), _by_type(s.past_6m)
            )
            change_12m, matched_12m = type_change(
                _by_type(s.current), _by_type(s.past_12m)
            )
            relative_6m = (
                change_6m - region_change_6m
                if change_6m is not None and region_change_6m is not None
                else None
            )
            g = grades.get(s.pnu)
            trend_rows.append(
                TrendRow(
                    s.pnu,
                    band,
                    sgg,
                    base_ym,
                    round(median([t.price for t in s.current])),
                    len(s.current),
                    s.count_6m,
                    change_6m,
                    change_12m,
                    matched_6m,
                    matched_12m,
                    relative_6m,
                    g.grade if g else None,
                    g.rank if g else None,
                    g.total if g else None,
                    g.window_months if g else None,
                )
            )
            # 월별 시계열은 목록(apt_band_trend)에 오른 쌍만 — 상세 패널은 목록에서만 열리고 Railway 메모리 비용을 줄인다.
            by_month = prices_by_key(
                trades_by_complex[(s.pnu, band)], lambda t: t.deal_ym
            )
            for ym, median_price, trade_count in monthly_series(
                by_month, history_months
            ):
                if median_price is not None:
                    monthly_rows.append(
                        MonthlyRow(s.pnu, band, ym, median_price, trade_count)
                    )

    return BandTables(monthly_rows, trend_rows, region_rows)
