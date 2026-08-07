"""서사 문구 — 데이터 기반 템플릿 + YAML 오버라이드.

투자 단정 표현은 템플릿에 존재하지 않는다. 오버라이드 문구의 금지어·길이
검사는 publication.validate() 에서 최종 수행된다 (여기서는 구조만 검증).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import yaml

from scripts.insta_cards.publication import FitFor
from scripts.insta_cards.theme import format_eok

NUDGE_LABELS = {
    "cost": "가성비",
    "newlywed": "신혼육아",
    "education": "학군",
    "senior": "시니어",
    "nature": "자연친화",
    "safety": "안전",
    "commute": "출퇴근",
    "pet": "반려동물",
    "investment": "투자",
}

SUBTYPE_LABELS = {
    "subway": "지하철",
    "bus": "버스",
    "mart": "마트",
    "convenience_store": "편의점",
    "pharmacy": "약국",
    "hospital": "병원",
    "general_hospital": "종합병원",
    "park": "공원",
    "school": "학교",
    "kindergarten": "유치원",
    "assigned_elementary": "배정 초등학교",
    "library": "도서관",
    "academy": "학원",
    "cctv": "CCTV",
    "police": "경찰서",
    "fire_station": "소방서",
    "cafe": "카페",
    "kids_cafe": "키즈카페",
    "pediatric_clinic": "소아과",
    "obgyn_clinic": "산부인과",
    "pet_facility": "반려동물시설",
    "animal_hospital": "동물병원",
    "pet_shop": "펫샵",
    "score_price": "가격 점수",
    "score_jeonse": "전세가율 점수",
    "score_safety": "안전 점수",
    "score_crime": "범죄 안전 점수",
    "score_parking": "주차 점수",
    "score_elevator": "엘리베이터 점수",
    "score_air": "대기질 점수",
}

OVERRIDE_ALLOWED_KEYS = {"hook", "why", "fit_for"}


@dataclass(frozen=True)
class CopyBundle:
    hook: str
    why: tuple[str, ...]
    fit_for: FitFor | None


class CopyOverrideError(ValueError):
    pass


def contributor_labels(top_contributors: list[dict], limit: int = 3) -> list[str]:
    labels = []
    for row in top_contributors[:limit]:
        subtype = row.get("subtype", "")
        labels.append(SUBTYPE_LABELS.get(subtype, subtype))
    return labels


def load_copy_overrides(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise CopyOverrideError(f"오버라이드 파일은 매핑이어야 합니다: {path}")
    unknown = set(data) - OVERRIDE_ALLOWED_KEYS
    if unknown:
        raise CopyOverrideError(
            f"허용되지 않는 키: {sorted(unknown)} (허용: {sorted(OVERRIDE_ALLOWED_KEYS)})"
        )
    if "hook" in data and (
        not isinstance(data["hook"], str) or not data["hook"].strip()
    ):
        raise CopyOverrideError("hook: 비어있지 않은 문자열이어야 합니다.")
    if "why" in data:
        if not isinstance(data["why"], list) or not all(
            isinstance(w, str) and w.strip() for w in data["why"]
        ):
            raise CopyOverrideError("why: 비어있지 않은 문자열 목록이어야 합니다.")
    if "fit_for" in data:
        ff = data["fit_for"]
        if (
            not isinstance(ff, dict)
            or set(ff) != {"a", "b"}
            or not all(isinstance(ff[k], str) and ff[k].strip() for k in ("a", "b"))
        ):
            raise CopyOverrideError(
                "fit_for: {a: 문자열, b: 문자열} 형식이어야 합니다."
            )
    return data


def apply_overrides(bundle: CopyBundle, overrides: dict) -> CopyBundle:
    changes = {}
    if "hook" in overrides:
        changes["hook"] = overrides["hook"].strip()
    if "why" in overrides:
        changes["why"] = tuple(w.strip() for w in overrides["why"])
    if "fit_for" in overrides:
        changes["fit_for"] = FitFor(
            a=overrides["fit_for"]["a"].strip(), b=overrides["fit_for"]["b"].strip()
        )
    return replace(bundle, **changes)


def _join(labels: list[str]) -> str:
    return "·".join(labels) if labels else "생활 인프라"


# 점수형 기여 항목(가격 점수·안전 점수 …)은 "접근" 이라는 말과 붙지 않는다 —
# "가격이 높아도 가격 점수 접근을 우선한다면" 같은 모순 문장이 나온다(2026-08-07).
_SCORE_LABELS = frozenset(
    label for key, label in SUBTYPE_LABELS.items() if key.startswith("score_")
)


def _first_facility(labels: list[str]) -> str | None:
    """접근성 표현에 쓸 수 있는 첫 시설 항목 (점수형 제외). 없으면 None."""
    for label in labels:
        if label not in _SCORE_LABELS:
            return label
    return None


# 두 대표 거래의 전용면적 차가 이 값 이하면 "면적이 사실상 같다"고 본다.
# 실측(2026-08-07, 큐 6개 조합): 대표 면적 차가 0.0 / 0.1 / 0.1 / 0.5 / 0.6 ㎡ 였다.
# 두 지역에 같은 목표 면적(--area-a/--area-b)을 주는 구조라 면적은 거의 항상 같고,
# 실제로 밴드가 다른 사례(2026-07-13 카드: 62.7 vs 83.0)는 20㎡ 대로 확연히 벌어진다.
BUDGET_CHOICE_AREA_TIE_THRESHOLD = 3.0


def build_budget_choice_copy(
    label_a: str,
    label_b: str,
    price_a: int,
    price_b: int,
    area_a: float,
    area_b: float,
    contributors_a: list[str],
    contributors_b: list[str],
) -> CopyBundle:
    hook = f"{label_a} {int(area_a)}㎡ vs {label_b} {int(area_b)}㎡, 당신의 선택은?"
    why = (
        f"{label_a} 대표 단지 최근 실거래 {format_eok(price_a)}, {label_b} 는 {format_eok(price_b)} 입니다.",
        f"{label_a} 는 {_join(contributors_a)} 접근성이 점수에 크게 기여했습니다.",
        f"{label_b} 는 {_join(contributors_b)} 접근성이 점수에 크게 기여했습니다.",
    )
    return CopyBundle(
        hook=hook,
        why=why,
        fit_for=_budget_choice_fit_for(
            label_a,
            label_b,
            price_a,
            price_b,
            area_a,
            area_b,
            contributors_a,
            contributors_b,
        ),
    )


def _narrow_fit_text(label: str, contributors: list[str]) -> str:
    facility = _first_facility(contributors)
    if facility:
        return f"{label}: 면적보다 입지·{facility} 접근을 우선한다면"
    return f"{label}: 면적보다 생활 점수를 우선한다면"


def _budget_choice_fit_for(
    label_a: str,
    label_b: str,
    price_a: int,
    price_b: int,
    area_a: float,
    area_b: float,
    contributors_a: list[str],
    contributors_b: list[str],
) -> FitFor:
    """면적·가격 실측값으로 문구를 고른다 — 고정 문구는 사실과 어긋난다(2026-08-07).

    이전에는 "B 는 같은 예산으로 더 넓은 면적" 이 상수였다. 두 문제가 있었다:
    1) 같은 목표 면적을 쓰므로 실제로는 면적이 거의 같다(최대 0.6㎡ 차) — 늘 거짓
    2) A 가 더 넓은 경우에도 B 를 넓다고 말한다 — 방향이 뒤집힌다
    """
    if abs(area_a - area_b) <= BUDGET_CHOICE_AREA_TIE_THRESHOLD:
        # 면적이 사실상 같다 → 차이는 가격과 입지에서 난다. 저렴한 쪽을 데이터로 판별.
        cheaper_is_a = price_a <= price_b
        cheap_label, cheap_side = (label_a, "a") if cheaper_is_a else (label_b, "b")
        other_label = label_b if cheaper_is_a else label_a
        other_contribs = contributors_b if cheaper_is_a else contributors_a
        cheap_text = f"{cheap_label}: 같은 면적대를 더 낮은 가격으로 잡고 싶다면"
        facility = _first_facility(other_contribs)
        other_text = (
            f"{other_label}: 가격이 높아도 {facility} 접근을 우선한다면"
            if facility
            else f"{other_label}: 가격이 높아도 생활 점수가 높은 쪽을 원한다면"
        )
        if cheap_side == "a":
            return FitFor(a=cheap_text, b=other_text)
        return FitFor(a=other_text, b=cheap_text)

    wider_is_b = area_b > area_a
    wide_text_a = f"{label_a}: 같은 예산으로 더 넓은 면적을 원한다면"
    wide_text_b = f"{label_b}: 같은 예산으로 더 넓은 면적을 원한다면"
    narrow_text_a = _narrow_fit_text(label_a, contributors_a)
    narrow_text_b = _narrow_fit_text(label_b, contributors_b)
    if wider_is_b:
        return FitFor(a=narrow_text_a, b=wide_text_b)
    return FitFor(a=wide_text_a, b=narrow_text_b)


def build_lifestyle_copy(
    profile_label: str, region_label: str, contributors: list[str]
) -> CopyBundle:
    hook = f"{region_label}에서 {profile_label} 조건으로 고른 단지"
    why = (f"{_join(contributors)} 접근성이 {profile_label} 점수에 크게 기여했습니다.",)
    return CopyBundle(hook=hook, why=why, fit_for=None)


def build_value_copy(region_label: str) -> CopyBundle:
    hook = f"{region_label}, 가격은 낮은데 생활점수는 높은 단지 5곳"
    why = ("가성비 넛지 상위 후보 중에서 ㎡당 가격이 낮은 순서로 골랐습니다.",)
    return CopyBundle(hook=hook, why=why, fit_for=None)


# 상위10 평균 점수 차가 이 값 이하면 승자를 선언하지 않는다(동률 표기).
# 감이 아니라 실측 분포의 단절점이다 — compare 큐 8개 쌍의 차이가
# 0.0 / 0.6 / 0.7 / 0.9 || 2.4 / 2.9 / 4.7 / 5.5 로 뚜렷하게 갈렸다(2026-08-05).
# 배경: 3일차(0.1점 차)에 승자 표현이 오해를 낳아 문구 오버라이드로 막았고,
# 10일차(0.7점 차)에 재발해 런북 예고대로 생성기 규칙으로 승격했다.
COMPARE_TIE_THRESHOLD = 1.0


def build_compare_copy(
    label_a: str,
    label_b: str,
    nudge_label: str,
    winner_label: str,
    score_gap: float,
) -> CopyBundle:
    hook = f"{label_a} vs {label_b}, {nudge_label} 점수가 높은 곳은?"
    if score_gap <= COMPARE_TIE_THRESHOLD:
        why = (
            f"{nudge_label} 상위 10개 단지 평균은 {score_gap:.1f}점 차 — "
            "두 지역은 사실상 동률입니다.",
            "차이는 점수가 아니라 가격·거래량·연식에서 납니다. 비교표에서 확인하세요.",
        )
    else:
        why = (
            f"{nudge_label} 상위 10개 단지 평균 점수는 {winner_label} 가 더 높았습니다.",
            "중위 실거래가·거래량·평균 연식은 비교표에서 확인하세요.",
        )
    return CopyBundle(hook=hook, why=why, fit_for=None)


def build_trade_top_copy(days: int, top_amount_manwon: int) -> CopyBundle:
    # "신고" 대신 "새로 포착된" — created_at 은 적재일이다 (trade_top 모듈 주석 참고).
    hook = f"최근 {days}일 새로 포착된 최고가는 {format_eok(top_amount_manwon)}"
    return CopyBundle(hook=hook, why=(), fit_for=None)
