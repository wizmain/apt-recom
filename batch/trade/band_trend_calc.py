"""면적대 가격 추세 계산 — 순수 함수 모듈 (DB·네트워크 import 금지).

단지·지역의 "최근 3개월 중위가 대비 6/12개월 전 변화율", 등급, 월별 시계열을 계산한다.
배치(DB 적재)는 이 모듈의 함수를 그대로 호출하고, 여기서는 I/O 를 하지 않는다.
"""

import calendar
import math
import statistics
from collections.abc import Hashable, Mapping, Sequence
from datetime import date, timedelta
from typing import NamedTuple

# 거래 신고 기한(계약 후 30일). 기준월은 이 기한이 지나 신고 지연분까지 들어온 달만 쓴다.
REPORT_DEADLINE_DAYS = 30
# 가격 비교 창 길이(개월). 거래가 드문 단지도 표본이 모이도록 3개월 롤링.
WINDOW_MONTHS = 3
# 현재 창과 비교할 과거 시점(개월 전).
CHANGE_OFFSETS = (6, 12)
# 시계열·12개월 대입 순위 산출에 쓰는 이력 길이(개월).
HISTORY_MONTHS = 60
# 주택형 키 소수 자릿수. 84.52/84.54 같은 표기 차이는 동일 주택형으로 묶지 않고 면적 그대로 비교한다.
TYPE_KEY_DECIMALS = 2
# 면적대 내 이상 거래 판정: 창 중앙값 대비 ±25% 밖(인스타 value 이상거래 제외 기준과 동일).
BAND_OUTLIER_MAX_DEVIATION = 0.25
# 아래 MIN_* 는 Task 3 실측(표본 분포) 후 조정 가능한 잠정값이다.
# 최근 창 최소 거래 수 — 1건은 중위가로 보기 어렵다.
MIN_RECENT_TRADES = 2
# 변화율 비교 시 현재/과거 창 각각의 최소 거래 수.
MIN_COMPARE_TRADES = 2
# 단지 등급 부여 최소 거래 수.
MIN_GRADE_TRADES = 3
# 지역 변화율 산출 최소 거래 수(지역은 단지보다 표본이 커야 안정적).
MIN_REGION_TRADES = 5
# 국토부 원문 거래유형 값. 특수관계 거래가 많아 가격 추세에서 제외한다.
EXCLUDED_DEALING_GBN = "직거래"

DECILE_COUNT = 10
DECILES_PER_COMPLEX_GRADE = 2  # 5등급 라벨 기준 십분위 2개씩


class BandDef(NamedTuple):
    code: str
    min_area: float
    max_area: float | None  # None = 상한 없음


def parse_band_extra(code: str, extra: str) -> BandDef:
    """common_code extra "하한,상한" 파싱. 상한이 비어 있으면 무제한 (예: "175,")."""
    lower_text, _, upper_text = extra.partition(",")
    upper_text = upper_text.strip()
    return BandDef(
        code,
        float(lower_text),
        float(upper_text) if upper_text else None,
    )


def band_of(area: float, bands: Sequence[BandDef]) -> str | None:
    """면적이 속한 면적대 코드. 하한 포함·상한 제외, 어느 대에도 없으면 None."""
    for band in bands:
        if area >= band.min_area and (band.max_area is None or area < band.max_area):
            return band.code
    return None


def type_key(area: float) -> float:
    return round(area, TYPE_KEY_DECIMALS)


def base_month(today: date) -> int:
    """신고 기한이 지난 가장 최근 달(YYYYMM). 월말일 + 기한 < today 인 첫 달."""
    year, month = today.year, today.month
    while True:
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        if month_end + timedelta(days=REPORT_DEADLINE_DAYS) < today:
            return year * 100 + month


def shift_month(ym: int, months: int) -> int:
    index = (ym // 100) * 12 + (ym % 100 - 1) + months
    return (index // 12) * 100 + index % 12 + 1


def window(end_ym: int, length: int = WINDOW_MONTHS) -> list[int]:
    """end_ym 로 끝나는 length 개월 (오름차순)."""
    return [shift_month(end_ym, offset) for offset in range(-(length - 1), 1)]


def median(values: Sequence[float]) -> float:
    """중앙값. 빈 입력은 ValueError (호출자가 비어 있음을 먼저 걸러야 한다)."""
    if not values:
        raise ValueError("median of empty sequence")
    return statistics.median(values)


def drop_outliers(
    prices: Sequence[float],
    max_deviation: float = BAND_OUTLIER_MAX_DEVIATION,
) -> list[float]:
    """중앙값 대비 ±max_deviation 밖의 가격 제외."""
    if not prices:
        return []
    center = median(prices)
    return [p for p in prices if abs(p - center) / center <= max_deviation]


def type_change(
    current: Mapping[Hashable, Sequence[float]],
    past: Mapping[Hashable, Sequence[float]],
) -> tuple[float | None, int]:
    """주택형별 중위가 비율을 현재 창 거래 수로 가중평균한 변화율(%)과 비교 주택형 수.

    면적이 다른 주택형을 섞어 중위가를 구하면 구성 변화가 가격 변화로 오인되므로
    같은 주택형끼리만 비교한다.
    """
    current_total = sum(len(v) for v in current.values())
    past_total = sum(len(v) for v in past.values())
    if current_total < MIN_COMPARE_TRADES or past_total < MIN_COMPARE_TRADES:
        return None, 0

    weighted_sum = 0.0
    weight_total = 0
    matched = 0
    for key, current_prices in current.items():
        past_prices = past.get(key)
        if not current_prices or not past_prices:
            continue
        weight = len(current_prices)
        weighted_sum += weight * median(current_prices) / median(past_prices)
        weight_total += weight
        matched += 1
    if matched == 0:
        return None, 0
    return (weighted_sum / weight_total - 1) * 100, matched


def region_grade(rank: int, total: int, labels: Sequence[str]) -> str:
    """순위(1=최상)를 라벨 수만큼 균등 분할."""
    return labels[(rank - 1) * len(labels) // total]


def complex_grade(rank: int, total: int, labels: Sequence[str]) -> tuple[str, int]:
    """(등급, 십분위). 십분위 2개씩 한 등급."""
    decile = math.ceil(rank * DECILE_COUNT / total)
    return labels[(decile - 1) // DECILES_PER_COMPLEX_GRADE], decile


def placement_rank(value: float, population_desc: Sequence[float]) -> int:
    """내림차순 모집단에서 value 보다 큰 값의 수 + 1."""
    return sum(1 for v in population_desc if v > value) + 1


def monthly_series(
    prices_by_month: Mapping[int, Sequence[float]],
    months: Sequence[int],
) -> list[tuple[int, int | None, int]]:
    """월별 (ym, 중위가격 or None, 건수). 이상 거래는 해당 월을 끝으로 하는 롤링 창 중앙값 기준 제외."""
    series: list[tuple[int, int | None, int]] = []
    for ym in months:
        window_prices = [p for m in window(ym) for p in prices_by_month.get(m, ())]
        if not window_prices:
            series.append((ym, None, 0))
            continue
        center = median(window_prices)
        kept = [
            p
            for p in prices_by_month.get(ym, ())
            if abs(p - center) / center <= BAND_OUTLIER_MAX_DEVIATION
        ]
        if not kept:
            series.append((ym, None, 0))
        else:
            series.append((ym, round(median(kept)), len(kept)))
    return series
