"""기존 고유번호 키 매핑(match_method 'api_%')을 현재 규칙으로 재판정한다 (ADR-015, 설계 4-4).

배경: #319 머지 전 운영 거래 배치가 옛 규칙(대표 행 하나의 주소·물리 게이트 없음·법정동 이름 매칭)으로
고유번호 키 매핑을 만들었다(예 28260-138 → 개편 전 법정동 PNU, 44150-25 → 주공3 api_name_exact).
rekey 는 이미 있는 매핑을 판정하지 않으므로, 과거 행이 그 잘못된 매핑을 따라가 불변식에 걸린다.
그래서 rekey 전에 이 단계를 각 대상 DB 에서 먼저 돌린다.

판정은 map_api_keys 와 같은 코드(trade_key_mapping.decide_api_keys — F1 실존 PNU 상속, 주소 PNU)와
같은 물리 게이트(mapping_gate — 비상속 판정만)를 쓴다. 이름 매칭은 없다.
  - 같은 PNU → 유지(행을 고쳐 쓰지 않는다 — match_method 도 그대로)
  - 다른 PNU(게이트 통과) → 교체(pnu·match_method 갱신)
  - 근거 없음(게이트 거부 포함) → 매핑 삭제. 그 키의 행은 미매핑이 된다(fallback 매핑 없음). 아직 키 변경
    전인 과거 행은 이름 키에 있어 영향이 없고, 이후 rekey 가 그 키를 다시 판정한다(매핑 못 하면 계획 행 되돌림).
    rekey 는 **이미 키를 바꾼 행을 다시 보지 않는다** — 그래서 rekey 체크포인트(done/failed/rolled_back)가 있는
    구에 행이 있는 키는 삭제하지 않고 blocked_delete 로 보고만 한다(--allow-delete-rekeyed 로만 삭제).
    적재기가 쓴 행은 미매핑으로 남는다(로그·리포트 — 보이던 행 손실은 따로 센다).

    python -m batch.remap_official_keys --target local --dry-run
    python -m batch.remap_official_keys --target local --apply
    python -m batch.remap_official_keys --target railway --dry-run   # 운영은 사용자 실행

한 실행 = 한 트랜잭션. --apply 일 때만 커밋하고 common_code 에 요약을 남긴다(대상 0건이어도 — rekey
순서 강제가 영원히 막히지 않게). 거래 배치와는
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
from batch.rekey_trades import CHECKPOINT_GROUP as REKEY_CHECKPOINT_GROUP
from batch.rekey_trades import db_url
from batch.trade.audit_mappings import find_violations
from batch.trade.mapping_gate import REJECT_LOG_SAMPLE, gate_keys
from batch.trade.remap_verification import (
    CHECKPOINT_GROUP,
    CHECKPOINT_STATUS,
    FIELD_JUDGED,
    FIELD_VERIFIED,
)
from batch.trade.trade_key_mapping import (
    MATCH_INHERIT_LEGACY,
    KeyDecision,
    KeyDecisions,
    decide_api_keys,
)
from batch.trade.trade_keys import try_trade_write_lock

ACTION_KEEP = "keep"
ACTION_REPLACE = "replace"
ACTION_DELETE = "delete"
ACTION_BLOCKED_DELETE = (
    "blocked_delete"  # 삭제 대상이지만 이미 키를 바꾼 구에 행이 있어 보류
)
OFFICIAL_KEY_METHOD_PATTERN = r"api\_%"
DEFAULT_REPORT_DIR = "reports/rekey"
GATE_SOURCE = "remap_official_keys"
DELETE_LOG_SAMPLE = 50
REPLACE_LOG_SAMPLE = 50
ROW_COLUMNS = ("trade_rows", "rent_rows", "inferred_rows")
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
    "old_pnu_exists",
    "sgg_rekeyed",
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
    rekeyed_keys: set[str] = frozenset(),
    allow_delete_rekeyed: bool = False,
) -> list[RemapItem]:
    """키별 재판정 계획. 판정이 없거나 물리 게이트가 거부한 키는 근거 없음(삭제)이다.

    rekeyed_keys: 이미 키를 바꾼 구(rekey 체크포인트 있음)에 행이 있는 키 — 삭제하면 그 행이 영구 미매핑이
    되므로(rekey 는 다시 보지 않는다) allow_delete_rekeyed 가 아니면 blocked_delete(매핑 그대로)로 둔다.
    """
    items = []
    for key in sorted(old):
        decision = None if key in gate_rejected else decided.get(key)
        action = classify(old[key].pnu, decision)
        if action == ACTION_DELETE and key in rekeyed_keys and not allow_delete_rekeyed:
            action = ACTION_BLOCKED_DELETE
        items.append(RemapItem(key, action, old[key], decision))
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


def non_inherit_verdicts(
    items: list[RemapItem],
) -> tuple[dict[str, str], list[str]]:
    """체크포인트용 (verified {키: PNU}, judged) — rekey F3b 가 기존 비상속 매핑을 신뢰할지 판단하는 근거.

    judged: 재판정 당시 비상속이던 키 + 재판정 후 비상속인 키. verified: 그중 재판정 후 비상속 매핑으로
    남은 키와 그 PNU(유지 — 행 그대로라 기존 method·PNU, 교체 — 새 method·PNU). rekey 는 매핑 PNU 가
    여기 적힌 PNU 와 같을 때만 신뢰한다. 지운 키·blocked_delete 키는 judged 에만 남는다(미검증).
    """
    verified: dict[str, str] = {}
    judged: set[str] = set()
    for it in items:
        if it.action == ACTION_KEEP:
            after = (it.old.match_method, it.old.pnu)
        elif it.action == ACTION_REPLACE:
            after = (it.new.match_method, it.new.pnu)
        else:
            after = None
        if after is not None and after[0] != MATCH_INHERIT_LEGACY:
            verified[it.apt_seq] = after[1]
        if it.old.match_method != MATCH_INHERIT_LEGACY:
            judged.add(it.apt_seq)
    return dict(sorted(verified.items())), sorted(judged | set(verified))


class RowLoss(NamedTuple):
    visible: dict[str, int]  # 기존 PNU 가 apartments 에 있던 행 — 화면에서 사라진다
    invisible: dict[str, int]  # 기존 PNU 가 없던(끊긴) 행 — 이미 보이지 않던 행


def deleted_row_loss(
    items: list[RemapItem], counts: dict[str, dict], existing_pnus: set[str]
) -> RowLoss:
    """삭제(delete)로 미매핑이 되는 행 — 보이던 행 손실과 이미 보이지 않던 행을 나눠 센다."""
    visible = dict.fromkeys(ROW_COLUMNS, 0)
    invisible = dict.fromkeys(ROW_COLUMNS, 0)
    for it in items:
        if it.action != ACTION_DELETE:
            continue
        bucket = visible if it.old.pnu in existing_pnus else invisible
        for col in ROW_COLUMNS:
            bucket[col] += counts.get(it.apt_seq, {}).get(col, 0)
    return RowLoss(visible, invisible)


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


def _row_counts(conn, keys: list[str]) -> tuple[dict[str, dict[str, int]], dict]:
    """(키별 행 수, 키별 행이 있는 시군구 집합) — inferred_rows 는 rekey 가 추론으로 옮긴 과거 행."""
    out: dict[str, dict[str, int]] = {}
    sggs: dict[str, set[str]] = {}
    for table, col in (("trade_history", "trade_rows"), ("rent_history", "rent_rows")):
        for r in query_all(
            conn,
            f"SELECT apt_seq, sgg_cd, COUNT(*) n, "
            f"COUNT(*) FILTER (WHERE apt_seq_method LIKE 'infer\\_%%') inf "
            f"FROM {table} WHERE apt_seq = ANY(%s) GROUP BY 1, 2",
            [keys],
        ):
            d = out.setdefault(r["apt_seq"], dict.fromkeys(ROW_COLUMNS, 0))
            d[col] += r["n"]
            d["inferred_rows"] += r["inf"]
            sggs.setdefault(r["apt_seq"], set()).add(r["sgg_cd"])
    return out, sggs


def _rekeyed_sggs(conn) -> set[str]:
    """rekey 체크포인트(상태 무관 — done/failed/rolled_back)가 있는 시군구."""
    return {
        r["code"]
        for r in query_all(
            conn,
            "SELECT code FROM common_code WHERE group_id = %s",
            [REKEY_CHECKPOINT_GROUP],
        )
    }


def _existing_pnus(conn, pnus: list[str]) -> set[str]:
    return {
        r["pnu"]
        for r in query_all(
            conn, "SELECT pnu FROM apartments WHERE pnu = ANY(%s)", [pnus]
        )
    }


def _gate_rejections(conn, logger, old, decided, apply: bool) -> set[str]:
    """판정을 SAVEPOINT 안에 써서 물리 게이트(mapping_gate 와 같은 find_violations 판정)를 돌리고
    되돌린다 — 거부된 키 집합. 쓰기는 이후 _apply 가 한다(dry-run 은 쓰지 않는다)."""
    keys, rewrite = gate_candidates(old, decided)
    if not keys:
        return set()
    cur = conn.cursor()
    cur.execute("SAVEPOINT remap_gate")
    try:
        _update_mappings(conn, [(k, decided[k]) for k in rewrite])
        violations, _ = find_violations(conn, apt_seqs=keys)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT remap_gate")
    if violations:
        verb = "거부 → 매핑 삭제 대상" if apply else "거부 예정(dry-run — 쓰지 않음)"
        sample = [
            f"{v['apt_seq']} {v['apt_nm']} → {v['bld_nm']} [{v['match_method']}] "
            f"{', '.join(v['reasons'])}"
            for v in sorted(violations, key=lambda x: x["apt_seq"])[:REJECT_LOG_SAMPLE]
        ]
        logger.warning(
            f"  [{GATE_SOURCE}] 물리 감사 불통과 {verb} {len(violations):,}건 "
            f"(최대 {REJECT_LOG_SAMPLE}): {sample}"
        )
    return {v["apt_seq"] for v in violations}


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


def _write_report(
    path: str, items: list[RemapItem], counts, existing_pnus, rekeyed_keys
) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    zero = dict.fromkeys(ROW_COLUMNS, 0)
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
                    it.old.pnu in existing_pnus,
                    it.apt_seq in rekeyed_keys,
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


def remap(
    conn,
    logger,
    apply: bool,
    report_path: str,
    run_id: str,
    allow_delete_rekeyed: bool = False,
) -> dict:
    """재판정 → 리포트 → (apply 면) 교체·삭제 + 체크포인트. 커밋·롤백은 호출자 몫."""
    old = _old_mappings(conn)
    logger.info(f"재판정 대상 고유번호 키 매핑 {len(old):,}건")
    keys = sorted(old)
    kd = (
        decide_api_keys(conn, logger, keys, only_unmapped=False)
        if keys
        else KeyDecisions({}, [], {})
    )
    rejected = _gate_rejections(conn, logger, old, kd.decided, apply) if keys else set()
    counts, sggs_by_key = _row_counts(conn, keys) if keys else ({}, {})
    rekeyed_sggs = _rekeyed_sggs(conn)
    rekeyed_keys = {k for k, sggs in sggs_by_key.items() if sggs & rekeyed_sggs}
    items = plan_remap(old, kd.decided, rejected, rekeyed_keys, allow_delete_rekeyed)
    existing = (
        _existing_pnus(conn, sorted({m.pnu for m in old.values()})) if old else set()
    )
    _write_report(report_path, items, counts, existing, rekeyed_keys)

    summary = summarize(items)
    loss = deleted_row_loss(items, counts, existing)
    by_action = {a: [it for it in items if it.action == a] for a in summary}
    detail = {
        "run_at": run_id,
        "total": len(items),
        "by_action": summary,
        "gate_rejected": len(rejected),
        "visible_rows_lost": loss.visible,
        "invisible_rows_unmapped": loss.invisible,
        "allow_delete_rekeyed": allow_delete_rekeyed,
        "report": report_path,
    }
    logger.info(f"재판정 결과(기존 match_method 별): {summary}")
    logger.info(f"물리 게이트 거부 {len(rejected):,}건 (삭제·보류에 포함)")
    replaces = by_action.get(ACTION_REPLACE, [])
    if replaces:
        logger.warning(
            f"매핑 교체 {len(replaces):,}건 (최대 {REPLACE_LOG_SAMPLE}): "
            f"{[f'{it.apt_seq} {it.old.pnu}→{it.new.pnu}' for it in replaces[:REPLACE_LOG_SAMPLE]]}"
        )
    deletes = by_action.get(ACTION_DELETE, [])
    if deletes:
        logger.warning(
            f"매핑 삭제 {len(deletes):,}건 — 보이던 행 손실 {loss.visible}, "
            f"이미 보이지 않던(끊긴 PNU) 행 {loss.invisible} "
            f"(최대 {DELETE_LOG_SAMPLE}): {[it.apt_seq for it in deletes[:DELETE_LOG_SAMPLE]]}"
        )
    blocked = by_action.get(ACTION_BLOCKED_DELETE, [])
    if blocked:
        logger.warning(
            f"삭제 보류(blocked_delete — 이미 키를 바꾼 구에 행 있음, --allow-delete-rekeyed 로만 삭제) "
            f"{len(blocked):,}건 (최대 {DELETE_LOG_SAMPLE}): "
            f"{[it.apt_seq for it in blocked[:DELETE_LOG_SAMPLE]]}"
        )
    logger.info(f"전체 목록: {report_path}")
    if apply:
        _apply(conn, items)
        verified, judged = non_inherit_verdicts(items)
        _save_checkpoint(
            conn, run_id, {**detail, FIELD_VERIFIED: verified, FIELD_JUDGED: judged}
        )
    return detail


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--target", choices=["local", "railway"], required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    p.add_argument("--report", help="전체 목록 TSV 경로 (기본 reports/rekey/ 아래)")
    p.add_argument(
        "--allow-delete-rekeyed",
        action="store_true",
        help="이미 키를 바꾼 구에 행이 있는 키의 매핑도 삭제(그 행은 영구 미매핑 — rekey 가 다시 보지 않음)",
    )
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
        remap(conn, logger, args.apply, report, run_id, args.allow_delete_rekeyed)
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
