# 인스타 카드뉴스 5시리즈 캐러셀 생성기 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 인스타그램 정기 발행 5개 시리즈(trade_top·compare·value·budget_choice·lifestyle)를 6~9장 캐러셀 PNG + 발행 스냅샷 JSON으로 산출하는 `scripts/insta_cards/` 패키지를 구현한다.

**Architecture:** Publication(불변 dataclass, 검증 내장)을 단일 진실원으로 두고, 시리즈 모듈이 fetch→선정→Publication 조립을 담당하며, 공용 슬라이드 렌더러 8종이 이미지를, output 모듈이 원자적 쓰기를 담당한다. 이미지와 JSON은 같은 Publication을 소비한다.

**Tech Stack:** Python 3.12, Pillow(렌더), requests(운영 API), psycopg2 via `batch.db`(로컬 DB), PyYAML(문구 오버라이드), unittest(테스트).

**Spec:** `docs/superpowers/specs/2026-07-13-insta-cards-carousel-design.md` — 본 계획의 모든 요구사항 원본.

## Global Constraints

- 실행 cwd는 항상 워크트리 루트(`.worktrees/instagram-content-landing/`). 가상환경은 워크스페이스 공용 `../../.venv`만 사용 — 새 venv 생성 금지.
- 테스트: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
- 린트/포맷 검증: `../../.venv/bin/ruff check scripts/insta_cards scripts/tests` + `../../.venv/bin/ruff format --check scripts/insta_cards scripts/tests` (구현 중 수정은 `ruff format` / `ruff check --fix`)
- 변수/키 명명: snake_case, 소문자 시작. API/JSON 노출 이름에 `_` prefix 금지. TypeScript 아님 — Python만.
- 하드코딩 금지: 색·폰트·기간·임계치는 모듈 상수로만 정의. fallback 금지: 데이터 부족은 예외로 발행 중단, 조용한 축소 발행 금지.
- 금지어(투자 단정): `("오를", "저평가", "무조건", "확실", "급등", "투자 추천")` — hook/why/fit_for에 포함 시 검증 실패.
- 캔버스 1080×1080, footer 문구 `apt-recom.kr` / `공공데이터 기반 · 투자 자문이 아닙니다` 전 장 유지.
- 커밋: Conventional Commits(`feat(insta):` 등), AI 작업자 표기 금지.
- 시리즈 내부 enum 값은 underscore(`trade_top`), CLI 인자·slug는 하이픈(`trade-top`).
- 로컬 DB 접근은 `batch.db`의 `get_connection()`/`query_all(conn, sql, params)`만 사용 (raw SQL, `%s` placeholder).
- 운영 API base: `https://api.apt-recom.kr`, timeout 15초, 실패 시 재시도 없이 예외.

## File Map (전체 산출물)

| 파일 | 책임 | 생성 Task |
|---|---|---|
| `scripts/insta_cards/__init__.py` | 패키지 마커 (빈 파일) | 1 |
| `scripts/insta_cards/theme.py` | 디자인 토큰·폰트·배경·포맷 유틸 (기존 이관) | 1 |
| `scripts/insta_cards/textrules.py` | 텍스트 한도·줄바꿈·금지어 | 2 |
| `scripts/insta_cards/publication.py` | Publication 모델 + validate + 직렬화 | 3 |
| `scripts/insta_cards/copywriting.py` | 서사 문구 템플릿 + YAML 오버라이드 | 4 |
| `scripts/insta_cards/datasources.py` | 운영 API 클라이언트 + 로컬 거래 조회 + metrics 추출 | 5 |
| `scripts/insta_cards/slides.py` | 슬라이드 렌더러 8종 + 시리즈별 조합 | 6 |
| `scripts/insta_cards/output.py` | 원자적 쓰기 + 전역 slug 충돌 검사 | 7 |
| `scripts/insta_cards/series/__init__.py` | 패키지 마커 | 8 |
| `scripts/insta_cards/series/trade_top.py` | 최고가 + 급증(직전 기간 대비) | 8 |
| `scripts/insta_cards/series/value.py` | 숨은 가성비 | 9 |
| `scripts/insta_cards/series/compare.py` | 지역 집계 비교 + 1위 단지 | 10 |
| `scripts/insta_cards/series/budget_choice.py` | 같은 예산 A/B (적격 집합 → 대표 선정) | 11 |
| `scripts/insta_cards/series/lifestyle.py` | 넛지 프로필 추천 | 12 |
| `scripts/insta_cards/cli.py` + `__main__.py` | CLI 진입점 + 디스패치 | 13 |
| `scripts/generate_insta_cards.py` | 기존 파일 → deprecation shim으로 교체 | 13 |
| `scripts/tests/__init__.py`, `scripts/tests/test_insta_cards.py` | 단일 테스트 파일 (클래스 = 모듈 단위) | 1~13 누적 |
| `requirements.txt` | `PyYAML` 명시 추가 (이미 설치돼 있음 — 직접 의존 선언만) | 13 |

시리즈별 슬라이드 구성과 파일명 (Task 6에서 구현, 전 시리즈 공통 계약):

| 시리즈 | 파일명 순서 |
|---|---|
| budget_choice (9장) | 01-cover, 02-conditions, 03-candidate-a, 04-candidate-b, 05-comparison, 06-why, 07-fit, 08-caveats, 09-cta |
| compare (8장) | 01-cover, 02-conditions, 03-candidate-a, 04-candidate-b, 05-comparison, 06-why, 07-caveats, 08-cta |
| lifestyle (8장) | 01-cover, 02-conditions, 03-ranking, 04-candidate-1, 05-candidate-2, 06-candidate-3, 07-caveats, 08-cta |
| value (6장) | 01-cover, 02-conditions, 03-ranking, 04-why, 05-caveats, 06-cta |
| trade_top (6장) | 01-cover, 02-conditions, 03-ranking, 04-ranking-hot, 05-caveats, 06-cta |

`cover_image`는 항상 `"01-cover.png"`.

---

### Task 1: 패키지 골격 + theme.py 이관

**Files:**
- Create: `scripts/insta_cards/__init__.py` (빈 파일)
- Create: `scripts/insta_cards/theme.py`
- Create: `scripts/tests/__init__.py` (빈 파일)
- Create: `scripts/tests/test_insta_cards.py`

**Interfaces:**
- Consumes: 없음 (기존 `scripts/generate_insta_cards.py`의 디자인 토큰을 이관 — 기존 파일은 Task 13까지 수정하지 않는다)
- Produces (이후 전 Task가 사용):
  - 상수 `CANVAS_SIZE=1080`, `MARGIN_X=72`, `CONTENT_WIDTH=936`, `COLOR_BG_TOP`, `COLOR_BG_BOTTOM`, `COLOR_ACCENT_BLUE`, `COLOR_ACCENT_GREEN`, `COLOR_TEXT_WHITE`, `COLOR_TEXT_LIGHT`, `COLOR_TEXT_GRAY`, `COLOR_BAR_TRACK`, `FOOTER_BRAND`, `FOOTER_DISCLAIMER`
  - `get_font(weight: str, size: int) -> ImageFont.FreeTypeFont`
  - `make_gradient_background() -> Image.Image`
  - `truncate_text(draw, text: str, font, max_width: float) -> str`
  - `format_eok(manwon: int) -> str`, `format_price_per_m2(won_per_m2: float) -> str`
  - `@dataclass CardCanvas(image, draw, content_top: int, content_bottom: int)`
  - `build_base_canvas(eyebrow: str, title_lines: list[str]) -> CardCanvas`
  - `measuring_draw() -> ImageDraw.ImageDraw` (1×1 더미 이미지의 draw — 텍스트 폭 실측용)

- [ ] **Step 1: 패키지 마커 생성**

```bash
touch scripts/insta_cards/__init__.py scripts/tests/__init__.py
```

- [ ] **Step 2: 실패하는 테스트 작성** — `scripts/tests/test_insta_cards.py` 신규:

```python
"""insta_cards 패키지 테스트 — 클래스 1개 = 모듈 1개."""

import unittest


class TestTheme(unittest.TestCase):
    def test_format_eok(self):
        from scripts.insta_cards import theme

        self.assertEqual(theme.format_eok(43500), "4억 3,500만원")
        self.assertEqual(theme.format_eok(70000), "7억")
        self.assertEqual(theme.format_eok(9500), "9,500만원")

    def test_format_price_per_m2(self):
        from scripts.insta_cards import theme

        self.assertEqual(theme.format_price_per_m2(12345678.0), "1,235만원/㎡")

    def test_truncate_text_returns_ellipsis_when_too_wide(self):
        from scripts.insta_cards import theme

        draw = theme.measuring_draw()
        font = theme.get_font("semibold", 34)
        long_name = "아주아주아주아주긴한글단지이름테스트" * 3
        result = theme.truncate_text(draw, long_name, font, 300)
        self.assertTrue(result.endswith("…"))
        self.assertLessEqual(draw.textlength(result, font=font), 300)

    def test_build_base_canvas_dimensions(self):
        from scripts.insta_cards import theme

        canvas = theme.build_base_canvas("시리즈 라벨", ["타이틀 1행", "타이틀 2행"])
        self.assertEqual(canvas.image.size, (1080, 1080))
        self.assertGreater(canvas.content_bottom, canvas.content_top)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: 4 FAIL/ERROR — `ModuleNotFoundError: No module named 'scripts.insta_cards.theme'`

- [ ] **Step 4: theme.py 구현** — 기존 `scripts/generate_insta_cards.py:36-202`의 디자인 토큰·유틸을 이관 (기존 파일은 건드리지 않고 복사). 변경점: `build_card_canvas` → `build_base_canvas`(인자명 `eyebrow`), `_draw_footer` → `draw_footer`(모듈 간 공용), `measuring_draw()`·`CONTENT_WIDTH` 추가.

```python
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
```

- [ ] **Step 5: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (4 tests)

- [ ] **Step 6: 커밋**

```bash
git add scripts/insta_cards/__init__.py scripts/insta_cards/theme.py scripts/tests/__init__.py scripts/tests/test_insta_cards.py
git commit -m "feat(insta): 캐러셀 생성기 패키지 골격 + 디자인 토큰 이관"
```

---

### Task 2: textrules.py — 텍스트 한도·줄바꿈·금지어

**Files:**
- Create: `scripts/insta_cards/textrules.py`
- Modify: `scripts/tests/test_insta_cards.py` (TestTextRules 클래스 추가)

**Interfaces:**
- Consumes: `theme.get_font`, `theme.measuring_draw`, `theme.CONTENT_WIDTH`
- Produces:
  - `FORBIDDEN_COPY_TERMS: tuple[str, ...]` — `("오를", "저평가", "무조건", "확실", "급등", "투자 추천")`
  - `@dataclass(frozen=True) TextLimit(font_weight: str, font_size: int, max_width: int, max_lines: int)`
  - `TEXT_LIMITS: dict[str, TextLimit]` — 키: `"hook" "summary" "condition_value" "reason" "methodology" "caveat" "why" "fit_for"`
  - `MAX_CONDITIONS=6, MAX_REASONS=3, MAX_METRICS=7, MAX_METHODOLOGY=4, MAX_CAVEATS=4, MAX_WHY=3`
  - `wrap_text(text: str, font, max_width: float) -> list[str]` — 공백 우선, 안 되면 글자 단위 줄바꿈
  - `check_field(field: str, text: str) -> list[str]` — 한도 위반 메시지 목록 (빈 리스트 = 통과)
  - `find_forbidden_terms(text: str) -> list[str]`

- [ ] **Step 1: 실패하는 테스트 작성** — `TestTextRules` 클래스 추가:

```python
class TestTextRules(unittest.TestCase):
    def test_wrap_text_splits_long_korean(self):
        from scripts.insta_cards import textrules, theme

        font = theme.get_font("regular", 28)
        lines = textrules.wrap_text("가나다라마바사 아자차카타파하 " * 10, font, 400)
        draw = theme.measuring_draw()
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(draw.textlength(line, font=font), 400)

    def test_check_field_passes_short_hook(self):
        from scripts.insta_cards import textrules

        self.assertEqual(textrules.check_field("hook", "7억으로 어디까지?"), [])

    def test_check_field_rejects_overflow_hook(self):
        from scripts.insta_cards import textrules

        errors = textrules.check_field("hook", "아주 긴 훅 문장 " * 30)
        self.assertEqual(len(errors), 1)
        self.assertIn("hook", errors[0])

    def test_check_field_rejects_empty(self):
        from scripts.insta_cards import textrules

        self.assertEqual(len(textrules.check_field("summary", "  ")), 1)

    def test_check_field_unknown_field_raises(self):
        from scripts.insta_cards import textrules

        with self.assertRaises(KeyError):
            textrules.check_field("no_such_field", "text")

    def test_find_forbidden_terms(self):
        from scripts.insta_cards import textrules

        self.assertEqual(
            textrules.find_forbidden_terms("무조건 오를 아파트"), ["오를", "무조건"]
        )
        self.assertEqual(textrules.find_forbidden_terms("가격 대비 생활점수"), [])
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestTextRules -v`
Expected: ERROR — `ModuleNotFoundError: ... textrules`

- [ ] **Step 3: textrules.py 구현**

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (10 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/insta_cards/textrules.py scripts/tests/test_insta_cards.py
git commit -m "feat(insta): 텍스트 한도·줄바꿈·금지어 규칙"
```

---

### Task 3: publication.py — 모델 + 검증 + 직렬화

**Files:**
- Create: `scripts/insta_cards/publication.py`
- Modify: `scripts/tests/test_insta_cards.py` (TestPublication 클래스 + 공용 픽스처 함수 추가)

**Interfaces:**
- Consumes: `textrules.check_field`, `textrules.find_forbidden_terms`, `textrules.MAX_*`
- Produces (전 시리즈·slides·output·cli가 사용):
  - `SCHEMA_VERSION = 1`
  - `class Series(str, Enum)`: `TRADE_TOP="trade_top"`, `COMPARE="compare"`, `VALUE="value"`, `BUDGET_CHOICE="budget_choice"`, `LIFESTYLE="lifestyle"`
  - `SERIES_CLI_NAMES: dict[str, Series]` — `{"trade-top": TRADE_TOP, "compare": COMPARE, "value": VALUE, "budget-choice": BUDGET_CHOICE, "lifestyle": LIFESTYLE}`
  - `SERIES_SLUGS: dict[Series, str]` — 역방향 하이픈 표기
  - `FILTER_ALLOWLIST = frozenset({"min_area","max_area","min_price","max_price","min_floor","min_hhld","max_hhld","built_after","built_before"})`
  - `MIN_ITEMS: dict[Series, int]` — `{TRADE_TOP: 5, VALUE: 5, LIFESTYLE: 3, COMPARE: 2, BUDGET_CHOICE: 2}`
  - frozen dataclass들: `Metric(label, value, unit)`, `Condition(label, value)`, `Item(rank: int, name: str, region: str | None, pnu: str | None, metrics: tuple[Metric, ...], reasons: tuple[str, ...])`, `MapCta(id, label, nudges: tuple[str, ...], sigungu_code: str | None, region_label: str | None, filters: dict)`, `ComparisonColumn(name, values: tuple[str, ...])`, `Comparison(row_labels: tuple[str, ...], columns: tuple[ComparisonColumn, ...])`, `FitFor(a: str, b: str)`, `Narrative(why: tuple[str, ...], fit_for: FitFor | None)`
  - `Publication` frozen dataclass — 필드 순서: `schema_version, slug, status, series, title, eyebrow, hook, summary, generated_at, published_at, data_as_of, period_label, cover_image, cover_alt, conditions, items, secondary_items, comparison, narrative, methodology, caveats, map_ctas`
  - `class PublicationValidationError(ValueError)` — `.errors: list[str]`
  - `validate(pub: Publication) -> None` — 위반 시 PublicationValidationError (전체 위반 목록 수집 후 일괄 raise)
  - `to_json_dict(pub: Publication) -> dict` — Enum→value 변환 포함
- 검증 규칙 (spec §7): 필수 문자열 비어있지 않음 / status∈{draft,published}, published↔published_at 정합 / slug `^[a-z0-9]+(-[a-z0-9]+)*$` / rank 1부터 연속 / MIN_ITEMS / trade_top만 secondary_items 필수(5개)·다른 시리즈는 None / pnu `^\d{19}$` / budget_choice: comparison 필수 + row_labels == 각 item.metrics 라벨 / compare: comparison 필수 + columns 2개 / narrative.why: value·compare·budget_choice ≥1 / fit_for: budget_choice만 필수, 그 외 None / map_ctas: trade_top 빈 배열 허용·그 외 ≥1, id 유일, nudges ≥1, filters 키 allowlist / 금지어(hook·why·fit_for) / 텍스트 한도(hook·summary·condition value·reason·methodology·caveat·why·fit_for) / 개수 한도(MAX_*) / data_as_of `YYYY-MM-DD` + 미래 금지 / cover_image == "01-cover.png"

- [ ] **Step 1: 실패하는 테스트 작성** — 파일 상단에 공용 픽스처, 클래스 추가:

