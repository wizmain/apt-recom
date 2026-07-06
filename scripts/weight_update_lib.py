"""넛지 가중치 재배분 공통 라이브러리.

update_education/quality/store/hospital_weights 4개 스크립트에서 동일 로직이
반복 복제되어 공통화했다 (4번째 복제 시점 — 프로젝트 중복 규칙 초과).
신규 가중치 스크립트는 이 lib 의 얇은 래퍼로 작성한다:
additions dict 정의 + run_cli() 호출만.

핵심 규칙:
- shrink 재배분: 신규 축 추가 시 기존 전체 축을 (1 - 신규 합) 배로 비례 축소.
- all-or-nothing 가드: 일부 subtype 만 반영된 부분 상태에서 재실행하면
  이미 반영된 subtype 까지 재축소되어 합이 조용히 깨진다 — 즉시 중단.
- 합 검증: 재배분 후 넛지 합이 1.0(±0.02) 을 벗어나면 중단.
- 누적 희석 floor 가드: shrink 는 실행마다 누적된다 (예: newlywed 는
  Phase 2-1 ×0.90 → 2-2 ×0.88 → 2-3 ×0.89). 축 추가가 반복되면 기존 축이
  조용히 침식되므로, shrink 후 기존 축이 MIN_AXIS_WEIGHT 미만으로 떨어지면
  경고 후 중단한다. floor 는 하드 금지선이 아니라 "가중치 체계 재검토"
  트리거 — 의도된 희석이면 --allow-dilution(allow_dilution=True) 으로 진행.

적용 후 백엔드 재기동 필요 (_load_nudge_weights 캐시).
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
WEIGHT_SUM_TOLERANCE = 0.02
# 누적 희석 floor: 기존 축이 이 값 미만으로 축소되면 재검토 트리거 (위 docstring)
MIN_AXIS_WEIGHT = 0.05

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


def apply_weight_additions(
    conn,
    additions: dict[str, dict[str, float]],
    apply: bool,
    allow_dilution: bool = False,
) -> None:
    """넛지별 신규 subtype 가중치를 shrink 재배분으로 반영.

    additions: {nudge: {subtype: weight}} — 한 넛지에 다중 subtype 지원.
    apply=False 는 dry-run (커밋/롤백은 호출자 책임 — run_cli 참고).
    allow_dilution: 기존 축이 MIN_AXIS_WEIGHT 미만으로 떨어져도 진행.
    """
    cur = conn.cursor()

    for nudge, nudge_additions in additions.items():
        cur.execute(
            "SELECT code, name, extra FROM common_code "
            "WHERE group_id = %s AND code LIKE %s",
            [GROUP, f"{nudge}:%"],
        )
        current = {
            code.split(":", 1)[1]: float(extra) for code, _, extra in cur.fetchall()
        }
        print(
            f"[{nudge}] 현재 축: "
            + ", ".join(
                f"{s}={w}" for s, w in sorted(current.items(), key=lambda x: -x[1])
            )
        )

        existing = {s for s in nudge_additions if s in current}
        missing = set(nudge_additions) - existing
        if existing and missing:
            # all-or-nothing 가드 (docstring 참고)
            raise SystemExit(
                f"[{nudge}] 부분 반영 상태 감지 — 수동 정리 후 재실행 필요. "
                f"존재: {sorted(existing)} / 부재: {sorted(missing)}"
            )
        if not missing:
            for subtype in sorted(existing):
                print(
                    f"[{nudge}] {subtype} 이미 존재({current[subtype]}) — 재배분 스킵"
                )
            continue

        shrink = 1.0 - sum(nudge_additions.values())
        rebalanced = {s: round(w * shrink, 4) for s, w in current.items()}

        # 누적 희석 floor 가드 (docstring 참고) — 신규 축은 의도된 초기값이므로
        # 기존 축(shrink 대상)만 검사한다.
        diluted = {s: w for s, w in rebalanced.items() if w < MIN_AXIS_WEIGHT}
        if diluted:
            msg = (
                f"[{nudge}] 경고: shrink 후 기존 축이 floor({MIN_AXIS_WEIGHT}) 미만 — "
                f"{diluted}. 누적 희석으로 축이 침식되고 있다. "
                f"가중치 체계 재검토 권장."
            )
            print(msg)
            if not allow_dilution:
                raise SystemExit(f"{msg} 의도된 희석이면 --allow-dilution 으로 재실행.")

        rebalanced.update(nudge_additions)
        total = sum(rebalanced.values())
        print(f"[{nudge}] 재배분 합 = {total:.4f}")
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise SystemExit(f"{nudge} 가중치 합 이탈: {total}")

        for subtype, weight in rebalanced.items():
            print(f"  {'APPLY' if apply else 'DRY-RUN'} {nudge}:{subtype} = {weight}")
            if apply:
                cur.execute(
                    UPSERT_SQL, [GROUP, f"{nudge}:{subtype}", subtype, str(weight)]
                )


def run_cli(additions: dict[str, dict[str, float]], description: str | None) -> None:
    """가중치 스크립트 공통 CLI: --target/--apply/--allow-dilution + 트랜잭션."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--target", choices=["local", "railway"], default="local")
    parser.add_argument("--apply", action="store_true", help="실제 반영 (기본 dry-run)")
    parser.add_argument(
        "--allow-dilution",
        action="store_true",
        help=f"기존 축이 floor({MIN_AXIS_WEIGHT}) 미만으로 축소돼도 진행",
    )
    args = parser.parse_args()

    conn = get_conn(args.target)
    conn.autocommit = False
    try:
        apply_weight_additions(
            conn, additions, apply=args.apply, allow_dilution=args.allow_dilution
        )
        if args.apply:
            conn.commit()
            print("반영 완료 — 백엔드 재기동 필요 (가중치 캐시)")
        else:
            conn.rollback()
            print("dry-run 종료 — 반영하려면 --apply")
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
