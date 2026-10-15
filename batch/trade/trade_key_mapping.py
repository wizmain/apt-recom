"""새 키(국토부 고유번호) → PNU 매핑 (설계 4-2).

원칙: 혼입이 증명된 키만 귀속을 바꾸고 나머지는 기존 이름 키의 매핑을 상속한다 —
manual_fix·ADR-011·ADR-014 교정을 잃지 않기 위해서다. 판정 실패 시 아무 단지에나
붙이지 않는다(미매핑으로 남기고 로그 — enrich_new_apartments 가 단지 등록을 시도한다).

순위: 1 상속(이름 키 안 고유번호가 이 키 하나뿐이고 PNU 하나) → 2 주소 PNU → 3 미매핑.
법정동 이름 매칭은 두지 않는다(2026-10-15 제거) — 로컬 검증에서 이름 매칭 28건 중 절반가량이
틀렸고(숫자 지운 정규화 신관주공2 → 주공3, 포함 매칭 엘리시아 → 연동엘리시아), apt_area_type 이
없는 단지(38%)는 물리 게이트로도 판정하지 못했다. 이름 근거만 있는 키는 미매핑으로 둔다.

주소 판정은 키의 **모든** 거래 행으로 한다(대표 행 하나가 아니다) — 행정구역 개편
전후 umd_cd 가 섞인 키가 개편 전 코드로 없는 PNU 를 만들어 미매핑되던 문제(2026-10-14
로컬 적용 28260-138 마전동아). 주소 PNU 는 apartments 에 있는 것이 정확히 하나일 때만 쓴다.

F1 상속은 apartments 에 실존하는 PNU 로 매핑된 이름 키에서만 한다 — 끊긴 매핑(없는 PNU)은 미매핑
이름 키와 같게 취급한다(48123 에일린의뜰: 없는 PNU 상속이 혼입 키의 보이던 행까지 끌어감).
F2 상속이 아닌 판정(2순위 주소)은 넣은 직후 물리 감사(mapping_gate)를 통과해야 남는다 — 위반이면
지워 미매핑으로 둔다(2026-10-14 월계주공1·2 — 한 지번에 두 단지, 한쪽만 apartments 에 있음).

판정(decide_api_keys)은 DB 를 바꾸지 않는 공용 함수다 — map_api_keys(새 키 넣기)와
batch.remap_official_keys(옛 규칙으로 만들어진 기존 'api_%' 매핑 재판정)가 같은 규칙을 쓴다.
"""

from __future__ import annotations

from typing import NamedTuple

import psycopg2.extras

from batch.db import query_all
from batch.trade.mapping_gate import gate_keys, reject_unverified_mappings
from batch.trade.trade_keys import (
    address_choice_warning,
    address_pnu_counts,
    address_rows_by_key,
    most_frequent_value,
    unique_existing_pnu,
)

MATCH_INHERIT_LEGACY = "api_inherit_legacy"
MATCH_ADDRESS_PNU = "api_address_pnu"
WEAK_ADDRESS_LOG_SAMPLE = 50
FROZEN_INHERIT_LOG_SAMPLE = 50


class MappingInput(NamedTuple):
    apt_nm: str
    legacy_pnus: frozenset[str]
    address_pnu: str | None


def decide_mapping(inp: MappingInput) -> tuple[str, str] | None:
    if len(inp.legacy_pnus) == 1:
        return next(iter(inp.legacy_pnus)), MATCH_INHERIT_LEGACY
    if inp.address_pnu:
        return inp.address_pnu, MATCH_ADDRESS_PNU
    return None


