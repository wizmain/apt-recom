"""슬라이드 렌더러 — 공용 8종을 시리즈별로 조합한다.

새 시리즈 추가 시 이 파일의 렌더러는 재사용하고
build_slides() 의 시리즈 분기만 확장한다.
폰트·폭 값은 textrules.TEXT_LIMITS 와 동일하게 유지할 것 (검증-렌더 정합).
"""

from __future__ import annotations

from PIL import Image

from scripts.insta_cards import textrules
from scripts.insta_cards.publication import Item, Publication, Series
from scripts.insta_cards.theme import (
    CANVAS_SIZE,
    COLOR_ACCENT_BLUE,
    COLOR_ACCENT_GREEN,
    COLOR_BAR_TRACK,
    COLOR_BG_TOP,
    COLOR_TEXT_LIGHT,
    COLOR_TEXT_WHITE,
    COLOR_ZEBRA,
    CONTENT_WIDTH,
    MARGIN_X,
    build_base_canvas,
    get_font,
    truncate_text,
)

LIST_SIZE = 5
CHIP_HEIGHT = 72
CHIP_GAP = 20
ROW_GAP = 12
TEASER_HEIGHT = 300  # 커버 하단 티저 블록 높이
COMPARISON_EMPHASIS_ROWS = 2  # 비교표 상단 강조 행 수 (가격·면적)


def cta_question(pub: Publication) -> str:
    if pub.series in (Series.BUDGET_CHOICE, Series.COMPARE):
        # MIN_ITEMS[COMPARE|BUDGET_CHOICE]=2 가 validate 에서 보장됨.
        # compare 는 지역 대결이므로 region 우선, 없으면 단지명.
        if pub.series is Series.BUDGET_CHOICE:
            name_a = pub.items[0].name
            name_b = pub.items[1].name
        else:
            name_a = pub.items[0].region or pub.items[0].name
            name_b = pub.items[1].region or pub.items[1].name
        return f"여러분이라면 {name_a} vs {name_b}?"
    return "내 조건으로 직접 찾아보기"


def _wrapped_text(canvas, text, field, y, color, line_height=None, x=MARGIN_X):
    """textrules 한도와 동일 폰트로 줄바꿈 렌더. 반환: 다음 y."""
    limit = textrules.TEXT_LIMITS[field]
    font = get_font(limit.font_weight, limit.font_size)
    lines = textrules.wrap_text(text, font, limit.max_width)
    lh = line_height or round(limit.font_size * 1.35)
    for line in lines[: limit.max_lines]:
        canvas.draw.text((x, y), line, font=font, fill=color)
        y += lh
    return y


def _bulleted_text(canvas, text, field, y, color):
    """불릿(·)은 MARGIN_X, 본문은 BULLET_INDENT 들여쓰기 — 검증 폭과 렌더 폭 동일."""
    limit = textrules.TEXT_LIMITS[field]
    font = get_font(limit.font_weight, limit.font_size)
    canvas.draw.text((MARGIN_X, y), "·", font=font, fill=color)
    return _wrapped_text(
        canvas, text, field, y, color, x=MARGIN_X + textrules.BULLET_INDENT
    )