```python
def make_valid_value_publication(**overrides):
    """value 시리즈 기준 유효 Publication 픽스처. overrides 로 필드 교체."""
    from scripts.insta_cards import publication as p

    items = tuple(
        p.Item(
            rank=i + 1,
            name=f"단지{i + 1}",
            region="서울 노원구",
            pnu=f"{1111111111111111110 + i:d}",
            metrics=(p.Metric("㎡당 가격", "1,000", "만원/㎡"),),
            reasons=("지하철 도보권",),
        )
        for i in range(5)
    )
    base = dict(
        schema_version=p.SCHEMA_VERSION,
        slug="value-seoul-20260713",
        status="draft",
        series=p.Series.VALUE,
        title="숨은 가성비 TOP 5 — 서울",
        eyebrow="가성비 랭킹",
        hook="가격은 낮은데 생활점수는 높은 단지 5곳",
        summary="서울에서 ㎡당 가격이 낮고 가성비 점수가 높은 단지를 골랐습니다.",
        generated_at="2026-07-13T10:00:00",
        published_at=None,
        data_as_of="2026-07-13",
        period_label="가성비 넛지 상위 30 후보 기준",
        cover_image="01-cover.png",
        cover_alt="서울 숨은 가성비 아파트 TOP 5 카드",
        conditions=(p.Condition("지역", "서울"), p.Condition("최소 세대수", "100세대")),
        items=items,
        secondary_items=None,
        comparison=None,
        narrative=p.Narrative(why=("상위 후보 대비 ㎡당 가격이 낮습니다.",), fit_for=None),
        methodology=("가성비 넛지 상위 30개 후보 중 ㎡당 가격 오름차순 5곳",),
        caveats=("투자 자문이 아닙니다.", "신고 지연으로 최근 거래가 늦게 반영될 수 있습니다."),
        map_ctas=(
            p.MapCta(
                id="map-main",
                label="같은 조건으로 지도에서 보기",
                nudges=("cost",),
                sigungu_code=None,
                region_label="서울",
                filters={"min_hhld": 100},
            ),
        ),
    )
    base.update(overrides)
    return p.Publication(**base)


class TestPublication(unittest.TestCase):
    def _errors(self, **overrides):
        from scripts.insta_cards import publication as p

        try:
            p.validate(make_valid_value_publication(**overrides))
        except p.PublicationValidationError as e:
            return e.errors
        return []

    def test_valid_publication_passes(self):
        self.assertEqual(self._errors(), [])

    def test_slug_format(self):
        self.assertTrue(any("slug" in e for e in self._errors(slug="Bad_Slug")))

    def test_published_requires_published_at(self):
        self.assertTrue(
            any("published_at" in e for e in self._errors(status="published"))
        )

    def test_rank_must_be_sequential(self):
        from scripts.insta_cards import publication as p

        pub = make_valid_value_publication()
        broken = list(pub.items)
        broken[2] = p.Item(
            rank=99, name=broken[2].name, region=broken[2].region,
            pnu=broken[2].pnu, metrics=broken[2].metrics, reasons=broken[2].reasons,
        )
        self.assertTrue(any("rank" in e for e in self._errors(items=tuple(broken))))

    def test_min_items(self):
        pub = make_valid_value_publication()
        self.assertTrue(any("items" in e for e in self._errors(items=pub.items[:3])))

    def test_pnu_format(self):
        from scripts.insta_cards import publication as p

        pub = make_valid_value_publication()
        bad = p.Item(rank=1, name="x", region=None, pnu="123", metrics=pub.items[0].metrics, reasons=())
        items = (bad,) + tuple(
            p.Item(rank=i + 2, name=f"y{i}", region=None, pnu=None,
                   metrics=pub.items[0].metrics, reasons=())
            for i in range(4)
        )
        self.assertTrue(any("pnu" in e for e in self._errors(items=items)))

    def test_forbidden_term_in_hook(self):
        self.assertTrue(
            any("금지" in e for e in self._errors(hook="무조건 오를 단지 5곳"))
        )

    def test_caveats_required(self):
        self.assertTrue(any("caveats" in e for e in self._errors(caveats=())))

    def test_map_ctas_required_for_non_trade_top(self):
        self.assertTrue(any("map_ctas" in e for e in self._errors(map_ctas=())))

    def test_filter_allowlist(self):
        from scripts.insta_cards import publication as p

        cta = p.MapCta(
            id="map-main", label="지도", nudges=("cost",),
            sigungu_code=None, region_label=None, filters={"evil_key": 1},
        )
        self.assertTrue(any("filters" in e for e in self._errors(map_ctas=(cta,))))

    def test_data_as_of_future_rejected(self):
        self.assertTrue(any("data_as_of" in e for e in self._errors(data_as_of="2099-01-01")))

    def test_to_json_dict_serializes_enum(self):
        from scripts.insta_cards import publication as p

        d = p.to_json_dict(make_valid_value_publication())
        self.assertEqual(d["series"], "value")
        self.assertEqual(d["schema_version"], 1)
        import json

        json.dumps(d, ensure_ascii=False)  # 직렬화 가능해야 함
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestPublication -v`
Expected: ERROR — `ModuleNotFoundError: ... publication`

- [ ] **Step 3: publication.py 구현**

```python
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
        errors.extend(f"{fieldname}: {msg}" for msg in textrules.check_field(rule, value))

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
                errors.append(f"{name}: rank 는 1부터 연속이어야 함 (index {idx} = rank {item.rank})")
            if item.pnu is not None and not PNU_PATTERN.match(item.pnu):
                errors.append(f"{name}[{idx}].pnu: 19자리 숫자가 아님 — '{item.pnu}'")
            if not item.metrics or len(item.metrics) > textrules.MAX_METRICS:
                errors.append(f"{name}[{idx}].metrics: 1~{textrules.MAX_METRICS}개 필요")
            if len(item.reasons) > textrules.MAX_REASONS:
                errors.append(f"{name}[{idx}].reasons: 최대 {textrules.MAX_REASONS}개")
            for r_i, reason in enumerate(item.reasons):
                errors.extend(
                    f"{name}[{idx}].reasons[{r_i}]: {msg}"
                    for msg in textrules.check_field("reason", reason)
                )

    minimum = MIN_ITEMS[pub.series]
    if len(pub.items) < minimum:
        errors.append(f"items: {pub.series.value} 는 최소 {minimum}개 필요 (실제 {len(pub.items)})")
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
                    errors.append(f"comparison[{col.name}]: 값 개수가 행 라벨 수와 다름")
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
    seen_ids: set[str] = set()
    for idx, cta in enumerate(pub.map_ctas):
        if cta.id in seen_ids:
            errors.append(f"map_ctas[{idx}].id: 중복 — '{cta.id}'")
        seen_ids.add(cta.id)
        if not cta.nudges:
            errors.append(f"map_ctas[{idx}].nudges: 최소 1개 필요")
        bad_keys = set(cta.filters) - FILTER_ALLOWLIST
        if bad_keys:
            errors.append(f"map_ctas[{idx}].filters: 허용되지 않는 키 {sorted(bad_keys)}")

    if errors:
        raise PublicationValidationError(errors)


def to_json_dict(pub: Publication) -> dict:
    d = dataclasses.asdict(pub)
    d["series"] = pub.series.value
    return d
```