def mapping_inputs_by_key(
    rows,
    existing_pnus: set[str],
    legacy_pnus_by_key: dict[str, set[str]],
) -> dict[str, tuple[MappingInput, str]]:
    """키별 decide_mapping 입력과 시군구 — 키의 모든 행(집계 행, n = 행 수)으로 만든다.

    - 주소 PNU: 주소 필드가 있는 행들의 서로 다른 주소 PNU 중 apartments 에 있는 것이
      정확히 하나면 그것, 아니면 None(미매핑).
    - 이름(매핑 행 apt_nm)·시군구: 행 수 기준 최빈값(동률이면 사전순 첫 값).
    """
    names: dict[str, dict[str, int]] = {}
    sggs: dict[str, dict[str, int]] = {}
    for r in rows:
        key, n = r["apt_seq"], int(r.get("n") or 1)
        nm, sgg = r.get("apt_nm") or "", str(r["sgg_cd"])[:5]
        names.setdefault(key, {})[nm] = names.get(key, {}).get(nm, 0) + n
        sggs.setdefault(key, {})[sgg] = sggs.get(key, {}).get(sgg, 0) + n
    addr_by_key = address_rows_by_key(rows)
    out = {}
    for key, name_counts in names.items():
        out[key] = (
            MappingInput(
                apt_nm=most_frequent_value(name_counts),
                legacy_pnus=frozenset(legacy_pnus_by_key.get(key, ())),
                address_pnu=unique_existing_pnu(
                    addr_by_key.get(key, {}), existing_pnus
                ),
            ),
            most_frequent_value(sggs[key]),
        )
    return out


def warn_weak_address_choices(
    logger, counts_by_key: dict[str, dict[str, int]], chosen_by_key: dict[str, str]
) -> list[str]:
    """주소 PNU 매핑 중 근거가 약한 것(소수파 행·다수파와 다른 지번)을 경고한다 — 매핑은 그대로."""
    msgs = [
        m
        for key, pnu in sorted(chosen_by_key.items())
        if (m := address_choice_warning(key, counts_by_key.get(key, {}), pnu))
    ]
    if msgs:
        logger.warning(
            f"  주소 PNU 근거 약함(검토 대상) {len(msgs):,}건 "
            f"(최대 {WEAK_ADDRESS_LOG_SAMPLE}): {msgs[:WEAK_ADDRESS_LOG_SAMPLE]}"
        )
    return msgs


def inheritable_pnus_by_key(
    lks_by_key: dict[str, set[str]],
    ids_by_legacy: dict[str, set[str]],
    legacy_pnu: dict[str, str],
    existing_pnus: set[str],
) -> dict[str, set[str]]:
    """새 키별 상속 후보 PNU — 1순위 판정 입력(decide_mapping 은 후보가 정확히 하나일 때 상속).

    이름 키 L 이 후보를 내는 조건: L 안의 고유번호가 이 키 하나뿐이고, L 의 매핑 PNU 가
    apartments 에 실존한다(F1). 끊긴 매핑은 미매핑 이름 키처럼 후보에서 빠진다.
    """
    return {
        key: {
            legacy_pnu[lk]
            for lk in lks
            if ids_by_legacy.get(lk) == {key} and legacy_pnu.get(lk) in existing_pnus
        }
        for key, lks in lks_by_key.items()
    }


def mixed_legacy_ids(ids_by_legacy: dict[str, set[str]]) -> list[str]:
    """고유번호가 2개 이상 관측된(혼입) 이름 키들에 속한 고유번호."""
    return sorted({i for ids in ids_by_legacy.values() if len(ids) > 1 for i in ids})


# ── DB 래퍼 ──

