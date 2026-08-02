"""시도 레지스트리(sido)와 시도명 별칭(sido_alias)을 적재한다.

배경
  common_code sigungu 의 extra 는 시도명이 아니라 지오코딩 질의용 지역 접두라
  ("청주", "창원", "경기 화성시") 시도 정보원이 없었다. 별칭 프로브가 extra 와
  비교하다 "경남 → 창원" 같은 오류 쌍을 만든 원인이다(2026-08).

  또한 주소 문자열의 시도 표기가 DB 안에서도 혼재한다 — "광주 …" 1,150건,
  "전남 …" 840건, "전남광주통합특별시 …" 35건(실측). 시도 토큰이 다르면
  주소 매칭 키(enrich [L2] 등)가 갈라져 같은 주소가 매치되지 않는다.

적재 내용
  common_code 'sido'        code=시도코드(2자리), name=축약 표기, extra=정식 명칭
  common_code 'sido_alias'  code=표기, name=매칭용 canonical 토큰

  canonical 토큰은 표시용이 아니다. 개편 통합시(전남광주통합특별시)는
  광주·전남의 모든 표기를 "전남광주" 한 토큰으로 접는다 — 구표기 DB 주소와
  신표기 Kakao 주소가 같은 키가 되려면 양쪽이 같은 값으로 접혀야 한다.

  시도 17개와 정식 명칭은 행정 표준이므로 여기 정적으로 둔다. 개편으로
  새 표기가 관측되면(프로브 리포트의 시도명 후보) 이 목록에 추가한다.

사용
  .venv/bin/python scripts/seed_sido_registry.py            # 리포트
  .venv/bin/python scripts/seed_sido_registry.py --apply
  .venv/bin/python scripts/seed_sido_registry.py --target railway --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from batch.region_codes import SIDO_ALIAS_GROUP, SIDO_GROUP  # noqa: E402

# 시도코드 → (축약 표기, 정식 명칭). 축약 표기는 DB 주소의 지배적 표기와 맞춘다.
SIDO = {
    "11": ("서울", "서울특별시"),
    "26": ("부산", "부산광역시"),
    "27": ("대구", "대구광역시"),
    "28": ("인천", "인천광역시"),
    "29": ("광주", "광주광역시"),
    "30": ("대전", "대전광역시"),
    "31": ("울산", "울산광역시"),
    "36": ("세종", "세종특별자치시"),
    "41": ("경기", "경기도"),
    "43": ("충북", "충청북도"),
    "44": ("충남", "충청남도"),
    "46": ("전남", "전라남도"),
    "47": ("경북", "경상북도"),
    "48": ("경남", "경상남도"),
    "50": ("제주", "제주특별자치도"),
    "51": ("강원", "강원특별자치도"),
    "52": ("전북", "전북특별자치도"),
}

# 표기 → canonical 매칭 토큰.
# 기본: 축약·정식·구명칭이 같은 토큰으로 접힌다.
# 2026-08 개편: 광주·전남 통합 → 두 시도의 모든 표기를 "전남광주" 로 접는다
# (실측 — Kakao region_1depth_name "전남광주통합특별시", 시군구 코드 12xxx).
MERGED = {
    "전남광주": ["광주", "광주광역시", "전남", "전라남도", "전남광주통합특별시"],
}
LEGACY = {
    "강원": ["강원도"],
    "전북": ["전라북도"],
    "제주": ["제주도"],
}


def build_aliases() -> dict[str, str]:
    merged_members = {m for ms in MERGED.values() for m in ms}
    out: dict[str, str] = {}
    for _, (short, formal) in SIDO.items():
        if short not in merged_members:
            out[short] = short
            out[formal] = short
    for canonical, members in MERGED.items():
        for m in members:
            out[m] = canonical
    for canonical, members in LEGACY.items():
        for m in members:
            out[m] = canonical
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=["local", "railway"], default="local")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    aliases = build_aliases()
    print(f"sido {len(SIDO)}건 / sido_alias {len(aliases)}건")
    for k, v in sorted(aliases.items()):
        if k != v:
            print(f"  {k} → {v}")

    if not args.apply:
        print("\nREPORT 모드 — DB 변경 없음")
        return 0

    key = "DATABASE_URL" if args.target == "local" else "RAILWAY_DATABASE_URL"
    conn = psycopg2.connect(os.environ[key])
    cur = conn.cursor()
    for code, (short, formal) in SIDO.items():
        cur.execute(
            """INSERT INTO common_code (group_id, code, name, extra, sort_order)
               VALUES (%s, %s, %s, %s, 0)
               ON CONFLICT (group_id, code) DO UPDATE
                 SET name = EXCLUDED.name, extra = EXCLUDED.extra""",
            [SIDO_GROUP, code, short, formal],
        )
    for token, canonical in aliases.items():
        cur.execute(
            """INSERT INTO common_code (group_id, code, name, extra, sort_order)
               VALUES (%s, %s, %s, %s, 0)
               ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name""",
            [SIDO_ALIAS_GROUP, token, canonical, "매칭 전용 canonical 토큰"],
        )
    conn.commit()
    cur.execute("SELECT group_id, COUNT(*) FROM common_code WHERE group_id IN (%s,%s) GROUP BY 1",
                [SIDO_GROUP, SIDO_ALIAS_GROUP])
    print(f"\n[{args.target}] 적재 완료:", dict(cur.fetchall()))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
