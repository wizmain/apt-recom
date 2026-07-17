"""디자인 토큰 · 폰트 · 배경 · 포맷 유틸 — 렌더 코드는 이 상수만 참조한다.

색/폰트는 브랜드 아이콘(web/toss-miniapp/assets/jiptori-app-icon*)과 통일.
기존 scripts/generate_insta_cards.py 의 토큰을 이관했다 (shim 전환은 cli 구현 시).
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

CANVAS_SIZE = 1080
MARGIN_X = 72
CONTENT_WIDTH = CANVAS_SIZE - MARGIN_X * 2  # 936

COLOR_BG_TOP = (15, 27, 61)  # #0f1b3d
COLOR_BG_BOTTOM = (27, 17, 64)  # #1b1140
COLOR_ACCENT_BLUE = (96, 165, 250)  # #60a5fa
COLOR_ACCENT_GREEN = (52, 211, 153)  # #34d399
COLOR_TEXT_WHITE = (255, 255, 255)
COLOR_TEXT_LIGHT = (219, 234, 254)  # #dbeafe
COLOR_TEXT_GRAY = (148, 163, 184)
COLOR_BAR_TRACK = (40, 51, 92)
COLOR_ZEBRA = (22, 34, 70)  # 표·리스트 짝수행 배경 (배경보다 살짝 밝은 네이비)

FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
# index 는 AppleSDGothicNeo.ttc 실측 결과(0=Regular,2=Medium,4=SemiBold,
# 6=Bold,14=ExtraBold) — 폰트 교체 시 재실측할 것.
FONT_WEIGHT_INDEX = {
    "regular": 0,
    "medium": 2,
    "semibold": 4,
    "bold": 6,
    "extrabold": 14,
}

FOOTER_BRAND = "apt-recom.kr"
FOOTER_DISCLAIMER = "공공데이터 기반 · 투자 자문이 아닙니다"

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_measuring_image = Image.new("RGB", (1, 1))


def get_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(
            FONT_PATH, size, index=FONT_WEIGHT_INDEX[weight]
        )
    return _font_cache[key]


def measuring_draw() -> ImageDraw.ImageDraw:
    """텍스트 폭 실측 전용 draw (1×1 더미 이미지)."""
    return ImageDraw.Draw(_measuring_image)


def make_gradient_background() -> Image.Image:
    img = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), COLOR_BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(CANVAS_SIZE):
        t = y / (CANVAS_SIZE - 1)
        r = round(COLOR_BG_TOP[0] + (COLOR_BG_BOTTOM[0] - COLOR_BG_TOP[0]) * t)
        g = round(COLOR_BG_TOP[1] + (COLOR_BG_BOTTOM[1] - COLOR_BG_TOP[1]) * t)
        b = round(COLOR_BG_TOP[2] + (COLOR_BG_BOTTOM[2] - COLOR_BG_TOP[2]) * t)
        draw.line([(0, y), (CANVAS_SIZE, y)], fill=(r, g, b))
    return img


def truncate_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: float
) -> str:
    """폭 초과 시 말줄임(…). 데이터 유래 고유명(단지명·지역명) 전용 —
    서사 필드는 textrules 검증으로 초과 자체를 차단한다."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    truncated = text
    while truncated and draw.textlength(truncated + ellipsis, font=font) > max_width:
        truncated = truncated[:-1]
    return truncated + ellipsis


def format_eok(manwon: int) -> str:
    """만원 단위 정수 → '4억 3,500만원'."""
    eok, remainder = divmod(manwon, 10000)
    if eok <= 0:
        return f"{manwon:,}만원"
    if remainder:
        return f"{eok}억 {remainder:,}만원"
    return f"{eok}억"


def format_price_per_m2(won_per_m2: float) -> str:
    """원/㎡ → '만원/㎡'."""
    return f"{round(won_per_m2 / 10000):,}만원/㎡"


@dataclass
class CardCanvas:
    image: Image.Image
    draw: ImageDraw.ImageDraw
    content_top: int
    content_bottom: int


def build_base_canvas(eyebrow: str, title_lines: list[str]) -> CardCanvas:
    """상단 시리즈 라벨 + 타이틀(2줄 이내) + 하단 고정 푸터 베이스 캔버스."""
    img = make_gradient_background()
    draw = ImageDraw.Draw(img)

    label_font = get_font("semibold", 30)
    draw.text((MARGIN_X, 72), eyebrow, font=label_font, fill=COLOR_ACCENT_GREEN)

    title_font = get_font("extrabold", 60)
    title_y = 130
    for line in title_lines[:2]:
        draw.text((MARGIN_X, title_y), line, font=title_font, fill=COLOR_TEXT_WHITE)
        title_y += 74

    content_top = title_y + 24
    content_bottom = draw_footer(draw, img.size)
    return CardCanvas(
        image=img, draw=draw, content_top=content_top, content_bottom=content_bottom
    )


def draw_footer(draw: ImageDraw.ImageDraw, size: tuple[int, int]) -> int:
    width, height = size
    disclaimer_font = get_font("regular", 24)
    brand_font = get_font("bold", 32)

    disclaimer_y = height - 64
    brand_y = disclaimer_y - 44

    brand_w = draw.textlength(FOOTER_BRAND, font=brand_font)
    draw.text(
        ((width - brand_w) / 2, brand_y),
        FOOTER_BRAND,
        font=brand_font,
        fill=COLOR_TEXT_WHITE,
    )
    disclaimer_w = draw.textlength(FOOTER_DISCLAIMER, font=disclaimer_font)
    draw.text(
        ((width - disclaimer_w) / 2, disclaimer_y),
        FOOTER_DISCLAIMER,
        font=disclaimer_font,
        fill=COLOR_TEXT_GRAY,
    )
    return brand_y - 40
