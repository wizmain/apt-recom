"""senior/cost/newlywed 가중치 재배분 — 건축물대장 품질 지표 반영 (Phase 2-1).

| 넛지     | 신규 subtype   | 가중치 | 기존 subtype 처리      |
|----------|----------------|--------|------------------------|
| senior   | score_elevator | 0.15   | 기존 전체 × 0.85       |
| cost     | score_parking  | 0.10   | 기존 전체 × 0.90       |
| newlywed | score_parking  | 0.10   | 기존 전체 × 0.90       |

근거: 승강기는 시니어 이동성의 1차 제약(계단식 5층 = 실질 거주 불가),
세대당 주차는 자가용 세대(가성비·신혼육아)의 상시 비용/스트레스 요인.
초기값은 전문가 판단 — 다음 hedonic 실행이 이 축의 시장 계수를 자동 측정한다.
적용 후 백엔드 재기동 필요 (_load_nudge_weights 캐시).

주의: 로컬+Railway 반영 완료된 스크립트 — 신규 스크립트는 weight_update_lib 사용.

사용 (기본 dry-run):
  .venv/bin/python scripts/update_quality_weights.py
  .venv/bin/python scripts/update_quality_weights.py --apply
  .venv/bin/python scripts/update_quality_weights.py --target railway --apply  # 사용자 직접
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

GROUP = "nudge_weight"
# 넛지별 (신규 subtype, 신규 가중치)
QUALITY_ADDITIONS: dict[str, tuple[str, float]] = {
    "senior": ("score_elevator", 0.15),
    "cost": ("score_parking", 0.10),
    "newlywed": ("score_parking", 0.10),
}

UPSERT_SQL = """
    INSERT INTO common_code (group_id, code, name, extra, sort_order)
    VALUES (%s, %s, %s, %s, 0)
    ON CONFLICT (group_id, code) DO UPDATE SET
        name = EXCLUDED.name, extra = EXCLUDED.extra
"""


def get_conn(target: str):
    env_key = "RAILWAY_DATABASE_URL" if target == "railway" else "DATABASE_URL"
    url = os.getenv(env_key)
    if not url:
        raise SystemExit(f"{env_key} 미설정 (.env 확인)")
    return psycopg2.connect(url)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["local", "railway"], default="local")
    parser.add_argument("--apply", action="store_true", help="실제 반영 (기본 dry-run)")
    args = parser.parse_args()

    conn = get_conn(args.target)
    conn.autocommit = False
    cur = conn.cursor()

    for nudge, (new_subtype, new_weight) in QUALITY_ADDITIONS.items():
        cur.execute(
            "SELECT code, name, extra FROM common_code "
            "WHERE group_id = %s AND code LIKE %s",
            [GROUP, f"{nudge}:%"],
        )
        current = {
            code.split(":", 1)[1]: float(extra) for code, _, extra in cur.fetchall()
        }
        if new_subtype in current:
            print(
                f"[{nudge}] {new_subtype} 이미 존재({current[new_subtype]}) — 재배분 스킵"
            )
            continue

        shrink = 1.0 - new_weight
        rebalanced = {s: round(w * shrink, 4) for s, w in current.items()}
        rebalanced[new_subtype] = new_weight
        total = sum(rebalanced.values())
        print(f"[{nudge}] 재배분 합 = {total:.4f}")
        if abs(total - 1.0) > 0.02:
            raise SystemExit(f"{nudge} 가중치 합 이탈: {total}")

        for subtype, weight in rebalanced.items():
            print(
                f"  {'APPLY' if args.apply else 'DRY-RUN'} {nudge}:{subtype} = {weight}"
            )
            if args.apply:
                cur.execute(
                    UPSERT_SQL, [GROUP, f"{nudge}:{subtype}", subtype, str(weight)]
                )

    if args.apply:
        conn.commit()
        print("✅ 반영 완료 — 백엔드 재기동 필요 (가중치 캐시)")
    else:
        conn.rollback()
        print("dry-run 종료 — 반영하려면 --apply")
    conn.close()


if __name__ == "__main__":
    main()
