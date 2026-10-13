"""과거 거래 행 → 국토부 고유번호 추론 (설계 4-3). DB 접근 없음.

기존 이름 키 안에서 고유번호가 있는 행(known)으로 서명을 학습하고, 고유번호가 없는 행
(target)이 **유일하게** 한 번호를 가리킬 때만 그 번호를 돌려준다. 모호하면 결과에서
빠진다(호출자는 이름 키를 그대로 둔다 — 기존 매핑 그대로라 현재보다 나빠지지 않는다).

서명: 매매 = 준공연도 → 준공연도+면적, 전월세 = 면적(전월세 과거분에는 준공연도가 없다).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import NamedTuple

from batch.trade.trade_keys import (
    KEY_METHOD_INFER_AREA,
    KEY_METHOD_INFER_SINGLE,
    KEY_METHOD_INFER_YEAR,
    KEY_METHOD_INFER_YEAR_AREA,
)

# 면적 서명 비교 자리수 — 같은 주택형이 행마다 84.9234 / 84.92 로 기록되는 경우를 묶는다.
# 다른 단지 주택형 간 최소 차이(실측 84.89 vs 84.92)보다 거칠면 안 된다.
AREA_PRECISION = 2


class KnownRow(NamedTuple):
    legacy_key: str
    api_apt_seq: str
    build_year: int | None
    area: float | None


class TargetRow(NamedTuple):
    row_id: int
    legacy_key: str
    build_year: int | None
    area: float | None


class Inference(NamedTuple):
    api_apt_seq: str
    method: str


def _area(value: float | None) -> float | None:
    return None if value is None else round(float(value), AREA_PRECISION)


def _only(ids: set[str]) -> str | None:
    return next(iter(ids)) if len(ids) == 1 else None


def infer_keys(
    known: Iterable[KnownRow], targets: Iterable[TargetRow], use_build_year: bool
) -> dict[int, Inference]:
    ids_by_key: dict[str, set[str]] = defaultdict(set)
    by_year: dict[tuple, set[str]] = defaultdict(set)
    by_year_area: dict[tuple, set[str]] = defaultdict(set)
    by_area: dict[tuple, set[str]] = defaultdict(set)
    for k in known:
        area = _area(k.area)
        ids_by_key[k.legacy_key].add(k.api_apt_seq)
        by_year[(k.legacy_key, k.build_year)].add(k.api_apt_seq)
        by_year_area[(k.legacy_key, k.build_year, area)].add(k.api_apt_seq)
        by_area[(k.legacy_key, area)].add(k.api_apt_seq)

    out: dict[int, Inference] = {}
    for t in targets:
        ids = ids_by_key.get(t.legacy_key)
        if not ids:
            continue
        area = _area(t.area)
        if use_build_year:
            result = _infer_trade(t, ids, area, by_year, by_year_area)
        else:
            result = _infer_rent(t, ids, area, by_area)
        if result:
            out[t.row_id] = result
    return out


def _infer_trade(t, ids, area, by_year, by_year_area) -> Inference | None:
    year_ids = by_year.get((t.legacy_key, t.build_year), set())
    if len(ids) == 1:
        return Inference(_only(ids), KEY_METHOD_INFER_SINGLE) if year_ids else None
    hit = _only(year_ids)
    if hit:
        return Inference(hit, KEY_METHOD_INFER_YEAR)
    hit = _only(by_year_area.get((t.legacy_key, t.build_year, area), set()))
    return Inference(hit, KEY_METHOD_INFER_YEAR_AREA) if hit else None


def _infer_rent(t, ids, area, by_area) -> Inference | None:
    if area is None:
        return None
    area_ids = by_area.get((t.legacy_key, area), set())
    if len(ids) == 1:
        return Inference(_only(ids), KEY_METHOD_INFER_SINGLE) if area_ids else None
    hit = _only(area_ids)
    return Inference(hit, KEY_METHOD_INFER_AREA) if hit else None