- [ ] **Step 4: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (23 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/insta_cards/publication.py scripts/tests/test_insta_cards.py
git commit -m "feat(insta): Publication 모델 + 발행 검증 규칙"
```

---

### Task 4: copywriting.py — 서사 문구 템플릿 + YAML 오버라이드

**Files:**
- Create: `scripts/insta_cards/copywriting.py`
- Modify: `scripts/tests/test_insta_cards.py` (TestCopywriting 클래스 추가)

**Interfaces:**
- Consumes: `theme.format_eok`, `publication.FitFor`
- Produces:
  - `SUBTYPE_LABELS: dict[str, str]` — 넛지 subtype → 한국어 라벨 (아래 구현 참조)
  - `NUDGE_LABELS: dict[str, str]` — 기존 생성기의 넛지 라벨 이관
  - `@dataclass(frozen=True) CopyBundle(hook: str, why: tuple[str, ...], fit_for: FitFor | None)`
  - `class CopyOverrideError(ValueError)`
  - `load_copy_overrides(path: str) -> dict` — YAML 파싱 + 키/타입 검증 (허용 키: hook, why, fit_for)
  - `apply_overrides(bundle: CopyBundle, overrides: dict) -> CopyBundle` — 지정 키만 교체
  - `contributor_labels(top_contributors: list[dict], limit: int = 3) -> list[str]` — `[{"subtype": "subway", ...}]` → `["지하철", ...]`
  - 템플릿: `build_budget_choice_copy(label_a, label_b, price_a, price_b, area_a, area_b, contributors_a, contributors_b) -> CopyBundle` / `build_lifestyle_copy(profile_label, region_label, contributors) -> CopyBundle` / `build_value_copy(region_label) -> CopyBundle` / `build_compare_copy(label_a, label_b, nudge_label, winner_label) -> CopyBundle` / `build_trade_top_copy(days, top_amount_manwon) -> CopyBundle`
  - price 인자는 만원 단위 int, area 는 ㎡ float, contributors 는 라벨 문자열 리스트

- [ ] **Step 1: 실패하는 테스트 작성** — `TestCopywriting` 클래스 추가:

```python
class TestCopywriting(unittest.TestCase):
    def test_budget_choice_copy_has_no_forbidden_terms(self):
        from scripts.insta_cards import copywriting, textrules

        bundle = copywriting.build_budget_choice_copy(
            "서울 마포구", "성남 분당구", 69000, 68000, 59.9, 84.9,
            ["지하철", "마트"], ["공원", "학교"],
        )
        for text in (bundle.hook, *bundle.why, bundle.fit_for.a, bundle.fit_for.b):
            self.assertEqual(textrules.find_forbidden_terms(text), [])
        self.assertIn("59", bundle.hook)
        self.assertIn("84", bundle.hook)

    def test_contributor_labels_maps_subtypes(self):
        from scripts.insta_cards import copywriting

        rows = [{"subtype": "subway"}, {"subtype": "mart"}, {"subtype": "score_safety"}]
        self.assertEqual(
            copywriting.contributor_labels(rows), ["지하철", "마트", "안전 점수"]
        )

    def test_load_copy_overrides_rejects_unknown_key(self):
        import tempfile

        from scripts.insta_cards import copywriting

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("hook: 좋은 문구\nevil: 나쁜키\n")
        with self.assertRaises(copywriting.CopyOverrideError):
            copywriting.load_copy_overrides(f.name)

    def test_load_copy_overrides_rejects_wrong_type(self):
        import tempfile

        from scripts.insta_cards import copywriting

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("why: 문자열이면안됨\n")
        with self.assertRaises(copywriting.CopyOverrideError):
            copywriting.load_copy_overrides(f.name)

    def test_load_copy_overrides_rejects_empty_string(self):
        import tempfile

        from scripts.insta_cards import copywriting

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("hook: ''\n")
        with self.assertRaises(copywriting.CopyOverrideError):
            copywriting.load_copy_overrides(f.name)

    def test_apply_overrides_replaces_only_given_keys(self):
        from scripts.insta_cards import copywriting

        base = copywriting.build_value_copy("서울")
        merged = copywriting.apply_overrides(base, {"hook": "새 훅 문장"})
        self.assertEqual(merged.hook, "새 훅 문장")
        self.assertEqual(merged.why, base.why)
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestCopywriting -v`
Expected: ERROR — `ModuleNotFoundError: ... copywriting`

- [ ] **Step 3: copywriting.py 구현**

```python
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
        raise CopyOverrideError(f"허용되지 않는 키: {sorted(unknown)} (허용: {sorted(OVERRIDE_ALLOWED_KEYS)})")
    if "hook" in data and (not isinstance(data["hook"], str) or not data["hook"].strip()):
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
            raise CopyOverrideError("fit_for: {a: 문자열, b: 문자열} 형식이어야 합니다.")
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
    hook = f"{label_a} {area_a:.0f}㎡ vs {label_b} {area_b:.0f}㎡, 당신의 선택은?"
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
```

- [ ] **Step 4: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (29 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/insta_cards/copywriting.py scripts/tests/test_insta_cards.py
git commit -m "feat(insta): 서사 문구 템플릿 + YAML 오버라이드"
```

---

### Task 5: datasources.py — API 클라이언트 + 로컬 거래 조회 + metrics 추출

**Files:**
- Create: `scripts/insta_cards/datasources.py`
- Modify: `scripts/tests/test_insta_cards.py` (TestDatasources 클래스 추가)

**Interfaces:**
- Consumes: `batch.db.get_connection/query_all` (cwd=프로젝트 루트 전제), `requests`, `publication.Metric`, `theme.format_eok`
- Produces (시리즈 모듈이 사용):
  - `PROD_API_BASE = "https://api.apt-recom.kr"`, `API_TIMEOUT_SECONDS = 15`, `ELIGIBLE_TRADE_DAYS = 90`, `STALE_TRADE_WARN_HOURS = 24`
  - `class DataSourceError(RuntimeError)`
  - `post_nudge_score(payload: dict) -> list[dict]` — `POST /api/nudge/score`. 각 행 필수 키 `{"pnu","bld_nm","score","total_hhld_cnt","top_contributors"}` 누락 시 DataSourceError
  - `get_region_name(sigungu_code: str) -> str` — `GET /api/dashboard/regions`. 미발견 시 DataSourceError (코드 문자열 fallback 금지 — 기존 동작에서 의도 변경)
  - `get_apartment_detail(pnu: str) -> dict` — `GET /api/apartment/{pnu}`. 필수 키 `{"basic","scores","facility_summary","school","safety","mgmt_cost"}` 누락 시 DataSourceError
  - `extract_candidate_metrics(detail: dict, target_area: float | None) -> list[Metric]` — 순서 고정 4개: `지하철`, `배정 초등학교`, `안전점수`, `월 관리비`. 결측은 value=`"정보 없음"` (숨김 금지)
  - `fetch_recent_trades(conn, sigungu_code: str, *, max_amount: int | None = None, min_area: float | None = None, max_area: float | None = None, days: int = ELIGIBLE_TRADE_DAYS) -> dict[str, dict]` — pnu → 대표 거래 `{"pnu","deal_amount","exclu_use_ar","deal_date","bld_nm","use_apr_day"}`. 계약일 기준, 단지별 계약일 최신·동일일 최고가 (결정적 tie-break)
  - `open_local_db()` — `batch.db.get_connection()` lazy 위임 (import 시점 sys.path 요구 제거)
  - `stale_trade_warning(conn) -> str | None` — `MAX(created_at)` 이 24시간보다 오래면 경고 문자열
- 대표 거래 SQL (fetch_recent_trades 내부):

```sql
SELECT DISTINCT ON (m.pnu)
    m.pnu,
    t.deal_amount,
    t.exclu_use_ar,
    make_date(t.deal_year, t.deal_month, t.deal_day) AS deal_date,
    COALESCE(a.display_name, a.bld_nm) AS bld_nm,
    a.use_apr_day
FROM trade_history t
JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
JOIN apartments a ON a.pnu = m.pnu
WHERE a.sigungu_code = %s
  AND make_date(t.deal_year, t.deal_month, t.deal_day)
      >= CURRENT_DATE - (%s || ' days')::interval
  -- 이하 선택 조건: AND t.deal_amount <= %s / AND t.exclu_use_ar BETWEEN %s AND %s
ORDER BY m.pnu,
         make_date(t.deal_year, t.deal_month, t.deal_day) DESC,
         t.deal_amount DESC
```

- [ ] **Step 1: 실패하는 테스트 작성** — `TestDatasources` 클래스 추가 (HTTP는 `unittest.mock.patch`, DB는 `query_all` 패치):

```python
class TestDatasources(unittest.TestCase):
    def _detail_fixture(self):
        return {
            "basic": {"use_apr_day": "20150330", "sigungu_code": "41135"},
            "scores": {"cost": 71.2},
            "facility_summary": {"subway": {"nearest_distance_m": 480.0}},
            "school": {"elementary_school_name": "분당초", "estimated": False},
            "safety": {"safety_score": 78.5},
            "mgmt_cost": {
                "by_area": [
                    {"exclusive_area": 59, "per_unit_cost": 245000, "unit_count": 300},
                    {"exclusive_area": 84, "per_unit_cost": 310000, "unit_count": 200},
                ]
            },
        }

    def test_post_nudge_score_rejects_missing_keys(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import datasources

        fake = MagicMock()
        fake.json.return_value = [{"pnu": "1" * 19}]  # bld_nm 등 누락
        fake.raise_for_status.return_value = None
        with patch("scripts.insta_cards.datasources.requests.post", return_value=fake):
            with self.assertRaises(datasources.DataSourceError):
                datasources.post_nudge_score({"nudges": ["cost"]})

    def test_get_region_name_raises_when_not_found(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import datasources

        fake = MagicMock()
        fake.json.return_value = [{"code": "11440", "name": "서울 마포구"}]
        fake.raise_for_status.return_value = None
        with patch("scripts.insta_cards.datasources.requests.get", return_value=fake):
            self.assertEqual(datasources.get_region_name("11440"), "서울 마포구")
            with self.assertRaises(datasources.DataSourceError):
                datasources.get_region_name("99999")

    def test_get_apartment_detail_requires_keys(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import datasources

        fake = MagicMock()
        fake.json.return_value = {"basic": {}}  # 나머지 키 누락
        fake.raise_for_status.return_value = None
        with patch("scripts.insta_cards.datasources.requests.get", return_value=fake):
            with self.assertRaises(datasources.DataSourceError):
                datasources.get_apartment_detail("1" * 19)

    def test_extract_candidate_metrics_full(self):
        from scripts.insta_cards import datasources

        metrics = datasources.extract_candidate_metrics(self._detail_fixture(), 59.8)
        labels = [m.label for m in metrics]
        self.assertEqual(labels, ["지하철", "배정 초등학교", "안전점수", "월 관리비"])
        self.assertIn("480", metrics[0].value)
        self.assertEqual(metrics[1].value, "분당초")
        # target_area 59.8 → by_area 59 선택 (가장 가까운 평형)
        self.assertIn("25만원", metrics[3].value)
        self.assertIn("연", metrics[3].value)

    def test_extract_candidate_metrics_missing_becomes_info_none(self):
        from scripts.insta_cards import datasources

        detail = self._detail_fixture()
        detail["school"] = None
        detail["mgmt_cost"] = None
        metrics = datasources.extract_candidate_metrics(detail, None)
        self.assertEqual(metrics[1].value, "정보 없음")
        self.assertEqual(metrics[3].value, "정보 없음")

    def test_fetch_recent_trades_builds_conditional_sql(self):
        from unittest.mock import patch

        from scripts.insta_cards import datasources

        captured = {}

        def fake_query_all(conn, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return [
                {
                    "pnu": "1" * 19,
                    "deal_amount": 68000,
                    "exclu_use_ar": 59.9,
                    "deal_date": None,
                    "bld_nm": "테스트단지",
                    "use_apr_day": "20100101",
                }
            ]

        with patch("scripts.insta_cards.datasources.query_all", fake_query_all):
            result = datasources.fetch_recent_trades(
                None, "11440", max_amount=70000, min_area=54.9, max_area=64.9
            )
        self.assertIn("deal_amount <= %s", captured["sql"])
        self.assertIn("exclu_use_ar BETWEEN %s AND %s", captured["sql"])
        self.assertEqual(list(result.keys()), ["1" * 19])
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestDatasources -v`
Expected: ERROR — `ModuleNotFoundError: ... datasources`

- [ ] **Step 3: datasources.py 구현**

```python
"""데이터 소스 — 운영 공개 API + 로컬 DB(batch.db) 접근을 한 곳에 모은다.

- API 실패·필수 키 누락은 DataSourceError 로 발행 중단 (재시도·fallback 없음).
- 로컬 DB 는 거래 테이블만 사용 — 증분 sync(batch.sync_from_railway)로 충분.
- 단지 단위 지표(지하철·배정초·안전·관리비)는 공개 detail API 로 취득 —
  서비스 화면과 동일 값 보장 (spec §5-4).
"""

from __future__ import annotations

import requests

from scripts.insta_cards.publication import Metric

PROD_API_BASE = "https://api.apt-recom.kr"
API_TIMEOUT_SECONDS = 15
ELIGIBLE_TRADE_DAYS = 90  # "최근 실거래" 적격 기간 (계약일 기준)
STALE_TRADE_WARN_HOURS = 24

NUDGE_SCORE_REQUIRED_KEYS = {"pnu", "bld_nm", "score", "total_hhld_cnt", "top_contributors"}
DETAIL_REQUIRED_KEYS = {"basic", "scores", "facility_summary", "school", "safety", "mgmt_cost"}


class DataSourceError(RuntimeError):
    pass


def open_local_db():
    """batch.db 커넥션 — cwd 가 프로젝트 루트여야 import 가능 (실행 정책)."""
    from batch.db import get_connection

    return get_connection()


def query_all(conn, sql, params=None):
    from batch.db import query_all as batch_query_all

    return batch_query_all(conn, sql, params)


def post_nudge_score(payload: dict) -> list[dict]:
    resp = requests.post(
        f"{PROD_API_BASE}/api/nudge/score", json=payload, timeout=API_TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list):
        raise DataSourceError(f"nudge/score 응답이 목록이 아님: {type(rows)}")
    for i, row in enumerate(rows):
        missing = NUDGE_SCORE_REQUIRED_KEYS - set(row)
        if missing:
            raise DataSourceError(f"nudge/score 응답 [{i}] 필수 키 누락: {sorted(missing)}")
    return rows


def get_region_name(sigungu_code: str) -> str:
    resp = requests.get(
        f"{PROD_API_BASE}/api/dashboard/regions", timeout=API_TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    for region in resp.json():
        if region.get("code") == sigungu_code:
            return region["name"]
    raise DataSourceError(f"dashboard/regions 에 없는 시군구 코드: {sigungu_code}")


def get_apartment_detail(pnu: str) -> dict:
    resp = requests.get(
        f"{PROD_API_BASE}/api/apartment/{pnu}", timeout=API_TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    detail = resp.json()
    missing = DETAIL_REQUIRED_KEYS - set(detail)
    if missing:
        raise DataSourceError(f"apartment/{pnu} 응답 필수 키 누락: {sorted(missing)}")
    return detail


INFO_NONE = "정보 없음"  # 결측 표기 — 값 생략이지 fallback 아님 (숨김 금지)


def extract_candidate_metrics(detail: dict, target_area: float | None) -> list[Metric]:
    """detail API 응답 → 후보 공통 지표 4개 (순서 고정)."""
    facility = detail.get("facility_summary") or {}
    subway = facility.get("subway") or {}
    subway_value = (
        f"{round(subway['nearest_distance_m']):,}m"
        if subway.get("nearest_distance_m") is not None
        else INFO_NONE
    )

    school = detail.get("school") or {}
    school_name = school.get("elementary_school_name")
    if school_name and school.get("estimated"):
        school_value = f"{school_name}(추정)"
    elif school_name:
        school_value = school_name
    else:
        school_value = INFO_NONE

    safety = detail.get("safety") or {}
    safety_value = (
        f"{safety['safety_score']:.0f}점"
        if safety.get("safety_score") is not None
        else INFO_NONE
    )

    mgmt = detail.get("mgmt_cost") or {}
    by_area = mgmt.get("by_area") or []
    mgmt_value = INFO_NONE
    if by_area:
        if target_area is not None:
            entry = min(by_area, key=lambda r: abs(r["exclusive_area"] - target_area))
        else:
            entry = max(by_area, key=lambda r: r.get("unit_count") or 0)
        monthly = entry.get("per_unit_cost")
        if monthly:
            monthly_man = round(monthly / 10000)
            annual_man = round(monthly * 12 / 10000)
            mgmt_value = f"{monthly_man}만원 (연 {annual_man}만원)"

    return [
        Metric("지하철", subway_value, ""),
        Metric("배정 초등학교", school_value, ""),
        Metric("안전점수", safety_value, ""),
        Metric("월 관리비", mgmt_value, ""),
    ]


def fetch_recent_trades(
    conn,
    sigungu_code: str,
    *,
    max_amount: int | None = None,
    min_area: float | None = None,
    max_area: float | None = None,
    days: int = ELIGIBLE_TRADE_DAYS,
) -> dict[str, dict]:
    """지역 내 최근 계약일 기준 대표 거래(단지당 1건, 결정적 tie-break).

    반환: pnu → {pnu, deal_amount, exclu_use_ar, deal_date, bld_nm, use_apr_day}
    """
    conditions = [
        "a.sigungu_code = %s",
        "make_date(t.deal_year, t.deal_month, t.deal_day) >= CURRENT_DATE - (%s || ' days')::interval",
    ]
    params: list = [sigungu_code, days]
    if max_amount is not None:
        conditions.append("t.deal_amount <= %s")
        params.append(max_amount)
    if min_area is not None and max_area is not None:
        conditions.append("t.exclu_use_ar BETWEEN %s AND %s")
        params.extend([min_area, max_area])

    sql = f"""
        SELECT DISTINCT ON (m.pnu)
            m.pnu,
            t.deal_amount,
            t.exclu_use_ar,
            make_date(t.deal_year, t.deal_month, t.deal_day) AS deal_date,
            COALESCE(a.display_name, a.bld_nm) AS bld_nm,
            a.use_apr_day
        FROM trade_history t
        JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        JOIN apartments a ON a.pnu = m.pnu
        WHERE {" AND ".join(conditions)}
        ORDER BY m.pnu,
                 make_date(t.deal_year, t.deal_month, t.deal_day) DESC,
                 t.deal_amount DESC
    """
    rows = query_all(conn, sql, params)
    return {r["pnu"]: dict(r) for r in rows}


def stale_trade_warning(conn) -> str | None:
    rows = query_all(
        conn,
        "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 3600.0 AS age_hours "
        "FROM trade_history",
    )
    age = rows[0]["age_hours"] if rows else None
    if age is None or age > STALE_TRADE_WARN_HOURS:
        return (
            f"경고: 로컬 trade_history 최신 적재가 {age and round(age) or '?'}시간 전입니다. "
            "batch.sync_from_railway 실행을 권장합니다."
        )
    return None
```

- [ ] **Step 4: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (35 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/insta_cards/datasources.py scripts/tests/test_insta_cards.py
git commit -m "feat(insta): 데이터 소스 계층 — 운영 API + 로컬 거래 조회 + metrics 추출"
```

---

### Task 6: slides.py — 슬라이드 렌더러 8종 + 시리즈별 조합

**Files:**
- Create: `scripts/insta_cards/slides.py`
- Modify: `scripts/tests/test_insta_cards.py` (TestSlides 클래스 + budget_choice/trade_top 픽스처 추가)

**Interfaces:**
- Consumes: `theme.*`, `textrules.wrap_text`, `publication.Publication/Series/Item`
- Produces:
  - `build_slides(pub: Publication) -> list[tuple[str, Image.Image]]` — (파일명, 이미지) 목록. 시리즈별 구성·파일명은 File Map 표와 동일. 알 수 없는 시리즈는 KeyError
  - 내부 렌더러 (개별 테스트 가능하도록 모듈 공개): `render_cover(pub)`, `render_conditions(pub)`, `render_candidate(pub, item, heading)`, `render_ranking(pub, items, heading)`, `render_comparison(pub)`, `render_why(pub)`, `render_fit(pub)`, `render_caveats(pub)`, `render_cta(pub)` — 모두 `Image.Image` 반환, 1080×1080
  - `cta_question(pub) -> str` — budget_choice/compare 는 `"여러분이라면 {A} vs {B}?"`, 그 외 `"내 조건으로 직접 찾아보기"`
- 레이아웃 규칙: 폰트·폭은 `textrules.TEXT_LIMITS` 와 동일 값 사용 (한도 검증과 렌더 불일치 금지). 고유명(단지명·지역명)만 `truncate_text`.

- [ ] **Step 1: 실패하는 테스트 작성** — 픽스처 2개 + `TestSlides`:

```python
def make_valid_budget_choice_publication():
    from scripts.insta_cards import publication as p

    row_labels = ("최근 실거래가", "전용면적", "준공연도", "지하철", "배정 초등학교", "안전점수", "월 관리비")

    def item(rank, name, region, pnu_seed, values):
        return p.Item(
            rank=rank, name=name, region=region, pnu=f"{pnu_seed:019d}",
            metrics=tuple(p.Metric(lbl, v, "") for lbl, v in zip(row_labels, values)),
            reasons=("지하철 도보권", "마트 인접"),
        )

    values_a = ("6억 9,000만원", "59.9㎡", "2015년", "480m", "마포초", "78점", "25만원 (연 300만원)")
    values_b = ("6억 8,000만원", "84.9㎡", "2010년", "890m", "분당초", "81점", "31만원 (연 372만원)")
    return p.Publication(
        schema_version=p.SCHEMA_VERSION,
        slug="budget-choice-11440-vs-41135-20260713",
        status="draft",
        series=p.Series.BUDGET_CHOICE,
        title="같은 7억, 서울 59㎡ vs 분당 84㎡",
        eyebrow="같은 예산, 다른 선택",
        hook="서울 59㎡ vs 분당 84㎡, 당신의 선택은?",
        summary="같은 7억 예산으로 두 지역 대표 단지를 비교했습니다.",
        generated_at="2026-07-13T10:00:00",
        published_at=None,
        data_as_of="2026-07-13",
        period_label="계약일 기준 최근 90일 실거래",
        cover_image="01-cover.png",
        cover_alt="7억 예산 서울 분당 아파트 비교 카드",
        conditions=(
            p.Condition("예산", "7억 이하"),
            p.Condition("면적", "59㎡ / 84㎡"),
            p.Condition("기준일", "2026-07-13"),
        ),
        items=(
            item(1, "마포한강푸르지오", "서울 마포구", 1, values_a),
            item(2, "분당파크뷰", "성남 분당구", 2, values_b),
        ),
        secondary_items=None,
        comparison=p.Comparison(
            row_labels=row_labels,
            columns=(
                p.ComparisonColumn("마포한강푸르지오", values_a),
                p.ComparisonColumn("분당파크뷰", values_b),
            ),
        ),
        narrative=p.Narrative(
            why=("두 지역의 ㎡당 가격 차이가 면적 차이로 이어집니다.",),
            fit_for=p.FitFor(a="입지·교통 우선이라면 서울", b="면적 우선이라면 분당"),
        ),
        methodology=("각 지역 예산 이하 실거래 단지 중 넛지 점수 1위를 대표로 선정",),
        caveats=("투자 자문이 아닙니다.", "신고 지연으로 최근 거래가 늦게 반영될 수 있습니다."),
        map_ctas=(
            p.MapCta("map-a", "마포 조건으로 보기", ("cost",), "11440", "서울 마포구", {"max_price": 70000}),
            p.MapCta("map-b", "분당 조건으로 보기", ("cost",), "41135", "성남 분당구", {"max_price": 70000}),
        ),
    )


def make_valid_trade_top_publication():
    from scripts.insta_cards import publication as p

    def price_item(rank):
        return p.Item(
            rank=rank, name=f"고가단지{rank}", region="서울 서초구", pnu=f"{rank:019d}",
            metrics=(p.Metric("거래가", f"{30 - rank}억", ""), p.Metric("전용면적", "84㎡", "")),
            reasons=(),
        )

    def hot_item(rank):
        return p.Item(
            rank=rank, name=f"급증동네{rank}", region=None, pnu=None,
            metrics=(
                p.Metric("신고 건수", f"{200 - rank * 10}건", ""),
                p.Metric("직전 대비", f"+{50 - rank * 5}건", ""),
            ),
            reasons=(),
        )

    return p.Publication(
        schema_version=p.SCHEMA_VERSION,
        slug="trade-top-20260713",
        status="draft",
        series=p.Series.TRADE_TOP,
        title="이번 주 신고 최고가 TOP 5",
        eyebrow="신고일 기준 · 최근 7일",
        hook="최근 7일 신고 최고가는 29억",
        summary="신고일 기준 최근 7일 최고가 거래와 신고 급증 동네를 모았습니다.",
        generated_at="2026-07-13T10:00:00",
        published_at=None,
        data_as_of="2026-07-13",
        period_label="신고일 기준 최근 7일",
        cover_image="01-cover.png",
        cover_alt="최근 7일 아파트 신고 최고가 TOP 5 카드",
        conditions=(p.Condition("기간", "신고일 기준 최근 7일"), p.Condition("기준일", "2026-07-13")),
        items=tuple(price_item(i + 1) for i in range(5)),
        secondary_items=tuple(hot_item(i + 1) for i in range(5)),
        comparison=None,
        narrative=p.Narrative(why=(), fit_for=None),
        methodology=("단지별 최고가 1건 기준, 신고일 최근 7일 집계", "급증은 직전 7일 대비 신고 건수 증가"),
        caveats=("투자 자문이 아닙니다.", "신고일 기준이라 계약 시점과 다를 수 있습니다."),
        map_ctas=(),
    )


class TestSlides(unittest.TestCase):
    def _assert_slides(self, pub, expected_names):
        from scripts.insta_cards import slides

        result = slides.build_slides(pub)
        self.assertEqual([name for name, _ in result], expected_names)
        for _, image in result:
            self.assertEqual(image.size, (1080, 1080))

    def test_value_slides(self):
        self._assert_slides(
            make_valid_value_publication(),
            ["01-cover.png", "02-conditions.png", "03-ranking.png",
             "04-why.png", "05-caveats.png", "06-cta.png"],
        )

    def test_budget_choice_slides(self):
        self._assert_slides(
            make_valid_budget_choice_publication(),
            ["01-cover.png", "02-conditions.png", "03-candidate-a.png",
             "04-candidate-b.png", "05-comparison.png", "06-why.png",
             "07-fit.png", "08-caveats.png", "09-cta.png"],
        )

    def test_trade_top_slides(self):
        self._assert_slides(
            make_valid_trade_top_publication(),
            ["01-cover.png", "02-conditions.png", "03-ranking.png",
             "04-ranking-hot.png", "05-caveats.png", "06-cta.png"],
        )

    def test_cta_question_variants(self):
        from scripts.insta_cards import slides

        self.assertIn("vs", slides.cta_question(make_valid_budget_choice_publication()))
        self.assertEqual(
            slides.cta_question(make_valid_value_publication()), "내 조건으로 직접 찾아보기"
        )

    def test_long_names_do_not_crash(self):
        import dataclasses

        from scripts.insta_cards import publication as p, slides

        pub = make_valid_value_publication()
        long_item = p.Item(
            rank=1, name="아주아주아주아주아주아주긴한글단지이름" * 3,
            region="서울 노원구", pnu="1" * 19,
            metrics=(p.Metric("㎡당 가격", "1,000", "만원/㎡"),), reasons=("이유",),
        )
        items = (long_item,) + pub.items[1:]
        pub = dataclasses.replace(pub, items=items)
        for _, image in slides.build_slides(pub):
            self.assertEqual(image.size, (1080, 1080))
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestSlides -v`
Expected: ERROR — `ModuleNotFoundError: ... slides`

- [ ] **Step 3: slides.py 구현**

```python
"""슬라이드 렌더러 — 공용 8종을 시리즈별로 조합한다.

새 시리즈 추가 시 이 파일의 렌더러는 재사용하고 SLIDE_PLANS 만 확장한다.
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
    COLOR_TEXT_LIGHT,
    COLOR_TEXT_WHITE,
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


def cta_question(pub: Publication) -> str:
    if pub.series in (Series.BUDGET_CHOICE, Series.COMPARE):
        name_a = pub.items[0].name if pub.series is Series.BUDGET_CHOICE else pub.map_ctas[0].region_label
        name_b = pub.items[1].name if pub.series is Series.BUDGET_CHOICE else pub.map_ctas[1].region_label
        return f"여러분이라면 {name_a} vs {name_b}?"
    return "내 조건으로 직접 찾아보기"


def _wrapped_text(canvas, text, field, y, color, line_height=None):
    """textrules 한도와 동일 폰트로 줄바꿈 렌더. 반환: 다음 y."""
    limit = textrules.TEXT_LIMITS[field]
    font = get_font(limit.font_weight, limit.font_size)
    lines = textrules.wrap_text(text, font, limit.max_width)
    lh = line_height or round(limit.font_size * 1.35)
    for line in lines[: limit.max_lines]:
        canvas.draw.text((MARGIN_X, y), line, font=font, fill=color)
        y += lh
    return y


def render_cover(pub: Publication) -> Image.Image:
    canvas = build_base_canvas(pub.eyebrow, [])
    y = canvas.content_top + 120
    y = _wrapped_text(canvas, pub.hook, "hook", y, COLOR_TEXT_WHITE)
    y += 40
    _wrapped_text(canvas, pub.summary, "summary", y, COLOR_TEXT_LIGHT)
    date_font = get_font("regular", 26)
    canvas.draw.text(
        (MARGIN_X, canvas.content_bottom - 40),
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
        canvas.draw.text((MARGIN_X + 24, y + 10), cond.label, font=label_font, fill=COLOR_TEXT_LIGHT)
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
        canvas.draw.text((MARGIN_X, y), item.region, font=region_font, fill=COLOR_TEXT_LIGHT)
        y += 46

    for metric in item.metrics:
        canvas.draw.text((MARGIN_X, y), metric.label, font=metric_label_font, fill=COLOR_TEXT_LIGHT)
        value = f"{metric.value}{metric.unit}"
        value = truncate_text(canvas.draw, value, metric_value_font, 520)
        value_w = canvas.draw.textlength(value, font=metric_value_font)
        canvas.draw.text(
            (MARGIN_X + CONTENT_WIDTH - value_w, y - 2),
            value,
            font=metric_value_font,
            fill=COLOR_ACCENT_GREEN,
        )
        y += 44 + ROW_GAP

    y += 12
    for reason in item.reasons:
        canvas.draw.text((MARGIN_X, y), f"· {reason}", font=reason_font, fill=COLOR_TEXT_WHITE)
        y += 40
    return canvas.image


def render_ranking(pub: Publication, items: tuple[Item, ...], heading: str) -> Image.Image:
    canvas = build_base_canvas(pub.eyebrow, [heading])
    rank_font = get_font("extrabold", 40)
    name_font = get_font("semibold", 32)
    meta_font = get_font("regular", 24)
    value_font = get_font("extrabold", 34)

    rows = items[:LIST_SIZE]
    row_height = (canvas.content_bottom - canvas.content_top) / LIST_SIZE
    for i, item in enumerate(rows):
        y = canvas.content_top + i * row_height + 8
        canvas.draw.text((MARGIN_X, y), f"{item.rank}", font=rank_font, fill=COLOR_ACCENT_BLUE)
        name_x = MARGIN_X + 64
        name = truncate_text(canvas.draw, item.name, name_font, CONTENT_WIDTH - 64 - 280)
        canvas.draw.text((name_x, y), name, font=name_font, fill=COLOR_TEXT_WHITE)
        # 보조행: region 또는 두 번째 metric
        meta = item.region or (
            f"{item.metrics[1].label} {item.metrics[1].value}" if len(item.metrics) > 1 else ""
        )
        if meta:
            canvas.draw.text((name_x, y + 40), meta, font=meta_font, fill=COLOR_TEXT_LIGHT)
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
    canvas = build_base_canvas(pub.eyebrow, ["한눈에 비교"])
    comp = pub.comparison
    header_font = get_font("semibold", 28)
    label_font = get_font("regular", 26)
    value_font = get_font("semibold", 26)

    label_col_width = 240
    value_col_width = (CONTENT_WIDTH - label_col_width) / 2
    y = canvas.content_top + 8

    for col_i, col in enumerate(comp.columns):
        x = MARGIN_X + label_col_width + col_i * value_col_width
        name = truncate_text(canvas.draw, col.name, header_font, value_col_width - 16)
        canvas.draw.text((x, y), name, font=header_font, fill=COLOR_ACCENT_BLUE if col_i else COLOR_ACCENT_GREEN)
    y += 52

    row_height = min(
        64, (canvas.content_bottom - y) / max(len(comp.row_labels), 1)
    )
    for row_i, row_label in enumerate(comp.row_labels):
        ry = y + row_i * row_height
        canvas.draw.text((MARGIN_X, ry), row_label, font=label_font, fill=COLOR_TEXT_LIGHT)
        for col_i, col in enumerate(comp.columns):
            x = MARGIN_X + label_col_width + col_i * value_col_width
            value = truncate_text(canvas.draw, col.values[row_i], value_font, value_col_width - 16)
            canvas.draw.text((x, ry), value, font=value_font, fill=COLOR_TEXT_WHITE)
    return canvas.image


def render_why(pub: Publication) -> Image.Image:
    canvas = build_base_canvas(pub.eyebrow, ["왜 이런 결과일까"])
    y = canvas.content_top + 24
    for why in pub.narrative.why:
        y = _wrapped_text(canvas, f"· {why}", "why", y, COLOR_TEXT_WHITE)
        y += 24
    return canvas.image


def render_fit(pub: Publication) -> Image.Image:
    canvas = build_base_canvas(pub.eyebrow, ["어떤 사람에게 맞을까"])
    fit = pub.narrative.fit_for
    half_width = CONTENT_WIDTH / 2 - 20
    box_top = canvas.content_top + 24
    box_bottom = canvas.content_bottom - 24
    font = get_font("regular", 30)
    for i, text in enumerate((fit.a, fit.b)):
        x = MARGIN_X + i * (half_width + 40)
        canvas.draw.rounded_rectangle(
            [x, box_top, x + half_width, box_bottom], radius=20, fill=COLOR_BAR_TRACK
        )
        lines = textrules.wrap_text(text, font, half_width - 48)
        ty = box_top + 32
        for line in lines[: textrules.TEXT_LIMITS["fit_for"].max_lines]:
            canvas.draw.text((x + 24, ty), line, font=font, fill=COLOR_TEXT_WHITE)
            ty += 42
    return canvas.image


def render_caveats(pub: Publication) -> Image.Image:
    canvas = build_base_canvas(pub.eyebrow, ["읽을 때 주의할 점"])
    y = canvas.content_top + 16
    section_font = get_font("semibold", 28)
    canvas.draw.text((MARGIN_X, y), "이렇게 골랐습니다", font=section_font, fill=COLOR_ACCENT_GREEN)
    y += 46
    for m in pub.methodology:
        y = _wrapped_text(canvas, f"· {m}", "methodology", y, COLOR_TEXT_LIGHT)
        y += 8
    y += 24
    canvas.draw.text((MARGIN_X, y), "주의하세요", font=section_font, fill=COLOR_ACCENT_BLUE)
    y += 46
    for c in pub.caveats:
        y = _wrapped_text(canvas, f"· {c}", "caveat", y, COLOR_TEXT_LIGHT)
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
        canvas.draw.text(((CANVAS_SIZE - w) / 2, y), line, font=question_font, fill=COLOR_TEXT_WHITE)
        y += 70

    y += 60
    action = "댓글로 알려주세요 · 프로필 링크에서 내 조건으로 확인"
    w = canvas.draw.textlength(action, font=action_font)
    canvas.draw.text(((CANVAS_SIZE - w) / 2, y), action, font=action_font, fill=COLOR_ACCENT_GREEN)

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
            ("03-candidate-a.png", render_candidate(pub, pub.items[0], "지역 A 추천 1위")),
            ("04-candidate-b.png", render_candidate(pub, pub.items[1], "지역 B 추천 1위")),
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
            ("04-ranking-hot.png", render_ranking(pub, pub.secondary_items, "신고 급증 동네 TOP 5")),
            ("05-caveats.png", render_caveats(pub)),
            ("06-cta.png", render_cta(pub)),
        ]
    raise KeyError(f"슬라이드 구성이 정의되지 않은 시리즈: {pub.series}")
```

- [ ] **Step 4: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (40 tests)

- [ ] **Step 5: 육안 확인용 샘플 저장 (수동, 커밋 대상 아님)**

```bash
../../.venv/bin/python -c "
from scripts.tests.test_insta_cards import make_valid_budget_choice_publication
from scripts.insta_cards.slides import build_slides
for name, img in build_slides(make_valid_budget_choice_publication()):
    img.save(f'/tmp/insta-preview-{name}')
print('saved to /tmp/insta-preview-*.png')
"
open /tmp/insta-preview-01-cover.png
```
레이아웃이 어긋나면 렌더러 좌표를 수정하고 테스트 재실행 (테스트는 크기·비충돌만 검증 — 미관은 육안).

- [ ] **Step 6: 커밋**

```bash
git add scripts/insta_cards/slides.py scripts/tests/test_insta_cards.py
git commit -m "feat(insta): 캐러셀 슬라이드 렌더러 8종 + 시리즈 조합"
```

---

### Task 7: output.py — 원자적 쓰기 + 전역 slug 충돌 검사

**Files:**
- Create: `scripts/insta_cards/output.py`
- Modify: `scripts/tests/test_insta_cards.py` (TestOutput 클래스 추가)

**Interfaces:**
- Consumes: `publication.to_json_dict`, `slides.build_slides` 결과 형식 `list[tuple[str, Image]]`
- Produces:
  - `OUTPUT_ROOT: Path` — `<repo>/reports/insta`
  - `class SlugConflictError(RuntimeError)`
  - `find_existing_slug_dir(slug: str, root: Path = OUTPUT_ROOT) -> Path | None` — `root/*/slug` 전 날짜 스캔 (`.tmp-` 디렉토리는 무시)
  - `write_publication(pub, slides: list[tuple[str, Image]], *, force: bool = False, root: Path = OUTPUT_ROOT) -> Path` — 임시 디렉토리에 PNG 전부 + `publication.json` 저장 → 성공 시 `root/{오늘}/{slug}/` 로 atomic rename. 실패 시 임시 디렉토리 삭제. 기존 slug 존재 시 force 없으면 SlugConflictError, force면 기존 디렉토리 통째 삭제 후 교체

- [ ] **Step 1: 실패하는 테스트 작성** — `TestOutput` 클래스 추가:

```python
class TestOutput(unittest.TestCase):
    def _run(self, tmp, pub=None, force=False, slides=None):
        from pathlib import Path

        from scripts.insta_cards import output, slides as slides_mod

        pub = pub or make_valid_value_publication()
        slides = slides if slides is not None else slides_mod.build_slides(pub)
        return output.write_publication(pub, slides, force=force, root=Path(tmp))

    def test_write_creates_all_files(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            final_dir = self._run(tmp)
            pngs = sorted(p.name for p in final_dir.glob("*.png"))
            self.assertEqual(len(pngs), 6)
            self.assertEqual(pngs[0], "01-cover.png")
            data = json.loads((final_dir / "publication.json").read_text())
            self.assertEqual(data["slug"], "value-seoul-20260713")
            # 임시 디렉토리가 남지 않아야 함
            self.assertEqual(list(Path(tmp).glob("**/*.tmp-*")), [])

    def test_slug_conflict_across_dates(self):
        import tempfile
        from pathlib import Path

        from scripts.insta_cards import output

        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "2026-07-01" / "value-seoul-20260713"
            old.mkdir(parents=True)
            (old / "stale.png").write_bytes(b"x")
            with self.assertRaises(output.SlugConflictError):
                self._run(tmp)

    def test_force_replaces_whole_directory(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "2026-07-01" / "value-seoul-20260713"
            old.mkdir(parents=True)
            (old / "stale.png").write_bytes(b"x")
            final_dir = self._run(tmp, force=True)
            self.assertFalse(old.exists())
            self.assertFalse((final_dir / "stale.png").exists())

    def test_render_failure_leaves_no_final_dir(self):
        import tempfile
        from pathlib import Path

        class Boom:
            def save(self, *a, **kw):
                raise RuntimeError("render boom")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                self._run(tmp, slides=[("01-cover.png", Boom())])
            self.assertEqual(list(Path(tmp).glob("**/value-seoul-20260713")), [])
            self.assertEqual(list(Path(tmp).glob("**/*.tmp-*")), [])
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestOutput -v`
Expected: ERROR — `ModuleNotFoundError: ... output`

- [ ] **Step 3: output.py 구현**

```python
"""출력 — 임시 디렉토리 렌더 후 atomic rename. 부분 산출물이 남지 않는다.

slug 는 랜딩 URL 키이므로 날짜와 무관하게 전역 유일해야 한다 (spec §3).
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import date
from pathlib import Path

from PIL import Image

from scripts.insta_cards.publication import Publication, to_json_dict

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "reports" / "insta"
TMP_MARKER = ".tmp-"


class SlugConflictError(RuntimeError):
    pass


def find_existing_slug_dir(slug: str, root: Path = OUTPUT_ROOT) -> Path | None:
    if not root.exists():
        return None
    for date_dir in sorted(root.iterdir()):
        if not date_dir.is_dir() or TMP_MARKER in date_dir.name:
            continue
        candidate = date_dir / slug
        if candidate.is_dir():
            return candidate
    return None


def write_publication(
    pub: Publication,
    slides: list[tuple[str, Image.Image]],
    *,
    force: bool = False,
    root: Path = OUTPUT_ROOT,
) -> Path:
    existing = find_existing_slug_dir(pub.slug, root)
    if existing is not None and not force:
        raise SlugConflictError(
            f"slug '{pub.slug}' 가 이미 존재합니다: {existing} — 덮어쓰려면 --force"
        )

    date_dir = root / date.today().isoformat()
    date_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = date_dir / f"{pub.slug}{TMP_MARKER}{os.getpid()}"
    final_dir = date_dir / pub.slug

    try:
        tmp_dir.mkdir()
        for filename, image in slides:
            image.save(tmp_dir / filename, format="PNG")
        (tmp_dir / "publication.json").write_text(
            json.dumps(to_json_dict(pub), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if existing is not None:
            shutil.rmtree(existing)  # --force: 이전 슬라이드 잔존 방지, 통째 교체
        os.replace(tmp_dir, final_dir)
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return final_dir
```

- [ ] **Step 4: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (44 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/insta_cards/output.py scripts/tests/test_insta_cards.py
git commit -m "feat(insta): 원자적 출력 + 전역 slug 충돌 검사"
```

---

### Task 8: series/trade_top.py — 최고가 + 직전 기간 대비 급증

**Files:**
- Create: `scripts/insta_cards/series/__init__.py` (빈 파일)
- Create: `scripts/insta_cards/series/trade_top.py`
- Modify: `scripts/tests/test_insta_cards.py` (TestTradeTopSeries 클래스 추가)

**Interfaces:**
- Consumes: `datasources.open_local_db/query_all/stale_trade_warning`, `copywriting.build_trade_top_copy/apply_overrides`, `publication.*`
- Produces (cli가 사용 — 모든 시리즈 모듈 공통 계약):
  - `run(args, *, slug: str, status: str, published_at: str | None, copy_overrides: dict | None) -> Publication`
  - `args` 사용 필드: `args.days: int`
- 내부 (테스트 대상):
  - `fetch_top_price_trades(conn, days: int) -> list[dict]` — 기존 쿼리(`generate_insta_cards.py:218-252`) + **select 에 `m.pnu` 추가** (PRD G2). 반환 키: `pnu, apt_display_name, sigungu_name, deal_amount, exclu_use_ar`
  - `fetch_hot_districts(conn, days: int) -> list[dict]` — 직전 동일 기간 대비. 반환 키: `sigungu_name, current_count, prev_count, delta`
  - `MIN_REPORT_COUNT = 20` — 현재 기간 신고 건수 미달 지역 제외 (표본 규칙)
  - `build_publication(price_rows, hot_rows, days, *, slug, status, published_at, copy_overrides) -> Publication`
  - 결과 5개 미만(가격·급증 어느 쪽이든) 시 `ValueError` — 발행 실패
- 급증 SQL (직전 동일 기간 대비, 신고일 `created_at` 기준):

```sql
WITH current_window AS (
    SELECT sgg_cd, COUNT(*) AS cnt FROM trade_history
    WHERE created_at >= NOW() - (%s || ' days')::interval
    GROUP BY sgg_cd
), prev_window AS (
    SELECT sgg_cd, COUNT(*) AS cnt FROM trade_history
    WHERE created_at >= NOW() - (%s || ' days')::interval * 2
      AND created_at <  NOW() - (%s || ' days')::interval
    GROUP BY sgg_cd
)
SELECT c.sgg_cd,
       c.cnt AS current_count,
       COALESCE(p.cnt, 0) AS prev_count,
       c.cnt - COALESCE(p.cnt, 0) AS delta
FROM current_window c
LEFT JOIN prev_window p ON p.sgg_cd = c.sgg_cd
WHERE c.cnt >= %s AND c.cnt > COALESCE(p.cnt, 0)
ORDER BY delta DESC, c.cnt DESC
LIMIT 5
```

- [ ] **Step 1: 실패하는 테스트 작성** — `TestTradeTopSeries`:

```python
class TestTradeTopSeries(unittest.TestCase):
    def _price_rows(self, n=5):
        return [
            {
                "pnu": f"{i + 1:019d}",
                "apt_display_name": f"단지{i + 1}",
                "sigungu_name": "서울 서초구",
                "deal_amount": 300000 - i * 10000,
                "exclu_use_ar": 84.9,
            }
            for i in range(n)
        ]

    def _hot_rows(self, n=5):
        return [
            {
                "sigungu_name": f"동네{i + 1}",
                "current_count": 200 - i * 10,
                "prev_count": 150 - i * 10,
                "delta": 50,
            }
            for i in range(n)
        ]

    def test_build_publication_passes_validation(self):
        from scripts.insta_cards import publication as p
        from scripts.insta_cards.series import trade_top

        pub = trade_top.build_publication(
            self._price_rows(), self._hot_rows(), days=7,
            slug="trade-top-20260713", status="draft",
            published_at=None, copy_overrides=None,
        )
        p.validate(pub)  # 예외 없어야 함
        self.assertEqual(pub.series, p.Series.TRADE_TOP)
        self.assertEqual(pub.items[0].pnu, f"{1:019d}")
        self.assertEqual(len(pub.secondary_items), 5)
        self.assertEqual(pub.map_ctas, ())
        self.assertIn("직전", pub.secondary_items[0].metrics[1].label + pub.methodology[1])

    def test_insufficient_rows_raise(self):
        from scripts.insta_cards.series import trade_top

        with self.assertRaises(ValueError):
            trade_top.build_publication(
                self._price_rows(3), self._hot_rows(), days=7,
                slug="trade-top-20260713", status="draft",
                published_at=None, copy_overrides=None,
            )

    def test_hot_sql_filters_by_min_report_count(self):
        from unittest.mock import patch

        from scripts.insta_cards.series import trade_top

        captured = {}

        def fake_query_all(conn, sql, params=None):
            captured["sql"], captured["params"] = sql, params
            return []

        with patch("scripts.insta_cards.series.trade_top.query_all", fake_query_all):
            trade_top.fetch_hot_districts(None, 7)
        self.assertIn("prev_window", captured["sql"])
        self.assertIn(trade_top.MIN_REPORT_COUNT, captured["params"])
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestTradeTopSeries -v`
Expected: ERROR — `ModuleNotFoundError: ... series.trade_top`

- [ ] **Step 3: 구현** — `scripts/insta_cards/series/__init__.py` 빈 파일 + `trade_top.py`:

```python
"""trade_top — 신고일 기준 최고가 TOP 5 + 직전 기간 대비 신고 급증 동네 TOP 5.

의미론 (변경 금지):
- 최고가: 신고일(created_at) 기준 최근 N일, 단지별 최고가 1건 (DISTINCT ON).
- 급증: 직전 동일 기간 대비 증가 건수 — 카운트만으로 '급증' 표현 금지 (spec §5-5).
"""

from __future__ import annotations

from datetime import date, datetime

from scripts.insta_cards.copywriting import apply_overrides, build_trade_top_copy
from scripts.insta_cards.datasources import open_local_db, query_all, stale_trade_warning
from scripts.insta_cards.publication import (
    SCHEMA_VERSION,
    Condition,
    Item,
    Metric,
    Narrative,
    Publication,
    Series,
)

LIST_SIZE = 5
MIN_REPORT_COUNT = 20  # 표본 미달 지역 제외 (제안서 '표본 적은 지역 순위 제외')


def fetch_top_price_trades(conn, days: int) -> list[dict]:
    rows = query_all(
        conn,
        """
        SELECT pnu, apt_display_name, sgg_cd, deal_amount, exclu_use_ar
        FROM (
            SELECT DISTINCT ON (COALESCE(m.pnu, t.sgg_cd || ':' || t.apt_nm))
                m.pnu,
                COALESCE(a.display_name, a.bld_nm, t.apt_nm) AS apt_display_name,
                t.sgg_cd,
                t.deal_amount,
                t.exclu_use_ar
            FROM trade_history t
            LEFT JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
            LEFT JOIN apartments a ON a.pnu = m.pnu
            WHERE t.created_at >= NOW() - (%s || ' days')::interval
            ORDER BY COALESCE(m.pnu, t.sgg_cd || ':' || t.apt_nm),
                     t.deal_amount DESC
        ) per_complex
        ORDER BY deal_amount DESC
        LIMIT %s
        """,
        [days, LIST_SIZE],
    )
    names = _load_sigungu_names(conn)
    return [
        {
            "pnu": r["pnu"],
            "apt_display_name": r["apt_display_name"],
            "sigungu_name": names.get(r["sgg_cd"], r["sgg_cd"]),
            "deal_amount": r["deal_amount"],
            "exclu_use_ar": r["exclu_use_ar"],
        }
        for r in rows
    ]


def fetch_hot_districts(conn, days: int) -> list[dict]:
    rows = query_all(
        conn,
        """
        WITH current_window AS (
            SELECT sgg_cd, COUNT(*) AS cnt FROM trade_history
            WHERE created_at >= NOW() - (%s || ' days')::interval
            GROUP BY sgg_cd
        ), prev_window AS (
            SELECT sgg_cd, COUNT(*) AS cnt FROM trade_history
            WHERE created_at >= NOW() - (%s || ' days')::interval * 2
              AND created_at <  NOW() - (%s || ' days')::interval
            GROUP BY sgg_cd
        )
        SELECT c.sgg_cd,
               c.cnt AS current_count,
               COALESCE(p.cnt, 0) AS prev_count,
               c.cnt - COALESCE(p.cnt, 0) AS delta
        FROM current_window c
        LEFT JOIN prev_window p ON p.sgg_cd = c.sgg_cd
        WHERE c.cnt >= %s AND c.cnt > COALESCE(p.cnt, 0)
        ORDER BY delta DESC, c.cnt DESC
        LIMIT %s
        """,
        [days, days, days, MIN_REPORT_COUNT, LIST_SIZE],
    )
    names = _load_sigungu_names(conn)
    return [
        {
            "sigungu_name": names.get(r["sgg_cd"], r["sgg_cd"]),
            "current_count": r["current_count"],
            "prev_count": r["prev_count"],
            "delta": r["delta"],
        }
        for r in rows
    ]


def _load_sigungu_names(conn) -> dict[str, str]:
    rows = query_all(
        conn,
        "SELECT code, name, extra FROM common_code WHERE group_id = %s",
        ["sigungu"],
    )
    return {
        r["code"]: f"{r['name']}({r['extra']})"
        if r["extra"] and r["extra"] != r["name"]
        else r["name"]
        for r in rows
    }


def build_publication(
    price_rows: list[dict],
    hot_rows: list[dict],
    days: int,
    *,
    slug: str,
    status: str,
    published_at: str | None,
    copy_overrides: dict | None,
) -> Publication:
    if len(price_rows) < LIST_SIZE:
        raise ValueError(f"최고가 거래가 {len(price_rows)}건 — {LIST_SIZE}건 미만이라 발행 중단")
    if len(hot_rows) < LIST_SIZE:
        raise ValueError(
            f"급증 조건(현재 {MIN_REPORT_COUNT}건 이상 + 직전 대비 증가) 충족 지역이 "
            f"{len(hot_rows)}곳 — {LIST_SIZE}곳 미만이라 발행 중단"
        )

    from scripts.insta_cards.theme import format_eok

    items = tuple(
        Item(
            rank=i + 1,
            name=r["apt_display_name"] or "-",
            region=r["sigungu_name"],
            pnu=r["pnu"],
            metrics=(
                Metric("거래가", format_eok(r["deal_amount"]), ""),
                Metric("전용면적", f"{r['exclu_use_ar']:.0f}㎡", ""),
            ),
            reasons=(),
        )
        for i, r in enumerate(price_rows)
    )
    secondary = tuple(
        Item(
            rank=i + 1,
            name=r["sigungu_name"],
            region=None,
            pnu=None,
            metrics=(
                Metric("신고 건수", f"{r['current_count']:,}건", ""),
                Metric("직전 대비", f"+{r['delta']:,}건", ""),
            ),
            reasons=(),
        )
        for i, r in enumerate(hot_rows)
    )

    copy = build_trade_top_copy(days, price_rows[0]["deal_amount"])
    if copy_overrides:
        copy = apply_overrides(copy, copy_overrides)

    period_label = f"신고일 기준 최근 {days}일"
    today = date.today().isoformat()
    return Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        status=status,
        series=Series.TRADE_TOP,
        title=f"최근 {days}일 신고 최고가 TOP 5",
        eyebrow=f"신고일 기준 · 최근 {days}일",
        hook=copy.hook,
        summary="신고일 기준 최고가 거래와 신고가 크게 늘어난 동네를 모았습니다.",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label=period_label,
        cover_image="01-cover.png",
        cover_alt=f"최근 {days}일 아파트 신고 최고가 TOP 5 카드",
        conditions=(
            Condition("기간", period_label),
            Condition("집계 단위", "단지별 최고가 1건"),
            Condition("기준일", today),
        ),
        items=items,
        secondary_items=secondary,
        comparison=None,
        narrative=Narrative(why=copy.why, fit_for=copy.fit_for),
        methodology=(
            "최고가: 신고일 기준 최근 기간, 단지별 최고가 1건만 집계",
            f"급증: 직전 {days}일 대비 신고 건수 증가분 (현재 {MIN_REPORT_COUNT}건 이상 지역만)",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "신고일 기준이라 실제 계약 시점과 다를 수 있습니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=(),  # 랭킹은 넛지 조건이 아님 — 가짜 의도 부여 금지 (PRD Q3)
    )


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        price_rows = fetch_top_price_trades(conn, args.days)
        hot_rows = fetch_hot_districts(conn, args.days)
    finally:
        conn.close()
    return build_publication(
        price_rows, hot_rows, args.days,
        slug=slug, status=status, published_at=published_at,
        copy_overrides=copy_overrides,
    )
```

- [ ] **Step 4: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (47 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/insta_cards/series/ scripts/tests/test_insta_cards.py
git commit -m "feat(insta): trade_top 시리즈 — pnu 보존 + 직전 기간 대비 급증 계산"
```

---

### Task 9: series/value.py — 숨은 가성비

**Files:**
- Create: `scripts/insta_cards/series/value.py`
- Modify: `scripts/tests/test_insta_cards.py` (TestValueSeries 클래스 추가)

**Interfaces:**
- Consumes: `datasources.post_nudge_score/open_local_db/query_all/stale_trade_warning`, `copywriting.build_value_copy/apply_overrides/contributor_labels`, `theme.format_price_per_m2`, `publication.*`
- Produces:
  - `run(args, *, slug, status, published_at, copy_overrides) -> Publication` — args 사용 필드: `args.region`(키워드), `args.nudge`(기본 "cost"), `args.min_hhld`
  - `select_candidates(candidates: list[dict], price_map: dict[str, float], min_households: int) -> list[dict]` — 순수 함수: min_hhld 재검증(위반 시 ValueError), price 보유만, ㎡당 가격 오름차순 상위 5 (동가는 pnu 오름차순 tie-break), 5개 미만 ValueError
  - `CANDIDATE_POOL_SIZE = 30`
- 의미론 유지 (PRD §9): min_hhld 미달 혼입 → 예외 / price 전무 → 예외 / 5개 미만 → 발행 실패

- [ ] **Step 1: 실패하는 테스트 작성** — `TestValueSeries`:

```python
class TestValueSeries(unittest.TestCase):
    def _candidates(self, n=8):
        return [
            {
                "pnu": f"{i + 1:019d}",
                "bld_nm": f"단지{i + 1}",
                "score": 80.0 - i,
                "total_hhld_cnt": 500,
                "top_contributors": [{"subtype": "subway"}, {"subtype": "mart"}],
            }
            for i in range(n)
        ]

    def test_select_candidates_sorts_by_price(self):
        from scripts.insta_cards.series import value

        candidates = self._candidates()
        price_map = {c["pnu"]: 10_000_000.0 - i * 100_000 for i, c in enumerate(candidates)}
        top5 = value.select_candidates(candidates, price_map, 100)
        prices = [price_map[c["pnu"]] for c in top5]
        self.assertEqual(prices, sorted(prices))
        self.assertEqual(len(top5), 5)

    def test_select_candidates_rejects_undersized(self):
        from scripts.insta_cards.series import value

        candidates = self._candidates()
        candidates[0]["total_hhld_cnt"] = 10
        with self.assertRaises(ValueError):
            value.select_candidates(candidates, {c["pnu"]: 1.0 for c in candidates}, 100)

    def test_select_candidates_requires_five_with_price(self):
        from scripts.insta_cards.series import value

        candidates = self._candidates()
        price_map = {candidates[0]["pnu"]: 1.0}  # 1건만 price 보유
        with self.assertRaises(ValueError):
            value.select_candidates(candidates, price_map, 100)

    def test_run_builds_valid_publication(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import publication as p
        from scripts.insta_cards.series import value

        candidates = self._candidates()
        price_map = {c["pnu"]: 9_000_000.0 + i for i, c in enumerate(candidates)}

        args = MagicMock()
        args.region, args.nudge, args.min_hhld = "서울", "cost", 100

        with (
            patch("scripts.insta_cards.series.value.post_nudge_score", return_value=candidates),
            patch("scripts.insta_cards.series.value.fetch_price_per_m2_by_pnu", return_value=price_map),
            patch("scripts.insta_cards.series.value.open_local_db", return_value=MagicMock()),
            patch("scripts.insta_cards.series.value.stale_trade_warning", return_value=None),
        ):
            pub = value.run(
                args, slug="value-11000-20260713", status="draft",
                published_at=None, copy_overrides=None,
            )
        p.validate(pub)
        self.assertEqual(pub.series, p.Series.VALUE)
        self.assertEqual(len(pub.items), 5)
        self.assertEqual(pub.map_ctas[0].nudges, ("cost",))
        self.assertEqual(pub.map_ctas[0].filters, {"min_hhld": 100})
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestValueSeries -v`
Expected: ERROR — `ModuleNotFoundError: ... series.value`

- [ ] **Step 3: 구현** — `scripts/insta_cards/series/value.py`:

```python
"""value — 가성비 넛지 상위 후보 중 min_hhld 통과 + ㎡당 가격 오름차순 TOP 5.

의미론 (변경 금지, PRD §9): min_hhld 미달 혼입·price 전무·5개 미만은 모두
예외로 발행 중단. fallback 없음.
"""

from __future__ import annotations

from datetime import date, datetime

from scripts.insta_cards.copywriting import (
    apply_overrides,
    build_value_copy,
    contributor_labels,
)
from scripts.insta_cards.datasources import (
    open_local_db,
    post_nudge_score,
    query_all,
    stale_trade_warning,
)
from scripts.insta_cards.publication import (
    SCHEMA_VERSION,
    Condition,
    Item,
    MapCta,
    Metric,
    Narrative,
    Publication,
    Series,
)
from scripts.insta_cards.theme import format_price_per_m2

CANDIDATE_POOL_SIZE = 30
LIST_SIZE = 5


def fetch_price_per_m2_by_pnu(conn, pnu_list: list[str]) -> dict[str, float]:
    if not pnu_list:
        return {}
    placeholders = ",".join(["%s"] * len(pnu_list))
    rows = query_all(
        conn,
        f"SELECT pnu, price_per_m2 FROM apt_price_score "
        f"WHERE pnu IN ({placeholders}) AND price_per_m2 IS NOT NULL",
        pnu_list,
    )
    return {r["pnu"]: r["price_per_m2"] for r in rows}


def select_candidates(
    candidates: list[dict], price_map: dict[str, float], min_households: int
) -> list[dict]:
    undersized = [c for c in candidates if (c.get("total_hhld_cnt") or 0) < min_households]
    if undersized:
        raise ValueError(
            f"nudge/score 응답에 min_hhld({min_households}) 미달 단지 "
            f"{len(undersized)}건 포함 — API 필터 동작을 확인할 것."
        )
    merged = [
        {**c, "price_per_m2": price_map[c["pnu"]]}
        for c in candidates
        if c["pnu"] in price_map
    ]
    if len(merged) < LIST_SIZE:
        raise ValueError(
            f"price_per_m2 보유 후보 {len(merged)}건 — {LIST_SIZE}건 미만이라 발행 중단"
        )
    merged.sort(key=lambda c: (c["price_per_m2"], c["pnu"]))  # 결정적 tie-break
    return merged[:LIST_SIZE]


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    candidates = post_nudge_score(
        {
            "nudges": [args.nudge],
            "top_n": CANDIDATE_POOL_SIZE,
            "keyword": args.region,
            "min_hhld": args.min_hhld,
        }
    )
    if not candidates:
        raise ValueError(f"'{args.region}' 에 대한 넛지 점수 결과가 없습니다.")

    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        price_map = fetch_price_per_m2_by_pnu(conn, [c["pnu"] for c in candidates])
    finally:
        conn.close()

    top5 = select_candidates(candidates, price_map, args.min_hhld)

    items = tuple(
        Item(
            rank=i + 1,
            name=c["bld_nm"],
            region=args.region,
            pnu=c["pnu"],
            metrics=(
                Metric("㎡당 가격", format_price_per_m2(c["price_per_m2"]), ""),
                Metric("가성비 점수", f"{c['score']:.1f}", ""),
            ),
            reasons=tuple(contributor_labels(c["top_contributors"], 2)),
        )
        for i, c in enumerate(top5)
    )

    copy = build_value_copy(args.region)
    if copy_overrides:
        copy = apply_overrides(copy, copy_overrides)

    today = date.today().isoformat()
    return Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        status=status,
        series=Series.VALUE,
        title=f"숨은 가성비 TOP 5 — {args.region}",
        eyebrow="가성비 랭킹",
        hook=copy.hook,
        summary=f"{args.region} 가성비 넛지 상위 후보 중 ㎡당 가격이 낮은 5곳입니다.",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label=f"가성비 넛지 상위 {CANDIDATE_POOL_SIZE} 후보 기준",
        cover_image="01-cover.png",
        cover_alt=f"{args.region} 숨은 가성비 아파트 TOP 5 카드",
        conditions=(
            Condition("지역", args.region),
            Condition("최소 세대수", f"{args.min_hhld}세대"),
            Condition("기준일", today),
        ),
        items=items,
        secondary_items=None,
        comparison=None,
        narrative=Narrative(why=copy.why, fit_for=copy.fit_for),
        methodology=(
            f"가성비 넛지 상위 {CANDIDATE_POOL_SIZE}개 후보 중 ㎡당 가격 오름차순 {LIST_SIZE}곳",
            "가격은 apt_price_score 의 ㎡당 가격 (로컬 적재 기준)",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "가격 데이터는 로컬 적재 시점 기준입니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=(
            MapCta(
                id="map-main",
                label=f"가성비 조건 그대로 {args.region} 지도에서 보기",
                nudges=(args.nudge,),
                sigungu_code=None,
                region_label=args.region,
                filters={"min_hhld": args.min_hhld},
            ),
        ),
    )
```

- [ ] **Step 4: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (51 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/insta_cards/series/value.py scripts/tests/test_insta_cards.py
git commit -m "feat(insta): value 시리즈 캐러셀 — 기존 의미론 유지"
```

---

### Task 10: series/compare.py — 지역 집계 비교 + 1위 단지

**Files:**
- Create: `scripts/insta_cards/series/compare.py`
- Modify: `scripts/tests/test_insta_cards.py` (TestCompareSeries 클래스 추가)

**Interfaces:**
- Consumes: `datasources.post_nudge_score/get_region_name/get_apartment_detail/extract_candidate_metrics/open_local_db/query_all/stale_trade_warning`, `copywriting.build_compare_copy/apply_overrides/NUDGE_LABELS`, `theme.format_eok`, `publication.*`
- Produces:
  - `run(args, *, slug, status, published_at, copy_overrides) -> Publication` — args 사용 필드: `args.regions`(콤마 구분 시군구 코드 2개 문자열), `args.nudge`(기본 "newlywed")
  - `fetch_region_aggregate(conn, sigungu_code: str, days: int = 90) -> dict` — `{"median_amount": float | None, "trade_count": int, "avg_age": float | None}` (계약일 기준 최근 90일)
  - `COMPARISON_ROW_LABELS = ("넛지 점수(상위10 평균)", "중위 실거래가(90일)", "거래 건수(90일)", "평균 연식")`
- 비교 단위 규칙 (spec §5-3): 비교표=지역 집계, 후보 장=각 지역 넛지 1위 단지 (detail API metrics). 어느 지역이든 top10 이 비면 예외. 집계 결측(중위가 None)은 "정보 없음" 표기.

- [ ] **Step 1: 실패하는 테스트 작성** — `TestCompareSeries`:

```python
class TestCompareSeries(unittest.TestCase):
    def _scored(self, base):
        return [
            {
                "pnu": f"{base + i:019d}",
                "bld_nm": f"단지{base + i}",
                "score": 80.0 - i,
                "total_hhld_cnt": 500,
                "top_contributors": [{"subtype": "subway"}],
            }
            for i in range(10)
        ]

    def test_run_builds_valid_publication(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import publication as p
        from scripts.insta_cards.series import compare

        detail = {
            "basic": {"use_apr_day": "20150330"},
            "scores": {},
            "facility_summary": {"subway": {"nearest_distance_m": 480.0}},
            "school": {"elementary_school_name": "테스트초", "estimated": False},
            "safety": {"safety_score": 78.0},
            "mgmt_cost": None,
        }
        args = MagicMock()
        args.regions, args.nudge = "11440,41135", "newlywed"

        def fake_scored(payload):
            return self._scored(1 if payload["sigungu_code"] == "11440" else 100)

        aggregate = {"median_amount": 95000.0, "trade_count": 120, "avg_age": 14.2}
        with (
            patch("scripts.insta_cards.series.compare.post_nudge_score", side_effect=fake_scored),
            patch("scripts.insta_cards.series.compare.get_region_name",
                  side_effect=lambda c: {"11440": "서울 마포구", "41135": "성남 분당구"}[c]),
            patch("scripts.insta_cards.series.compare.get_apartment_detail", return_value=detail),
            patch("scripts.insta_cards.series.compare.fetch_region_aggregate", return_value=aggregate),
            patch("scripts.insta_cards.series.compare.open_local_db", return_value=MagicMock()),
            patch("scripts.insta_cards.series.compare.stale_trade_warning", return_value=None),
        ):
            pub = compare.run(
                args, slug="compare-11440-vs-41135-20260713", status="draft",
                published_at=None, copy_overrides=None,
            )
        p.validate(pub)
        self.assertEqual(pub.series, p.Series.COMPARE)
        self.assertEqual(len(pub.items), 2)
        self.assertEqual(len(pub.map_ctas), 2)
        self.assertEqual(pub.comparison.row_labels, compare.COMPARISON_ROW_LABELS)
        self.assertIn("상위 10개", " ".join(pub.methodology))

    def test_empty_top10_raises(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards.series import compare

        args = MagicMock()
        args.regions, args.nudge = "11440,41135", "newlywed"
        with (
            patch("scripts.insta_cards.series.compare.post_nudge_score", return_value=[]),
            patch("scripts.insta_cards.series.compare.get_region_name", return_value="서울 마포구"),
        ):
            with self.assertRaises(ValueError):
                compare.run(
                    args, slug="compare-x-20260713", status="draft",
                    published_at=None, copy_overrides=None,
                )

    def test_regions_must_be_two(self):
        from unittest.mock import MagicMock

        from scripts.insta_cards.series import compare

        args = MagicMock()
        args.regions, args.nudge = "11440", "newlywed"
        with self.assertRaises(ValueError):
            compare.run(
                args, slug="compare-x-20260713", status="draft",
                published_at=None, copy_overrides=None,
            )
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestCompareSeries -v`
Expected: ERROR — `ModuleNotFoundError: ... series.compare`

- [ ] **Step 3: 구현** — `scripts/insta_cards/series/compare.py`:

```python
"""compare — 비교표는 지역 집계, 후보 장은 각 지역 넛지 1위 단지 (spec §5-3).

점수는 '넛지 상위 10개 단지 평균' — '지역 전체 평균' 표현 금지 (PRD 계약).
"""

from __future__ import annotations

from datetime import date, datetime

from scripts.insta_cards.copywriting import NUDGE_LABELS, apply_overrides, build_compare_copy
from scripts.insta_cards.datasources import (
    INFO_NONE,
    extract_candidate_metrics,
    get_apartment_detail,
    get_region_name,
    open_local_db,
    post_nudge_score,
    query_all,
    stale_trade_warning,
)
from scripts.insta_cards.publication import (
    SCHEMA_VERSION,
    Comparison,
    ComparisonColumn,
    Condition,
    Item,
    MapCta,
    Metric,
    Narrative,
    Publication,
    Series,
)
from scripts.insta_cards.theme import format_eok

TOP_N = 10
AGGREGATE_DAYS = 90
COMPARISON_ROW_LABELS = (
    "넛지 점수(상위10 평균)",
    "중위 실거래가(90일)",
    "거래 건수(90일)",
    "평균 연식",
)


def fetch_region_aggregate(conn, sigungu_code: str, days: int = AGGREGATE_DAYS) -> dict:
    price_rows = query_all(
        conn,
        """
        SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY t.deal_amount) AS median_amount,
               COUNT(*) AS trade_count
        FROM trade_history t
        JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        JOIN apartments a ON a.pnu = m.pnu
        WHERE a.sigungu_code = %s
          AND make_date(t.deal_year, t.deal_month, t.deal_day)
              >= CURRENT_DATE - (%s || ' days')::interval
        """,
        [sigungu_code, days],
    )
    age_rows = query_all(
        conn,
        """
        SELECT AVG(EXTRACT(YEAR FROM CURRENT_DATE)
                   - CAST(SUBSTRING(a.use_apr_day, 1, 4) AS INTEGER)) AS avg_age
        FROM apartments a
        WHERE a.sigungu_code = %s AND a.use_apr_day ~ '^[0-9]{4}'
        """,
        [sigungu_code],
    )
    return {
        "median_amount": price_rows[0]["median_amount"] if price_rows else None,
        "trade_count": (price_rows[0]["trade_count"] if price_rows else 0) or 0,
        "avg_age": age_rows[0]["avg_age"] if age_rows else None,
    }


def _column_values(avg_score: float, aggregate: dict) -> tuple[str, ...]:
    median = aggregate["median_amount"]
    avg_age = aggregate["avg_age"]
    return (
        f"{avg_score:.1f}점",
        format_eok(round(median)) if median else INFO_NONE,
        f"{aggregate['trade_count']:,}건",
        f"{avg_age:.0f}년" if avg_age is not None else INFO_NONE,
    )


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    codes = [c.strip() for c in args.regions.split(",") if c.strip()]
    if len(codes) != 2:
        raise ValueError("compare 는 --regions 에 시군구 코드 2개(콤마 구분)가 필요합니다.")
    nudge = args.nudge
    nudge_label = NUDGE_LABELS[nudge]

    regions = []
    for code in codes:
        name = get_region_name(code)
        top10 = post_nudge_score({"nudges": [nudge], "top_n": TOP_N, "sigungu_code": code})
        if not top10:
            raise ValueError(f"{name}({code}) 에 대한 넛지 점수 결과가 없습니다.")
        regions.append(
            {
                "code": code,
                "name": name,
                "avg_score": sum(r["score"] for r in top10) / len(top10),
                "top1": top10[0],
            }
        )

    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        for region in regions:
            region["aggregate"] = fetch_region_aggregate(conn, region["code"])
    finally:
        conn.close()

    items = []
    for rank, region in enumerate(regions, start=1):
        top1 = region["top1"]
        detail = get_apartment_detail(top1["pnu"])
        metrics = [Metric(f"{nudge_label} 점수", f"{top1['score']:.1f}점", "")]
        metrics.extend(extract_candidate_metrics(detail, None))
        items.append(
            Item(
                rank=rank,
                name=top1["bld_nm"],
                region=region["name"],
                pnu=top1["pnu"],
                metrics=tuple(metrics),
                reasons=(),
            )
        )

    winner = max(regions, key=lambda r: r["avg_score"])
    copy = build_compare_copy(regions[0]["name"], regions[1]["name"], nudge_label, winner["name"])
    if copy_overrides:
        copy = apply_overrides(copy, copy_overrides)

    today = date.today().isoformat()
    return Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        status=status,
        series=Series.COMPARE,
        title=f"{regions[0]['name']} vs {regions[1]['name']} — {nudge_label}",
        eyebrow="동네 비교",
        hook=copy.hook,
        summary=f"{nudge_label} 기준으로 두 지역의 추천 상위 단지와 시세를 비교했습니다.",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label=f"계약일 기준 최근 {AGGREGATE_DAYS}일 실거래 + 넛지 점수",
        cover_image="01-cover.png",
        cover_alt=f"{regions[0]['name']} {regions[1]['name']} 아파트 비교 카드",
        conditions=(
            Condition("비교 기준", f"{nudge_label} 넛지"),
            Condition("지역", f"{regions[0]['name']} / {regions[1]['name']}"),
            Condition("기준일", today),
        ),
        items=tuple(items),
        secondary_items=None,
        comparison=Comparison(
            row_labels=COMPARISON_ROW_LABELS,
            columns=tuple(
                ComparisonColumn(
                    name=r["name"], values=_column_values(r["avg_score"], r["aggregate"])
                )
                for r in regions
            ),
        ),
        narrative=Narrative(why=copy.why, fit_for=copy.fit_for),
        methodology=(
            f"점수는 각 지역 {nudge_label} 넛지 상위 {TOP_N}개 단지의 평균 (지역 전체 평균 아님)",
            f"가격·거래량은 계약일 기준 최근 {AGGREGATE_DAYS}일 실거래 집계",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "신고 지연으로 최근 거래가 늦게 반영될 수 있습니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=tuple(
            MapCta(
                id=f"map-{'ab'[i]}",
                label=f"{r['name']} 추천 보기",
                nudges=(nudge,),
                sigungu_code=r["code"],
                region_label=r["name"],
                filters={},
            )
            for i, r in enumerate(regions)
        ),
    )
```

- [ ] **Step 4: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (54 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/insta_cards/series/compare.py scripts/tests/test_insta_cards.py
git commit -m "feat(insta): compare 시리즈 — 지역 집계 비교표 + 1위 단지 상세"
```

---

### Task 11: series/budget_choice.py — 같은 예산, 다른 선택

**Files:**
- Create: `scripts/insta_cards/series/budget_choice.py`
- Modify: `scripts/tests/test_insta_cards.py` (TestBudgetChoiceSeries 클래스 추가)

**Interfaces:**
- Consumes: `datasources.fetch_recent_trades/post_nudge_score/get_apartment_detail/extract_candidate_metrics/open_local_db/stale_trade_warning`, `copywriting.build_budget_choice_copy/apply_overrides/contributor_labels`, `theme.format_eok`, `publication.*`
- Produces:
  - `run(args, *, slug, status, published_at, copy_overrides) -> Publication` — args 사용 필드: `args.budget: int`(만원), `args.regions: str`(코드 2개), `args.area_a: float`, `args.area_b: float`, `args.area_tolerance: float`(기본 5.0), `args.nudge: str`(기본 "cost"), `args.pnu_a: str | None`, `args.pnu_b: str | None`
  - `select_representative(eligible: dict[str, dict], scored: list[dict], override_pnu: str | None) -> tuple[dict, dict]` — 순수 함수. 반환 `(대표 거래 dict, scored 행 dict — override 가 scored 에 없으면 빈 dict)`. 규칙: override 지정 시 eligible 소속 필수(아니면 ValueError — 검증 우회 불가), 미지정 시 scored 순서(점수순)대로 eligible 교집합 첫 번째, 교집합 공집합 시 ValueError
  - `SCORE_POOL_SIZE = 50`
  - `ROW_LABELS = ("최근 실거래가", "전용면적", "준공연도", "지하철", "배정 초등학교", "안전점수", "월 관리비")`
- "같은 예산" 보장 (spec §5-1): 카드 표기 가격은 eligible(면적 밴드 + 계약일 90일 + 예산 이하)의 대표 거래 — API 추정가(max_price)는 후보 축소용으로만 사용

- [ ] **Step 1: 실패하는 테스트 작성** — `TestBudgetChoiceSeries`:

```python
class TestBudgetChoiceSeries(unittest.TestCase):
    def _eligible(self, seeds):
        return {
            f"{s:019d}": {
                "pnu": f"{s:019d}",
                "deal_amount": 68000,
                "exclu_use_ar": 59.9,
                "deal_date": None,
                "bld_nm": f"단지{s}",
                "use_apr_day": "20150330",
            }
            for s in seeds
        }

    def _scored(self, seeds):
        return [
            {
                "pnu": f"{s:019d}",
                "bld_nm": f"단지{s}",
                "score": 90.0 - i,
                "total_hhld_cnt": 500,
                "top_contributors": [{"subtype": "subway"}],
            }
            for i, s in enumerate(seeds)
        ]

    def test_select_representative_intersects_by_score_order(self):
        from scripts.insta_cards.series import budget_choice

        eligible = self._eligible([3, 4])
        scored = self._scored([1, 2, 3, 4])  # 1,2 는 eligible 아님
        trade, row = budget_choice.select_representative(eligible, scored, None)
        self.assertEqual(trade["pnu"], f"{3:019d}")
        self.assertEqual(row["pnu"], f"{3:019d}")

    def test_select_representative_empty_intersection_raises(self):
        from scripts.insta_cards.series import budget_choice

        with self.assertRaises(ValueError):
            budget_choice.select_representative(self._eligible([9]), self._scored([1, 2]), None)

    def test_override_must_be_eligible(self):
        from scripts.insta_cards.series import budget_choice

        eligible = self._eligible([3])
        with self.assertRaises(ValueError):
            budget_choice.select_representative(eligible, self._scored([3]), f"{7:019d}")

    def test_run_builds_valid_publication(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import publication as p
        from scripts.insta_cards.series import budget_choice

        detail = {
            "basic": {"use_apr_day": "20150330"},
            "scores": {},
            "facility_summary": {"subway": {"nearest_distance_m": 480.0}},
            "school": {"elementary_school_name": "테스트초", "estimated": False},
            "safety": {"safety_score": 78.0},
            "mgmt_cost": {"by_area": [{"exclusive_area": 59, "per_unit_cost": 245000, "unit_count": 100}]},
        }
        args = MagicMock()
        args.budget, args.regions = 70000, "11440,41135"
        args.area_a, args.area_b, args.area_tolerance = 59.0, 84.0, 5.0
        args.nudge, args.pnu_a, args.pnu_b = "cost", None, None

        def fake_trades(conn, code, **kw):
            return self._eligible([1, 2] if code == "11440" else [5, 6])

        def fake_scored(payload):
            return self._scored([1, 2] if payload["sigungu_code"] == "11440" else [5, 6])

        with (
            patch("scripts.insta_cards.series.budget_choice.fetch_recent_trades", side_effect=fake_trades),
            patch("scripts.insta_cards.series.budget_choice.post_nudge_score", side_effect=fake_scored),
            patch("scripts.insta_cards.series.budget_choice.get_region_name",
                  side_effect=lambda c: {"11440": "서울 마포구", "41135": "성남 분당구"}[c]),
            patch("scripts.insta_cards.series.budget_choice.get_apartment_detail", return_value=detail),
            patch("scripts.insta_cards.series.budget_choice.open_local_db", return_value=MagicMock()),
            patch("scripts.insta_cards.series.budget_choice.stale_trade_warning", return_value=None),
        ):
            pub = budget_choice.run(
                args, slug="budget-choice-11440-vs-41135-20260713", status="draft",
                published_at=None, copy_overrides=None,
            )
        p.validate(pub)
        self.assertEqual(pub.series, p.Series.BUDGET_CHOICE)
        self.assertEqual(pub.comparison.row_labels, budget_choice.ROW_LABELS)
        self.assertEqual(len(pub.map_ctas), 2)
        self.assertEqual(pub.map_ctas[0].filters["max_price"], 70000)
        # 카드 표기 가격은 eligible 대표 거래에서 나온다 (예산 이하 보장)
        self.assertIn("6억 8,000만원", pub.items[0].metrics[0].value)
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestBudgetChoiceSeries -v`
Expected: ERROR — `ModuleNotFoundError: ... series.budget_choice`

- [ ] **Step 3: 구현** — `scripts/insta_cards/series/budget_choice.py`:

```python
"""budget_choice — 같은 예산으로 두 지역 대표 단지 비교 (spec §5-1).

'같은 예산' 보장: 대표 거래는 로컬 DB 적격 집합(면적 밴드 + 계약일 90일 +
예산 이하)에서 나온다. nudge/score 의 max_price 는 추정가라 후보 축소용으로만
쓰고, 카드 표기 가격의 근거로 쓰지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime

from scripts.insta_cards.copywriting import (
    apply_overrides,
    build_budget_choice_copy,
    contributor_labels,
)
from scripts.insta_cards.datasources import (
    extract_candidate_metrics,
    fetch_recent_trades,
    get_apartment_detail,
    get_region_name,
    open_local_db,
    post_nudge_score,
    stale_trade_warning,
)
from scripts.insta_cards.publication import (
    SCHEMA_VERSION,
    Comparison,
    ComparisonColumn,
    Condition,
    FitFor,
    Item,
    MapCta,
    Metric,
    Narrative,
    Publication,
    Series,
)
from scripts.insta_cards.theme import format_eok

SCORE_POOL_SIZE = 50
ROW_LABELS = ("최근 실거래가", "전용면적", "준공연도", "지하철", "배정 초등학교", "안전점수", "월 관리비")


def select_representative(
    eligible: dict[str, dict], scored: list[dict], override_pnu: str | None
) -> tuple[dict, dict]:
    """적격 집합(예산·면적·기간 보장) ∩ 넛지 점수 순서 → 대표 1개.

    override 도 적격 집합 검증을 우회할 수 없다 (spec §5-1 규칙 4).
    """
    if override_pnu is not None:
        if override_pnu not in eligible:
            raise ValueError(
                f"--pnu 오버라이드 {override_pnu} 가 적격 집합(면적·예산·최근 90일 거래)에 없습니다."
            )
        row = next((r for r in scored if r["pnu"] == override_pnu), {})
        return eligible[override_pnu], row
    for row in scored:  # scored 는 점수 내림차순 (서버 정렬)
        if row["pnu"] in eligible:
            return eligible[row["pnu"]], row
    raise ValueError(
        f"적격 집합 {len(eligible)}건과 넛지 상위 {len(scored)}건의 교집합이 없습니다 — "
        "예산·면적 밴드를 조정하세요."
    )


def _build_candidate(trade: dict, scored_row: dict, region_name: str, target_area: float, rank: int) -> tuple[Item, list[str]]:
    detail = get_apartment_detail(trade["pnu"])
    built_year = (trade.get("use_apr_day") or "")[:4] or "정보 없음"
    metrics = [
        Metric("최근 실거래가", format_eok(trade["deal_amount"]), ""),
        Metric("전용면적", f"{trade['exclu_use_ar']:.1f}㎡", ""),
        Metric("준공연도", f"{built_year}년" if built_year != "정보 없음" else built_year, ""),
    ]
    metrics.extend(extract_candidate_metrics(detail, target_area))
    contributors = contributor_labels(scored_row.get("top_contributors", []), 2)
    item = Item(
        rank=rank,
        name=trade["bld_nm"],
        region=region_name,
        pnu=trade["pnu"],
        metrics=tuple(metrics),
        reasons=tuple(f"{c} 접근성 기여" for c in contributors),
    )
    return item, contributors


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    codes = [c.strip() for c in args.regions.split(",") if c.strip()]
    if len(codes) != 2:
        raise ValueError("budget-choice 는 --regions 에 시군구 코드 2개가 필요합니다.")
    tol = args.area_tolerance
    plans = [
        {"code": codes[0], "area": args.area_a, "override": args.pnu_a},
        {"code": codes[1], "area": args.area_b, "override": args.pnu_b},
    ]

    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        for plan in plans:
            plan["name"] = get_region_name(plan["code"])
            plan["eligible"] = fetch_recent_trades(
                conn,
                plan["code"],
                max_amount=args.budget,
                min_area=plan["area"] - tol,
                max_area=plan["area"] + tol,
            )
            if not plan["eligible"]:
                raise ValueError(
                    f"{plan['name']}: 예산 {format_eok(args.budget)} 이하 · "
                    f"{plan['area']:.0f}±{tol:.0f}㎡ · 최근 90일 계약 거래가 없습니다."
                )
    finally:
        conn.close()

    for plan in plans:
        scored = post_nudge_score(
            {
                "nudges": [args.nudge],
                "top_n": SCORE_POOL_SIZE,
                "sigungu_code": plan["code"],
                "min_area": plan["area"] - tol,
                "max_area": plan["area"] + tol,
            }
        )
        plan["trade"], plan["scored_row"] = select_representative(
            plan["eligible"], scored, plan["override"]
        )

    items, contributors = [], []
    for rank, plan in enumerate(plans, start=1):
        item, contribs = _build_candidate(
            plan["trade"], plan["scored_row"], plan["name"], plan["area"], rank
        )
        items.append(item)
        contributors.append(contribs)

    copy = build_budget_choice_copy(
        plans[0]["name"], plans[1]["name"],
        plans[0]["trade"]["deal_amount"], plans[1]["trade"]["deal_amount"],
        plans[0]["trade"]["exclu_use_ar"], plans[1]["trade"]["exclu_use_ar"],
        contributors[0], contributors[1],
    )
    if copy_overrides:
        copy = apply_overrides(copy, copy_overrides)
    fit_for = copy.fit_for or FitFor(a=plans[0]["name"], b=plans[1]["name"])

    today = date.today().isoformat()
    budget_label = format_eok(args.budget)
    return Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        status=status,
        series=Series.BUDGET_CHOICE,
        title=f"같은 {budget_label}, {plans[0]['name']} vs {plans[1]['name']}",
        eyebrow="같은 예산, 다른 선택",
        hook=copy.hook,
        summary=f"{budget_label} 예산으로 두 지역의 대표 단지를 나란히 비교했습니다.",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label="계약일 기준 최근 90일 실거래",
        cover_image="01-cover.png",
        cover_alt=f"{budget_label} 예산 {plans[0]['name']} {plans[1]['name']} 아파트 비교 카드",
        conditions=(
            Condition("예산", f"{budget_label} 이하"),
            Condition("면적 A", f"{args.area_a:.0f}±{tol:.0f}㎡"),
            Condition("면적 B", f"{args.area_b:.0f}±{tol:.0f}㎡"),
            Condition("기준일", today),
        ),
        items=tuple(items),
        secondary_items=None,
        comparison=Comparison(
            row_labels=ROW_LABELS,
            columns=tuple(
                ComparisonColumn(
                    name=item.name, values=tuple(m.value for m in item.metrics)
                )
                for item in items
            ),
        ),
        narrative=Narrative(why=copy.why, fit_for=fit_for),
        methodology=(
            "각 지역에서 목표 면적대의 최근 90일 계약 거래가 예산 이하인 단지만 후보로 구성",
            "후보 중 넛지 점수 1위를 대표로 선정 (--pnu 로 수동 지정 가능)",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "계약일 기준이라 신고 지연으로 최근 거래가 빠질 수 있습니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=tuple(
            MapCta(
                id=f"map-{'ab'[i]}",
                label=f"{plan['name']} 조건으로 보기",
                nudges=(args.nudge,),
                sigungu_code=plan["code"],
                region_label=plan["name"],
                filters={
                    "max_price": args.budget,
                    "min_area": round(plan["area"] - tol, 1),
                    "max_area": round(plan["area"] + tol, 1),
                },
            )
            for i, plan in enumerate(plans)
        ),
    )
```

- [ ] **Step 4: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (58 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/insta_cards/series/budget_choice.py scripts/tests/test_insta_cards.py
git commit -m "feat(insta): budget_choice 시리즈 — 실거래 적격 집합 기반 대표 선정"
```

---

### Task 12: series/lifestyle.py — 넛지 프로필 추천

**Files:**
- Create: `scripts/insta_cards/series/lifestyle.py`
- Modify: `scripts/tests/test_insta_cards.py` (TestLifestyleSeries 클래스 추가)

**Interfaces:**
- Consumes: budget_choice 와 동일한 datasources/copywriting 함수 + `copywriting.build_lifestyle_copy/NUDGE_LABELS`
- Produces:
  - `run(args, *, slug, status, published_at, copy_overrides) -> Publication` — args 사용 필드: `args.profile: str`(NUDGE_LABELS 키), `args.region: str`(시군구 코드 5자리), `args.max_price: int | None`, `args.min_area: float | None`, `args.max_area: float | None`, `args.min_hhld: int`
  - `select_candidates(eligible: dict[str, dict], scored: list[dict], min_households: int) -> list[dict]` — 순수 함수: min_hhld 재검증(위반 시 ValueError) → scored 순서대로 eligible 교집합 최대 5개, 3개 미만 ValueError. 반환 행은 `{**scored_row, "trade": eligible[pnu]}`
  - `MAX_CANDIDATES = 5`, `MIN_CANDIDATES = 3`, `SCORE_POOL_SIZE = 50`

- [ ] **Step 1: 실패하는 테스트 작성** — `TestLifestyleSeries`:

```python
class TestLifestyleSeries(unittest.TestCase):
    def _eligible(self, seeds):
        return {
            f"{s:019d}": {
                "pnu": f"{s:019d}",
                "deal_amount": 65000,
                "exclu_use_ar": 74.9,
                "deal_date": None,
                "bld_nm": f"단지{s}",
                "use_apr_day": "20180501",
            }
            for s in seeds
        }

    def _scored(self, seeds, hhld=500):
        return [
            {
                "pnu": f"{s:019d}",
                "bld_nm": f"단지{s}",
                "score": 90.0 - i,
                "total_hhld_cnt": hhld,
                "top_contributors": [{"subtype": "kindergarten"}, {"subtype": "mart"}],
            }
            for i, s in enumerate(seeds)
        ]

    def test_select_candidates_caps_at_five(self):
        from scripts.insta_cards.series import lifestyle

        result = lifestyle.select_candidates(
            self._eligible(range(1, 10)), self._scored(range(1, 10)), 100
        )
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["trade"]["bld_nm"], "단지1")

    def test_select_candidates_requires_three(self):
        from scripts.insta_cards.series import lifestyle

        with self.assertRaises(ValueError):
            lifestyle.select_candidates(self._eligible([1, 2]), self._scored([1, 2]), 100)

    def test_select_candidates_rejects_undersized(self):
        from scripts.insta_cards.series import lifestyle

        with self.assertRaises(ValueError):
            lifestyle.select_candidates(
                self._eligible([1, 2, 3]), self._scored([1, 2, 3], hhld=10), 100
            )

    def test_run_builds_valid_publication(self):
        from unittest.mock import MagicMock, patch

        from scripts.insta_cards import publication as p
        from scripts.insta_cards.series import lifestyle

        detail = {
            "basic": {"use_apr_day": "20180501"},
            "scores": {},
            "facility_summary": {"subway": {"nearest_distance_m": 620.0}},
            "school": {"elementary_school_name": "판교초", "estimated": False},
            "safety": {"safety_score": 82.0},
            "mgmt_cost": None,
        }
        args = MagicMock()
        args.profile, args.region, args.min_hhld = "newlywed", "41135", 100
        args.max_price, args.min_area, args.max_area = 70000, None, None

        with (
            patch("scripts.insta_cards.series.lifestyle.fetch_recent_trades",
                  return_value=self._eligible(range(1, 7))),
            patch("scripts.insta_cards.series.lifestyle.post_nudge_score",
                  return_value=self._scored(range(1, 7))),
            patch("scripts.insta_cards.series.lifestyle.get_region_name", return_value="성남 분당구"),
            patch("scripts.insta_cards.series.lifestyle.get_apartment_detail", return_value=detail),
            patch("scripts.insta_cards.series.lifestyle.open_local_db", return_value=MagicMock()),
            patch("scripts.insta_cards.series.lifestyle.stale_trade_warning", return_value=None),
        ):
            pub = lifestyle.run(
                args, slug="lifestyle-newlywed-41135-20260713", status="draft",
                published_at=None, copy_overrides=None,
            )
        p.validate(pub)
        self.assertEqual(pub.series, p.Series.LIFESTYLE)
        self.assertEqual(len(pub.items), 5)
        self.assertEqual(pub.map_ctas[0].nudges, ("newlywed",))
        self.assertEqual(pub.map_ctas[0].filters["max_price"], 70000)
        self.assertIn("min_hhld", pub.map_ctas[0].filters)
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestLifestyleSeries -v`
Expected: ERROR — `ModuleNotFoundError: ... series.lifestyle`

- [ ] **Step 3: 구현** — `scripts/insta_cards/series/lifestyle.py`:

```python
"""lifestyle — 넛지 프로필 파라미터화 추천 (파일럿: newlywed, spec §5-2).

통근시간 조건은 지원하지 않는다 — 조건 칩에 '지하철·버스 접근성 반영'으로
표기 (통근시간 사칭 금지). /api/commute 표시 연동은 후속 (--destination).
"""

from __future__ import annotations

from datetime import date, datetime

from scripts.insta_cards.copywriting import (
    NUDGE_LABELS,
    apply_overrides,
    build_lifestyle_copy,
    contributor_labels,
)
from scripts.insta_cards.datasources import (
    extract_candidate_metrics,
    fetch_recent_trades,
    get_apartment_detail,
    get_region_name,
    open_local_db,
    post_nudge_score,
    stale_trade_warning,
)
from scripts.insta_cards.publication import (
    SCHEMA_VERSION,
    Condition,
    Item,
    MapCta,
    Metric,
    Narrative,
    Publication,
    Series,
)
from scripts.insta_cards.theme import format_eok

SCORE_POOL_SIZE = 50
MAX_CANDIDATES = 5
MIN_CANDIDATES = 3


def select_candidates(
    eligible: dict[str, dict], scored: list[dict], min_households: int
) -> list[dict]:
    undersized = [r for r in scored if (r.get("total_hhld_cnt") or 0) < min_households]
    if undersized:
        raise ValueError(
            f"nudge/score 응답에 min_hhld({min_households}) 미달 단지 "
            f"{len(undersized)}건 포함 — API 필터 동작을 확인할 것."
        )
    picked = [
        {**row, "trade": eligible[row["pnu"]]}
        for row in scored
        if row["pnu"] in eligible
    ][:MAX_CANDIDATES]
    if len(picked) < MIN_CANDIDATES:
        raise ValueError(
            f"적격 후보 {len(picked)}건 — {MIN_CANDIDATES}건 미만이라 발행 중단 "
            f"(적격 집합 {len(eligible)}건 / 점수 상위 {len(scored)}건)"
        )
    return picked


def run(args, *, slug, status, published_at, copy_overrides) -> Publication:
    profile_label = NUDGE_LABELS[args.profile]
    region_name = get_region_name(args.region)

    conn = open_local_db()
    try:
        warning = stale_trade_warning(conn)
        if warning:
            print(warning)
        eligible = fetch_recent_trades(
            conn,
            args.region,
            max_amount=args.max_price,
            min_area=args.min_area,
            max_area=args.max_area,
        )
    finally:
        conn.close()
    if not eligible:
        raise ValueError(f"{region_name}: 조건에 맞는 최근 90일 계약 거래가 없습니다.")

    payload = {
        "nudges": [args.profile],
        "top_n": SCORE_POOL_SIZE,
        "sigungu_code": args.region,
        "min_hhld": args.min_hhld,
    }
    if args.max_price is not None:
        payload["max_price"] = args.max_price
    if args.min_area is not None:
        payload["min_area"] = args.min_area
    if args.max_area is not None:
        payload["max_area"] = args.max_area
    scored = post_nudge_score(payload)

    picked = select_candidates(eligible, scored, args.min_hhld)

    items = []
    for rank, row in enumerate(picked, start=1):
        trade = row["trade"]
        detail = get_apartment_detail(row["pnu"])
        built_year = (trade.get("use_apr_day") or "")[:4] or "정보 없음"
        metrics = [
            Metric("최근 실거래가", format_eok(trade["deal_amount"]), ""),
            Metric("전용면적", f"{trade['exclu_use_ar']:.1f}㎡", ""),
            Metric("준공연도", f"{built_year}년" if built_year != "정보 없음" else built_year, ""),
        ]
        metrics.extend(extract_candidate_metrics(detail, trade["exclu_use_ar"]))
        items.append(
            Item(
                rank=rank,
                name=trade["bld_nm"],
                region=region_name,
                pnu=row["pnu"],
                metrics=tuple(metrics),
                reasons=tuple(contributor_labels(row["top_contributors"], 3)),
            )
        )

    top_contribs = contributor_labels(picked[0]["top_contributors"], 3)
    copy = build_lifestyle_copy(profile_label, region_name, top_contribs)
    if copy_overrides:
        copy = apply_overrides(copy, copy_overrides)

    today = date.today().isoformat()
    conditions = [
        Condition("라이프스타일", profile_label),
        Condition("지역", region_name),
        Condition("접근성", "지하철·버스 접근성 반영"),
    ]
    if args.max_price is not None:
        conditions.append(Condition("예산", f"{format_eok(args.max_price)} 이하"))
    conditions.append(Condition("기준일", today))

    cta_filters = {"min_hhld": args.min_hhld}
    if args.max_price is not None:
        cta_filters["max_price"] = args.max_price
    if args.min_area is not None:
        cta_filters["min_area"] = args.min_area
    if args.max_area is not None:
        cta_filters["max_area"] = args.max_area

    return Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        status=status,
        series=Series.LIFESTYLE,
        title=f"{region_name} {profile_label} 추천 단지",
        eyebrow=f"라이프스타일 추천 · {profile_label}",
        hook=copy.hook,
        summary=f"{region_name}에서 {profile_label} 넛지 점수가 높고 최근 거래가 있는 단지입니다.",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        published_at=published_at,
        data_as_of=today,
        period_label="계약일 기준 최근 90일 실거래 + 넛지 점수",
        cover_image="01-cover.png",
        cover_alt=f"{region_name} {profile_label} 아파트 추천 카드",
        conditions=tuple(conditions),
        items=tuple(items),
        secondary_items=None,
        comparison=None,
        narrative=Narrative(why=copy.why, fit_for=copy.fit_for),
        methodology=(
            f"{profile_label} 넛지 상위 {SCORE_POOL_SIZE} 후보와 최근 90일 계약 거래 보유 단지의 교집합",
            "표시 가격은 각 단지의 최근 계약 거래 기준",
        ),
        caveats=(
            "투자 자문이 아닙니다.",
            "통근시간이 아닌 지하철·버스 접근성 점수 기준입니다.",
            "지도에서는 최신 데이터로 다시 계산되어 순서가 달라질 수 있습니다.",
        ),
        map_ctas=(
            MapCta(
                id="map-main",
                label=f"{profile_label} 조건 그대로 {region_name} 지도에서 보기",
                nudges=(args.profile,),
                sigungu_code=args.region,
                region_label=region_name,
                filters=cta_filters,
            ),
        ),
    )
```

- [ ] **Step 4: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (62 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/insta_cards/series/lifestyle.py scripts/tests/test_insta_cards.py
git commit -m "feat(insta): lifestyle 시리즈 — 넛지 프로필 파라미터화 추천"
```

---

### Task 13: cli.py + __main__.py + 기존 스크립트 shim + requirements

**Files:**
- Create: `scripts/insta_cards/cli.py`
- Create: `scripts/insta_cards/__main__.py`
- Modify: `scripts/generate_insta_cards.py` (전체 내용을 shim 으로 교체)
- Modify: `requirements.txt` (PyYAML 추가 — 이미 설치되어 있으므로 선언만)
- Modify: `scripts/tests/test_insta_cards.py` (TestCli 클래스 추가)

**Interfaces:**
- Consumes: 모든 시리즈 모듈의 `run(args, *, slug, status, published_at, copy_overrides)`, `publication.validate/SERIES_CLI_NAMES/SERIES_SLUGS/SLUG_PATTERN`, `slides.build_slides`, `output.write_publication/SlugConflictError`, `copywriting.load_copy_overrides/NUDGE_LABELS`
- Produces:
  - `build_parser() -> argparse.ArgumentParser`
  - `build_auto_slug(series, args) -> str` — trade-top: `trade-top-{yyyymmdd}` / compare·budget-choice: `{series_slug}-{codeA}-vs-{codeB}-{yyyymmdd}` / lifestyle: `lifestyle-{profile}-{region}-{yyyymmdd}` / value: `value-{region}-{yyyymmdd}`. 결과가 SLUG_PATTERN 위반(한글 키워드 등)이면 `SystemExit`("--slug 를 직접 지정하세요") — 자동 음차 변환 금지
  - `main(argv: list[str] | None = None) -> None`
- CLI 옵션 전체 (기존 3종 옵션 하위호환 유지):
  - 공통: `--series`(필수, choices=SERIES_CLI_NAMES 키), `--slug`, `--publish`(store_true), `--copy-file`, `--dry-run`(store_true), `--force`(store_true)
  - trade-top: `--days`(기본 7)
  - compare/budget-choice: `--regions`
  - compare/value/budget-choice: `--nudge`(기본: compare=newlywed, value·budget-choice=cost)
  - value/lifestyle: `--region`(value 기본 "서울"), `--min-hhld`(기본 100)
  - budget-choice: `--budget`, `--area-a`, `--area-b`, `--area-tolerance`(기본 5.0), `--pnu-a`, `--pnu-b`
  - lifestyle: `--profile`, `--max-price`, `--min-area`, `--max-area`
- main 흐름: 파싱 → 시리즈 결정 → 시리즈별 필수 인자 검증(budget-choice 는 --budget/--regions/--area-a/--area-b, lifestyle 은 --profile/--region — 누락 시 `parser.error`) → nudge/profile 이 NUDGE_LABELS 에 없으면 `parser.error` → slug 결정(auto or --slug, SLUG_PATTERN 검증) → status/published_at (`--publish` → "published"/오늘, 아니면 "draft"/None) → copy_overrides 로드 → `pub = series.run(...)` → `publication.validate(pub)` → `--dry-run` 이면 요약 출력 후 종료(파일 생성 일절 없음) → `slides.build_slides(pub)` → `output.write_publication(pub, slides, force=args.force)` → 저장 경로 출력

- [ ] **Step 1: 실패하는 테스트 작성** — `TestCli`:

```python
class TestCli(unittest.TestCase):
    def test_legacy_options_still_parse(self):
        from scripts.insta_cards import cli

        parser = cli.build_parser()
        args = parser.parse_args(
            ["--series", "value", "--region", "서울", "--nudge", "cost", "--min-hhld", "100"]
        )
        self.assertEqual(args.series, "value")
        self.assertEqual(args.min_hhld, 100)

    def test_new_series_options_parse(self):
        from scripts.insta_cards import cli

        parser = cli.build_parser()
        args = parser.parse_args(
            ["--series", "budget-choice", "--budget", "70000",
             "--regions", "11440,41135", "--area-a", "59", "--area-b", "84"]
        )
        self.assertEqual(args.budget, 70000)
        self.assertEqual(args.area_tolerance, 5.0)

    def test_auto_slug_for_budget_choice(self):
        from types import SimpleNamespace

        from scripts.insta_cards import cli, publication as p

        args = SimpleNamespace(regions="11440,41135", region=None, profile=None, days=7)
        slug = cli.build_auto_slug(p.Series.BUDGET_CHOICE, args)
        self.assertRegex(slug, r"^budget-choice-11440-vs-41135-\d{8}$")

    def test_auto_slug_rejects_non_ascii(self):
        from types import SimpleNamespace

        from scripts.insta_cards import cli, publication as p

        args = SimpleNamespace(regions=None, region="서울", profile=None, days=7)
        with self.assertRaises(SystemExit):
            cli.build_auto_slug(p.Series.VALUE, args)

    def test_dry_run_writes_nothing(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from scripts.insta_cards import cli

        pub = make_valid_value_publication()
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("scripts.insta_cards.series.value.run", return_value=pub),
                patch("scripts.insta_cards.output.OUTPUT_ROOT", Path(tmp)),
            ):
                cli.main(
                    ["--series", "value", "--region", "서울",
                     "--slug", "value-seoul-20260713", "--dry-run"]
                )
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_main_writes_publication(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from scripts.insta_cards import cli

        pub = make_valid_value_publication()
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("scripts.insta_cards.series.value.run", return_value=pub),
                patch("scripts.insta_cards.cli.OUTPUT_ROOT", Path(tmp)),
            ):
                cli.main(
                    ["--series", "value", "--region", "서울",
                     "--slug", "value-seoul-20260713"]
                )
            found = list(Path(tmp).glob("*/value-seoul-20260713/publication.json"))
            self.assertEqual(len(found), 1)

    def test_shim_module_delegates(self):
        import importlib

        shim = importlib.import_module("scripts.generate_insta_cards")
        from scripts.insta_cards import cli

        self.assertIs(shim.main, cli.main)
```

- [ ] **Step 2: 실패 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards.TestCli -v`
Expected: ERROR — `ModuleNotFoundError: ... cli`

- [ ] **Step 3: cli.py 구현**

```python
"""CLI — 시리즈 디스패치. 검증 실패·데이터 부족은 그대로 예외로 죽는다.

사용:
  .venv/bin/python -m scripts.insta_cards --series budget-choice \
      --budget 70000 --regions 11440,41135 --area-a 59 --area-b 84
  .venv/bin/python -m scripts.insta_cards --series value --region 서울 --slug value-seoul-20260713
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# 직접 실행(-m 없이 shim 경유) 대비 — 프로젝트 루트를 sys.path 에 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.insta_cards import output as output_mod  # noqa: E402
from scripts.insta_cards.copywriting import NUDGE_LABELS, load_copy_overrides  # noqa: E402
from scripts.insta_cards.output import OUTPUT_ROOT, write_publication  # noqa: E402
from scripts.insta_cards.publication import (  # noqa: E402
    SERIES_CLI_NAMES,
    SERIES_SLUGS,
    SLUG_PATTERN,
    Series,
    validate,
)
from scripts.insta_cards.slides import build_slides  # noqa: E402

DEFAULT_TRADE_TOP_DAYS = 7
DEFAULT_MIN_HOUSEHOLDS = 100
DEFAULT_AREA_TOLERANCE = 5.0
DEFAULT_NUDGES = {
    Series.COMPARE: "newlywed",
    Series.VALUE: "cost",
    Series.BUDGET_CHOICE: "cost",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="인스타그램 카드뉴스 캐러셀 생성")
    parser.add_argument("--series", required=True, choices=sorted(SERIES_CLI_NAMES))
    parser.add_argument("--slug", type=str, default=None, help="미지정 시 자동 생성")
    parser.add_argument("--publish", action="store_true", help="status=published 로 발행")
    parser.add_argument("--copy-file", type=str, default=None, help="문구 오버라이드 YAML")
    parser.add_argument("--dry-run", action="store_true", help="검증·선정 결과만 출력")
    parser.add_argument("--force", action="store_true", help="동일 slug 디렉토리 통째 교체")
    # trade-top
    parser.add_argument("--days", type=int, default=DEFAULT_TRADE_TOP_DAYS)
    # compare / budget-choice
    parser.add_argument("--regions", type=str, default=None, help="시군구 코드 2개, 콤마 구분")
    parser.add_argument("--nudge", type=str, default=None)
    # value / lifestyle
    parser.add_argument("--region", type=str, default=None, help="value: 키워드 / lifestyle: 시군구 코드")
    parser.add_argument("--min-hhld", type=int, default=DEFAULT_MIN_HOUSEHOLDS)
    # budget-choice
    parser.add_argument("--budget", type=int, default=None, help="예산 상한 (만원)")
    parser.add_argument("--area-a", type=float, default=None)
    parser.add_argument("--area-b", type=float, default=None)
    parser.add_argument("--area-tolerance", type=float, default=DEFAULT_AREA_TOLERANCE)
    parser.add_argument("--pnu-a", type=str, default=None)
    parser.add_argument("--pnu-b", type=str, default=None)
    # lifestyle
    parser.add_argument("--profile", type=str, default=None, choices=sorted(NUDGE_LABELS))
    parser.add_argument("--max-price", type=int, default=None)
    parser.add_argument("--min-area", type=float, default=None)
    parser.add_argument("--max-area", type=float, default=None)
    return parser


def build_auto_slug(series: Series, args) -> str:
    stamp = date.today().strftime("%Y%m%d")
    series_slug = SERIES_SLUGS[series]
    if series is Series.TRADE_TOP:
        slug = f"{series_slug}-{stamp}"
    elif series in (Series.COMPARE, Series.BUDGET_CHOICE):
        codes = [c.strip() for c in (args.regions or "").split(",") if c.strip()]
        slug = f"{series_slug}-{'-vs-'.join(codes)}-{stamp}"
    elif series is Series.LIFESTYLE:
        slug = f"{series_slug}-{args.profile}-{args.region}-{stamp}"
    else:  # VALUE
        slug = f"{series_slug}-{args.region}-{stamp}"
    if not SLUG_PATTERN.match(slug):
        raise SystemExit(
            f"자동 slug '{slug}' 가 형식(소문자 ASCII+하이픈)에 맞지 않습니다 — "
            "--slug 를 직접 지정하세요."
        )
    return slug


def _validate_series_args(parser, series: Series, args) -> None:
    def require(names: list[str]) -> None:
        missing = [n for n in names if getattr(args, n.replace("-", "_")) is None]
        if missing:
            parser.error(f"--series {SERIES_SLUGS[series]} 에는 --{' --'.join(missing)} 가 필요합니다.")

    if series in (Series.COMPARE, Series.BUDGET_CHOICE):
        require(["regions"])
    if series is Series.BUDGET_CHOICE:
        require(["budget", "area-a", "area-b"])
    if series is Series.LIFESTYLE:
        require(["profile", "region"])
    if series is Series.VALUE and args.region is None:
        args.region = "서울"  # 기존 CLI 기본값 하위호환
    if args.nudge is None:
        args.nudge = DEFAULT_NUDGES.get(series, "cost")
    if args.nudge not in NUDGE_LABELS:
        parser.error(f"알 수 없는 넛지 id: {args.nudge} (허용: {', '.join(sorted(NUDGE_LABELS))})")


def _print_dry_run_summary(pub) -> None:
    print(f"[dry-run] slug={pub.slug} series={pub.series.value} status={pub.status}")
    print(f"[dry-run] title: {pub.title}")
    print(f"[dry-run] hook:  {pub.hook}")
    print(f"[dry-run] items ({len(pub.items)}):")
    for item in pub.items:
        first = item.metrics[0]
        print(f"  {item.rank}. {item.name} — {first.label} {first.value}{first.unit}")
    if pub.secondary_items:
        print(f"[dry-run] secondary_items: {len(pub.secondary_items)}건")
    print(f"[dry-run] map_ctas: {[cta.id for cta in pub.map_ctas]}")
    print("[dry-run] 파일은 생성하지 않았습니다.")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    series = SERIES_CLI_NAMES[args.series]
    _validate_series_args(parser, series, args)

    slug = args.slug or build_auto_slug(series, args)
    if not SLUG_PATTERN.match(slug):
        raise SystemExit(f"slug '{slug}' 형식 오류 — 소문자 ASCII+하이픈만 허용")
    status = "published" if args.publish else "draft"
    published_at = date.today().isoformat() if args.publish else None
    copy_overrides = load_copy_overrides(args.copy_file) if args.copy_file else None

    # 시리즈 모듈은 지연 임포트 — batch.db 의존을 실제 사용 시점으로 미룬다
    from scripts.insta_cards.series import (  # noqa: PLC0415
        budget_choice,
        compare,
        lifestyle,
        trade_top,
        value,
    )

    runners = {
        Series.TRADE_TOP: trade_top.run,
        Series.COMPARE: compare.run,
        Series.VALUE: value.run,
        Series.BUDGET_CHOICE: budget_choice.run,
        Series.LIFESTYLE: lifestyle.run,
    }
    pub = runners[series](
        args, slug=slug, status=status, published_at=published_at,
        copy_overrides=copy_overrides,
    )
    validate(pub)

    if args.dry_run:
        _print_dry_run_summary(pub)
        return

    slides = build_slides(pub)
    final_dir = write_publication(pub, slides, force=args.force, root=OUTPUT_ROOT)
    print(f"saved: {final_dir} ({len(slides)}장 + publication.json)")


if __name__ == "__main__":
    main()
```

주의: `test_main_writes_publication` 은 `cli.OUTPUT_ROOT` 를 patch 하므로 cli 는 `OUTPUT_ROOT` 를 모듈 이름공간으로 import 해서 `write_publication(..., root=OUTPUT_ROOT)` 처럼 명시 전달해야 한다 (위 코드가 그렇게 되어 있다). `test_dry_run_writes_nothing` 은 `output.OUTPUT_ROOT` 를 patch — dry-run 경로는 output 을 아예 호출하지 않으므로 둘 다 통과해야 정상.

- [ ] **Step 4: __main__.py + shim + requirements**

`scripts/insta_cards/__main__.py`:

```python
from scripts.insta_cards.cli import main

main()
```

`scripts/generate_insta_cards.py` 전체 교체:

```python
"""(deprecated) 인스타 카드 생성 구 진입점 — scripts/insta_cards 패키지로 이관됨.

기존 옵션(--series trade-top/compare/value, --days, --regions, --nudge,
--region, --min-hhld)은 새 CLI 가 그대로 받는다. 출력은 단일 카드가 아니라
캐러셀 디렉토리(reports/insta/{날짜}/{slug}/)로 바뀌었다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.insta_cards.cli import main  # noqa: E402

if __name__ == "__main__":
    print(
        "[deprecated] scripts/generate_insta_cards.py 대신 "
        "`python -m scripts.insta_cards` 를 사용하세요.",
        file=sys.stderr,
    )
    main()
```

`requirements.txt` 에 한 줄 추가 (알파벳 순 위치에):

```
PyYAML
```

- [ ] **Step 5: 통과 확인**

Run: `../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v`
Expected: `OK` (69 tests)

Run: `../../.venv/bin/python -m scripts.insta_cards --help`
Expected: usage 출력에 `--series {budget-choice,compare,lifestyle,trade-top,value}` 포함

- [ ] **Step 6: 커밋**

```bash
git add scripts/insta_cards/cli.py scripts/insta_cards/__main__.py scripts/generate_insta_cards.py requirements.txt scripts/tests/test_insta_cards.py
git commit -m "feat(insta): CLI 진입점 + 기존 스크립트 shim 전환"
```

---

### Task 14: 통합 검증 + 파일럿 draft 스모크

**Files:**
- 수정 없음 (검증 전용). 발견된 문제는 해당 모듈에서 수정 후 재검증.

**Interfaces:**
- Consumes: 전체 패키지, 로컬 DB(증분 sync 완료 상태), 운영 API

- [ ] **Step 1: 린트/포맷 검증**

```bash
../../.venv/bin/ruff format --check scripts/insta_cards scripts/tests
../../.venv/bin/ruff check scripts/insta_cards scripts/tests
```
Expected: 둘 다 오류 0건. 실패 시 `ruff format` / `ruff check --fix` 로 수정 후 테스트 재실행.

- [ ] **Step 2: 전체 테스트**

```bash
../../.venv/bin/python -m unittest scripts.tests.test_insta_cards -v
```
Expected: `OK` (69 tests)

- [ ] **Step 3: 로컬 DB 신선도 확인 (수동)**

```bash
cd ../.. && .venv/bin/python -m batch.sync_from_railway && cd - 
```
Expected: 증분 동기화 완료 로그. (trade-top·budget-choice·lifestyle·value·compare 모두 로컬 거래 테이블 사용)

- [ ] **Step 4: 실데이터 dry-run 스모크 (수동, 네트워크+DB 필요)**

```bash
../../.venv/bin/python -m scripts.insta_cards --series trade-top --dry-run
../../.venv/bin/python -m scripts.insta_cards --series value --region 서울 --slug value-seoul-pilot --dry-run
../../.venv/bin/python -m scripts.insta_cards --series budget-choice --budget 70000 \
    --regions 11440,41135 --area-a 59 --area-b 84 --dry-run
../../.venv/bin/python -m scripts.insta_cards --series lifestyle --profile newlywed \
    --region 41135 --max-price 70000 --dry-run
```
Expected: 각각 `[dry-run]` 요약 출력 + 파일 미생성. 데이터 부족 예외가 나면 지역·예산·면적 파라미터를 조정해 재시도 (조건 완화는 파라미터로만 — 코드 수정 금지).

- [ ] **Step 5: 파일럿 draft 2건 실제 생성 + 육안 확인 (수동)**

```bash
../../.venv/bin/python -m scripts.insta_cards --series budget-choice --budget 70000 \
    --regions 11440,41135 --area-a 59 --area-b 84
../../.venv/bin/python -m scripts.insta_cards --series lifestyle --profile newlywed \
    --region 41135 --max-price 70000
open reports/insta/$(date +%F)/
```
육안 체크리스트: 9장/8장 전부 생성, 표지 훅 2줄 이내, 조건 칩 잘림 없음, 비교표 열 정렬, footer 문구, publication.json 의 items·map_ctas 값이 카드와 일치.

- [ ] **Step 6: 기존 실행 경로 회귀 확인 (수동)**

```bash
../../.venv/bin/python scripts/generate_insta_cards.py --series value --region 서울 --slug value-seoul-shim-check --dry-run
```
Expected: deprecated 안내 후 dry-run 요약 정상 출력.

- [ ] **Step 7: 커밋 (검증 중 수정이 있었던 경우만)**

```bash
git status
git add -A scripts/ requirements.txt
git commit -m "fix(insta): 통합 스모크에서 발견된 문제 수정"
```

---

## Self-Review 결과 (계획 작성 후 점검)

1. **Spec 커버리지**: §3 패키지 구조(Task 1~7,13) / §4 슬라이드·텍스트 한도(Task 2,6) / §5-1~5-6 시리즈 사양(Task 8~12) / §6 CLI·자동 slug·shim(Task 13) / §7 검증 규칙(Task 3) / §8 테스트 케이스(각 Task Step 1 + Task 14) / §9 파일럿(Task 14 Step 5) — 커버 확인.
2. **의도적 제외**: spec §6 "CLI 시작 시 마지막 sync 시각 24h 초과 경고"는 datasources.stale_trade_warning 으로 구현하되 각 시리즈 run() 에서 conn 확보 직후 호출 (cli 가 아닌 시리즈 레벨 — conn 소유자가 시리즈이기 때문).
3. **타입 일관성**: 시리즈 run 시그니처 `run(args, *, slug, status, published_at, copy_overrides)` 5개 모듈 동일 / `fetch_recent_trades` 반환 dict 키 6개 동일 / Metric·Item 필드 Task 3 정의와 이후 사용 일치 확인.
4. **테스트 수 집계**: Task 순서대로 4→10→23→29→35→40→44→47→51→54→58→62→69 (누적). 실행 중 어긋나면 직전 Task 의 테스트 수정 여부를 확인할 것.