def _teaser_cards(canvas, items: tuple[Item, ...], top: float) -> None:
    """비교형 커버 티저 — 후보 A/B 미니 카드 + 중앙 VS 배지."""
    gap = 28
    card_w = (CONTENT_WIDTH - gap) / 2
    tag_font = get_font("extrabold", 38)
    name_font = get_font("semibold", 31)
    region_font = get_font("regular", 25)
    price_font = get_font("extrabold", 46)
    sub_font = get_font("regular", 25)
    for i, item in enumerate(items[:2]):
        x = MARGIN_X + i * (card_w + gap)
        canvas.draw.rounded_rectangle(
            [x, top, x + card_w, top + TEASER_HEIGHT], radius=24, fill=COLOR_BAR_TRACK
        )
        canvas.draw.text(
            (x + 28, top + 24), "AB"[i], font=tag_font, fill=COLOR_ACCENT_BLUE
        )
        name = truncate_text(canvas.draw, item.name, name_font, card_w - 56)
        canvas.draw.text(
            (x + 28, top + 84), name, font=name_font, fill=COLOR_TEXT_WHITE
        )
        if item.region:
            canvas.draw.text(
                (x + 28, top + 130),
                item.region,
                font=region_font,
                fill=COLOR_TEXT_LIGHT,
            )
        value = truncate_text(
            canvas.draw, item.metrics[0].value, price_font, card_w - 56
        )
        canvas.draw.text(
            (x + 28, top + 182), value, font=price_font, fill=COLOR_ACCENT_GREEN
        )
        if len(item.metrics) > 1:
            sub = f"{item.metrics[1].label} {item.metrics[1].value}"
            sub = truncate_text(canvas.draw, sub, sub_font, card_w - 56)
            canvas.draw.text(
                (x + 28, top + 244), sub, font=sub_font, fill=COLOR_TEXT_LIGHT
            )
    # 중앙 VS 배지
    bx, by, r = CANVAS_SIZE / 2, top + TEASER_HEIGHT / 2, 40
    canvas.draw.ellipse(
        [bx - r, by - r, bx + r, by + r],
        fill=COLOR_BG_TOP,
        outline=COLOR_TEXT_LIGHT,
        width=2,
    )
    vs_font = get_font("bold", 30)
    w = canvas.draw.textlength("VS", font=vs_font)
    canvas.draw.text((bx - w / 2, by - 20), "VS", font=vs_font, fill=COLOR_TEXT_WHITE)


def _teaser_ranking(canvas, items: tuple[Item, ...], top: float) -> None:
    """랭킹형 커버 티저 — TOP 3 미리보기 리스트."""
    rows = items[:3]
    row_h = TEASER_HEIGHT / 3
    rank_font = get_font("extrabold", 36)
    name_font = get_font("semibold", 30)
    value_font = get_font("extrabold", 32)
    for i, item in enumerate(rows):
        ry = top + i * row_h
        if i % 2 == 0:
            canvas.draw.rounded_rectangle(
                [MARGIN_X - 16, ry, CANVAS_SIZE - MARGIN_X + 16, ry + row_h - 8],
                radius=14,
                fill=COLOR_ZEBRA,
            )
        ty = ry + (row_h - 44) / 2
        canvas.draw.text(
            (MARGIN_X, ty), f"{item.rank}", font=rank_font, fill=COLOR_ACCENT_BLUE
        )
        value = f"{item.metrics[0].value}{item.metrics[0].unit}"
        value_w = canvas.draw.textlength(value, font=value_font)
        name = truncate_text(
            canvas.draw, item.name, name_font, CONTENT_WIDTH - 64 - value_w - 40
        )
        canvas.draw.text(
            (MARGIN_X + 64, ty + 2), name, font=name_font, fill=COLOR_TEXT_WHITE
        )
        canvas.draw.text(
            (CANVAS_SIZE - MARGIN_X - value_w, ty),
            value,
            font=value_font,
            fill=COLOR_ACCENT_GREEN,
        )


def render_cover(pub: Publication) -> Image.Image:
    """L2 레이아웃 — 상단 대형 훅 + 하단 시리즈별 콘텐츠 티저 (하단 공백 제거)."""
    canvas = build_base_canvas(pub.eyebrow, [])
    y = canvas.content_top + 36
    y = _wrapped_text(canvas, pub.hook, "hook", y, COLOR_TEXT_WHITE)
    y += 20
    _wrapped_text(canvas, pub.summary, "summary", y, COLOR_TEXT_LIGHT)

    teaser_top = canvas.content_bottom - TEASER_HEIGHT - 56
    if pub.series in (Series.BUDGET_CHOICE, Series.COMPARE):
        _teaser_cards(canvas, pub.items, teaser_top)
    else:
        _teaser_ranking(canvas, pub.items, teaser_top)

    date_font = get_font("regular", 26)
    canvas.draw.text(
        (MARGIN_X, canvas.content_bottom - 36),
        f"데이터 기준일 {pub.data_as_of}",
        font=date_font,
        fill=COLOR_TEXT_LIGHT,
    )
    return canvas.image


