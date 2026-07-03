"""탐색 갤러리(explore_preset)·기본 추천 넛지(recommend_default) common_code 시드.

D안(큐레이션 딥링크 갤러리 /explore)과 E3안(신규거래 배너 → 이 지역 추천)이
소비하는 코드 데이터를 common_code 에 upsert 한다. 하드코딩 금지 원칙에 따라
프리셋 정의는 프론트 코드가 아닌 DB 에 두며, 이 스크립트가 유일한 시드 경로다.

- explore_preset: code=프리셋 id, name=타일 제목,
  extra=JSON {emoji, description, nudges[], sigungu_code, region_label}
- recommend_default: code=nudge 코드 (배너 '이 지역 추천'의 기본 세트)

각 프리셋의 sigungu_code 가 apartments 에 실존하는지 검증하고, 없으면 해당
프리셋을 건너뛰며 경고를 남긴다 (깨진 딥링크 방지).

사용 (기본 dry-run):
  .venv/bin/python scripts/seed_explore_presets.py                     # local dry-run
  .venv/bin/python scripts/seed_explore_presets.py --apply             # local 반영
  .venv/bin/python scripts/seed_explore_presets.py --target railway --apply
    ⚠️ production 쓰기 — CLAUDE.md 정책상 railway 는 사용자가 직접 실행한다.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

GROUP_EXPLORE = "explore_preset"
GROUP_RECOMMEND_DEFAULT = "recommend_default"

# 배너 "이 지역 추천"의 기본 넛지 세트 — 가성비/출퇴근/학군 (범용 균형 조합)
RECOMMEND_DEFAULT_NUDGES = [
    ("cost", "가성비", 1),
    ("commute", "출퇴근", 2),
    ("education", "학군", 3),
]

# /explore 큐레이션 타일 — (code, 제목, extra, sort_order)
EXPLORE_PRESETS = [
    (
        "gangnam_edu",
        "강남구 · 학군과 안전",
        {
            "emoji": "🏫",
            "description": "학군과 치안을 모두 잡는 강남 라이프",
            "nudges": ["education", "safety"],
            "sigungu_code": "11680",
            "region_label": "강남구",
        },
        1,
    ),
    (
        "bundang_commute",
        "성남 분당 · 출퇴근과 신혼",
        {
            "emoji": "🚇",
            "description": "판교 출퇴근과 신혼 라이프의 균형",
            "nudges": ["commute", "newlywed"],
            "sigungu_code": "41135",
            "region_label": "성남시 분당구",
        },
        2,
    ),
    (
        "mapo_value",
        "마포구 · 출퇴근과 가성비",
        {
            "emoji": "☕",
            "description": "도심 접근성과 합리적인 가격",
            "nudges": ["commute", "cost"],
            "sigungu_code": "11440",
            "region_label": "마포구",
        },
        3,
    ),
    (
        "nowon_edu_value",
        "노원구 · 학군과 가성비",
        {
            "emoji": "🎒",
            "description": "교육 인프라와 부담 없는 가격대",
            "nudges": ["education", "cost"],
            "sigungu_code": "11350",
            "region_label": "노원구",
        },
        4,
    ),
    (
        "yeongtong_family",
        "수원 영통 · 학군과 신혼",
        {
            "emoji": "👨‍👩‍👧",
            "description": "젊은 가족이 정착하기 좋은 신도시",
            "nudges": ["education", "newlywed"],
            "sigungu_code": "41117",
            "region_label": "수원시 영통구",
        },
        5,
    ),
    (
        "haeundae_nature",
        "부산 해운대 · 자연과 투자",
        {
            "emoji": "🌊",
            "description": "바다 조망과 투자 가치를 동시에",
            "nudges": ["nature", "investment"],
            "sigungu_code": "26350",
            "region_label": "부산 해운대구",
        },
        6,
    ),
]

UPSERT_SQL = """
    INSERT INTO common_code (group_id, code, name, extra, sort_order)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (group_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        extra = EXCLUDED.extra,
        sort_order = EXCLUDED.sort_order
"""


def get_conn(target: str):
    if target == "railway":
        url = os.getenv("RAILWAY_DATABASE_URL")
        if not url:
            raise SystemExit("RAILWAY_DATABASE_URL 미설정 (.env 확인)")
    else:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise SystemExit("DATABASE_URL 미설정 (.env 확인)")
    return psycopg2.connect(url)


def sigungu_exists(cur, sigungu_code: str) -> bool:
    cur.execute(
        "SELECT 1 FROM apartments WHERE sigungu_code = %s LIMIT 1", [sigungu_code]
    )
    return cur.fetchone() is not None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["local", "railway"], default="local")
    parser.add_argument("--apply", action="store_true", help="실제 반영 (기본 dry-run)")
    args = parser.parse_args()

    conn = get_conn(args.target)
    conn.autocommit = False
    cur = conn.cursor()

    planned: list[tuple[str, str, str, str, int]] = []

    for code, name, sort_order in RECOMMEND_DEFAULT_NUDGES:
        planned.append((GROUP_RECOMMEND_DEFAULT, code, name, "", sort_order))

    for code, name, extra, sort_order in EXPLORE_PRESETS:
        if not sigungu_exists(cur, extra["sigungu_code"]):
            print(
                f"⚠️  skip {code}: sigungu_code={extra['sigungu_code']} 가 apartments 에 없음"
            )
            continue
        planned.append(
            (
                GROUP_EXPLORE,
                code,
                name,
                json.dumps(extra, ensure_ascii=False),
                sort_order,
            )
        )

    for row in planned:
        print(
            f"{'APPLY' if args.apply else 'DRY-RUN'} upsert: {row[0]}/{row[1]} — {row[2]}"
        )

    if args.apply:
        for row in planned:
            cur.execute(UPSERT_SQL, list(row))
        conn.commit()
        print(f"✅ {args.target} 반영 완료: {len(planned)}행")
    else:
        conn.rollback()
        print(f"dry-run 종료 ({len(planned)}행 예정) — 반영하려면 --apply")

    conn.close()


if __name__ == "__main__":
    main()
