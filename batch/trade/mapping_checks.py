"""거래 apt_seq ↔ 아파트 PNU 매핑의 물리적 정합성 검증 — 순수 함수만 모은다.

이름 유사도만으로는 오매핑을 못 잡는다. `목동신시가지14` 와 `목동14단지` 처럼
표기만 다른 정상 매핑이 있는가 하면, `산내마을1단지행복주택` 이 `산내마을8단지
월드메르디앙` 에 붙은 것처럼 이름이 비슷해도 다른 단지인 경우가 있다.

그래서 이름이 아니라 물리적 지표로 판정한다. 실제로 이 지표들이
`29200_부영애시앙1차` 를 병합 대상에서 걸러냈다 — Kakao 주소는 산정 셀트리움과
같았지만 거래에 진본에 없는 84.28㎡ 주택형과 21층이 있었다.

DB·네트워크에 의존하지 않아야 scripts/tests 의 CI(psycopg2 미설치)에서
검증할 수 있다. 여기에 I/O 를 추가하면 그 테스트가 깨진다.
호출부는 DB 에서 읽은 값을 평범한 dict 로 넘긴다.
"""

import re
from typing import NamedTuple

from batch.trade.name_matching import _BUILD_YEAR_TOLERANCE, _names_overlap

# 주택형 면적 대조 허용 오차(㎡). 84.28 과 84.82 는 다른 주택형이므로
# 그 차이(0.54)보다 작아야 한다.
AREA_TOLERANCE = 0.3

# 실적 면적 중 이 비율 이상이 진본 주택형과 맞아야 정합으로 본다.
AREA_MATCH_MIN_RATIO = 0.5

# 면적이 이 비율 이하로 맞으면 단독으로도 오매핑 근거가 된다.
# 맞는 단지라면 거래 대부분이 등록된 주택형에 떨어져야 한다.
# 기준점은 부영애시앙1차 — 건축물대장·K-APT 로 다른 단지임이 확인된 건이
# 16% 였다. 표본 검증에서 오탐은 전부 타임라인·층이었고 면적 신호는 모두
# 진짜였다(충무주공 10%, 이매촌 21%).
AREA_STRONG_RATIO = 0.25

# 준공 전 분양권·입주권 거래를 허용하는 폭(년). 이 여유가 없으면
# 신축 단지의 정상 거래가 전부 오매핑으로 잡힌다 — 실제로 신당파인힐하나유보라
# (준공 2019, 최초거래 2018) 처럼 이름·층·주택형이 완전일치하는 건이 걸렸다.
PRESALE_TOLERANCE_YEARS = 2

# 최고층 초과 허용 폭. 건축물대장 max_floor 는 대표동 기준이거나 옥탑·필로티
# 계산 차이로 1~2층 어긋나는 일이 흔하다. 소규모·노후 단지에서 두드러진다.
FLOOR_TOLERANCE = 3

_COMPLEX_NUM_RE = re.compile(r"(\d+)\s*(?:단지|차)")


class Signal(NamedTuple):
    """오매핑 의심 신호. strong 이면 단독으로도 판정 근거가 된다."""

    code: str
    detail: str
    strong: bool


def complex_numbers(name: str) -> set[str]:
    """이름에서 단지·차수 번호를 뽑는다. `가락(1차)쌍용` → {'1'}"""
    return set(_COMPLEX_NUM_RE.findall(name or ""))


def complex_number_conflict(trade_nm: str, bld_nm: str) -> bool:
    """양쪽 다 단지 번호를 갖는데 겹치는 값이 하나도 없으면 다른 단지다.

    한쪽에만 번호가 있으면 판단하지 않는다 — `충무주공(872)` 처럼 번호가
    지번인 경우와 구분되지 않기 때문이다.
    """
    a, b = complex_numbers(trade_nm), complex_numbers(bld_nm)
    return bool(a and b and not (a & b))


def jibun_points_elsewhere(jibun_pnus, jibun_owner_pnus, apt_pnu) -> bool:
    """거래 지번이 매핑처가 아닌 **실존하는 다른 단지**를 가리키는지.

    PNU 는 법정동코드+산여부+본번+부번을 인코딩하므로 거래 지번으로 같은 키를 만들어
    대조할 수 있다 (실측: 이안용산1차 지번 11-14 → PNU ...000110014).

    두 조건을 모두 요구한다.
      1) 거래 지번 중 매핑처 PNU 와 같은 것이 하나도 없다
      2) 거래 지번 중 apartments 에 실존하는 다른 PNU 가 있다

    (1) 만으로는 부족하다 — 단지가 여러 필지에 걸치면 대표 필지가 아닌 지번으로
    신고된 거래가 정상적으로 존재한다. `jibun_owner_pnus` 는 숫자 PNU 만 담기므로
    `TRADE_` 더미 매핑은 자연히 배제된다.

    **단독 판정 근거로 쓰지 않는다(strong=False).** 전량 실측(2026-08-21)에서 이 신호
    단독 확정은 2,240건(실적 59만건)이었고 그중 58%가 거래명과 매핑처 이름이 사실상
    같은 경우였다 — `대동`→`대동`(지번주인 `대방대동아파트`), `하나`→`하나`(지번주인
    `효성하나아파트`). 이름이 짧고 흔하면 지번이 가리키는 곳도 매핑된 곳도 그럴듯해서
    이 신호만으로는 어느 쪽이 맞는지 가리지 못한다. 다른 물리 지표와 함께 어긋날 때만
    확정한다(신규 확정 880건).
    """
    keys = set(jibun_pnus or [])
    owners = set(jibun_owner_pnus or [])
    if not keys or not owners:
        return False
    if apt_pnu and apt_pnu in keys:
        return False
    return bool(owners - {apt_pnu})