# 키의 모든 행을 (이름·주소) 단위로 집계해 가져온다 — 대표 행 하나(DISTINCT ON)가 아니다.
# {*_mapping_filter}: 새 매핑(map_api_keys)은 매핑 없는 키만, 재판정(remap_official_keys)은 전부.
# {pending_union}: 재판정 전용 _PENDING_ROWS_SQL.
_KEY_ROWS_SQL = """
    SELECT apt_seq, sgg_cd, apt_nm, umd_cd, land_cd, bonbun, bubun, SUM(n) AS n
    FROM (
        SELECT apt_seq, sgg_cd, apt_nm, umd_cd, land_cd, bonbun, bubun, COUNT(*) AS n
        FROM trade_history t
        WHERE apt_seq_method IS NOT NULL {seq_filter} {trade_mapping_filter}
        GROUP BY 1, 2, 3, 4, 5, 6, 7
        UNION ALL
        SELECT apt_seq, sgg_cd, apt_nm, NULL, NULL, NULL, NULL, COUNT(*)
        FROM rent_history r
        WHERE apt_seq_method IS NOT NULL {seq_filter} {rent_mapping_filter}
        GROUP BY 1, 2, 3
        {pending_union}
    ) u
    GROUP BY 1, 2, 3, 4, 5, 6, 7
    ORDER BY 1
"""
# 재판정 전용: 아직 키 변경 전(apt_seq_method IS NULL)이지만 API 원본 고유번호가 이 키인 과거 행.
# rekey 가 이 행들을 그대로 이 키로 옮기므로(plan_sgg 'api'), 재판정은 그 근거까지 본다 —
# 적재기가 쓴 몇 행만 보면 개편 전 법정동 주소 같은 소수파 근거로 판정한다(28260-138).
_PENDING_ROWS_SQL = """
        UNION ALL
        SELECT btrim(api_apt_seq), sgg_cd, apt_nm, umd_cd, land_cd, bonbun, bubun, COUNT(*)
        FROM trade_history
        WHERE apt_seq_method IS NULL AND btrim(api_apt_seq) = ANY(%(seqs)s)
        GROUP BY 1, 2, 3, 4, 5, 6, 7
        UNION ALL
        SELECT btrim(api_apt_seq), sgg_cd, apt_nm, NULL, NULL, NULL, NULL, COUNT(*)
        FROM rent_history
        WHERE apt_seq_method IS NULL AND btrim(api_apt_seq) = ANY(%(seqs)s)
        GROUP BY 1, 2, 3
"""
_LEGACY_KEYS_SQL = (
    "SELECT DISTINCT apt_seq, legacy_apt_seq FROM trade_history "
    "WHERE apt_seq = ANY(%(s)s) AND legacy_apt_seq IS NOT NULL "
    "UNION SELECT DISTINCT apt_seq, legacy_apt_seq FROM rent_history "
    "WHERE apt_seq = ANY(%(s)s) AND legacy_apt_seq IS NOT NULL"
)
# 키 변경 전 행의 이름 키는 apt_seq 자신이다
_PENDING_LEGACY_KEYS_SQL = (
    " UNION SELECT DISTINCT btrim(api_apt_seq), apt_seq FROM trade_history "
    "WHERE apt_seq_method IS NULL AND btrim(api_apt_seq) = ANY(%(s)s) "
    "UNION SELECT DISTINCT btrim(api_apt_seq), apt_seq FROM rent_history "
    "WHERE apt_seq_method IS NULL AND btrim(api_apt_seq) = ANY(%(s)s)"
)
_UNMAPPED_FILTER = "AND NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = {alias}.apt_seq)"

# 이름 키별 관측된 고유번호(API 원본만) — 상속 조건 "고유번호가 이 키 하나뿐" 판정용
_LEGACY_IDS_SQL = """
    SELECT lk, ARRAY_AGG(DISTINCT api_apt_seq) AS ids FROM (
        SELECT COALESCE(legacy_apt_seq, apt_seq) AS lk, api_apt_seq FROM trade_history
        WHERE api_apt_seq IS NOT NULL
          AND (legacy_apt_seq = ANY(%(lks)s) OR apt_seq = ANY(%(lks)s))
        UNION ALL
        SELECT COALESCE(legacy_apt_seq, apt_seq), api_apt_seq FROM rent_history
        WHERE api_apt_seq IS NOT NULL
          AND (legacy_apt_seq = ANY(%(lks)s) OR apt_seq = ANY(%(lks)s))
    ) x GROUP BY lk
"""


class KeyDecision(NamedTuple):
    """키 하나의 판정 결과 — trade_apt_mapping 한 행의 값. 물리 게이트(F2) 전이다."""

    pnu: str
    match_method: str
    apt_nm: str
    sgg_cd: str


class KeyDecisions(NamedTuple):
    decided: dict[str, KeyDecision]
    unmapped: list[str]  # 판정 근거 없음(상속·주소 모두 실패)
    ids_by_legacy: dict[str, set[str]]


