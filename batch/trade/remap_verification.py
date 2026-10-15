"""기존 고유번호 키 매핑 재판정(remap_official_keys) 체크포인트 — 기록 형식과 rekey 쪽 해석 (설계 4-4·4-5).

trade_apt_mapping 에는 생성 시각이 없어 "어느 규칙으로 만들어졌나"를 행에서 알 수 없다. 그래서 재판정
--apply 가 common_code 체크포인트(extra JSON)에 **비상속 판정 대상 키와 그 결과**를 남긴다 — 수백 건 규모라
작고, 실행 시각별로 남아 감사할 수 있다.

rekey 의 F3b 판단(검증된 비상속 매핑의 출발·도착 PNU 를 허용 목록에 넣는다)에서 '이번 실행 이전부터 있던'
비상속 매핑 K 는 다음일 때 검증 후보로 본다:
  (a) 최신 체크포인트의 verified 에 있고 현재 PNU 가 거기 적힌 PNU 와 같다 — 재판정이 현재 규칙·물리
      게이트로 유지/교체한 그 매핑이다.
  (b) 최신 체크포인트의 judged 에 없다 — 재판정 당시 비상속 매핑이 아니었으니, 그 뒤 현재 규칙의
      map_api_keys(게이트 포함)가 만든 것이다(재판정 이후의 쓰기는 #319 이후 코드뿐).
judged 에 있는데 verified 에 없는 키(재판정이 지운 뒤 다시 생긴 키, blocked_delete 로 남긴 키)는 미검증이다.
그 키로 행이 옮겨져 귀속이 바뀌면 rekey 는 그 구를 실패로 남긴다 — rekey 는 이미 키를 바꾼 행을 다시 보지
않으므로 재판정을 다시 돌려도 이미 바뀐 행은 고쳐지지 않고, 아직 바꾸지 않은 구에서만 판정이 달라진다.
후보는 rekey 가 옮긴 전체 행으로 다시 감사해(after_violations) 위반이 없을 때만 검증으로 쓴다 — 재판정의
게이트는 적재 행 몇 개만 본다. 상속 매핑은 대상이 아니다(오늘과 같음).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import NamedTuple

from batch.db import query_all

CHECKPOINT_GROUP = "remap_official_keys_checkpoint"
CHECKPOINT_STATUS = "applied"
FIELD_VERIFIED = "verified_non_inherit_keys"
FIELD_JUDGED = "judged_non_inherit_keys"


class RemapVerification(NamedTuple):
    run_at: str
    verified: Mapping[str, str]  # 키 → 재판정이 확인한 PNU
    judged: frozenset[str]


def verification_from_checkpoint(
    code: str, extra: str | None
) -> RemapVerification | None:
    """체크포인트 한 행 → 판정 집합. 키 목록이 없는 옛 형식이면 None(재판정 다시 필요)."""
    try:
        detail = json.loads(extra or "")
    except ValueError:
        return None
    if FIELD_JUDGED not in detail or not isinstance(detail.get(FIELD_VERIFIED), dict):
        return None  # 키 목록 없음 또는 PNU 없는 옛 형식(목록) — 재판정 다시 필요
    return RemapVerification(
        code, dict(detail[FIELD_VERIFIED]), frozenset(detail[FIELD_JUDGED])
    )


def load_latest(conn) -> RemapVerification | None:
    """가장 최근 성공(--apply) 재판정 체크포인트. code 는 실행 시각(YYYYmmddTHHMMSS±zzzz)이라 정렬 가능."""
    rows = query_all(
        conn,
        "SELECT code, extra FROM common_code WHERE group_id = %s AND name = %s "
        "ORDER BY code DESC LIMIT 1",
        [CHECKPOINT_GROUP, CHECKPOINT_STATUS],
    )
    return (
        verification_from_checkpoint(rows[0]["code"], rows[0]["extra"])
        if rows
        else None
    )


def verified_existing_keys(
    pre_existing: set[str],
    mappings,
    remap: RemapVerification | None,
    inherit_method: str,
) -> set[str]:
    """이번 실행 이전부터 있던 비상속 매핑 중 검증된 키 — (a) 재판정이 유지/교체 (b) 재판정 이후 생성.

    mappings: apt_seq·pnu·match_method 를 가진 현재 매핑 행들. remap 이 없으면 빈 집합(오늘과 같음).
    rekey 는 이 결과에서 변경 후 감사 위반 키를 다시 뺀다(regated_existing_keys).
    """
    if remap is None:
        return set()
    return {
        m["apt_seq"]
        for m in mappings
        if m["apt_seq"] in pre_existing
        and m["match_method"] != inherit_method
        and (
            remap.verified.get(m["apt_seq"]) == m["pnu"]
            or m["apt_seq"] not in remap.judged
        )
    }


def regated_existing_keys(candidates: set[str], after_violations) -> set[str]:
    """검증 후보 중 rekey 가 옮긴 전체 행 감사(after_violations)에 위반이 없는 키."""
    return candidates - {v["apt_seq"] for v in after_violations}
