"""새 키(국토부 고유번호) → PNU 매핑 (설계 4-2).

원칙: 혼입이 증명된 키만 귀속을 바꾸고 나머지는 기존 이름 키의 매핑을 상속한다 —
manual_fix·ADR-011·ADR-014 교정을 잃지 않기 위해서다. 판정 실패 시 아무 단지에나
붙이지 않는다(미매핑으로 남기고 로그 — enrich_new_apartments 가 단지 등록을 시도한다).

순위: 1 상속(이름 키 안 고유번호가 이 키 하나뿐이고 PNU 하나) → 2 주소 PNU →
3 같은 법정동 이름 매칭(정확·포함·핵심명, 유일할 때만) → 4 미매핑.

주소·법정동 판정은 키의 **모든** 거래 행으로 한다(대표 행 하나가 아니다) — 행정구역 개편
전후 umd_cd 가 섞인 키가 개편 전 코드로 없는 PNU 를 만들어 미매핑되던 문제(2026-10-14
로컬 적용 28260-138 마전동아). 주소 PNU 는 apartments 에 있는 것이 정확히 하나일 때만 쓴다.
"""

from __future__ import annotations

from typing import NamedTuple

import psycopg2.extras

from batch.db import query_all
from batch.trade.recalc_price import _core_name, _normalize_name
from batch.trade.trade_keys import address_rows_by_key, unique_existing_pnu

MIN_CONTAINS_LEN = 3  # recalc_price 포함 매칭과 같은 하한
MATCH_INHERIT_LEGACY = "api_inherit_legacy"
FROZEN_INHERIT_LOG_SAMPLE = 50
MIN_CORE_LEN = 2


class MappingInput(NamedTuple):
    apt_nm: str
    legacy_pnus: frozenset[str]
    address_pnu: str | None
    name_candidates: tuple[tuple[str, str], ...]


def decide_mapping(inp: MappingInput) -> tuple[str, str] | None:
    if len(inp.legacy_pnus) == 1:
        return next(iter(inp.legacy_pnus)), MATCH_INHERIT_LEGACY
    if inp.address_pnu:
        return inp.address_pnu, "api_address_pnu"
    return _match_name(inp.apt_nm, inp.name_candidates)


def _match_name(apt_nm: str, candidates) -> tuple[str, str] | None:
    norm, core = _normalize_name(apt_nm), _core_name(apt_nm)
    cands = [(pnu, _normalize_name(nm), _core_name(nm)) for pnu, nm in candidates]
    # 정확 일치도 유일할 때만 — 같은 법정동 동명 단지 둘이면 고르지 않는다
    # (recalc_price 의 이름 매칭은 첫 후보를 골라 혼입을 만들 수 있다).
    found = [pnu for pnu, c_norm, _ in cands if c_norm and c_norm == norm]
    if len(found) == 1:
        return found[0], "api_name_exact"
    if norm:
        found = [
            pnu
            for pnu, c_norm, _ in cands
            if c_norm
            and len(min(norm, c_norm, key=len)) >= MIN_CONTAINS_LEN
            and (norm in c_norm or c_norm in norm)
        ]
        if len(found) == 1:
            return found[0], "api_name_contains"
    if core and len(core) >= MIN_CORE_LEN:
        found = [pnu for pnu, _, c_core in cands if c_core == core]
        if len(found) == 1:
            return found[0], "api_name_core"
    return None


def most_frequent_value(counts: dict[str, int]) -> str:
    """가장 많이 나온 값. 동률이면 사전순 첫 값(결정적). 비어 있으면 빈 문자열."""
    if not counts:
        return ""
    return min(counts, key=lambda v: (-counts[v], v))


def mapping_inputs_by_key(
    rows,
    existing_pnus: set[str],
    cands_by_bjd: dict[str, list[tuple[str, str]]],
    legacy_pnus_by_key: dict[str, set[str]],
) -> dict[str, tuple[MappingInput, str]]:
    """키별 decide_mapping 입력과 시군구 — 키의 모든 행(집계 행, n = 행 수)으로 만든다.

    - 주소 PNU: 주소 필드가 있는 행들의 서로 다른 주소 PNU 중 apartments 에 있는 것이
      정확히 하나면 그것, 아니면 None(3순위로 넘어간다).
    - 이름 후보: 행들의 서로 다른 법정동(sgg_cd||umd_cd) 후보의 합집합.
    - 이름·시군구: 행 수 기준 최빈값(동률이면 사전순 첫 값).
    """
    names: dict[str, dict[str, int]] = {}
    sggs: dict[str, dict[str, int]] = {}
    bjds: dict[str, set[str]] = {}
    for r in rows:
        key, n = r["apt_seq"], int(r.get("n") or 1)
        nm, sgg = r.get("apt_nm") or "", str(r["sgg_cd"])[:5]
        names.setdefault(key, {})[nm] = names.get(key, {}).get(nm, 0) + n
        sggs.setdefault(key, {})[sgg] = sggs.get(key, {}).get(sgg, 0) + n
        bjds.setdefault(key, set())
        if r.get("umd_cd"):
            bjds[key].add(f"{sgg}{r['umd_cd']}")
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
                name_candidates=tuple(
                    c for bjd in sorted(bjds[key]) for c in cands_by_bjd.get(bjd, ())
                ),
            ),
            most_frequent_value(sggs[key]),
        )
    return out