def render_conditions(pub: Publication) -> Image.Image:
    canvas = build_base_canvas(pub.eyebrow, ["이 카드의 조건"])
    label_font = get_font("regular", 26)
    value_font = get_font("semibold", 30)
    y = canvas.content_top + 24
    for cond in pub.conditions:
        canvas.draw.rounded_rectangle(
            [MARGIN_X, y, MARGIN_X + CONTENT_WIDTH, y + CHIP_HEIGHT],
            radius=16,
            fill=COLOR_BAR_TRACK,
        )
        canvas.draw.text(
            (MARGIN_X + 24, y + 10), cond.label, font=label_font, fill=COLOR_TEXT_LIGHT
        )
        value = truncate_text(canvas.draw, cond.value, value_font, 420)
        value_w = canvas.draw.textlength(value, font=value_font)
        canvas.draw.text(
            (MARGIN_X + CONTENT_WIDTH - 24 - value_w, y + 18),
            value,
            font=value_font,
            fill=COLOR_TEXT_WHITE,
        )
        y += CHIP_HEIGHT + CHIP_GAP
    period_font = get_font("regular", 26)
    canvas.draw.text(
        (MARGIN_X, y + 12),
        f"{pub.period_label} · 기준일 {pub.data_as_of}",
        font=period_font,
        fill=COLOR_ACCENT_GREEN,
    )
    return canvas.image


def render_candidate(pub: Publication, item: Item, heading: str) -> Image.Image:
    canvas = build_base_canvas(pub.eyebrow, [heading])
    name_font = get_font("extrabold", 44)
    region_font = get_font("regular", 28)
    metric_label_font = get_font("regular", 26)
    metric_value_font = get_font("semibold", 30)
    reason_font = get_font("regular", 28)

    y = canvas.content_top + 8
    name = truncate_text(canvas.draw, item.name, name_font, CONTENT_WIDTH)
    canvas.draw.text((MARGIN_X, y), name, font=name_font, fill=COLOR_TEXT_WHITE)
    y += 58
    if item.region:
        canvas.draw.text(
            (MARGIN_X, y), item.region, font=region_font, fill=COLOR_TEXT_LIGHT
        )
        y += 46
    y += 12

    # metrics 를 남은 세로 공간에 균등 분배 (reasons 블록 몫은 제외) — 상단 몰림 방지
    reasons_height = len(item.reasons) * 44 + (16 if item.reasons else 0)
    metrics_bottom = canvas.content_bottom - reasons_height - 8
    metric_row_h = min(76, (metrics_bottom - y) / max(len(item.metrics), 1))
    for mi, metric in enumerate(item.metrics):
        ry = y + mi * metric_row_h
        if mi % 2 == 0:
            canvas.draw.rounded_rectangle(
                [
                    MARGIN_X - 16,
                    ry,
                    CANVAS_SIZE - MARGIN_X + 16,
                    ry + metric_row_h - 10,
                ],
                radius=12,
                fill=COLOR_ZEBRA,
            )
        ty = ry + (metric_row_h - 40) / 2
        canvas.draw.text(
            (MARGIN_X, ty + 2),
            metric.label,
            font=metric_label_font,
            fill=COLOR_TEXT_LIGHT,
        )
        value = f"{metric.value}{metric.unit}"
        value = truncate_text(canvas.draw, value, metric_value_font, 520)
        value_w = canvas.draw.textlength(value, font=metric_value_font)
        canvas.draw.text(
            (MARGIN_X + CONTENT_WIDTH - value_w, ty),
            value,
            font=metric_value_font,
            fill=COLOR_ACCENT_GREEN,
        )

    y = metrics_bottom + 8
    for reason in item.reasons:
        canvas.draw.text(
            (MARGIN_X, y), f"· {reason}", font=reason_font, fill=COLOR_TEXT_WHITE
        )
        y += 44
    return canvas.image


