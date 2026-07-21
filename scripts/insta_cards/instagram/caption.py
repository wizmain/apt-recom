"""캡션 자동 생성 — 원격 manifest 데이터로 프로필 킷 골격을 조립.

해시태그는 최대 5개(Instagram 현행 정책), 금지어는 생성기와 동일 상수를
캡션 전체(오버라이드 포함)에 적용한다 (spec §6).
"""

from __future__ import annotations

import re

from scripts.insta_cards.textrules import FORBIDDEN_COPY_TERMS

CAPTION_MAX_CHARS = 2200
MAX_HASHTAGS = 5
LANDING_HOST = "apt-recom.kr/content/"

COMPARISON_SERIES = {"budget_choice", "compare"}

SERIES_BASE_HASHTAGS = {
    "trade_top": ["#아파트", "#실거래가", "#부동산시세"],
    "compare": ["#아파트", "#동네비교", "#내집마련"],
    "value": ["#아파트", "#가성비아파트", "#내집마련"],
    "budget_choice": ["#아파트", "#아파트비교", "#내집마련"],
    "lifestyle": ["#아파트", "#아파트추천", "#내집마련"],
}


class CaptionError(ValueError):
    pass


def _region_hashtags(manifest: dict) -> list[str]:
    """map_ctas.region_label → 동적 지역 태그 (괄호 제거, 최대 2개)."""
    tags: list[str] = []
    for cta in manifest.get("map_ctas", []):
        label = cta.get("region_label") or ""
        name = re.sub(r"\(.*?\)", "", label).strip()
        if name and f"#{name}" not in tags:
            tags.append(f"#{name}")
        if len(tags) == 2:
            break
    return tags


def _engagement_line(series: str) -> str:
    if series in COMPARISON_SERIES:
        return "여러분이라면 A vs B? 댓글로 알려주세요 👇"
    return "우리 동네는 몇 위일까요? 댓글로 알려주세요 👇"


def build_caption(manifest: dict) -> str:
    series = manifest["series"]
    slug = manifest["slug"]
    base_tags = SERIES_BASE_HASHTAGS[series]
    tags = (base_tags + _region_hashtags(manifest))[:MAX_HASHTAGS]

    notice = "데이터 기준 {d} · 공공데이터 기반 · 투자 자문이 아닙니다".format(
        d=manifest["data_as_of"]
    )
    if series == "trade_top":
        notice += "\n신고일 기준 · 계약일과 다를 수 있습니다"

    caption = "\n".join(
        [
            manifest["hook"],
            "",
            manifest["summary"],
            _engagement_line(series),
            "",
            "🔗 이 카드의 모든 숫자와 근거 → 프로필 링크",
            f"{LANDING_HOST}{slug}",
            "",
            notice,
            "",
            " ".join(tags),
        ]
    )
    validate_caption(caption, slug)
    return caption


def validate_caption(caption: str, slug: str) -> None:
    found = [t for t in FORBIDDEN_COPY_TERMS if t in caption]
    if found:
        raise CaptionError(f"캡션에 금지어 포함 {found} — 발행 차단")
    if len(caption) > CAPTION_MAX_CHARS:
        raise CaptionError(f"캡션 {len(caption)}자 — {CAPTION_MAX_CHARS}자 한도 초과")
    if f"{LANDING_HOST}{slug}" not in caption:
        raise CaptionError("캡션에 랜딩 링크가 없습니다")
