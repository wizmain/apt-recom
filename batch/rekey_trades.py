"""과거 거래 키를 국토부 고유번호로 바꾼다 (ADR-015, 설계 4-3·4-4·4-5).

구(sgg) 하나를 한 트랜잭션으로 처리하고, **커밋 전에** 불변식을 검사해 실패하면 그 구를
롤백한다. 원래 키는 legacy_apt_seq 에 남아 사후 롤백(--rollback)도 가능하다.

    python -m batch.rekey_trades --target local --dry-run            # 계획 건수만
    python -m batch.rekey_trades --target local --apply              # 로컬 적용
    python -m batch.rekey_trades --target railway --apply --limit 20 # 운영(사용자 실행)
    python -m batch.rekey_trades --target local --rollback --sgg 11590

전체 실행(--sgg 생략)은 체크포인트가 done/failed/rolled_back 인 구를 건너뛴다(롤백한 구를
다음 --apply 가 되살리지 않는다). --sgg 로 명시한 구는 상태와 무관하게 다시 실행한다.
감사(audit) 위반은 **같은 행**을 변경 전 키(old_keys)와 변경 후 키(new_keys)로 각각 세어 비교한다.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from typing import NamedTuple

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from batch.db import query_all, vacuum_tables
from batch.logger import setup_logger
from batch.trade.audit_mappings import audit
from batch.trade.trade_key_inference import KnownRow, TargetRow, infer_keys
from batch.trade.trade_key_mapping import map_api_keys
from batch.trade.trade_keys import KEY_METHOD_API, try_trade_write_lock

CHECKPOINT_GROUP = "rekey_trades_checkpoint"
TABLES = ("trade_history", "rent_history")
SKIP_STATUSES = (
    "done",
    "failed",
    "rolled_back",
)  # 전체 실행에서 건너뛰는 체크포인트 상태
DEFAULT_VACUUM_EVERY = 20  # 구 N개마다 VACUUM (ANALYZE) — 운영 1GB 캡 bloat 완화


class Snapshot(NamedTuple):
    rows: dict[str, int]
    unmapped: int
    pnu_counts: dict[str, int]


def plan_sgg(
    trade_known, trade_api_rows, trade_targets, rent_known, rent_api_rows, rent_targets
):
    """테이블별 (id, new_key, method). *_api_rows 는 이미 고유번호가 있는 이름 키 행 (id, api)."""
    plan = {}
    for table, known, api_rows, targets, use_year in (
        ("trade_history", trade_known, trade_api_rows, trade_targets, True),
        ("rent_history", rent_known, rent_api_rows, rent_targets, False),
    ):
        items = [(rid, api, KEY_METHOD_API) for rid, api in api_rows]
        items += [
            (rid, inf.api_apt_seq, inf.method)
            for rid, inf in infer_keys(known, targets, use_build_year=use_year).items()
        ]
        plan[table] = items
    return plan


def check_invariants(
    before, after, allowed_pnus, audit_before, audit_after
) -> list[str]:
    errors = []
    if before.rows != after.rows:
        errors.append(f"행 수 변화 {before.rows} → {after.rows}")
    if after.unmapped > before.unmapped:
        errors.append(f"미매핑 행 증가 {before.unmapped} → {after.unmapped}")
    changed = {
        p
        for p in set(before.pnu_counts) | set(after.pnu_counts)
        if before.pnu_counts.get(p, 0) != after.pnu_counts.get(p, 0)
    }
    outside = changed - allowed_pnus
    if outside:
        errors.append(f"혼입 키와 무관한 PNU 귀속 변화 {sorted(outside)[:20]}")
    if audit_after > audit_before:
        errors.append(f"감사 위반 증가 {audit_before} → {audit_after}")
    return errors


# ── DB ──


def _db_url(target: str) -> str:
    url = os.getenv("DATABASE_URL" if target == "local" else "RAILWAY_DATABASE_URL")
    if not url:
        raise SystemExit(f"{target} DB URL 미설정 (.env 확인)")
    return url


def _sggs(conn) -> list[str]:
    rows = query_all(
        conn,
        """
        SELECT sgg_cd, SUM(n) AS n FROM (
            SELECT sgg_cd, COUNT(*) n FROM trade_history GROUP BY 1
            UNION ALL SELECT sgg_cd, COUNT(*) FROM rent_history GROUP BY 1) x
        GROUP BY 1 ORDER BY 2""",
    )  # 작은 구부터 — 초반 실패를 싸게 발견
    return [r["sgg_cd"] for r in rows]


def _known(conn, sgg, table, with_year):
    year = "build_year" if with_year else "NULL::int"
    return [
        KnownRow(r["lk"], r["api_apt_seq"], r["by"], r["area"])
        for r in query_all(
            conn,
            f"""
            SELECT COALESCE(legacy_apt_seq, apt_seq) AS lk, api_apt_seq, {year} AS by,
                   exclu_use_ar AS area
            FROM {table} WHERE sgg_cd = %s AND api_apt_seq IS NOT NULL AND btrim(api_apt_seq) <> ''""",
            [sgg],
        )
    ]


def _targets(conn, sgg, table, with_year):
    year = "build_year" if with_year else "NULL::int"
    rows = query_all(
        conn,
        f"""
        SELECT id, apt_seq, api_apt_seq, {year} AS by, exclu_use_ar AS area
        FROM {table} WHERE sgg_cd = %s AND apt_seq_method IS NULL""",
        [sgg],
    )
    # 공백뿐인 aptSeq 는 없는 것으로 본다 (빈 키 금지)
    api_rows = [
        (r["id"], r["api_apt_seq"].strip())
        for r in rows
        if (r["api_apt_seq"] or "").strip()
    ]
    targets = [
        TargetRow(r["id"], r["apt_seq"], r["by"], r["area"])
        for r in rows
        if not (r["api_apt_seq"] or "").strip()
    ]
    return api_rows, targets


def _snapshot(conn, sgg) -> Snapshot:
    rows, pnu_counts, unmapped = {}, Counter(), 0
    for t in TABLES:
        rows[t] = query_all(
            conn, f"SELECT COUNT(*) c FROM {t} WHERE sgg_cd = %s", [sgg]
        )[0]["c"]
        for r in query_all(
            conn,
            f"""
            SELECT m.pnu, COUNT(*) c FROM {t} x LEFT JOIN trade_apt_mapping m ON m.apt_seq = x.apt_seq
            WHERE x.sgg_cd = %s GROUP BY m.pnu""",
            [sgg],
        ):
            if r["pnu"] is None:
                unmapped += r["c"]
            else:
                pnu_counts[r["pnu"]] += r["c"]
    return Snapshot(rows, unmapped, dict(pnu_counts))


def _allowed_pnus(conn, sgg, trade_known, rent_known) -> set[str]:
    """귀속이 바뀌어도 되는 PNU — 혼입 이름 키(고유번호 2개+)의 기존 매핑 대상."""
    ids = {}
    for k in list(trade_known) + list(rent_known):
        ids.setdefault(k.legacy_key, set()).add(k.api_apt_seq)
    mixed = sorted(lk for lk, s in ids.items() if len(s) > 1)
    if not mixed:
        return set()
    return {
        r["pnu"]
        for r in query_all(
            conn, "SELECT pnu FROM trade_apt_mapping WHERE apt_seq = ANY(%s)", [mixed]
        )
    }


def _current_keys(conn, plan) -> list[str]:
    """계획 대상 행들의 현재(변경 전) apt_seq."""
    keys = set()
    for table, items in plan.items():
        if items:
            keys |= {
                r["apt_seq"]
                for r in query_all(
                    conn,
                    f"SELECT DISTINCT apt_seq FROM {table} WHERE id = ANY(%s)",
                    [[rid for rid, _, _ in items]],
                )
            }
    return sorted(keys)


def _apply(conn, table, items):
    psycopg2.extras.execute_values(
        conn.cursor(),
        f"""
        UPDATE {table} t SET legacy_apt_seq = t.apt_seq, apt_seq = v.new_key, apt_seq_method = v.method
        FROM (VALUES %s) AS v(id, new_key, method) WHERE t.id = v.id""",
        items,
        template="(%s::int, %s, %s)",
        page_size=5000,
    )


def _save_checkpoint(conn, sgg, status, detail):
    conn.cursor().execute(
        """
        INSERT INTO common_code (group_id, code, name, extra, sort_order) VALUES (%s, %s, %s, %s, 0)
        ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name, extra = EXCLUDED.extra""",
        [CHECKPOINT_GROUP, sgg, status, json.dumps(detail, ensure_ascii=False)],
    )
    conn.commit()


def _done(conn) -> set[str]:
    return {
        r["code"]
        for r in query_all(
            conn,
            "SELECT code FROM common_code WHERE group_id = %s AND name = ANY(%s)",
            [CHECKPOINT_GROUP, list(SKIP_STATUSES)],
        )
    }


def rekey_sgg(conn, sgg, logger, apply: bool) -> str:
    tk, rk = (
        _known(conn, sgg, "trade_history", True),
        _known(conn, sgg, "rent_history", False),
    )
    t_api, t_tg = _targets(conn, sgg, "trade_history", True)
    r_api, r_tg = _targets(conn, sgg, "rent_history", False)
    plan = plan_sgg(tk, t_api, t_tg, tk + rk, r_api, r_tg)
    counts = {t: dict(Counter(m for _, _, m in items)) for t, items in plan.items()}
    logger.info(f"[{sgg}] 계획 {counts}")
    if not apply:
        return "planned"

    allowed = _allowed_pnus(conn, sgg, tk, rk)
    before = _snapshot(conn, sgg)
    # 같은 행을 변경 전 키로 감사 → 변경 후 키로 감사 (PNU 집합이 달라 생기는 오탐 방지)
    old_keys = _current_keys(conn, plan)
    audit_before = len(audit(conn, logger, apt_seqs=old_keys)) if old_keys else 0
    for table, items in plan.items():
        if items:
            _apply(conn, table, items)
    new_keys = sorted({k for items in plan.values() for _, k, _ in items})
    if new_keys:
        map_api_keys(conn, logger, apt_seqs=new_keys)
        # 상속(api_inherit_legacy)이 아닌 새 매핑은 귀속이 바뀌는 게 정상이다 — 예: 매핑이 없던
        # 상도1동대림이 주소 PNU 로 처음 거래를 갖는다. 혼입 키 기존 PNU 와 함께 허용 목록에 넣는다.
        allowed |= {
            r["pnu"]
            for r in query_all(
                conn,
                """
            SELECT pnu FROM trade_apt_mapping
            WHERE apt_seq = ANY(%s) AND match_method <> 'api_inherit_legacy'""",
                [new_keys],
            )
        }
    after = _snapshot(conn, sgg)
    audit_after = len(audit(conn, logger, apt_seqs=new_keys)) if new_keys else 0
    errors = check_invariants(before, after, allowed, audit_before, audit_after)
    if errors:
        conn.rollback()
        logger.error(f"[{sgg}] 검증 실패 → 롤백: {errors}")
        _save_checkpoint(conn, sgg, "failed", {"errors": errors, "plan": counts})
        return "failed"
    conn.commit()
    _save_checkpoint(conn, sgg, "done", {"plan": counts})
    return "done"


def rollback_sgg(conn, sgg, logger):
    """사후 롤백 — 이 구의 모든 키를 이름 키로 되돌리고 남는 고유번호 매핑을 지운다."""
    for t in TABLES:
        conn.cursor().execute(
            f"""
            UPDATE {t} SET apt_seq = legacy_apt_seq, legacy_apt_seq = NULL, apt_seq_method = NULL
            WHERE sgg_cd = %s AND apt_seq_method IS NOT NULL AND legacy_apt_seq IS NOT NULL""",
            [sgg],
        )
    conn.cursor().execute(
        r"""
        DELETE FROM trade_apt_mapping m WHERE m.sgg_cd = %s AND m.match_method LIKE 'api\_%%'
          AND NOT EXISTS (SELECT 1 FROM trade_history t WHERE t.apt_seq = m.apt_seq)
          AND NOT EXISTS (SELECT 1 FROM rent_history r WHERE r.apt_seq = m.apt_seq)""",
        [sgg],
    )
    conn.commit()
    _save_checkpoint(conn, sgg, "rolled_back", {})
    logger.info(f"[{sgg}] 롤백 완료")


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--target", choices=["local", "railway"], required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    p.add_argument(
        "--sgg", action="append", help="대상 시군구(반복 가능). 생략 시 전체"
    )
    p.add_argument("--limit", type=int, default=0, help="이번 실행 최대 구 수")
    p.add_argument("--vacuum-every", type=int, default=DEFAULT_VACUUM_EVERY)
    args = p.parse_args()
    logger = setup_logger("rekey_trades")

    url = _db_url(args.target)
    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        if not try_trade_write_lock(conn):
            raise SystemExit("거래 배치 실행 중 — 배치 사이 시간에 다시 실행")
        if args.rollback:
            if not args.sgg:
                raise SystemExit("--rollback 은 --sgg 필수")
            for sgg in args.sgg:
                rollback_sgg(conn, sgg, logger)
            return
        if args.sgg:
            todo = args.sgg
        else:
            done = _done(conn)
            todo = [s for s in _sggs(conn) if s not in done]
        if args.limit:
            todo = todo[: args.limit]
        summary = Counter()
        for i, sgg in enumerate(todo, 1):
            summary[rekey_sgg(conn, sgg, logger, apply=args.apply)] += 1
            if args.apply and args.vacuum_every and i % args.vacuum_every == 0:
                vacuum_tables(url, list(TABLES) + ["trade_apt_mapping"], logger)
        if args.apply:
            vacuum_tables(url, list(TABLES) + ["trade_apt_mapping"], logger)
        logger.info(f"완료: {dict(summary)} (대상 {len(todo)}개 구)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