def render_ranking(
    pub: Publication, items: tuple[Item, ...], heading: str
) -> Image.Image:
    canvas = build_base_canvas(pub.eyebrow, [heading])
    rank_font = get_font("extrabold", 40)
    name_font = get_font("semibold", 32)
    meta_font = get_font("regular", 24)
    value_font = get_font("extrabold", 34)

    rows = items[:LIST_SIZE]
    row_height = (canvas.content_bottom - canvas.content_top) / LIST_SIZE
    for i, item in enumerate(rows):
        top = canvas.content_top + i * row_height
        if i % 2 == 0:
            canvas.draw.rounded_rectangle(
                [
                    MARGIN_X - 16,
                    top,
                    CANVAS_SIZE - MARGIN_X + 16,
                    top + row_height - 12,
                ],
                radius=14,
                fill=COLOR_ZEBRA,
            )
        y = top + (row_height - 84) / 2
        canvas.draw.text(
            (MARGIN_X, y), f"{item.rank}", font=rank_font, fill=COLOR_ACCENT_BLUE
        )
        name_x = MARGIN_X + 64
        name = truncate_text(
            canvas.draw, item.name, name_font, CONTENT_WIDTH - 64 - 280
        )
        canvas.draw.text((name_x, y), name, font=name_font, fill=COLOR_TEXT_WHITE)
        # 보조행: region 또는 두 번째 metric
        meta = item.region or (
            f"{item.metrics[1].label} {item.metrics[1].value}"
            if len(item.metrics) > 1
            else ""
        )
        if meta:
            canvas.draw.text(
                (name_x, y + 40), meta, font=meta_font, fill=COLOR_TEXT_LIGHT
            )
        # 우측 강조값: 첫 번째 metric
        value = f"{items[i].metrics[0].value}{items[i].metrics[0].unit}"
        value_w = canvas.draw.textlength(value, font=value_font)
        canvas.draw.text(
            (CANVAS_SIZE - MARGIN_X - value_w, y + 4),
            value,
            font=value_font,
            fill=COLOR_ACCENT_GREEN,
        )
    return canvas.image


def render_comparison(pub: Publication) -> Image.Image:
    """L3 레이아웃 — 표를 콘텐츠 영역 전체로 확장 + 지브라 + 상단 행 강조."""
    canvas = build_base_canvas(pub.eyebrow, ["한눈에 비교"])
    comp = pub.comparison
    header_font = get_font("semibold", 30)
    label_font = get_font("regular", 28)

    label_col_width = 300
    value_col_width = (CONTENT_WIDTH - label_col_width) / 2
    y = canvas.content_top + 12

    for col_i, col in enumerate(comp.columns):
        x = MARGIN_X + label_col_width + col_i * value_col_width
        name = truncate_text(canvas.draw, col.name, header_font, value_col_width - 16)
        canvas.draw.text(
            (x, y),
            name,
            font=header_font,
            fill=COLOR_ACCENT_BLUE if col_i else COLOR_ACCENT_GREEN,
        )
    table_top = y + 64
    table_bottom = canvas.content_bottom - 8
    row_height = (table_bottom - table_top) / max(len(comp.row_labels), 1)

    for row_i, row_label in enumerate(comp.row_labels):
        ry = table_top + row_i * row_height
        if row_i % 2 == 0:
            canvas.draw.rounded_rectangle(
                [MARGIN_X - 16, ry, CANVAS_SIZE - MARGIN_X + 16, ry + row_height - 10],
                radius=12,
                fill=COLOR_ZEBRA,
            )
        emphasized = row_i < COMPARISON_EMPHASIS_ROWS
        value_font = get_font(
            "extrabold" if emphasized else "semibold", 34 if emphasized else 28
        )
        ty = ry + (row_height - value_font.size) / 2 - 6
        label = truncate_text(canvas.draw, row_label, label_font, label_col_width - 20)
        canvas.draw.text(
            (MARGIN_X, ty + 2), label, font=label_font, fill=COLOR_TEXT_LIGHT
        )
        for col_i, col in enumerate(comp.columns):
            x = MARGIN_X + label_col_width + col_i * value_col_width
            value = truncate_text(
                canvas.draw, col.values[row_i], value_font, value_col_width - 16
            )
            canvas.draw.text((x, ty), value, font=value_font, fill=COLOR_TEXT_WHITE)
    return canvas.image


