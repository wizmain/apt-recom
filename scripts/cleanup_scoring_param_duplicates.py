"""common_code 스코어링 파라미터 그룹의 '코드 기본값 중복 행' 정리.

배경: facility_decay / facility_distance / density_factor 의 프로필 그룹
(major_city/provincial)과 글로벌 facility_distance 그룹에 코드 기본값
(×프로필 배율)과 완전히 동일한 행이 적재되어 있었다 (2026-07-31 로컬·Railway
전수 비교 — 105행 전부 중복, 실오버라이드 0건). 로더 merge semantics
(web/backend/services/scoring.py)상 DB 행이 코드 기본값보다 우선하므로,
중복 행이 남아 있으면 코드 기본값을 수정해도 DB 값이 이겨서 프로필 배율
관계가 조용히 깨진다.

정책: DB 는 기본값과 다른 값만 오버라이드로 유지한다 (override-only).
이 스크립트는 "현재 코드 기본값의 로더 스케일 결과와 정확히 일치하는 행"만
삭제하고, 다른 값(실오버라이드)은 절대 건드리지 않는다 — 재실행해도 안전
(멱등). 삭제 전 대상 행을 JSON 으로 백업한다.

적용 후 백엔드 재기동(또는 invalidate_cache) 시에도 로더 산출값은 삭제 전과
동일하다 — merge 가 같은 값을 코드 기본값에서 복원하기 때문.

사용법:
  .venv/bin/python scripts/cleanup_scoring_param_duplicates.py --target both            # dry-run
  .venv/bin/python scripts/cleanup_scoring_param_duplicates.py --target both --confirm  # 삭제
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

# 코드 기본값·배율은 런타임 로더와 같은 소스를 import 한다 (복제 금지).
# scripts 는 로컬 실행 전용이라 web/backend 를 sys.path 에 추가해도
# 배포 경계(웹↔배치 상호 import 금지)와 무관하다.
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
from services.scoring import (  # noqa: E402
    _DECAY_MULTIPLIER,
    _DEFAULT_DENSITY_FACTOR,
    _DEFAULT_FACILITY_DECAY,
    _DEFAULT_MAX_DISTANCE,
    _DENSITY_MULTIPLIER,
    _MAX_DIST_MULTIPLIER,
)

BACKUP_DIR = REPO_ROOT / "scripts" / "backups"

PROFILES = ("metro", "major_city", "provincial")


def _scaled_default(kind: str, profile: str | None, subtype: str) -> float | None:
    """로더의 스케일링 semantics 를 그대로 재현한 기대값. 미등록 subtype 은 None.

    반올림 방식이 로더(_load_*_by_profile)와 정확히 일치해야 중복 판정이
    어긋나지 않는다 — decay 는 float(round(v*mult)), 나머지는 round(v*mult, 1).
    """
    if kind == "facility_decay":
        base = _DEFAULT_FACILITY_DECAY.get(subtype)
        if base is None:
            return None
        return float(round(base * _DECAY_MULTIPLIER[profile]))
    if kind == "density_factor":
        base = _DEFAULT_DENSITY_FACTOR.get(subtype)
        if base is None:
            return None
        return round(base * _DENSITY_MULTIPLIER[profile], 1)
    if kind == "facility_distance":
        base = _DEFAULT_MAX_DISTANCE.get(subtype)
        if base is None:
            return None
        if profile is None:  # 글로벌 그룹 — 배율 없음
            return float(base)
        return round(base * _MAX_DIST_MULTIPLIER[profile], 1)
    raise ValueError(f"unknown kind: {kind}")


def _target_groups() -> list[tuple[str, str, str | None]]:
    """(group_id, kind, profile) 목록 — 글로벌 facility_distance + 프로필 3종 × 3그룹."""
    groups: list[tuple[str, str, str | None]] = [
        ("facility_distance", "facility_distance", None)
    ]
    for kind in ("facility_decay", "facility_distance", "density_factor"):
        for profile in PROFILES:
            groups.append((f"{kind}_{profile}", kind, profile))
    return groups


def get_conn(target: str):
    env_key = "RAILWAY_DATABASE_URL" if target == "railway" else "DATABASE_URL"
    url = os.getenv(env_key)
    if not url:
        raise SystemExit(f"{env_key} 미설정 (.env 확인)")
    return psycopg2.connect(url)


def cleanup(target: str, confirm: bool) -> None:
    conn = get_conn(target)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    duplicates: list[dict] = []  # 삭제 대상 (기본값과 정확히 일치)
    overrides: list[dict] = []  # 보존 대상 (실오버라이드)

    for group_id, kind, profile in _target_groups():
        cur.execute(
            "SELECT group_id, code, name, extra, sort_order FROM common_code "
            "WHERE group_id = %s ORDER BY code",
            [group_id],
        )
        for row in cur.fetchall():
            expected = _scaled_default(kind, profile, row["code"])
            entry = dict(row) | {"expected_default": expected}
            if expected is not None and float(row["name"]) == expected:
                duplicates.append(entry)
            else:
                overrides.append(entry)

    mode = "APPLY" if confirm else "DRY-RUN"
    print(f"\n[{target}] {mode} — 중복 {len(duplicates)}행 삭제 대상, "
          f"실오버라이드 {len(overrides)}행 보존")
    for e in overrides:
        print(f"  KEEP {e['group_id']}.{e['code']} = {e['name']} "
              f"(기본값 스케일 {e['expected_default']})")
    for e in duplicates:
        print(f"  {'DELETE' if confirm else 'would-delete'} "
              f"{e['group_id']}.{e['code']} = {e['name']}")

    if not confirm or not duplicates:
        return

    # 삭제 전 백업 (기본값에서 재구성 가능하지만 이중 안전장치)
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"common_code_dup_cleanup_{target}_{stamp}.json"
    backup_path.write_text(
        json.dumps(duplicates, ensure_ascii=False, indent=2, default=str)
    )
    print(f"  백업: {backup_path}")

    for e in duplicates:
        cur.execute(
            "DELETE FROM common_code WHERE group_id = %s AND code = %s AND name = %s",
            [e["group_id"], e["code"], e["name"]],
        )
    conn.commit()
    print(f"  ✅ {len(duplicates)}행 삭제 완료")
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target", choices=["local", "railway", "both"], required=True
    )
    parser.add_argument(
        "--confirm", action="store_true", help="실제 삭제 (기본 dry-run)"
    )
    args = parser.parse_args()

    targets = ["local", "railway"] if args.target == "both" else [args.target]
    for target in targets:
        cleanup(target, args.confirm)


if __name__ == "__main__":
    main()