def decide_api_keys(
    conn, logger, apt_seqs: list[str] | None = None, *, only_unmapped: bool = True
) -> KeyDecisions:
    """고유번호 키들의 매핑을 판정한다(F1 상속·주소 PNU) — DB 를 바꾸지 않는다.

    only_unmapped=True: 매핑 없는 키만(map_api_keys). False: 기존 매핑과 무관하게 키의 모든 행으로
    판정하고, 키 변경 전이지만 API 원본 고유번호가 이 키인 과거 행(_PENDING_ROWS_SQL)도 근거에
    넣는다(remap_official_keys 재판정 — apt_seqs 필수). 판정 규칙(decide_mapping)은 같다. 물리 게이트(F2)는 판정 결과를 DB 에 쓴 뒤
    호출부가 돌린다(감사 SQL 이 trade_apt_mapping 을 읽는다).
    """
    if not only_unmapped and not apt_seqs:
        raise ValueError("재판정(only_unmapped=False)은 apt_seqs 필수")
    seq_filter = "AND apt_seq = ANY(%(seqs)s)" if apt_seqs else ""
    params = {"seqs": list(apt_seqs)} if apt_seqs else {}
    rows = query_all(
        conn,
        _KEY_ROWS_SQL.format(
            seq_filter=seq_filter,
            trade_mapping_filter=_UNMAPPED_FILTER.format(alias="t")
            if only_unmapped
            else "",
            rent_mapping_filter=_UNMAPPED_FILTER.format(alias="r")
            if only_unmapped
            else "",
            pending_union="" if only_unmapped else _PENDING_ROWS_SQL,
        ),
        params or None,
    )
    if not rows:
        return KeyDecisions({}, [], {})

    lks_by_key: dict[str, set[str]] = {}
    for r in query_all(
        conn,
        _LEGACY_KEYS_SQL + ("" if only_unmapped else _PENDING_LEGACY_KEYS_SQL),
        {"s": sorted({r["apt_seq"] for r in rows})},
    ):
        lks_by_key.setdefault(r["apt_seq"], set()).add(r["legacy_apt_seq"])
    legacy_keys = sorted(set().union(*lks_by_key.values())) if lks_by_key else []
    ids_by_legacy = (
        {
            r["lk"]: set(r["ids"])
            for r in query_all(conn, _LEGACY_IDS_SQL, {"lks": legacy_keys})
        }
        if legacy_keys
        else {}
    )
    legacy_rows = (
        query_all(
            conn,
            "SELECT m.apt_seq, m.pnu, (a.pnu IS NOT NULL) AS pnu_exists "
            "FROM trade_apt_mapping m LEFT JOIN apartments a ON a.pnu = m.pnu "
            "WHERE m.apt_seq = ANY(%s)",
            [legacy_keys],
        )
        if legacy_keys
        else []
    )
    legacy_pnu = {r["apt_seq"]: r["pnu"] for r in legacy_rows}
    legacy_existing = {r["pnu"] for r in legacy_rows if r["pnu_exists"]}

    addr_values = sorted(
        {p for by_pnu in address_rows_by_key(rows).values() for p in by_pnu}
    )
    existing_pnus = (
        {
            r["pnu"]
            for r in query_all(
                conn, "SELECT pnu FROM apartments WHERE pnu = ANY(%s)", [addr_values]
            )
        }
        if addr_values
        else set()
    )

    inherit_by_key = inheritable_pnus_by_key(
        lks_by_key, ids_by_legacy, legacy_pnu, legacy_existing
    )
    _warn_dangling_legacy(logger, lks_by_key, legacy_pnu, legacy_existing)
    decided: dict[str, KeyDecision] = {}
    unmapped: list[str] = []
    for key, (inp, sgg_cd) in mapping_inputs_by_key(
        rows, existing_pnus, inherit_by_key
    ).items():
        decision = decide_mapping(inp)
        if decision:
            decided[key] = KeyDecision(decision[0], decision[1], inp.apt_nm, sgg_cd)
        else:
            unmapped.append(key)
    warn_weak_address_choices(
        logger,
        address_pnu_counts(rows),
        {k: d.pnu for k, d in decided.items() if d.match_method == MATCH_ADDRESS_PNU},
    )
    return KeyDecisions(decided, unmapped, ids_by_legacy)


