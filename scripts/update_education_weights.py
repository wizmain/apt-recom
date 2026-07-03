"""education 넛지 가중치 재배분 — 배정초교(assigned_elementary) 1급 지표 반영 (Phase 1-1).

| subtype             | 기존  | 신규 | 근거                                        |
|---------------------|-------|------|---------------------------------------------|
| assigned_elementary | —     | 0.30 | 학군 넛지의 1급 지표 (실제 배정교 접근성)   |
| school              | 0.296 | 0.15 | 일반 학교 밀도는 보조 지표로 강등           |
| kindergarten        | 0.253 | 0.20 | 유지(소폭 조정)                             |
| library             | 0.251 | 0.15 | 과대가중 완화 (진단 보고서 §3.4 유사 논리)  |
| park                | 0.200 | 0.20 | 유지                                        |

초기값은 전문가 판단 — hedonic 검증(batch/ml/hedonic_validation.py) 결과로
재조정한다. 적용 후 백엔드 재기동 필요 (_load_nudge_weights 모듈 캐시).

사용 (기본 dry-run):
  .venv/bin/python scripts/update_education_weights.py
  .venv/bin/python scripts/update_education_weights.py --apply
  .venv/bin/python scripts/update_education_weights.py --target railway --apply
    ⚠️ production 쓰기 — 사용자가 직접 실행한다.
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
NUDGE = "education"

EDUCATION_WEIGHTS: dict[str, float] = {
    "assigned_elementary": 0.30,
    "school": 0.15,
    "kindergarten": 0.20,
    "library": 0.15,
    "park": 0.20,
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

    total = sum(EDUCATION_WEIGHTS.values())
    if abs(total - 1.0) > 1e-9:
        raise SystemExit(f"가중치 합이 1.0 이 아님: {total}")

    conn = get_conn(args.target)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(
        "SELECT code, extra FROM common_code WHERE group_id = %s AND code LIKE %s",
        [GROUP, f"{NUDGE}:%"],
    )
    current = dict(cur.fetchall())
    print(f"현재 education 가중치: {current}")

    for subtype, weight in EDUCATION_WEIGHTS.items():
        code = f"{NUDGE}:{subtype}"
        print(f"{'APPLY' if args.apply else 'DRY-RUN'} upsert: {code} = {weight}")
        if args.apply:
            cur.execute(UPSERT_SQL, [GROUP, code, subtype, str(weight)])

    # 신규 세트에 없는 기존 education:* 는 제거 (가중치 합 1.0 유지)
    stale = [c for c in current if c.split(":", 1)[1] not in EDUCATION_WEIGHTS]
    for code in stale:
        print(f"{'APPLY' if args.apply else 'DRY-RUN'} delete stale: {code}")
        if args.apply:
            cur.execute(
                "DELETE FROM common_code WHERE group_id = %s AND code = %s",
                [GROUP, code],
            )

    if args.apply:
        conn.commit()
        print(f"✅ {args.target} 반영 완료 — 백엔드 재기동 필요 (가중치 캐시)")
    else:
        conn.rollback()
        print("dry-run 종료 — 반영하려면 --apply")
    conn.close()


if __name__ == "__main__":
    main()
