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

F3a 귀속 보존 키(옮겨진 행 전부가 이름 키 시절과 같은 PNU 를 가리키는 새 키)는 감사 비교 양쪽에서
뺀다 — 행 단위 귀속이 그대로라 이번 변경이 만든 문제가 아니고, 행 일부만 떼어 감사하면 기존
오매핑(주로 레거시 auto_create)이 새 위반처럼 드러난다. 뺀 위반은 버리지 않고 재매칭 검토 목록으로
로그·체크포인트 detail 에 남긴다. 귀속이 바뀐 키는 전부 계속 감사한다.
F3b 이번 실행에서 만든 비상속 매핑(map_api_keys 의 물리 게이트 통과분)으로 행을 보낸 이름 키들의
기존 PNU(출발 PNU)도 귀속 변화 허용 목록에 넣는다.
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
from batch.trade.trade_key_mapping import MATCH_INHERIT_LEGACY, map_api_keys
from batch.trade.trade_keys import KEY_METHOD_API, try_trade_write_lock

CHECKPOINT_GROUP = "rekey_trades_checkpoint"
TABLES = ("trade_history", "rent_history")
SKIP_STATUSES = (
    "done",
    "failed",
    "rolled_back",
)  # 전체 실행에서 건너뛰는 체크포인트 상태
DEFAULT_VACUUM_EVERY = 20  # 구 N개마다 VACUUM (ANALYZE) — 운영 1GB 캡 bloat 완화
REVERTED_KEY_LOG_SAMPLE = 20
REMATCH_REVIEW_LOG_SAMPLE = 20


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


def rows_to_revert(plan, unmapped_keys: set[str]) -> dict[str, list[int]]:
    """테이블별 되돌릴 행 id — 이번 계획 행 중 새 키가 매핑되지 못한 것만.

    계획에 없는 행(적재기가 쓴 'api' 행 등)은 건드리지 않는다. 되돌린 행은 이름 키 매핑을
    그대로 쓰므로 현상 유지다(혼입이면 혼입 그대로 — Task 10·단지 등록 후 다시 키 변경).
    """
    return {
        table: [rid for rid, key, _ in items if key in unmapped_keys]
        for table, items in plan.items()
    }


def baseline_violation_count(before_violations, moved_old_keys: set[str]) -> int:
    """변경 전 감사 위반 중 아직 옮겨진 행이 남은 이름 키의 것만 센다.

    계획 행이 전부 되돌려진 이름 키는 변경 후 감사(새 키)에 대응하는 행이 없다 — 그 키의
    기존 위반을 기준선에 남기면 새 키의 신규 위반을 가리는 여유가 된다(리뷰 Fix round 1).
    """
    return sum(1 for v in before_violations if v["apt_seq"] in moved_old_keys)


def reverted_key_map(pairs) -> dict[str, list[str]]:
    """(새 키, 이름 키) 쌍 → {새 키: [이름 키…]}. 한 고유번호가 이름 변형 키 여럿에 걸칠 수 있어 목록."""
    out: dict[str, set[str]] = {}
    for new_key, legacy_key in pairs:
        out.setdefault(new_key, set()).add(legacy_key)
    return {k: sorted(v) for k, v in sorted(out.items())}


def created_mapping_pnus(pre_existing_keys: set[str], mappings_after) -> set[str]:
    """이번 실행에서 새로 생긴 비상속 매핑의 PNU — 귀속 변화 허용 목록에 더한다.

    이미 있던 매핑은 제외한다: 실행 전부터 잘못 붙어 있던 매핑이 허용 목록을 넓혀
    엉뚱한 귀속 변화를 검증에서 통과시키지 않게 한다 (최종 리뷰 #1c).
    mappings_after: apt_seq·pnu·match_method 를 가진 행들.
    """
    return {
        m["pnu"]
        for m in mappings_after
        if m["apt_seq"] not in pre_existing_keys
        and m["match_method"] != MATCH_INHERIT_LEGACY
    }


