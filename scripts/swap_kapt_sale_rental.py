"""임대 레코드가 차지한 PNU 를 분양·혼합 레코드에 돌려준다 (ADR-014).

입력은 `scripts.kapt_rental_swap_candidates` 가 만든 검수 목록 CSV 다. **사람이 목록을 확인한 뒤**
실행한다. 기본은 dry-run 이고 `--apply` 를 붙여야 반영된다.

대상
  신뢰도 HIGH 만 — 주소 일치 + 실거래 면적이 분양 레코드 주택형과 일치 + PNU 당 후보 1건.
  MEDIUM 은 개별 확인 후 CSV 의 confidence 를 HIGH 로 고쳐 넣는다. LOW 는 대상이 아니다.

PNU 1건당 (한 트랜잭션, `batch.kapt.companion_records.swap_records`)
  1. 임대 레코드와 그 유래 행(apt_kapt_info·apt_area_type·apt_area_info·apt_mgmt_cost)을
     `KAPT_<임대코드>` 로 옮기고 parent_pnu 로 소속 단지를 기록
  2. `KAPT_<분양코드>` 에 있던 분양 레코드와 유래 행을 실제 PNU 로
  3. apartments 의 세대수·동수·최고층·사용승인일을 분양 레코드 값으로
  4. CSV 의 `combine_households` 가 `yes` 면 임대 레코드를 동반 레코드로 연결해 세대수를
     분양+임대 합산으로 올린다. `review`(미확정)·`no` 면 분양 세대수로 둔다 — 자리를 내주는 임대
     레코드가 이웃한 다른 단지인 경우가 있어(군자주공14단지 ↔ 안산군자13단지) 추정으로 더하지 않는다.
     `review` 는 사람이 yes/no 로 고친 뒤 실행하는 것이 원칙이다.
  지우는 행은 없다. 같은 CSV 에서 sale/rental 코드를 맞바꾸면 역교환된다.

실행 시점에 DB 를 다시 본다 — 목록을 만든 뒤 상태가 바뀌었으면 그 PNU 는 건너뛰고 사유를 남긴다.

사용
  .venv/bin/python -m scripts.swap_kapt_sale_rental --candidates reports/kapt_swap_candidates_YYYYMMDD.csv
  .venv/bin/python -m scripts.swap_kapt_sale_rental --candidates ... --apply
  .venv/bin/python -m scripts.swap_kapt_sale_rental --candidates ... --target railway --apply

Railway
  `parent_pnu` 컬럼이 있어야 한다(백엔드 배포 시 create_tables 가 만든다). 로컬을 교체한 뒤
  `push_table_to_railway` 로 밀면 안 된다 — UPSERT 전용이라 옛 더미 행이 Railway 에 남는다.
  같은 CSV 로 이 스크립트를 `--target railway` 로 실행한다.

반영 후
  apt_mgmt_cost 는 임대 기준 이력이 더미로 옮겨져 실제 PNU 가 빈다 — 분양 기준은
  `python -m batch.kapt.collect_mgmt_cost --source xlsx ...` 재적재로 채운다.
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import Counter
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

from batch.kapt.companion_records import (
    CompanionRecordError,
    ensure_parent_pnu_column,
    swap_records,
)
from batch.logger import setup_logger

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

TARGET_CONFIDENCE = "HIGH"
REQUIRED_COLUMNS = (
    "confidence",
    "pnu",
    "sale_kapt_code",
    "rental_kapt_code",
    "combine_households",
)
# combine_households 가 이 값일 때만 임대 레코드를 동반 레코드로 연결해 세대수를 합산한다.
# 'review'(미확정)·'no' 는 교체는 하되 합산하지 않는다 — 추정으로 두 단지를 더하지 않는다.
COMBINE_YES = "yes"

STATE_SQL = """
SELECT a.total_hhld_cnt, k.kapt_code, k.kapt_name, k.sale_type, k.ho_cnt
FROM apartments a LEFT JOIN apt_kapt_info k ON k.pnu = a.pnu
WHERE a.pnu = %s
"""


def _db_url(target: str) -> str:
    if target == "local":
        url = os.getenv("DATABASE_URL")
    elif target == "railway":
        url = os.getenv("RAILWAY_DATABASE_URL")
        if url and "railway" not in url:
            raise SystemExit(
                "RAILWAY_DATABASE_URL 이 Railway 형태가 아님 — 안전상 중단"
            )
    else:
        raise SystemExit(f"unknown target: {target}")
    if not url:
        raise SystemExit(f"{target} DB URL 미설정")
    return url


def load_targets(path: Path) -> list[dict]:
    """CSV 에서 교체 대상을 읽는다. 한 PNU 에 HIGH 가 둘 이상이면 모호하므로 그 PNU 는 뺀다."""
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"CSV 에 필수 컬럼 없음: {missing}")
        rows = [r for r in reader if r["confidence"] == TARGET_CONFIDENCE]

    per_pnu = Counter(r["pnu"] for r in rows)
    return [r for r in rows if per_pnu[r["pnu"]] == 1]


def _state(cur, pnu: str) -> tuple | None:
    cur.execute(STATE_SQL, [pnu])
    return cur.fetchone()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--candidates", type=Path, required=True, help="검수 목록 CSV")
    ap.add_argument("--target", choices=["local", "railway"], default="local")
    ap.add_argument("--apply", action="store_true", help="반영 (기본은 dry-run)")
    ap.add_argument(
        "--pnu", action="append", default=[], help="이 PNU 만 (반복 지정 가능)"
    )
    args = ap.parse_args()

    logger = setup_logger(f"swap_kapt_sale_rental_{args.target}")
    targets = load_targets(args.candidates)
    if args.pnu:
        wanted = set(args.pnu)
        targets = [t for t in targets if t["pnu"] in wanted]
    mode = "APPLY" if args.apply else "DRY-RUN"
    logger.info(
        f"[{args.target}] {mode} — 대상 {len(targets)} PNU ({args.candidates.name})"
    )

    conn = psycopg2.connect(_db_url(args.target))
    swapped = rejected = uncombined = 0
    try:
        cur = conn.cursor()
        try:
            ensure_parent_pnu_column(cur)
        except CompanionRecordError as e:
            logger.error(str(e))
            return 1

        for t in targets:
            pnu, sale_code, rental_code = (
                t["pnu"],
                t["sale_kapt_code"],
                t["rental_kapt_code"],
            )
            combine = t["combine_households"].strip().lower() == COMBINE_YES
            before = _state(cur, pnu)
            try:
                swap_records(
                    cur,
                    pnu,
                    incoming_kapt_code=sale_code,
                    outgoing_kapt_code=rental_code,
                    link_as_companion=combine,
                )
            except CompanionRecordError as e:
                conn.rollback()
                rejected += 1
                logger.warning(f"  거부 {pnu} {t.get('bld_nm', '')}: {e}")
                continue

            after = _state(cur, pnu)
            if args.apply:
                conn.commit()
            else:
                conn.rollback()
            swapped += 1
            if not combine:
                uncombined += 1
            note = "합산" if combine else f"분양만 — 합산 {t['combine_households']}"
            logger.info(
                f"  {pnu} {t.get('bld_nm', '')[:18]}: "
                f"{before[2]}({before[3]}) {before[0]:,}세대 → "
                f"{after[2]}({after[3]}) {after[0]:,}세대 [{note}]"
            )
    finally:
        conn.close()

    verb = "반영" if args.apply else "반영 예정(dry-run — 변경 없음)"
    logger.info(
        f"[{args.target}] {verb} {swapped}건 (그중 합산 안 함 {uncombined}건 — no·review), 거부 {rejected}건"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
