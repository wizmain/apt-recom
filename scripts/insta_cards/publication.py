"""Publication — 발행물의 단일 진실원 (이미지·JSON이 같은 객체를 소비).

validate() 실패는 발행 전체 차단이다. 부분 발행·fallback 없음 (spec §7).
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from scripts.insta_cards import textrules

SCHEMA_VERSION = 1

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PNU_PATTERN = re.compile(r"^\d{19}$")
DATE_FORMAT = "%Y-%m-%d"

FILTER_ALLOWLIST = frozenset(
    {
        "min_area",
        "max_area",
        "min_price",
        "max_price",
        "min_floor",
        "min_hhld",
        "max_hhld",
        "built_after",
        "built_before",
    }
)


class Series(str, Enum):
    TRADE_TOP = "trade_top"
    COMPARE = "compare"
    VALUE = "value"
    BUDGET_CHOICE = "budget_choice"
    LIFESTYLE = "lifestyle"


SERIES_CLI_NAMES: dict[str, Series] = {
    "trade-top": Series.TRADE_TOP,
    "compare": Series.COMPARE,
    "value": Series.VALUE,
    "budget-choice": Series.BUDGET_CHOICE,
    "lifestyle": Series.LIFESTYLE,
}
SERIES_SLUGS: dict[Series, str] = {v: k for k, v in SERIES_CLI_NAMES.items()}

MIN_ITEMS: dict[Series, int] = {
    Series.TRADE_TOP: 5,
    Series.VALUE: 5,
    Series.LIFESTYLE: 3,
    Series.COMPARE: 2,
    Series.BUDGET_CHOICE: 2,
}

# narrative.why ≥1 이 필요한 시리즈 (이유 슬라이드 보유)
SERIES_WITH_WHY = {Series.VALUE, Series.COMPARE, Series.BUDGET_CHOICE}


@dataclass(frozen=True)
class Metric:
    label: str
    value: str
    unit: str


@dataclass(frozen=True)
class Condition:
    label: str
    value: str


@dataclass(frozen=True)
class Item:
    rank: int
    name: str
    region: str | None
    pnu: str | None
    metrics: tuple[Metric, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MapCta:
    id: str
    label: str
    nudges: tuple[str, ...]
    sigungu_code: str | None
    region_label: str | None
    filters: dict = field(default_factory=dict)
    # 지역이 시군구 코드가 아니라 키워드(예: "서울")인 시리즈용 — 딥링크의
    # keyword 파라미터로 소비되어 서울 전역 스코어링을 재현한다 (G1 해소).
    # 기존 positional 생성 호환을 위해 마지막 필드로 둔다.
    keyword: str | None = None


@dataclass(frozen=True)
class ComparisonColumn:
    name: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class Comparison:
    row_labels: tuple[str, ...]
    columns: tuple[ComparisonColumn, ...]


@dataclass(frozen=True)
class FitFor:
    a: str
    b: str


@dataclass(frozen=True)
class Narrative:
    why: tuple[str, ...]
    fit_for: FitFor | None


@dataclass(frozen=True)
class Publication:
    schema_version: int
    slug: str
    status: str
    series: Series
    title: str
    eyebrow: str
    hook: str
    summary: str
    generated_at: str
    published_at: str | None
    data_as_of: str
    period_label: str
    cover_image: str
    cover_alt: str
    conditions: tuple[Condition, ...]
    items: tuple[Item, ...]
    secondary_items: tuple[Item, ...] | None
    comparison: Comparison | None
    narrative: Narrative
    methodology: tuple[str, ...]
    caveats: tuple[str, ...]
    map_ctas: tuple[MapCta, ...]


class PublicationValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("발행 검증 실패:\n" + "\n".join(f"- {e}" for e in errors))


def validate(pub: Publication) -> None:  # noqa: C901 — 규칙 나열형 검증 함수
    errors: list[str] = []

    def text_check(fieldname: str, rule: str, value: str) -> None:
        errors.extend(
            f"{fieldname}: {msg}" for msg in textrules.check_field(rule, value)
        )

    def forbidden_check(fieldname: str, value: str) -> None:
        found = textrules.find_forbidden_terms(value)
        if found:
            errors.append(f"{fieldname}: 금지어 포함 {found} — 단정 표현 불가")

    # --- 기본 필드 ---
    if pub.schema_version != SCHEMA_VERSION:
        errors.append(f"schema_version: {SCHEMA_VERSION} 이어야 합니다.")
    if not SLUG_PATTERN.match(pub.slug):
        errors.append(f"slug: 소문자 ASCII+하이픈만 허용 — '{pub.slug}'")
    if pub.status not in ("draft", "published"):
        errors.append(f"status: draft|published 만 허용 — '{pub.status}'")
    if pub.status == "published" and not pub.published_at:
        errors.append("published_at: published 상태에서는 필수입니다.")
    if pub.status == "draft" and pub.published_at is not None:
        errors.append("published_at: draft 상태에서는 null 이어야 합니다.")
    for name in ("title", "eyebrow", "cover_alt", "period_label"):
        if not getattr(pub, name).strip():
            errors.append(f"{name}: 빈 값은 허용되지 않습니다.")
    if pub.cover_image != "01-cover.png":
        errors.append("cover_image: '01-cover.png' 이어야 합니다.")
    try:
        as_of = datetime.strptime(pub.data_as_of, DATE_FORMAT).date()
        if as_of > date.today():
            errors.append(f"data_as_of: 미래 날짜 불가 — {pub.data_as_of}")
    except ValueError:
        errors.append(f"data_as_of: YYYY-MM-DD 형식이 아님 — '{pub.data_as_of}'")

    # --- 텍스트 한도 + 금지어 ---
    text_check("hook", "hook", pub.hook)
    text_check("summary", "summary", pub.summary)
    forbidden_check("hook", pub.hook)
    for i, why in enumerate(pub.narrative.why):
        text_check(f"narrative.why[{i}]", "why", why)
        forbidden_check(f"narrative.why[{i}]", why)
    if pub.narrative.fit_for is not None:
        for side in ("a", "b"):
            value = getattr(pub.narrative.fit_for, side)
            text_check(f"narrative.fit_for.{side}", "fit_for", value)
            forbidden_check(f"narrative.fit_for.{side}", value)
    for i, cond in enumerate(pub.conditions):
        text_check(f"conditions[{i}]", "condition_value", cond.value)
    for i, m in enumerate(pub.methodology):
        text_check(f"methodology[{i}]", "methodology", m)
    for i, c in enumerate(pub.caveats):
        text_check(f"caveats[{i}]", "caveat", c)

    # --- 개수 한도 ---
    if not pub.conditions or len(pub.conditions) > textrules.MAX_CONDITIONS:
        errors.append(f"conditions: 1~{textrules.MAX_CONDITIONS}개 필요")
    if not pub.methodology or len(pub.methodology) > textrules.MAX_METHODOLOGY:
        errors.append(f"methodology: 1~{textrules.MAX_METHODOLOGY}개 필요")
    if not pub.caveats or len(pub.caveats) > textrules.MAX_CAVEATS:
        errors.append(f"caveats: 1~{textrules.MAX_CAVEATS}개 필요")
    if len(pub.narrative.why) > textrules.MAX_WHY:
        errors.append(f"narrative.why: 최대 {textrules.MAX_WHY}개")

    # --- items ---
    def check_items(name: str, items: tuple[Item, ...]) -> None:
        for idx, item in enumerate(items):
            if item.rank != idx + 1:
                errors.append(
                    f"{name}: rank 는 1부터 연속이어야 함 (index {idx} = rank {item.rank})"
                )
            if not item.name or not str(item.name).strip():
                errors.append(f"{name}[{idx}].name: 빈 값은 허용되지 않습니다.")
            if item.pnu is not None and not PNU_PATTERN.match(item.pnu):
                errors.append(f"{name}[{idx}].pnu: 19자리 숫자가 아님 — '{item.pnu}'")
            if not item.metrics or len(item.metrics) > textrules.MAX_METRICS:
                errors.append(
                    f"{name}[{idx}].metrics: 1~{textrules.MAX_METRICS}개 필요"
                )
            if len(item.reasons) > textrules.MAX_REASONS:
                errors.append(f"{name}[{idx}].reasons: 최대 {textrules.MAX_REASONS}개")
            for r_i, reason in enumerate(item.reasons):
                errors.extend(
                    f"{name}[{idx}].reasons[{r_i}]: {msg}"
                    for msg in textrules.check_field("reason", reason)
                )

    minimum = MIN_ITEMS[pub.series]
    if len(pub.items) < minimum:
        errors.append(
            f"items: {pub.series.value} 는 최소 {minimum}개 필요 (실제 {len(pub.items)})"
        )
    check_items("items", pub.items)

    if pub.series is Series.TRADE_TOP:
        if pub.secondary_items is None or len(pub.secondary_items) < 5:
            errors.append("secondary_items: trade_top 은 5개 필요")
        else:
            check_items("secondary_items", pub.secondary_items)
    elif pub.secondary_items is not None:
        errors.append("secondary_items: trade_top 외 시리즈는 null 이어야 함")

    # --- comparison ---
    if pub.series in (Series.COMPARE, Series.BUDGET_CHOICE):
        if pub.comparison is None:
            errors.append("comparison: 비교형 시리즈는 필수")
        else:
            if len(pub.comparison.columns) != 2:
                errors.append("comparison: 열은 2개(A/B)여야 함")
            for col in pub.comparison.columns:
                if len(col.values) != len(pub.comparison.row_labels):
                    errors.append(
                        f"comparison[{col.name}]: 값 개수가 행 라벨 수와 다름"
                    )
            if pub.series is Series.BUDGET_CHOICE:
                rows = pub.comparison.row_labels
                for idx, item in enumerate(pub.items):
                    labels = tuple(m.label for m in item.metrics)
                    if labels != rows:
                        errors.append(
                            f"items[{idx}].metrics 라벨이 comparison 행과 불일치: {labels} != {rows}"
                        )
    elif pub.comparison is not None:
        errors.append("comparison: 비교형 외 시리즈는 null 이어야 함")

    # --- narrative 시리즈 규칙 ---
    if pub.series in SERIES_WITH_WHY and not pub.narrative.why:
        errors.append("narrative.why: 이 시리즈는 최소 1개 필요")
    if pub.series is Series.BUDGET_CHOICE and pub.narrative.fit_for is None:
        errors.append("narrative.fit_for: budget_choice 는 필수")
    if pub.series is not Series.BUDGET_CHOICE and pub.narrative.fit_for is not None:
        errors.append("narrative.fit_for: budget_choice 외 시리즈는 null 이어야 함")

    # --- map_ctas ---
    if pub.series is not Series.TRADE_TOP and not pub.map_ctas:
        errors.append("map_ctas: trade_top 외 시리즈는 최소 1개 필요")
    if pub.series in (Series.COMPARE, Series.BUDGET_CHOICE) and len(pub.map_ctas) != 2:
        errors.append("map_ctas: 비교형 시리즈는 정확히 2개 필요")
    seen_ids: set[str] = set()
    for idx, cta in enumerate(pub.map_ctas):
        if cta.id in seen_ids:
            errors.append(f"map_ctas[{idx}].id: 중복 — '{cta.id}'")
        seen_ids.add(cta.id)
        if not cta.nudges:
            errors.append(f"map_ctas[{idx}].nudges: 최소 1개 필요")
        if cta.keyword is not None and not cta.keyword.strip():
            errors.append(f"map_ctas[{idx}].keyword: 빈 문자열 불가 (미사용 시 null)")
        bad_keys = set(cta.filters) - FILTER_ALLOWLIST
        if bad_keys:
            errors.append(
                f"map_ctas[{idx}].filters: 허용되지 않는 키 {sorted(bad_keys)}"
            )

    if errors:
        raise PublicationValidationError(errors)


def to_json_dict(pub: Publication) -> dict:
    d = dataclasses.asdict(pub)
    d["series"] = pub.series.value
    return d