def created_non_inherit_keys(pre_existing_keys: set[str], mappings_after) -> set[str]:
    """이번 실행에서 새로 생긴 비상속 매핑의 키 — map_api_keys 의 물리 게이트(F2)를 통과한 것들."""
    return {
        m["apt_seq"]
        for m in mappings_after
        if m["apt_seq"] not in pre_existing_keys
        and m["match_method"] != MATCH_INHERIT_LEGACY
    }


def preserving_keys(
    moved_pairs: dict[str, set[str]],
    old_pnu: dict[str, str],
    new_pnu: dict[str, str],
) -> set[str]:
    """귀속 보존 새 키 (F3a) — 옮겨진 행의 이름 키가 전부 새 키와 같은 PNU 로 매핑돼 있던 것.

    moved_pairs: {새 키: {옮겨진 행의 이름 키…}}, old_pnu: 이름 키 → 변경 전 PNU,
    new_pnu: 새 키 → 변경 후 PNU. 이름 키가 미매핑이었거나 PNU 가 다르면 보존이 아니다.
    """
    return {
        k
        for k, lks in moved_pairs.items()
        if k in new_pnu and lks and all(old_pnu.get(lk) == new_pnu[k] for lk in lks)
    }


def fully_preserved_old_keys(
    moved_pairs: dict[str, set[str]], preserving: set[str]
) -> set[str]:
    """옮겨진 행이 전부 귀속 보존 새 키로 간 이름 키 — 감사 기준선에서 뺀다 (F3a)."""
    targets: dict[str, set[str]] = {}
    for k, lks in moved_pairs.items():
        for lk in lks:
            targets.setdefault(lk, set()).add(k)
    return {lk for lk, ks in targets.items() if ks <= preserving}


def source_pnus(
    moved_pairs: dict[str, set[str]], old_pnu: dict[str, str], verified_keys: set[str]
) -> set[str]:
    """검증된 비상속 새 키로 행을 보낸 이름 키들의 변경 전 PNU (F3b 허용 목록 추가분)."""
    return {
        old_pnu[lk]
        for k, lks in moved_pairs.items()
        if k in verified_keys
        for lk in lks
        if lk in old_pnu
    }


class AuditComparison(NamedTuple):
    before: int
    after: int
    rematch_review: list[dict]


def compare_audits(
    before_violations,
    after_violations,
    moved_old_keys: set[str],
    preserving: set[str],
    preserved_old: set[str],
    moved_pairs: dict[str, set[str]],
) -> AuditComparison:
    """감사 위반 비교 (F3a) — 귀속 보존 키는 양쪽에서 빼고, 변경 후 위반은 재매칭 검토 목록으로.

    대칭 규칙: 보존 키의 변경 후 위반은 그 키의 이름 키가 전부 기준선에서 빠졌을 때(preserved_old)만
    뺀다. 이름 키가 비보존 키로도 행을 보내 기준선에 남았는데 보존 키 위반만 빼면, 남은 기준선
    위반이 비보존 키의 신규 위반을 가리는 여유가 된다 (리뷰 3a6485a..d4e551c #1).
    """
    excluded = {k for k in preserving if moved_pairs.get(k, set()) <= preserved_old}
    before = baseline_violation_count(before_violations, moved_old_keys - preserved_old)
    after = sum(1 for v in after_violations if v["apt_seq"] not in excluded)
    review = [
        {
            "apt_seq": v["apt_seq"],
            "legacy_keys": sorted(moved_pairs.get(v["apt_seq"], ())),
            "pnu": v.get("pnu"),
            "apt_nm": v.get("apt_nm"),
            "bld_nm": v.get("bld_nm"),
            "match_method": v.get("match_method"),
            "reasons": v.get("reasons", []),
        }
        for v in sorted(after_violations, key=lambda x: x["apt_seq"])
        if v["apt_seq"] in excluded
    ]
    return AuditComparison(before, after, review)


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
            SELECT COALESCE(legacy_apt_seq, apt_seq) AS lk, btrim(api_apt_seq) AS api_apt_seq, {year} AS by,
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


