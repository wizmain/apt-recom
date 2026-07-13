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
    fit_for = FitFor(
        a=f"{label_a}: 면적보다 입지·{_join(contributors_a[:1])} 접근을 우선한다면",
        b=f"{label_b}: 같은 예산으로 더 넓은 면적을 원한다면",
    )
    return CopyBundle(hook=hook, why=why, fit_for=fit_for)


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


def build_compare_copy(
    label_a: str, label_b: str, nudge_label: str, winner_label: str
) -> CopyBundle:
    hook = f"{label_a} vs {label_b}, {nudge_label} 점수가 높은 곳은?"
    why = (
        f"{nudge_label} 상위 10개 단지 평균 점수는 {winner_label} 가 더 높았습니다.",
        "중위 실거래가·거래량·평균 연식은 비교표에서 확인하세요.",
    )
    return CopyBundle(hook=hook, why=why, fit_for=None)


def build_trade_top_copy(days: int, top_amount_manwon: int) -> CopyBundle:
    hook = f"최근 {days}일 신고 최고가는 {format_eok(top_amount_manwon)}"
    return CopyBundle(hook=hook, why=(), fit_for=None)