def render_why(pub: Publication) -> Image.Image:
    canvas = build_base_canvas(pub.eyebrow, ["왜 이런 결과일까"])
    y = canvas.content_top + 24
    for why in pub.narrative.why:
        y = _bulleted_text(canvas, why, "why", y, COLOR_TEXT_WHITE)
        y += 24
    return canvas.image


def render_fit(pub: Publication) -> Image.Image:
    """박스 높이를 내용에 맞추고 세로 중앙 배치 — 하단 공백 제거."""
    canvas = build_base_canvas(pub.eyebrow, ["어떤 사람에게 맞을까"])
    fit = pub.narrative.fit_for
    half_width = CONTENT_WIDTH / 2 - 20
    font = get_font("regular", 30)
    max_lines = textrules.TEXT_LIMITS["fit_for"].max_lines
    wrapped = [
        textrules.wrap_text(text, font, half_width - 48)[:max_lines]
        for text in (fit.a, fit.b)
    ]
    line_count = max(len(lines) for lines in wrapped)
    box_h = 64 + line_count * 42
    area = canvas.content_bottom - canvas.content_top
    box_top = canvas.content_top + (area - box_h) / 2
    for i, lines in enumerate(wrapped):
        x = MARGIN_X + i * (half_width + 40)
        canvas.draw.rounded_rectangle(
            [x, box_top, x + half_width, box_top + box_h],
            radius=20,
            fill=COLOR_BAR_TRACK,
        )
        ty = box_top + 32
        for line in lines:
            canvas.draw.text((x + 24, ty), line, font=font, fill=COLOR_TEXT_WHITE)
            ty += 42
    return canvas.image


def render_caveats(pub: Publication) -> Image.Image:
    canvas = build_base_canvas(pub.eyebrow, ["읽을 때 주의할 점"])
    y = canvas.content_top + 16
    section_font = get_font("semibold", 28)
    canvas.draw.text(
        (MARGIN_X, y), "이렇게 골랐습니다", font=section_font, fill=COLOR_ACCENT_GREEN
    )
    y += 46
    for m in pub.methodology:
        y = _bulleted_text(canvas, m, "methodology", y, COLOR_TEXT_LIGHT)
        y += 8
    y += 24
    canvas.draw.text(
        (MARGIN_X, y), "주의하세요", font=section_font, fill=COLOR_ACCENT_BLUE
    )
    y += 46
    for c in pub.caveats:
        y = _bulleted_text(canvas, c, "caveat", y, COLOR_TEXT_LIGHT)
        y += 8
    return canvas.image


