"""기존 고유번호 키 매핑(match_method 'api_%')을 현재 규칙으로 재판정한다 (ADR-015, 설계 4-4).

배경: #319 머지 전 운영 거래 배치가 옛 규칙(대표 행 하나의 주소·물리 게이트 없음·법정동 이름 매칭)으로
고유번호 키 매핑을 만들었다(예 28260-138 → 개편 전 법정동 PNU, 44150-25 → 주공3 api_name_exact).
rekey 는 이미 있는 매핑을 판정하지 않으므로, 과거 행이 그 잘못된 매핑을 따라가 불변식에 걸린다.
그래서 rekey 전에 이 단계를 각 대상 DB 에서 먼저 돌린다.

판정은 map_api_keys 와 같은 코드(trade_key_mapping.decide_api_keys — F1 실존 PNU 상속, 주소 PNU)와
같은 물리 게이트(mapping_gate — 비상속 판정만)를 쓴다. 이름 매칭은 없다.
  - 같은 PNU → 유지(행을 고쳐 쓰지 않는다 — match_method 도 그대로)
  - 다른 PNU(게이트 통과) → 교체(pnu·match_method 갱신)
  - 근거 없음(게이트 거부 포함) → 매핑 삭제. 그 키의 행은 미매핑이 된다 — 과거 행은 이후 rekey 가
    이름 키로 되돌리고(계획 행 되돌림), 적재기가 쓴 행은 미매핑으로 남는다(로그). fallback 매핑 없음.

    python -m batch.remap_official_keys --target local --dry-run
    python -m batch.remap_official_keys --target local --apply
    python -m batch.remap_official_keys --target railway --dry-run   # 운영은 사용자 실행

한 실행 = 한 트랜잭션. --apply 일 때만 커밋하고 common_code 에 요약을 남긴다. 거래 배치와는
advisory lock(try_trade_write_lock)으로 상호 배제한다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime
from typing import NamedTuple

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from batch.db import query_all
from batch.logger import setup_logger
from batch.rekey_trades import db_url
from batch.trade.mapping_gate import gate_keys, reject_unverified_mappings
from batch.trade.trade_key_mapping import (
    MATCH_INHERIT_LEGACY,
    KeyDecision,
    decide_api_keys,
)
from batch.trade.trade_keys import try_trade_write_lock

CHECKPOINT_GROUP = "remap_official_keys_checkpoint"
CHECKPOINT_STATUS = "applied"
ACTION_KEEP = "keep"
ACTION_REPLACE = "replace"
ACTION_DELETE = "delete"
OFFICIAL_KEY_METHOD_PATTERN = r"api\_%"
DEFAULT_REPORT_DIR = "reports/rekey"
GATE_SOURCE = "remap_official_keys"
DELETE_LOG_SAMPLE = 50
REPORT_FIELDS = (
    "apt_seq",
    "sgg_cd",
    "action",
    "old_pnu",
    "old_method",
    "new_pnu",
    "new_method",
    "trade_rows",
    "rent_rows",
    "inferred_rows",
)


class OldMapping(NamedTuple):
    pnu: str
    match_method: str
    sgg_cd: str


class RemapItem(NamedTuple):
    apt_seq: str
    action: str
    old: OldMapping
    new: KeyDecision | None


def classify(old_pnu: str, decision: KeyDecision | None) -> str:
    """기존 PNU 와 (게이트를 거친) 새 판정 → keep / replace / delete."""
    if decision is None:
        return ACTION_DELETE
    return ACTION_KEEP if decision.pnu == old_pnu else ACTION_REPLACE


def plan_remap(
    old: dict[str, OldMapping],
    decided: dict[str, KeyDecision],
    gate_rejected: set[str],
) -> list[RemapItem]:
    """키별 재판정 계획. 판정이 없거나 물리 게이트가 거부한 키는 근거 없음(삭제)이다."""
    items = []
    for key in sorted(old):
        decision = None if key in gate_rejected else decided.get(key)
        items.append(
            RemapItem(key, classify(old[key].pnu, decision), old[key], decision)
        )
    return items


def gate_candidates(old: dict[str, OldMapping], decided: dict[str, KeyDecision]):
    """물리 게이트 대상 — 비상속 판정 키 (map_api_keys 와 같은 면제 규칙).

    반환: (게이트할 키, 그중 게이트 전에 판정 PNU 로 바꿔 써야 하는 키 — 기존 PNU 와 다른 것).
    """
    keys = gate_keys(
        [(k, d.match_method) for k, d in decided.items() if k in old],
        {MATCH_INHERIT_LEGACY},
    )
    return keys, [k for k in keys if decided[k].pnu != old[k].pnu]


def summarize(items: list[RemapItem]) -> dict[str, dict[str, int]]:
    """{action: {기존 match_method: 건수}}."""
    out: dict[str, Counter] = {}
    for it in items:
        out.setdefault(it.action, Counter())[it.old.match_method] += 1
    return {a: dict(sorted(c.items())) for a, c in sorted(out.items())}


# ── DB ──


def _old_mappings(conn) -> dict[str, OldMapping]:
    return {
        r["apt_seq"]: OldMapping(r["pnu"], r["match_method"], r["sgg_cd"])
        for r in query_all(
            conn,
            "SELECT apt_seq, pnu, match_method, sgg_cd FROM trade_apt_mapping "
            "WHERE match_method LIKE %s",
            [OFFICIAL_KEY_METHOD_PATTERN],
        )
    }


def _row_counts(conn, keys: list[str]) -> dict[str, dict[str, int]]:
    """키별 행 수 — inferred_rows 는 rekey 가 추론으로 옮긴 과거 행(apt_seq_method 'infer_%')."""
    out: dict[str, dict[str, int]] = {}
    for table, col in (("trade_history", "trade_rows"), ("rent_history", "rent_rows")):
        for r in query_all(
            conn,
            f"SELECT apt_seq, COUNT(*) n, "
            f"COUNT(*) FILTER (WHERE apt_seq_method LIKE 'infer\\_%%') inf "
            f"FROM {table} WHERE apt_seq = ANY(%s) GROUP BY 1",
            [keys],
        ):
            d = out.setdefault(
                r["apt_seq"], {"trade_rows": 0, "rent_rows": 0, "inferred_rows": 0}
            )
            d[col] += r["n"]
            d["inferred_rows"] += r["inf"]
    return out


def _gate_rejections(conn, logger, old, decided) -> set[str]:
    """판정을 SAVEPOINT 안에 써서 물리 게이트를 돌리고 되돌린다 — 거부된 키 집합."""
    keys, rewrite = gate_candidates(old, decided)
    if not keys:
        return set()
    cur = conn.cursor()
    cur.execute("SAVEPOINT remap_gate")
    try:
        _update_mappings(conn, [(k, decided[k]) for k in rewrite])
        rejected = {
            v["apt_seq"]
            for v in reject_unverified_mappings(conn, logger, keys, source=GATE_SOURCE)
        }
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT remap_gate")
    return rejected


def _update_mappings(conn, pairs: list[tuple[str, KeyDecision]]) -> None:
    if pairs:
        psycopg2.extras.execute_values(
            conn.cursor(),
            "UPDATE trade_apt_mapping m SET pnu = v.pnu, match_method = v.method "
            "FROM (VALUES %s) AS v(apt_seq, pnu, method) WHERE m.apt_seq = v.apt_seq",
            [(k, d.pnu, d.match_method) for k, d in pairs],
        )


def _apply(conn, items: list[RemapItem]) -> None:
    _update_mappings(
        conn, [(it.apt_seq, it.new) for it in items if it.action == ACTION_REPLACE]
    )
    deletes = [it.apt_seq for it in items if it.action == ACTION_DELETE]
    if deletes:
        conn.cursor().execute(
            "DELETE FROM trade_apt_mapping WHERE apt_seq = ANY(%s)", [deletes]
        )


def _write_report(path: str, items: list[RemapItem], counts) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    zero = {"trade_rows": 0, "rent_rows": 0, "inferred_rows": 0}
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(REPORT_FIELDS)
        for it in items:
            c = counts.get(it.apt_seq, zero)
            w.writerow(
                [
                    it.apt_seq,
                    it.old.sgg_cd,
                    it.action,
                    it.old.pnu,
                    it.old.match_method,
                    it.new.pnu if it.new else "",
                    it.new.match_method if it.new else "",
                    c["trade_rows"],
                    c["rent_rows"],
                    c["inferred_rows"],
                ]
            )


def _save_checkpoint(conn, run_id: str, detail: dict) -> None:
    conn.cursor().execute(
        """
        INSERT INTO common_code (group_id, code, name, extra, sort_order) VALUES (%s, %s, %s, %s, 0)
        ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name, extra = EXCLUDED.extra""",
        [
            CHECKPOINT_GROUP,
            run_id,
            CHECKPOINT_STATUS,
            json.dumps(detail, ensure_ascii=False),
        ],
    )


def remap(conn, logger, apply: bool, report_path: str, run_id: str) -> dict:
    """재판정 → 리포트 → (apply 면) 교체·삭제 + 체크포인트. 커밋·롤백은 호출자 몫."""
    old = _old_mappings(conn)
    logger.info(f"재판정 대상 고유번호 키 매핑 {len(old):,}건")
    if not old:
        return {}
    keys = sorted(old)
    kd = decide_api_keys(conn, logger, keys, only_unmapped=False)
    rejected = _gate_rejections(conn, logger, old, kd.decided)
    items = plan_remap(old, kd.decided, rejected)
    counts = _row_counts(conn, keys)
    _write_report(report_path, items, counts)

    summary = summarize(items)
    deletes = [it for it in items if it.action == ACTION_DELETE]
    unmapped_rows = {
        col: sum(counts.get(it.apt_seq, {}).get(col, 0) for it in deletes)
        for col in ("trade_rows", "rent_rows", "inferred_rows")
    }
    detail = {
        "run_at": run_id,
        "total": len(items),
        "by_action": summary,
        "gate_rejected": len(rejected),
        "unmapped_rows_by_delete": unmapped_rows,
        "report": report_path,
    }
    logger.info(f"재판정 결과(기존 match_method 별): {summary}")
    logger.info(f"물리 게이트 거부 {len(rejected):,}건 (삭제에 포함)")
    if deletes:
        logger.warning(
            f"매핑 삭제 {len(deletes):,}건 → 미매핑이 되는 행 {unmapped_rows} "
            f"(최대 {DELETE_LOG_SAMPLE}): {[it.apt_seq for it in deletes[:DELETE_LOG_SAMPLE]]}"
        )
    logger.info(f"전체 목록: {report_path}")
    if apply:
        _apply(conn, items)
        _save_checkpoint(conn, run_id, detail)
    return detail


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--target", choices=["local", "railway"], required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    p.add_argument("--report", help="전체 목록 TSV 경로 (기본 reports/rekey/ 아래)")
    args = p.parse_args()
    logger = setup_logger("remap_official_keys")

    run_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    report = args.report or os.path.join(
        DEFAULT_REPORT_DIR,
        f"remap_{args.target}_{'apply' if args.apply else 'dryrun'}_{run_id}.tsv",
    )
    conn = psycopg2.connect(db_url(args.target))
    conn.autocommit = False
    try:
        if not try_trade_write_lock(conn):
            raise SystemExit("거래 배치 실행 중 — 배치 사이 시간에 다시 실행")
        remap(conn, logger, args.apply, report, run_id)
        if args.apply:
            conn.commit()
            logger.info("커밋 완료")
        else:
            conn.rollback()
            logger.info("dry-run — 변경 없음(롤백)")
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    main()
