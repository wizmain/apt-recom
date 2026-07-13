"""텍스트 정책 — 길이 한도(렌더링 가능성) + 금지어(투자 단정 표현).

한도 초과·금지어 포함은 publication.validate() 에서 발행 차단 사유가 된다.
truncate 로 조용히 줄이지 않는다 (고유명 제외 — theme.truncate_text 참조).
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import ImageFont

from scripts.insta_cards.theme import CONTENT_WIDTH, get_font, measuring_draw

# 투자 단정 표현 — hook/why/fit_for 에 포함되면 발행 차단 (오버라이드 문구 포함)
FORBIDDEN_COPY_TERMS = ("오를", "저평가", "무조건", "확실", "급등", "투자 추천")

MAX_CONDITIONS = 6
MAX_REASONS = 3
MAX_METRICS = 7
MAX_METHODOLOGY = 4
MAX_CAVEATS = 4
MAX_WHY = 3


@dataclass(frozen=True)
class TextLimit:
    font_weight: str
    font_size: int
    max_width: int
    max_lines: int


# 각 필드가 그려질 슬라이드의 실제 폰트·폭 기준 (slides.py 렌더러와 동일 값 유지)
TEXT_LIMITS: dict[str, TextLimit] = {
    "hook": TextLimit("extrabold", 64, CONTENT_WIDTH, 3),
    "summary": TextLimit("semibold", 34, CONTENT_WIDTH, 2),
    "condition_value": TextLimit("semibold", 30, 420, 1),
    "reason": TextLimit("regular", 28, CONTENT_WIDTH - 64, 1),
    "methodology": TextLimit("regular", 26, CONTENT_WIDTH, 2),
    "caveat": TextLimit("regular", 26, CONTENT_WIDTH, 2),
    "why": TextLimit("semibold", 32, CONTENT_WIDTH, 2),
    "fit_for": TextLimit("regular", 30, 440, 3),
}


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """공백 단위 우선, 한 단어가 폭을 넘으면 글자 단위로 자르는 greedy wrap."""
    draw = measuring_draw()
    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        # 단어 자체가 폭 초과 → 글자 단위 분해
        chunk = ""
        for ch in word:
            if draw.textlength(chunk + ch, font=font) <= max_width:
                chunk += ch
            else:
                lines.append(chunk)
                chunk = ch
        current = chunk
    if current:
        lines.append(current)
    return lines


def check_field(field: str, text: str) -> list[str]:
    """필드 한도 검사 — 위반 메시지 목록 반환 (빈 리스트 = 통과)."""
    limit = TEXT_LIMITS[field]  # 미정의 필드는 KeyError = 구현 버그
    if not text or not text.strip():
        return [f"{field}: 빈 문자열은 허용되지 않습니다."]
    font = get_font(limit.font_weight, limit.font_size)
    lines = wrap_text(text.strip(), font, limit.max_width)
    if len(lines) > limit.max_lines:
        return [
            f"{field}: {limit.max_lines}줄 한도 초과 (실제 {len(lines)}줄) — "
            f"문구를 줄이거나 --copy-file 로 교체하세요: {text[:40]}…"
        ]
    return []


def find_forbidden_terms(text: str) -> list[str]:
    return [term for term in FORBIDDEN_COPY_TERMS if term in text]