def _mappings(conn, keys: list[str]) -> list[dict]:
    return query_all(
        conn,
        "SELECT apt_seq, pnu, match_method FROM trade_apt_mapping WHERE apt_seq = ANY(%s)",
        [keys],
    )


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


def _key_pairs(conn, table, ids) -> list[tuple[str, str]]:
    return [
        (r["apt_seq"], r["legacy_apt_seq"])
        for r in query_all(
            conn,
            f"SELECT DISTINCT apt_seq, legacy_apt_seq FROM {table} "
            "WHERE id = ANY(%s) AND legacy_apt_seq IS NOT NULL",
            [ids],
        )
    ]


def _moved_pairs(conn, plan, reverted_ids: dict[str, list[int]]) -> dict[str, set[str]]:
    """되돌리지 않은 계획 행들의 {새 키: {변경 전 이름 키…}}."""
    out: dict[str, set[str]] = {}
    for table, items in plan.items():
        skip = set(reverted_ids.get(table, ()))
        ids = [rid for rid, _, _ in items if rid not in skip]
        if ids:
            for new_key, legacy_key in _key_pairs(conn, table, ids):
                out.setdefault(new_key, set()).add(legacy_key)
    return out


def _revert(conn, table, ids):
    """_apply 의 역 — 이름 키로 되돌린다(legacy_apt_seq 는 _apply 가 채운 변경 전 키)."""
    conn.cursor().execute(
        f"""
        UPDATE {table} SET apt_seq = legacy_apt_seq, legacy_apt_seq = NULL, apt_seq_method = NULL
        WHERE id = ANY(%s) AND legacy_apt_seq IS NOT NULL""",
        [ids],
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

    errors, reverted, rematch_review = apply_and_verify(conn, sgg, logger, plan, tk, rk)
    detail = {"plan": counts, "reverted": reverted, "rematch_review": rematch_review}
    if errors:
        conn.rollback()
        logger.error(f"[{sgg}] 검증 실패 → 롤백: {errors}")
        _save_checkpoint(conn, sgg, "failed", {"errors": errors, **detail})
        return "failed"
    conn.commit()
    _save_checkpoint(conn, sgg, "done", detail)
    return "done"


def apply_and_verify(
    conn, sgg, logger, plan, tk, rk
) -> tuple[list[str], dict, list[dict]]:
    """계획 적용 → 새 키 매핑(F1 상속·F2 물리 게이트) → 매핑 못 한 키의 계획 행 되돌림 → 불변식 검사.

    커밋·롤백하지 않는다(호출자 몫). 반환: (불변식 위반 목록, 되돌림 요약, 재매칭 검토 목록).
    """
    allowed = _allowed_pnus(conn, sgg, tk, rk)
    before = _snapshot(conn, sgg)
    # 같은 행을 변경 전 키로 감사 → 변경 후 키로 감사 (PNU 집합이 달라 생기는 오탐 방지)
    old_keys = _current_keys(conn, plan)
    old_pnu = (
        {m["apt_seq"]: m["pnu"] for m in _mappings(conn, old_keys)} if old_keys else {}
    )
    before_violations = audit(conn, logger, apt_seqs=old_keys) if old_keys else []
    for table, items in plan.items():
        if items:
            _apply(conn, table, items)
    new_keys = sorted({k for items in plan.values() for _, k, _ in items})
    reverted = {"keys": 0, "rows": {t: 0 for t in plan}, "map": {}}
    reverted_ids: dict[str, list[int]] = {}
    new_pnu: dict[str, str] = {}
    verified: set[str] = set()
    if new_keys:
        pre_existing = {r["apt_seq"] for r in _mappings(conn, new_keys)}
        map_api_keys(conn, logger, apt_seqs=new_keys)
        mappings_after = _mappings(conn, new_keys)
        new_pnu = {m["apt_seq"]: m["pnu"] for m in mappings_after}
        # 매핑 못 한(물리 게이트 거부 포함) 새 키는 계획 행만 이름 키로 되돌린다 — 현상 유지
        unmapped_keys = set(new_keys) - set(new_pnu)
        if unmapped_keys:
            reverted, reverted_ids = _revert_unmapped(
                conn, sgg, logger, plan, unmapped_keys
            )
            new_keys = [k for k in new_keys if k not in unmapped_keys]
        # 이번에 만든 비상속 매핑은 귀속이 바뀌는 게 정상이다 — 도착 PNU(최종 리뷰 #1c)와
        # 그리로 행을 보낸 이름 키의 출발 PNU(F3b)를 허용 목록에 넣는다.
        allowed |= created_mapping_pnus(pre_existing, mappings_after)
        verified = created_non_inherit_keys(pre_existing, mappings_after)
    # 감사 기준선은 아직 옮겨진 행이 남은 이름 키로 좁힌다 (되돌린 키의 위반은 비교 대상 아님)
    moved_pairs = _moved_pairs(conn, plan, reverted_ids) if new_keys else {}
    moved_old_keys = set().union(*moved_pairs.values()) if moved_pairs else set()
    allowed |= source_pnus(moved_pairs, old_pnu, verified)
    preserving = preserving_keys(moved_pairs, old_pnu, new_pnu)
    after = _snapshot(conn, sgg)
    after_violations = audit(conn, logger, apt_seqs=new_keys) if new_keys else []
    cmp = compare_audits(
        before_violations,
        after_violations,
        moved_old_keys,
        preserving,
        fully_preserved_old_keys(moved_pairs, preserving),
        moved_pairs,
    )
    logger.info(
        f"[{sgg}] 감사 위반 기준선 {cmp.before} (변경 전 전체 {len(before_violations)}) "
        f"→ 변경 후 {cmp.after} (귀속 보존 키 {len(preserving):,}개 제외)"
    )
    if cmp.rematch_review:
        logger.warning(
            f"[{sgg}] 재매칭 검토 대상(귀속 보존 — 기존 오매핑이 드러남) {len(cmp.rematch_review)}건 "
            f"(최대 {REMATCH_REVIEW_LOG_SAMPLE}): "
            f"{[(r['apt_seq'], r['apt_nm'], r['bld_nm']) for r in cmp.rematch_review[:REMATCH_REVIEW_LOG_SAMPLE]]}"
        )
    errors = check_invariants(before, after, allowed, cmp.before, cmp.after)
    return errors, reverted, cmp.rematch_review


def _revert_unmapped(
    conn, sgg, logger, plan, unmapped_keys: set[str]
) -> tuple[dict, dict[str, list[int]]]:
    """반환: (체크포인트용 요약 — 전체 {새 키: [이름 키]} 포함, 테이블별 되돌린 id)."""
    ids_by_table = rows_to_revert(plan, unmapped_keys)
    pairs = []
    for table, ids in ids_by_table.items():
        if ids:
            pairs += _key_pairs(conn, table, ids)
            _revert(conn, table, ids)
    keys = sorted(unmapped_keys)
    rows = {t: len(ids) for t, ids in ids_by_table.items()}
    logger.warning(
        f"[{sgg}] 매핑 못 한 새 키 {len(keys):,}개 — 계획 행 되돌림 {rows} "
        f"(최대 {REVERTED_KEY_LOG_SAMPLE}): {keys[:REVERTED_KEY_LOG_SAMPLE]}"
    )
    return {
        "keys": len(keys),
        "rows": rows,
        "map": reverted_key_map(pairs),
    }, ids_by_table


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