def mixed_legacy_ids(ids_by_legacy: dict[str, set[str]]) -> list[str]:
    """고유번호가 2개 이상 관측된(혼입) 이름 키들에 속한 고유번호."""
    return sorted({i for ids in ids_by_legacy.values() if len(ids) > 1 for i in ids})


# ── DB 래퍼 ──

# 키의 모든 행을 (이름·주소) 단위로 집계해 가져온다 — 대표 행 하나(DISTINCT ON)가 아니다.
_UNMAPPED_SQL = """
    SELECT apt_seq, sgg_cd, apt_nm, umd_cd, land_cd, bonbun, bubun, SUM(n) AS n
    FROM (
        SELECT apt_seq, sgg_cd, apt_nm, umd_cd, land_cd, bonbun, bubun, COUNT(*) AS n
        FROM trade_history t
        WHERE apt_seq_method IS NOT NULL {seq_filter}
          AND NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = t.apt_seq)
        GROUP BY 1, 2, 3, 4, 5, 6, 7
        UNION ALL
        SELECT apt_seq, sgg_cd, apt_nm, NULL, NULL, NULL, NULL, COUNT(*)
        FROM rent_history r
        WHERE apt_seq_method IS NOT NULL {seq_filter}
          AND NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = r.apt_seq)
        GROUP BY 1, 2, 3
    ) u
    GROUP BY 1, 2, 3, 4, 5, 6, 7
    ORDER BY 1
"""

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


def map_api_keys(conn, logger, apt_seqs: list[str] | None = None) -> int:
    """매핑 없는 새 키를 판정해 trade_apt_mapping 에 넣는다. 커밋하지 않는다."""
    seq_filter = "AND apt_seq = ANY(%(seqs)s)" if apt_seqs else ""
    params = {"seqs": list(apt_seqs)} if apt_seqs else {}
    rows = query_all(conn, _UNMAPPED_SQL.format(seq_filter=seq_filter), params or None)
    if not rows:
        return 0

    lks_by_key: dict[str, set[str]] = {}
    for r in query_all(
        conn,
        "SELECT DISTINCT apt_seq, legacy_apt_seq FROM trade_history "
        "WHERE apt_seq = ANY(%(s)s) AND legacy_apt_seq IS NOT NULL "
        "UNION SELECT DISTINCT apt_seq, legacy_apt_seq FROM rent_history "
        "WHERE apt_seq = ANY(%(s)s) AND legacy_apt_seq IS NOT NULL",
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
    legacy_pnu = (
        {
            r["apt_seq"]: r["pnu"]
            for r in query_all(
                conn,
                "SELECT apt_seq, pnu FROM trade_apt_mapping WHERE apt_seq = ANY(%s)",
                [legacy_keys],
            )
        }
        if legacy_keys
        else {}
    )

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

    bjds = sorted({f"{str(r['sgg_cd'])[:5]}{r['umd_cd']}" for r in rows if r["umd_cd"]})
    cands_by_bjd: dict[str, list[tuple[str, str]]] = {}
    if bjds:
        for a in query_all(
            conn,
            "SELECT pnu, COALESCE(display_name, bld_nm) AS nm, bjd_code FROM apartments "
            "WHERE bjd_code = ANY(%s) AND pnu NOT LIKE 'TRADE%%'",
            [bjds],
        ):
            cands_by_bjd.setdefault(a["bjd_code"], []).append((a["pnu"], a["nm"] or ""))

    inherit_by_key = {
        key: {
            legacy_pnu[lk]
            for lk in lks
            if ids_by_legacy.get(lk) == {key} and lk in legacy_pnu
        }
        for key, lks in lks_by_key.items()
    }
    new_rows, unmapped = [], []
    for key, (inp, sgg_cd) in mapping_inputs_by_key(
        rows, existing_pnus, cands_by_bjd, inherit_by_key
    ).items():
        decision = decide_mapping(inp)
        if decision:
            new_rows.append((key, decision[0], inp.apt_nm, sgg_cd, decision[1]))
        else:
            unmapped.append(key)

    if new_rows:
        psycopg2.extras.execute_values(
            conn.cursor(),
            "INSERT INTO trade_apt_mapping (apt_seq, pnu, apt_nm, sgg_cd, match_method) "
            "VALUES %s ON CONFLICT (apt_seq) DO NOTHING",
            new_rows,
        )
    logger.info(f"  고유번호 키 매핑 {len(new_rows):,}건, 미매핑 {len(unmapped):,}건")
    if unmapped:
        logger.warning(f"  미매핑 고유번호 키(최대 50): {unmapped[:50]}")
    _warn_frozen_inherits(conn, logger, ids_by_legacy)
    return len(new_rows)


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