def render_cta(pub: Publication) -> Image.Image:
    canvas = build_base_canvas(pub.eyebrow, [])
    question_font = get_font("extrabold", 52)
    action_font = get_font("semibold", 34)
    note_font = get_font("regular", 26)

    y = canvas.content_top + 160
    question = cta_question(pub)
    lines = textrules.wrap_text(question, question_font, CONTENT_WIDTH)
    for line in lines[:3]:
        w = canvas.draw.textlength(line, font=question_font)
        canvas.draw.text(
            ((CANVAS_SIZE - w) / 2, y), line, font=question_font, fill=COLOR_TEXT_WHITE
        )
        y += 70

    y += 60
    action = "댓글로 알려주세요 · 프로필 링크에서 내 조건으로 확인"
    w = canvas.draw.textlength(action, font=action_font)
    canvas.draw.text(
        ((CANVAS_SIZE - w) / 2, y), action, font=action_font, fill=COLOR_ACCENT_GREEN
    )

    note = "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다"
    w = canvas.draw.textlength(note, font=note_font)
    canvas.draw.text(
        ((CANVAS_SIZE - w) / 2, canvas.content_bottom - 40),
        note,
        font=note_font,
        fill=COLOR_TEXT_LIGHT,
    )
    return canvas.image


def build_slides(pub: Publication) -> list[tuple[str, Image.Image]]:
    if pub.series is Series.BUDGET_CHOICE:
        return [
            ("01-cover.png", render_cover(pub)),
            ("02-conditions.png", render_conditions(pub)),
            ("03-candidate-a.png", render_candidate(pub, pub.items[0], "후보 A")),
            ("04-candidate-b.png", render_candidate(pub, pub.items[1], "후보 B")),
            ("05-comparison.png", render_comparison(pub)),
            ("06-why.png", render_why(pub)),
            ("07-fit.png", render_fit(pub)),
            ("08-caveats.png", render_caveats(pub)),
            ("09-cta.png", render_cta(pub)),
        ]
    if pub.series is Series.COMPARE:
        return [
            ("01-cover.png", render_cover(pub)),
            ("02-conditions.png", render_conditions(pub)),
            (
                "03-candidate-a.png",
                render_candidate(pub, pub.items[0], "지역 A 추천 1위"),
            ),
            (
                "04-candidate-b.png",
                render_candidate(pub, pub.items[1], "지역 B 추천 1위"),
            ),
            ("05-comparison.png", render_comparison(pub)),
            ("06-why.png", render_why(pub)),
            ("07-caveats.png", render_caveats(pub)),
            ("08-cta.png", render_cta(pub)),
        ]
    if pub.series is Series.LIFESTYLE:
        return [
            ("01-cover.png", render_cover(pub)),
            ("02-conditions.png", render_conditions(pub)),
            ("03-ranking.png", render_ranking(pub, pub.items, "추천 후보")),
            ("04-candidate-1.png", render_candidate(pub, pub.items[0], "추천 1")),
            ("05-candidate-2.png", render_candidate(pub, pub.items[1], "추천 2")),
            ("06-candidate-3.png", render_candidate(pub, pub.items[2], "추천 3")),
            ("07-caveats.png", render_caveats(pub)),
            ("08-cta.png", render_cta(pub)),
        ]
    if pub.series is Series.VALUE:
        return [
            ("01-cover.png", render_cover(pub)),
            ("02-conditions.png", render_conditions(pub)),
            ("03-ranking.png", render_ranking(pub, pub.items, "숨은 가성비 TOP 5")),
            ("04-why.png", render_why(pub)),
            ("05-caveats.png", render_caveats(pub)),
            ("06-cta.png", render_cta(pub)),
        ]
    if pub.series is Series.TRADE_TOP:
        return [
            ("01-cover.png", render_cover(pub)),
            ("02-conditions.png", render_conditions(pub)),
            ("03-ranking.png", render_ranking(pub, pub.items, "신고 최고가 TOP 5")),
            (
                "04-ranking-hot.png",
                render_ranking(pub, pub.secondary_items, "신고 급증 동네 TOP 5"),
            ),
            ("05-caveats.png", render_caveats(pub)),
            ("06-cta.png", render_cta(pub)),
        ]
    raise KeyError(f"슬라이드 구성이 정의되지 않은 시리즈: {pub.series}")
