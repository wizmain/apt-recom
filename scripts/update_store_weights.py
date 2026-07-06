"""pet/newlywed/cost 가중치 재배분 — 상가정보 유래 시설 반영 (Phase 2-2).

| 넛지     | 신규 subtype (가중치)                  | 기존 subtype 처리 |
|----------|-----------------------------------------|--------------------|
| pet      | pet_shop (0.15)                         | 기존 전체 × 0.85   |
| newlywed | kids_cafe (0.08) + cafe (0.04)          | 기존 전체 × 0.88   |
| cost     | cafe (0.05)                              | 기존 전체 × 0.95   |

근거: 소상공인시장진흥공단 상가정보로 전국 카페/키즈카페/펫샵/피트니스를
`facilities` 에 적재(Task 1~2). pet_shop 은 반려동물 축의 직접 신호,
kids_cafe/cafe 는 신혼·가성비 넛지의 생활편의 신호로 반영한다.
fitness 는 이번 단계에서 가중치를 배정하지 않는다 — hedonic 재실행(Task 4)으로
시장 계수를 측정한 뒤 별도 결정.

update_quality_weights.py 골격을 재사용하되, 한 넛지에 여러 subtype 을
동시에 추가할 수 있도록 QUALITY_ADDITIONS 를
dict[nudge, dict[subtype, weight]] 구조로 확장했다.

적용 후 백엔드 재기동 필요 (_load_nudge_weights 캐시).

사용 (기본 dry-run):
  .venv/bin/python scripts/update_store_weights.py
  .venv/bin/python scripts/update_store_weights.py --apply
  .venv/bin/python scripts/update_store_weights.py --target railway --apply  # 사용자 직접
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
# 넛지별 {신규 subtype: 신규 가중치} — 다중 추가 지원
QUALITY_ADDITIONS: dict[str, dict[str, float]] = {
    "pet": {"pet_shop": 0.15},
    "newlywed": {"kids_cafe": 0.08, "cafe": 0.04},
    "cost": {"cafe": 0.05},
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

    for nudge, additions in QUALITY_ADDITIONS.items():
        cur.execute(
            "SELECT code, name, extra FROM common_code "
            "WHERE group_id = %s AND code LIKE %s",
            [GROUP, f"{nudge}:%"],
        )
        current = {
            code.split(":", 1)[1]: float(extra) for code, _, extra in cur.fetchall()
        }

        pending = {
            subtype: weight
            for subtype, weight in additions.items()
            if subtype not in current
        }
        already = set(additions) - set(pending)
        for subtype in already:
            print(f"[{nudge}] {subtype} 이미 존재({current[subtype]}) — 재배분 스킵")
        if not pending:
            continue

        shrink = 1.0 - sum(pending.values())
        rebalanced = {s: round(w * shrink, 4) for s, w in current.items()}
        rebalanced.update(pending)
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
        print("반영 완료 — 백엔드 재기동 필요 (가중치 캐시)")
    else:
        conn.rollback()
        print("dry-run 종료 — 반영하려면 --apply")
    conn.close()


if __name__ == "__main__":
    main()
