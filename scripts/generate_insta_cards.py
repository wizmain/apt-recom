"""인스타그램 카드 자동 생성 — 거래 TOP5 / 지역 비교 / 숨은 가성비.

1080x1080 PNG 카드를 ``reports/insta/{YYYY-MM-DD}/`` 아래에 저장한다.
DB 는 batch.db (get_connection/query_all) 로 로컬 DictConnection 을 사용하고,
compare/value 시리즈는 운영 공개 API(api.apt-recom.kr) 를 호출한다.

사용:
  .venv/bin/python scripts/generate_insta_cards.py --series trade-top [--days 7]
  .venv/bin/python scripts/generate_insta_cards.py --series compare --regions 11440,11200 [--nudge newlywed]
  .venv/bin/python scripts/generate_insta_cards.py --series value [--region 서울] [--nudge cost]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# 프로젝트 루트를 sys.path 에 추가 — `python scripts/generate_insta_cards.py` 직접
# 실행 시(-m 없이) 에도 `batch` 패키지를 임포트하기 위함. web/backend 코드에서
# batch 를 sys.path 로 끌어오는 것은 Railway 배포 제약(backend 디렉토리만 배포)
# 때문에 금지지만, 이 스크립트는 로컬 전용 배치 유틸이라 해당 제약이 없다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from batch.db import get_connection, query_all  # noqa: E402

# ---------------------------------------------------------------------------
# 디자인 토큰 — 브랜드 아이콘(web/toss-miniapp/assets/jiptori-app-icon*)과 통일.
# 색은 여기 한 곳에서만 정의하고 렌더링 코드는 이 상수만 참조한다(하드코딩 금지).
# ---------------------------------------------------------------------------
CANVAS_SIZE = 1080

COLOR_BG_TOP = (15, 27, 61)  # #0f1b3d
COLOR_BG_BOTTOM = (27, 17, 64)  # #1b1140
COLOR_ACCENT_BLUE = (96, 165, 250)  # #60a5fa
COLOR_ACCENT_GREEN = (52, 211, 153)  # #34d399
COLOR_TEXT_WHITE = (255, 255, 255)
COLOR_TEXT_LIGHT = (219, 234, 254)  # #dbeafe
COLOR_TEXT_GRAY = (148, 163, 184)  # 푸터 보조문구용 회색

FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
# index 는 AppleSDGothicNeo.ttc 실측 결과(0=Regular,2=Medium,4=SemiBold,
# 6=Bold,14=ExtraBold,16=Heavy) — 시스템 폰트 컬렉션 순서가 바뀔 수 있으니
# 폰트가 교체되면 다시 실측할 것.
FONT_WEIGHT_INDEX = {
    "regular": 0,
    "medium": 2,
    "semibold": 4,
    "bold": 6,
    "extrabold": 14,
}

FOOTER_BRAND = "apt-recom.kr"
FOOTER_DISCLAIMER = "공공데이터 기반 · 투자 자문이 아닙니다"

PROD_API_BASE = "https://api.apt-recom.kr"
API_TIMEOUT_SECONDS = 15

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

DEFAULT_TRADE_TOP_DAYS = 7
DEFAULT_COMPARE_NUDGE = "newlywed"
DEFAULT_VALUE_NUDGE = "cost"
VALUE_CANDIDATE_POOL_SIZE = 30
CARD_LIST_SIZE = 5

OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "reports" / "insta"

MARGIN_X = 72


# ---------------------------------------------------------------------------
# 폰트 / 렌더링 공통 유틸
# ---------------------------------------------------------------------------
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def get_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(
            FONT_PATH, size, index=FONT_WEIGHT_INDEX[weight]
        )
    return _font_cache[key]


def make_gradient_background() -> Image.Image:
    """세로 그라디언트(#0f1b3d → #1b1140) 배경. PIL 로 직접 그린다."""
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
    """폭 초과 시 말줄임(…) 처리. draw.textlength 로 실측."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    truncated = text
    while truncated and draw.textlength(truncated + ellipsis, font=font) > max_width:
        truncated = truncated[:-1]
    return truncated + ellipsis


def format_eok(manwon: int) -> str:
    """만원 단위 정수 → '4억 3,500만원' 포맷 (deal_amount 는 만원 단위)."""
    eok, remainder = divmod(manwon, 10000)
    if eok <= 0:
        return f"{manwon:,}만원"
    if remainder:
        return f"{eok}억 {remainder:,}만원"
    return f"{eok}억"


def format_price_per_m2(won_per_m2: float) -> str:
    """apt_price_score.price_per_m2 는 원/㎡ 단위 → '만원/㎡' 로 변환."""
    return f"{round(won_per_m2 / 10000):,}만원/㎡"


# ---------------------------------------------------------------------------
# 공통 레이아웃: 헤더(시리즈 라벨 + 타이틀) / 푸터
# ---------------------------------------------------------------------------
@dataclass
class CardCanvas:
    image: Image.Image
    draw: ImageDraw.ImageDraw
    content_top: int
    content_bottom: int


def build_card_canvas(series_label: str, title_lines: list[str]) -> CardCanvas:
    """상단 라벨 + 타이틀(2줄 이내) + 하단 고정 푸터가 포함된 베이스 캔버스."""
    img = make_gradient_background()
    draw = ImageDraw.Draw(img)

    label_font = get_font("semibold", 30)
    draw.text((MARGIN_X, 72), series_label, font=label_font, fill=COLOR_ACCENT_GREEN)

    title_font = get_font("extrabold", 60)
    title_y = 130
    for line in title_lines[:2]:
        draw.text((MARGIN_X, title_y), line, font=title_font, fill=COLOR_TEXT_WHITE)
        title_y += 74

    content_top = title_y + 24
    content_bottom = _draw_footer(draw, img.size)

    return CardCanvas(
        image=img, draw=draw, content_top=content_top, content_bottom=content_bottom
    )


def _draw_footer(draw: ImageDraw.ImageDraw, size: tuple[int, int]) -> int:
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


# ---------------------------------------------------------------------------
# ① trade-top — 로컬 DB, 신고일(created_at) 기준 최근 N일 집계
# ---------------------------------------------------------------------------
def fetch_top_price_trades(conn, days: int) -> list[dict]:
    rows = query_all(
        conn,
        """
        SELECT
            COALESCE(a.display_name, a.bld_nm, t.apt_nm) AS apt_display_name,
            t.sgg_cd,
            t.deal_amount,
            t.exclu_use_ar
        FROM trade_history t
        LEFT JOIN trade_apt_mapping m ON t.apt_seq = m.apt_seq
        LEFT JOIN apartments a ON a.pnu = m.pnu
        WHERE t.created_at >= NOW() - (%s || ' days')::interval
        ORDER BY t.deal_amount DESC
        LIMIT %s
        """,
        [days, CARD_LIST_SIZE],
    )
    sigungu_names = _load_sigungu_names(conn)
    return [
        {
            "apt_display_name": r["apt_display_name"],
            "sigungu_name": sigungu_names.get(r["sgg_cd"], r["sgg_cd"]),
            "deal_amount": r["deal_amount"],
            "exclu_use_ar": r["exclu_use_ar"],
        }
        for r in rows
    ]


def fetch_top_hot_districts(conn, days: int) -> list[dict]:
    rows = query_all(
        conn,
        """
        SELECT t.sgg_cd, COUNT(*) AS report_count
        FROM trade_history t
        WHERE t.created_at >= NOW() - (%s || ' days')::interval
        GROUP BY t.sgg_cd
        ORDER BY report_count DESC
        LIMIT %s
        """,
        [days, CARD_LIST_SIZE],
    )
    sigungu_names = _load_sigungu_names(conn)
    return [
        {
            "sigungu_name": sigungu_names.get(r["sgg_cd"], r["sgg_cd"]),
            "report_count": r["report_count"],
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


def render_trade_top_price_card(rows: list[dict], days: int) -> Image.Image:
    canvas = build_card_canvas(
        f"신고일 기준 · 최근 {days}일",
        ["이번 주 신고된", "최고가 거래 TOP 5"],
    )
    draw = canvas.draw
    rank_font = get_font("extrabold", 40)
    name_font = get_font("semibold", 34)
    meta_font = get_font("regular", 26)
    amount_font = get_font("extrabold", 38)

    row_height = (canvas.content_bottom - canvas.content_top) / CARD_LIST_SIZE
    for i, row in enumerate(rows):
        y = canvas.content_top + i * row_height + 8
        draw.text((MARGIN_X, y), f"{i + 1}", font=rank_font, fill=COLOR_ACCENT_BLUE)

        name_x = MARGIN_X + 64
        name_max_width = CANVAS_SIZE - MARGIN_X - name_x - 20
        name = truncate_text(
            draw, row["apt_display_name"] or "-", name_font, name_max_width
        )
        draw.text((name_x, y), name, font=name_font, fill=COLOR_TEXT_WHITE)

        meta = f"{row['sigungu_name']} · 전용 {row['exclu_use_ar']:.0f}㎡"
        draw.text((name_x, y + 42), meta, font=meta_font, fill=COLOR_TEXT_LIGHT)

        amount_text = format_eok(row["deal_amount"])
        amount_w = draw.textlength(amount_text, font=amount_font)
        draw.text(
            (CANVAS_SIZE - MARGIN_X - amount_w, y + 6),
            amount_text,
            font=amount_font,
            fill=COLOR_ACCENT_GREEN,
        )
    return canvas.image


def render_trade_top_hot_card(rows: list[dict], days: int) -> Image.Image:
    canvas = build_card_canvas(
        f"신고일 기준 · 최근 {days}일",
        ["거래 신고 급증", "동네 TOP 5"],
    )
    draw = canvas.draw
    rank_font = get_font("extrabold", 40)
    name_font = get_font("semibold", 38)
    count_font = get_font("extrabold", 38)

    row_height = (canvas.content_bottom - canvas.content_top) / CARD_LIST_SIZE
    for i, row in enumerate(rows):
        y = canvas.content_top + i * row_height + 14
        draw.text((MARGIN_X, y), f"{i + 1}", font=rank_font, fill=COLOR_ACCENT_BLUE)

        name_x = MARGIN_X + 64
        name_max_width = CANVAS_SIZE - MARGIN_X - name_x - 220
        name = truncate_text(draw, row["sigungu_name"], name_font, name_max_width)
        draw.text((name_x, y), name, font=name_font, fill=COLOR_TEXT_WHITE)

        count_text = f"{row['report_count']:,}건"
        count_w = draw.textlength(count_text, font=count_font)
        draw.text(
            (CANVAS_SIZE - MARGIN_X - count_w, y),
            count_text,
            font=count_font,
            fill=COLOR_ACCENT_GREEN,
        )
    return canvas.image


def generate_trade_top_cards(days: int) -> list[tuple[str, Image.Image]]:
    conn = get_connection()
    try:
        price_rows = fetch_top_price_trades(conn, days)
        hot_rows = fetch_top_hot_districts(conn, days)
    finally:
        conn.close()

    cards = [
        ("trade-top-price.png", render_trade_top_price_card(price_rows, days)),
        ("trade-top-hot.png", render_trade_top_hot_card(hot_rows, days)),
    ]
    return cards


# ---------------------------------------------------------------------------
# ② compare — 운영 공개 API
# ---------------------------------------------------------------------------
def fetch_region_name(sigungu_code: str) -> str:
    resp = requests.get(
        f"{PROD_API_BASE}/api/dashboard/regions", timeout=API_TIMEOUT_SECONDS
    )
    resp.raise_for_status()
    for region in resp.json():
        if region["code"] == sigungu_code:
            return region["name"]
    return sigungu_code


def fetch_nudge_top(sigungu_code: str, nudge: str, top_n: int) -> list[dict]:
    resp = requests.post(
        f"{PROD_API_BASE}/api/nudge/score",
        json={"nudges": [nudge], "top_n": top_n, "sigungu_code": sigungu_code},
        timeout=API_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def render_compare_card(region_a: dict, region_b: dict, nudge: str) -> Image.Image:
    nudge_label = NUDGE_LABELS[nudge]
    canvas = build_card_canvas(
        "지역 비교",
        [f"{region_a['name']} vs {region_b['name']}", f"{nudge_label} 대결"],
    )
    draw = canvas.draw

    winner = region_a if region_a["avg_score"] >= region_b["avg_score"] else region_b

    score_font = get_font("extrabold", 96)
    name_font = get_font("semibold", 32)
    top1_font = get_font("regular", 26)

    block_width = CANVAS_SIZE / 2
    block_content_height = 176 + 40  # score~name~top1 라벨까지 실측 높이
    content_area_height = canvas.content_bottom - canvas.content_top
    block_top = canvas.content_top + (content_area_height - block_content_height) / 2

    for i, region in enumerate((region_a, region_b)):
        center_x = block_width * i + block_width / 2
        color = COLOR_ACCENT_GREEN if region is winner else COLOR_ACCENT_BLUE

        score_text = f"{region['avg_score']:.1f}"
        score_w = draw.textlength(score_text, font=score_font)
        draw.text(
            (center_x - score_w / 2, block_top), score_text, font=score_font, fill=color
        )

        name_max_width = block_width - 48
        name = truncate_text(draw, region["name"], name_font, name_max_width)
        name_w = draw.textlength(name, font=name_font)
        draw.text(
            (center_x - name_w / 2, block_top + 130),
            name,
            font=name_font,
            fill=COLOR_TEXT_WHITE,
        )

        top1_label = f"1위 {region['top1_apt_name']}"
        top1_label = truncate_text(draw, top1_label, top1_font, name_max_width)
        top1_w = draw.textlength(top1_label, font=top1_font)
        draw.text(
            (center_x - top1_w / 2, block_top + 176),
            top1_label,
            font=top1_font,
            fill=COLOR_TEXT_LIGHT,
        )

    return canvas.image


def generate_compare_card(sigungu_codes: list[str], nudge: str) -> Image.Image:
    if len(sigungu_codes) != 2:
        raise ValueError(
            "compare 시리즈는 --regions 에 시군구 코드 2개(콤마 구분)가 필요합니다."
        )

    regions = []
    for code in sigungu_codes:
        name = fetch_region_name(code)
        top10 = fetch_nudge_top(code, nudge, top_n=10)
        if not top10:
            raise ValueError(f"{name}({code}) 에 대한 넛지 점수 결과가 없습니다.")
        avg_score = sum(r["score"] for r in top10) / len(top10)
        regions.append(
            {
                "code": code,
                "name": name,
                "avg_score": avg_score,
                "top1_apt_name": top10[0]["bld_nm"],
            }
        )

    return render_compare_card(regions[0], regions[1], nudge)


# ---------------------------------------------------------------------------
# ③ value — 운영 공개 API(cost 상위 30) + 로컬 DB price_per_m2 보충
# ---------------------------------------------------------------------------
def fetch_nudge_candidates(region_keyword: str, nudge: str, top_n: int) -> list[dict]:
    resp = requests.post(
        f"{PROD_API_BASE}/api/nudge/score",
        json={"nudges": [nudge], "top_n": top_n, "keyword": region_keyword},
        timeout=API_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_price_per_m2_by_pnu(conn, pnu_list: list[str]) -> dict[str, float]:
    if not pnu_list:
        return {}
    placeholders = ",".join(["%s"] * len(pnu_list))
    rows = query_all(
        conn,
        f"SELECT pnu, price_per_m2 FROM apt_price_score WHERE pnu IN ({placeholders}) AND price_per_m2 IS NOT NULL",
        pnu_list,
    )
    return {r["pnu"]: r["price_per_m2"] for r in rows}


def render_value_card(rows: list[dict], region_label: str) -> Image.Image:
    canvas = build_card_canvas(
        "숨은 가성비",
        ["숨은 가성비 TOP 5", f"— {region_label}"],
    )
    draw = canvas.draw
    rank_font = get_font("extrabold", 40)
    name_font = get_font("semibold", 32)
    meta_font = get_font("regular", 24)
    price_font = get_font("extrabold", 34)

    row_height = (canvas.content_bottom - canvas.content_top) / CARD_LIST_SIZE
    for i, row in enumerate(rows):
        y = canvas.content_top + i * row_height + 8
        draw.text((MARGIN_X, y), f"{i + 1}", font=rank_font, fill=COLOR_ACCENT_BLUE)

        name_x = MARGIN_X + 64
        name_max_width = CANVAS_SIZE - MARGIN_X - name_x - 20
        name = truncate_text(draw, row["bld_nm"], name_font, name_max_width)
        draw.text((name_x, y), name, font=name_font, fill=COLOR_TEXT_WHITE)

        meta = f"가성비 점수 {row['score']:.1f}"
        draw.text((name_x, y + 40), meta, font=meta_font, fill=COLOR_TEXT_LIGHT)

        price_text = format_price_per_m2(row["price_per_m2"])
        price_w = draw.textlength(price_text, font=price_font)
        draw.text(
            (CANVAS_SIZE - MARGIN_X - price_w, y + 4),
            price_text,
            font=price_font,
            fill=COLOR_ACCENT_GREEN,
        )
    return canvas.image


def generate_value_card(region_keyword: str, nudge: str) -> Image.Image:
    candidates = fetch_nudge_candidates(
        region_keyword, nudge, VALUE_CANDIDATE_POOL_SIZE
    )
    if not candidates:
        raise ValueError(f"'{region_keyword}' 에 대한 넛지 점수 결과가 없습니다.")

    conn = get_connection()
    try:
        price_map = fetch_price_per_m2_by_pnu(conn, [c["pnu"] for c in candidates])
    finally:
        conn.close()

    merged = [
        {**c, "price_per_m2": price_map[c["pnu"]]}
        for c in candidates
        if c["pnu"] in price_map
    ]
    if not merged:
        raise ValueError(
            f"'{region_keyword}' 후보 단지에 price_per_m2 데이터가 없습니다."
        )

    merged.sort(key=lambda c: c["price_per_m2"])
    top5 = merged[:CARD_LIST_SIZE]
    return render_value_card(top5, region_keyword)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def save_card(image: Image.Image, output_dir: Path, filename: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    image.save(path, format="PNG")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="인스타그램 카드 자동 생성")
    parser.add_argument(
        "--series", required=True, choices=["trade-top", "compare", "value"]
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_TRADE_TOP_DAYS,
        help="trade-top: 신고일 기준 집계 기간(일)",
    )
    parser.add_argument(
        "--regions",
        type=str,
        default="",
        help="compare: 시군구 코드 2개, 콤마 구분 (예: 11440,11200)",
    )
    parser.add_argument(
        "--nudge",
        type=str,
        default="",
        help="compare/value: 넛지 id (예: cost, newlywed)",
    )
    parser.add_argument("--region", type=str, default="서울", help="value: 지역 키워드")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = OUTPUT_ROOT / date.today().isoformat()

    if args.series == "trade-top":
        cards = generate_trade_top_cards(args.days)
        for filename, image in cards:
            path = save_card(image, output_dir, filename)
            print(f"saved: {path}")

    elif args.series == "compare":
        codes = [c.strip() for c in args.regions.split(",") if c.strip()]
        nudge = args.nudge or DEFAULT_COMPARE_NUDGE
        if nudge not in NUDGE_LABELS:
            raise SystemExit(
                f"알 수 없는 넛지 id: {nudge} (허용: {', '.join(NUDGE_LABELS)})"
            )
        image = generate_compare_card(codes, nudge)
        path = save_card(image, output_dir, "compare.png")
        print(f"saved: {path}")

    elif args.series == "value":
        nudge = args.nudge or DEFAULT_VALUE_NUDGE
        if nudge not in NUDGE_LABELS:
            raise SystemExit(
                f"알 수 없는 넛지 id: {nudge} (허용: {', '.join(NUDGE_LABELS)})"
            )
        image = generate_value_card(args.region, nudge)
        path = save_card(image, output_dir, "value.png")
        print(f"saved: {path}")


if __name__ == "__main__":
    main()
