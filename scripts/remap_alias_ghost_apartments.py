"""괄호 별칭 유령 아파트 레코드를 진본 PNU 로 재매핑하는 일회용 스크립트.

배경
  국토부 거래 API 의 아파트명이 `세종리첸시아파밀리에H3블록(산울마을6단지)` 처럼
  `블록(별칭)` 형태이면 batch/trade/enrich_apartments.py 의 Kakao 키워드 검색이
  0건을 반환한다(POI 명은 `산울마을6단지세종리첸시아파밀리에H3아파트`).
  그 결과 좌표/주소가 NULL 인 `TRADE_<sgg>_<이름>` 유령 레코드가 생성되고,
  거래가 진본 대신 유령에 매핑돼 지도·시설정보가 끊긴다.

  진본 매핑을 막는 기존 가드 두 개는 이 패턴을 못 잡는다.
    - [L2] 주소 공유 진본 매핑 → Kakao 주소가 있어야 발동. 검색 0건이라 불가
    - [3] K-APT 이름 진본 바인딩 → 정규화 후 완전일치. 괄호 별칭은 불일치

  본 스크립트는 "괄호 안 별칭이 같은 시군구의 진본 이름과 정확히 일치" 하는 건만
  대상으로 하며, 각 쌍의 근거는 REMAP_PAIRS 의 note 에 개별 기재한다.
  3건은 거래 타임라인(build_year vs 준공연도)·최고층·Kakao 주소가 모두 일치하고,
  1건(시영2차)은 거래가 0건이라 타임라인 검증이 불가해 Kakao 주소 일치로만 확인했다.
  근본 원인(검색 쿼리 정규화)은 별도 수정 대상이다.

  이름이 유사해도 원부와 어긋나면 대상에서 제외한다. 예: apt_seq `29200_부영애시앙1차`
  (괄호 없음)는 Kakao 주소가 산정 셀트리움과 같지만 건축물대장·K-APT 어디에도
  거래상의 84.28㎡ 주택형과 21층이 없어 제외했다. 아래 목록의
  `부영애시앙1차(산정셀트리움)`(괄호 있음)은 이와 다른 apt_seq 이며 검증을 통과한 건이다.

수행 작업 (쌍 단위)
  1. trade_apt_mapping.pnu 를 진본으로 변경 (match_method = 'manual_fix')
  2. 유령 pnu 의 apt_price_score 고아 행 삭제
  3. 유령 apartments 행 삭제
  이후 recalc_price 재계산 시 가격점수가 진본 pnu 로 재생성된다.

사용
  .venv/bin/python scripts/remap_alias_ghost_apartments.py                    # dry-run
  .venv/bin/python scripts/remap_alias_ghost_apartments.py --apply            # 로컬 반영
  .venv/bin/python scripts/remap_alias_ghost_apartments.py --apply --target railway

주의
  --target railway 는 production 에 직접 쓴다. CLAUDE.md 의 Railway 직접접속 금지
  정책상 에이전트는 실행하지 않으며, 사용자가 의도적으로 실행한다.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")

MATCH_METHOD = "manual_fix"

# 재매핑 대상 — 전부 아래 근거로 교차검증 완료 (검증일 2026-07-28).
#   거래건수/기간, build_year vs 진본 준공연도, 거래 최고층 vs 진본 최고층,
#   괄호 제거 후 Kakao 키워드 검색 결과가 진본 도로명주소와 일치하는지
REMAP_PAIRS = [
    {
        "ghost_pnu": "TRADE_36110_세종리첸시아파밀리에H3블록(산울마을6단지)",
        "canonical_pnu": "3611011500003130014",
        "note": "산울마을6단지 | 산울2로 10 | 거래 14건(2024-07~2026-07) "
                "build_year 2024 = 준공 20240307, 최고층 32 <= 35",
    },
    {
        "ghost_pnu": "TRADE_36110_세종리첸시아파밀리에H2블록(산울마을7단지)",
        "canonical_pnu": "3611011500001520001",
        "note": "산울마을7단지 | 산울7로 11 | 거래 20건(2025-02~2026-07) "
                "build_year 2024 = 준공 20240307, 최고층 32 <= 34",
    },
    {
        "ghost_pnu": "TRADE_29200_부영애시앙1차(산정셀트리움)",
        "canonical_pnu": "2920012700011190000",
        "note": "산정 셀트리움 | 목련로 42 | 거래 73건(2023-01~2026-06) "
                "build_year 2008 = 준공 20081120, 최고층 20 <= 20",
    },
    {
        "ghost_pnu": "TRADE_29200_시영2차(우산빛여울채)",
        "canonical_pnu": "2920010900016030001",
        "note": "우산빛여울채 | 우산로 17 | 거래 0건 — 타임라인 검증 불가, "
                "Kakao '시영2차' 검색 결과가 진본과 동일 주소(우산로 17)인 점으로만 확인",
    },
]


def _connect(target: str):
    key = "DATABASE_URL" if target == "local" else "RAILWAY_DATABASE_URL"
    url = os.environ.get(key)
    if not url:
        raise SystemExit(f"{key} 환경변수가 없습니다.")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def _preflight(cur, pair: dict) -> list[str]:
    """적용 전 전제조건 확인. 문제가 있으면 사유 목록을 반환한다."""
    problems = []

    cur.execute("SELECT pnu FROM apartments WHERE pnu = %s", [pair["ghost_pnu"]])
    if not cur.fetchone():
        problems.append("유령 레코드 없음(이미 처리됨)")

    cur.execute(
        "SELECT pnu, bld_nm, lat, lng FROM apartments WHERE pnu = %s",
        [pair["canonical_pnu"]],
    )
    canon = cur.fetchone()
    if not canon:
        problems.append("진본 레코드 없음")
    elif canon["lat"] is None or canon["lng"] is None:
        problems.append("진본에 좌표 없음 — 재매핑해도 지도 연결 불가")

    return problems


def run(target: str, apply: bool) -> int:
    conn = _connect(target)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[{target}] {mode} — 재매핑 대상 {len(REMAP_PAIRS)}쌍\n")

    changed = 0
    skipped = 0

    for pair in REMAP_PAIRS:
        ghost, canon = pair["ghost_pnu"], pair["canonical_pnu"]
        print(f"● {ghost}")
        print(f"  → {canon}  ({pair['note']})")

        problems = _preflight(cur, pair)
        if problems:
            print(f"  [건너뜀] {', '.join(problems)}\n")
            skipped += 1
            continue

        cur.execute(
            "SELECT apt_seq, apt_nm, match_method FROM trade_apt_mapping WHERE pnu = %s",
            [ghost],
        )
        mappings = cur.fetchall()
        cur.execute("SELECT COUNT(*) c FROM apt_price_score WHERE pnu = %s", [ghost])
        score_rows = cur.fetchone()["c"]
        trade_total = 0
        for m in mappings:
            cur.execute(
                "SELECT COUNT(*) c FROM trade_history WHERE apt_seq = %s", [m["apt_seq"]]
            )
            trade_total += cur.fetchone()["c"]

        print(f"  매핑 {len(mappings)}건(거래 {trade_total}건) · apt_price_score {score_rows}행 · apartments 1행 삭제")

        if apply:
            cur.execute(
                "UPDATE trade_apt_mapping SET pnu = %s, match_method = %s WHERE pnu = %s",
                [canon, MATCH_METHOD, ghost],
            )
            cur.execute("DELETE FROM apt_price_score WHERE pnu = %s", [ghost])
            cur.execute("DELETE FROM apartments WHERE pnu = %s", [ghost])
        changed += 1
        print()

    if apply:
        conn.commit()
        print(f"반영 완료: {changed}쌍 (건너뜀 {skipped}쌍)")
        print("가격점수 재생성 필요: .venv/bin/python -m batch.trade.recalc_price")
    else:
        conn.rollback()
        print(f"DRY-RUN 종료: 적용 대상 {changed}쌍 (건너뜀 {skipped}쌍) — DB 변경 없음")

    conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=["local", "railway"], default="local")
    ap.add_argument("--apply", action="store_true", help="실제 반영 (기본은 dry-run)")
    args = ap.parse_args()
    return run(args.target, args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
