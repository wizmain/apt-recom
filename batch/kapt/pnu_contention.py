"""같은 PNU 를 두고 K-APT 레코드가 경합할 때의 규칙 (ADR-014). DB 를 쓰지 않는다.

`apt_kapt_info` 는 PNU 당 1건이다. 분양·임대 혼합 단지는 K-APT 단지코드가 따로 있어 같은 PNU 를
두고 다툰다. 임대 레코드가 자리를 차지하면 sale_type·세대수·주택형·관리비가 임대 기준이 되고
추천 모집단에서 단지가 빠진다 — 그래서 **분양·혼합이 임대를 이긴다.**

자리를 내준 레코드는 지우지 않고 `KAPT_<단지코드>` 더미 PNU 로 옮긴다(`companion_records`).
적재(`ingest_full_kapt` Phase C)와 교정 도구(`scripts/swap_kapt_sale_rental`)가 이 규칙을 함께 쓴다.
"""

from __future__ import annotations

import re

DUMMY_PNU_PREFIX = "KAPT_"

# 이름 비교 전에 걷어내는 표기 — 분양/임대 구분자와 관리 단위 접미. **단지 번호는 걷어내지 않는다**
# (1단지와 2단지는 다른 단지다).
_NAME_NOISE_RE = re.compile(
    r"\(분양\)|\(임대\)|임대|분양|아파트|관리사무소|제\d+|\d+차|[\s()\-·,]"
)

KEEP_EXISTING = "keep_existing"
REPLACE = "replace"

# 분양형태별 우선순위 — 큰 쪽이 PNU 를 갖는다. 표에 없는 값(미상·'사택 및 관사 등')은 0 이라
# 어느 쪽도 밀어내지 못하고 밀려나지도 않는다(같은 등급이면 기존 유지).
RENTAL_SALE_TYPE = "임대"
_SALE_TYPE_PRIORITY: dict[str, int] = {"분양": 2, "혼합": 2, RENTAL_SALE_TYPE: 1}
_UNRANKED = 0


def dummy_pnu(kapt_code: str) -> str:
    """실제 PNU 에 붙지 못한 K-APT 레코드의 키."""
    return f"{DUMMY_PNU_PREFIX}{kapt_code}"


def is_dummy_pnu(pnu: str | None) -> bool:
    return bool(pnu) and pnu.startswith(DUMMY_PNU_PREFIX)


def name_core(name: str | None) -> str:
    return _NAME_NOISE_RE.sub("", name or "")


def names_related(a: str | None, b: str | None) -> bool:
    """두 이름의 핵심부가 포함 관계인지 (`신당남산타운(분양)` ↔ `신당남산타운임대`).

    **같은 단지라는 충분조건일 뿐 필요조건이 아니다.** `돈암한신한진아파트` ↔ `동소문한진임대` 는
    같은 단지인데 관계없음으로 나온다(2026-09-20 카카오맵 대조로 확인). 그래서 이 결과가 거짓일 때
    "다른 단지"로 단정하지 않고 사람의 확인을 남긴다 — 세대수 합산 여부가 여기에 걸려 있다.
    """
    ca, cb = name_core(a), name_core(b)
    return bool(ca and cb and (ca in cb or cb in ca))


def _priority(sale_type: str | None) -> int:
    return _SALE_TYPE_PRIORITY.get((sale_type or "").strip(), _UNRANKED)


def resolve_contention(
    existing_sale_type: str | None, incoming_sale_type: str | None
) -> str:
    """PNU 를 이미 가진 레코드와 새로 들어오는 레코드 중 누가 PNU 를 갖는지.

    들어오는 쪽이 **분양·혼합이고 기존이 임대일 때만** 교체한다. 그 외(같은 등급, 어느 한쪽이
    미상)는 기존을 유지한다 — 근거 없이 자리를 바꾸면 매 적재마다 레코드가 뒤집힐 수 있다.
    """
    existing, incoming = _priority(existing_sale_type), _priority(incoming_sale_type)
    if existing == _SALE_TYPE_PRIORITY[RENTAL_SALE_TYPE] and incoming > existing:
        return REPLACE
    return KEEP_EXISTING