def map_api_keys(conn, logger, apt_seqs: list[str] | None = None) -> int:
    """매핑 없는 새 키를 판정해 trade_apt_mapping 에 넣는다. 커밋하지 않는다."""
    kd = decide_api_keys(conn, logger, apt_seqs)
    if not kd.decided and not kd.unmapped:
        return 0
    new_rows = [
        (key, d.pnu, d.apt_nm, d.sgg_cd, d.match_method)
        for key, d in kd.decided.items()
    ]
    unmapped = list(kd.unmapped)

    inserted: list[tuple[str, str]] = []
    if new_rows:
        returned = psycopg2.extras.execute_values(
            conn.cursor(),
            "INSERT INTO trade_apt_mapping (apt_seq, pnu, apt_nm, sgg_cd, match_method) "
            "VALUES %s ON CONFLICT (apt_seq) DO NOTHING RETURNING apt_seq, match_method",
            new_rows,
            fetch=True,
        )
        inserted = [(r[0], r[1]) for r in returned]
    # F2 — 이번에 넣은 비상속 매핑만 물리 감사한다 (상속은 이름 키 귀속 그대로라 대상 아님)
    rejected = {
        v["apt_seq"]
        for v in reject_unverified_mappings(
            conn,
            logger,
            gate_keys(inserted, {MATCH_INHERIT_LEGACY}),
            source="map_api_keys",
        )
    }
    unmapped += sorted(rejected)
    mapped = len(inserted) - len(rejected)
    logger.info(
        f"  고유번호 키 매핑 {mapped:,}건, 미매핑 {len(unmapped):,}건 "
        f"(물리 감사 거부 {len(rejected):,}건 포함)"
    )
    if unmapped:
        logger.warning(f"  미매핑 고유번호 키(최대 50): {unmapped[:50]}")
    _warn_frozen_inherits(conn, logger, kd.ids_by_legacy)
    return mapped


def _warn_dangling_legacy(logger, lks_by_key, legacy_pnu, legacy_existing) -> None:
    """apartments 에 없는 PNU 로 매핑된 이름 키 때문에 상속 후보에서 빠진 새 키를 알린다 (F1)."""
    keys = sorted(
        key
        for key, lks in lks_by_key.items()
        if any(lk in legacy_pnu and legacy_pnu[lk] not in legacy_existing for lk in lks)
    )
    if keys:
        logger.warning(
            f"  끊긴 이름 키 매핑(없는 PNU)은 상속하지 않음 — 해당 새 키 {len(keys):,}건 "
            f"(최대 {FROZEN_INHERIT_LOG_SAMPLE}): {keys[:FROZEN_INHERIT_LOG_SAMPLE]}"
        )


def _warn_frozen_inherits(conn, logger, ids_by_legacy: dict[str, set[str]]) -> None:
    """상속 매핑의 근거(이름 키 안 고유번호가 하나뿐)가 깨진 키를 알린다 — 재매핑하지 않는다.

    상속 당시엔 단일이던 이름 키에 이후 다른 고유번호가 나타나면, 상속한 PNU 가 혼입 시절
    대표 단지일 수 있다. 자동 재귀속은 하지 않는다(audit_mappings 원칙) — 사람 검토 대상으로
    로그만 남긴다 (최종 리뷰 #3). 이번 호출이 다룬 키의 이름 키만 보므로 추가 비용은
    trade_apt_mapping PK 조회 한 번이고, 새 고유번호가 처음 매핑될 때(그 회차) 한 번 경고된다.
    """
    mixed_ids = mixed_legacy_ids(ids_by_legacy)
    if not mixed_ids:
        return
    frozen = [
        r["apt_seq"]
        for r in query_all(
            conn,
            "SELECT apt_seq FROM trade_apt_mapping "
            "WHERE apt_seq = ANY(%s) AND match_method = %s ORDER BY apt_seq",
            [mixed_ids, MATCH_INHERIT_LEGACY],
        )
    ]
    if frozen:
        logger.warning(
            f"  상속 매핑 재검토 필요 — 이름 키가 혼입으로 바뀐 고유번호 키 {len(frozen):,}건 "
            f"(최대 {FROZEN_INHERIT_LOG_SAMPLE}): {frozen[:FROZEN_INHERIT_LOG_SAMPLE]}"
        )