def floor_exceeds(deal_max_floor: int | None, apt_max_floor: int | None) -> bool:
    """실적 최고층이 진본 최고층을 FLOOR_TOLERANCE 넘게 초과하는지.

    1~2층 차이는 건축물대장 표기 편차 범위라 근거로 쓰지 않는다.
    """
    if not deal_max_floor or not apt_max_floor:
        return False
    return deal_max_floor - apt_max_floor > FLOOR_TOLERANCE


def timeline_violation(use_apr_day: str | None,
                       min_deal_year: int | None,
                       median_build_year: int | None) -> bool:
    """거래·건축 연도가 준공일과 어긋나는지.

    name_matching._timeline_consistent 와 달리 준공 전 거래를
    PRESALE_TOLERANCE_YEARS 만큼 허용한다. 그쪽은 신규 매칭을 수락할지
    판단하는 보수적 게이트라 그대로 두고, 기존 매핑 감사에는 이 규칙을 쓴다.
    """
    if not use_apr_day or len(use_apr_day) < 4 or not use_apr_day[:4].isdigit():
        return False
    apt_year = int(use_apr_day[:4])

    if min_deal_year is not None and min_deal_year < apt_year - PRESALE_TOLERANCE_YEARS:
        return True
    if (median_build_year is not None
            and abs(median_build_year - apt_year) > _BUILD_YEAR_TOLERANCE):
        return True
    return False


def area_match_ratio(deal_areas, apt_areas) -> float | None:
    """실적 면적 중 진본 주택형과 맞는 비율. 어느 쪽이든 비면 None(판단 불가).

    deal_areas 는 건수로 가중한다. 면적 종류만 세면 소수의 예외 거래가
    과대평가된다 — `부영애시앙1차` 는 84.28㎡ 58건 + 84.84㎡ 11건인데
    종류만 세면 1/2=50% 로 통과하고, 건수로 세면 11/69=16% 로 걸린다.
    (면적, 건수) 쌍 또는 면적 스칼라(건수 1)를 섞어 받는다.
    """
    apt = [float(a) for a in (apt_areas or []) if a]
    if not apt:
        return None

    total = matched = 0
    for item in deal_areas or []:
        if isinstance(item, (tuple, list)):
            area, count = float(item[0]), int(item[1])
        else:
            area, count = float(item), 1
        if not area or count <= 0:
            continue
        total += count
        if any(abs(area - a) <= AREA_TOLERANCE for a in apt):
            matched += count

    return matched / total if total else None


def check_mapping(deal: dict, apt: dict) -> list[Signal]:
    """매핑이 물리적으로 어긋나는 신호 목록을 반환한다 (빈 목록이면 정합).

    신호를 모으기만 하고 판정하지 않는다. 오매핑 확정은 mismatch_confirmed 가
    한다 — 지표 하나만으로 판정하면 오탐이 많기 때문이다.

    deal — 거래·전월세 실적 집계
      apt_nm, max_floor, min_deal_year, median_build_year, areas,
      jibun_pnus(거래 지번으로 만든 PNU 키), jibun_owner_pnus(그중 실존 단지 PNU)
    apt  — 매핑 대상 아파트
      pnu, bld_nm, max_floor, use_apr_day, areas
    """
    signals = []

    if complex_number_conflict(deal.get("apt_nm"), apt.get("bld_nm")):
        signals.append(Signal(
            "complex_number",
            f"단지번호 {sorted(complex_numbers(deal.get('apt_nm')))}"
            f" vs {sorted(complex_numbers(apt.get('bld_nm')))}",
            strong=False,
        ))

    if jibun_points_elsewhere(
            deal.get("jibun_pnus"), deal.get("jibun_owner_pnus"), apt.get("pnu")):
        signals.append(Signal(
            "jibun",
            f"거래 지번이 다른 실존 단지 {sorted(set(deal['jibun_owner_pnus']))[:2]} 를 가리킴",
            strong=False,
        ))

    if floor_exceeds(deal.get("max_floor"), apt.get("max_floor")):
        signals.append(Signal(
            "floor", f"층 {deal['max_floor']} > 진본 {apt['max_floor']}", strong=False))

    if timeline_violation(apt.get("use_apr_day"),
                          deal.get("min_deal_year"),
                          deal.get("median_build_year")):
        signals.append(Signal("timeline", "타임라인", strong=False))

    ratio = area_match_ratio(deal.get("areas"), apt.get("areas"))
    if ratio is not None and ratio < AREA_MATCH_MIN_RATIO:
        signals.append(Signal(
            "area", f"면적 일치 {ratio:.0%}", strong=ratio <= AREA_STRONG_RATIO))

    return signals


def mismatch_confirmed(signals: list[Signal]) -> bool:
    """오매핑으로 확정할지 판단한다.

    지표 하나만으로는 확정하지 않는다. 표본 검증에서 단독 판정의 17%가
    오탐이었다 — 분양권 거래(타임라인), 건축물대장 층수 편차(층)가 대표적이다.
    실제 오매핑은 여러 지표가 함께 어긋났다.
      부영애시앙1차          층 + 면적
      산내마을1단지행복주택    단지번호 + 층 + 면적
    다만 주택형이 하나도 안 맞는 것(strong)은 단독으로도 다른 단지라는 뜻이다.
    """
    return any(s.strong for s in signals) or len(signals) >= 2


def name_consistent(trade_nm: str, bld_nm: str) -> bool:
    """이름 유사도 가드. 물리 지표와 달리 단독 판정 근거로 쓰지 않는다."""
    if not bld_nm:
        return True
    return _names_overlap(trade_nm or "", bld_nm)
