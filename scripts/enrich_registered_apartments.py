"""신규 등록된 아파트의 시설 집계·안전점수·파생 데이터를 채운다.

배경
  register_missing_apartments.py 로 등록한 PNU 는 좌표·주소·건축물대장 기본
  정보만 갖고 시작한다. 시설 요약(apt_facility_summary)·안전점수·배정초교·
  건축물대장 상세가 비어 있어 상세 화면이 사실상 빈 껍데기다.
  거래 배치는 자기가 등록한 신규 PNU 만 보충하므로(batch/run.py 6단계),
  스크립트로 등록한 건은 다음 quarterly(최대 3개월)까지 방치된다.

  본 스크립트는 batch/run.py 의 신규 아파트 보충 절차를 그대로 재사용한다.
  새 로직을 만들지 않고 같은 함수를 같은 순서로 호출한다.

절차 (batch/run.py 6~6b 와 동일 순서)
  1. recalc_for_new_apartments  시설 집계 + 안전점수 v3
  2. recalc_assigned_school     배정초교 — 1의 school 최근접 거리를 프록시로
                                쓰므로 반드시 1 이후에 실행해야 한다
  3. collect_building_register  승강기·주차 등 건축물대장 상세

  각 단계는 독립 격리한다. 하나가 실패해도 나머지는 진행한다.

대상 선정
  --pnu-file      개행 구분 PNU 목록
  --from-report   register_missing_apartments 리포트 JSON 의 REGISTER 건
  둘 다 없으면 apt_facility_summary 가 비어 있는 좌표 보유 아파트 전체.
  --force 없이는 이미 시설 요약이 있는 PNU 를 건너뛴다.

사용
  .venv/bin/python scripts/enrich_registered_apartments.py --from-report <json>
  .venv/bin/python scripts/enrich_registered_apartments.py --from-report <json> --apply
  .venv/bin/python scripts/enrich_registered_apartments.py --target railway --apply \
      --from-report <json>

주의
  시설 집계는 BallTree 로 전국 시설(84만행)을 적재하므로 메모리·시간이 든다.
  --limit 으로 나눠 돌릴 수 있고, 이미 처리된 PNU 는 기본적으로 제외되므로
  재실행하면 남은 것부터 이어진다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from batch.logger import setup_logger  # noqa: E402

# 대상 후보 — 좌표가 있어야 시설 집계가 가능하다.
PENDING_SQL = """
SELECT a.pnu
FROM apartments a
WHERE a.lat IS NOT NULL AND a.lng IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM apt_facility_summary f WHERE f.pnu = a.pnu)
ORDER BY a.pnu
"""


def _connect(target: str):
    key = "DATABASE_URL" if target == "local" else "RAILWAY_DATABASE_URL"
    url = os.environ.get(key)
    if not url:
        raise SystemExit(f"{key} 환경변수가 없습니다.")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def _rows(cur, sql, params=None):
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def resolve_targets(cur, args) -> list[str]:
    if args.pnu_file:
        pnus = [ln.strip() for ln in Path(args.pnu_file).read_text().splitlines()
                if ln.strip()]
    elif args.from_report:
        data = json.loads(Path(args.from_report).read_text())
        pnus = sorted({r["new"]["pnu"] for r in data
                       if r.get("status") == "REGISTER" and r.get("new")})
    else:
        pnus = [r["pnu"] for r in _rows(cur, PENDING_SQL)]

    if not pnus:
        return []

    # 좌표 없는 PNU 는 시설 집계 대상이 아니다.
    have = {r["pnu"] for r in _rows(cur,
        "SELECT pnu FROM apartments WHERE pnu = ANY(%s) AND lat IS NOT NULL", [pnus])}
    skipped_nocoord = len(pnus) - len(have)

    if not args.force:
        done = {r["pnu"] for r in _rows(cur,
            "SELECT DISTINCT pnu FROM apt_facility_summary WHERE pnu = ANY(%s)",
            [sorted(have)])}
        have -= done
        if done:
            print(f"  이미 처리됨 {len(done)}건 제외 (--force 로 재계산)")
    if skipped_nocoord:
        print(f"  좌표 없음 {skipped_nocoord}건 제외")

    return sorted(have)


def report_coverage(cur, pnus: list[str], label: str) -> None:
    """보유 현황. 배정초교는 별도 테이블이 아니라 apt_facility_summary 의
    assigned_elementary 서브타입으로 저장되므로 그 행을 직접 센다."""
    print(f"\n=== {label} ===")
    for tbl in ("apt_facility_summary", "apt_safety_score", "apt_building_register"):
        cur.execute(f"SELECT COUNT(DISTINCT pnu) c FROM {tbl} WHERE pnu = ANY(%s)",
                    [pnus])
        print(f"  {tbl:28s} {cur.fetchone()['c']:5d} / {len(pnus)}")
    cur.execute("""SELECT COUNT(DISTINCT pnu) c FROM apt_facility_summary
                   WHERE pnu = ANY(%s) AND facility_subtype = 'assigned_elementary'""",
                [pnus])
    print(f"  {'└ assigned_elementary':28s} {cur.fetchone()['c']:5d} / {len(pnus)}")


def run_step(name: str, fn, logger) -> None:
    """한 단계를 실행한다. 실패해도 다음 단계로 넘어간다."""
    try:
        fn()
        print(f"  [{name}] 완료")
    except Exception as e:  # noqa: BLE001 — 단계 격리가 목적
        logger.warning(f"{name} 실패: {e}")
        print(f"  [{name}] 실패: {e}")


def enrich(conn, pnus: list[str], logger) -> None:
    """batch/run.py 6~6b 와 동일한 순서로 보충한다."""
    from batch.annual.collect_building_register import collect_building_register
    from batch.quarterly.assigned_school import recalc_assigned_school
    from batch.quarterly.recalc_summary import recalc_for_new_apartments

    # 1. 시설 집계 + 안전점수. 2의 프록시(school 최근접 거리)를 만든다.
    run_step("시설집계/안전점수",
             lambda: recalc_for_new_apartments(conn, logger, pnus), logger)
    conn.commit()

    # 2. 배정초교 — 반드시 1 이후
    run_step("배정초교",
             lambda: recalc_assigned_school(conn, logger, pnu_list=pnus), logger)
    conn.commit()

    # 3. 건축물대장 상세 (승강기·주차)
    run_step("건축물대장 상세",
             lambda: collect_building_register(conn, logger, pnu_list=pnus), logger)
    conn.commit()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=["local", "railway"], default="local")
    ap.add_argument("--apply", action="store_true", help="실제 실행 (기본은 대상 확인만)")
    ap.add_argument("--limit", type=int, default=0, help="대상 수 제한 (0=전체)")
    ap.add_argument("--pnu-file", default="", help="개행 구분 PNU 목록 파일")
    ap.add_argument("--from-report", default="",
                    help="register_missing_apartments 리포트 JSON (REGISTER 건)")
    ap.add_argument("--force", action="store_true",
                    help="이미 시설 요약이 있는 PNU 도 재계산")
    args = ap.parse_args()

    conn = _connect(args.target)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    logger = setup_logger("enrich_registered")

    print(f"[{args.target}] {'APPLY' if args.apply else 'DRY-RUN'}")
    pnus = resolve_targets(cur, args)
    if args.limit > 0:
        pnus = pnus[:args.limit]

    if not pnus:
        print("\n대상 없음")
        conn.close()
        return 0

    print(f"\n대상 {len(pnus):,}건")
    report_coverage(cur, pnus, "실행 전 보유 현황")

    if not args.apply:
        conn.rollback()
        print("\nDRY-RUN — 변경 없음. 실행하려면 --apply")
        conn.close()
        return 0

    print(f"\n=== 보충 실행 ({len(pnus):,}건) ===")
    enrich(conn, pnus, logger)
    report_coverage(cur, pnus, "실행 후 보유 현황")

    print("\n참고: 유사도 벡터(apt_vectors)는 전체 재생성이라 별도 실행이 필요하다")
    print("      .venv/bin/python -c 'from batch.ml.build_vectors import build_all_vectors ...'")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
