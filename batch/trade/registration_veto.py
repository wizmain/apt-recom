"""고유번호 키 신규 등록 거부권 — 같은 법정동의 같은·포함 이름 단지가 있으면 등록하지 않는다.

이름 매칭 순위(3순위)를 뺀 뒤, 주소 PNU 가 apartments 에 없는 고유번호 키는 enrich 가 새 단지로
등록한다. 그런데 그중 상당수는 이미 다른 지번으로 등록된 실제 단지다(2026-10-15 로컬: 이전
api_name_* 28건 중 절반가량) — 그대로 등록하면 중복 단지가 생긴다.

이름은 **거부 근거로만** 쓴다(매핑 근거로는 쓰지 않는다): 후보가 있으면 등록·매핑 모두 하지 않고
모호로 분류해 로그로 남긴다. 사람 검토 후 매핑하거나 등록한다.
"""

from batch.trade.recalc_price import _normalize_name

# recalc_price 포함 매칭과 같은 하한 — 짧은 이름(예: '현대')이 아무 단지에나 포함되는 것을 막는다.
MIN_CONTAINS_NAME_LEN = 3
BJD_CODE_LEN = 10


def names_conflict(key_name: str, apartment_name: str) -> bool:
    """정규화 이름이 같거나, 짧은 쪽이 MIN_CONTAINS_NAME_LEN 이상이면서 한쪽이 다른 쪽을 포함."""
    a, b = _normalize_name(key_name), _normalize_name(apartment_name)
    if not a or not b:
        return False
    if a == b:
        return True
    return len(min(a, b, key=len)) >= MIN_CONTAINS_NAME_LEN and (a in b or b in a)


def duplicate_candidates(
    key_name: str, apartments_in_bjd: list[tuple[str, str]]
) -> list[str]:
    """같은 법정동 단지 (pnu, 이름) 중 이름이 겹치는 것의 PNU (정렬·중복 제거)."""
    return sorted(
        {pnu for pnu, nm in apartments_in_bjd if names_conflict(key_name, nm)}
    )


def veto_registrations(
    register: dict[str, list[str]],
    names: dict[str, str],
    apartments_by_bjd: dict[str, list[tuple[str, str]]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """등록 계획에서 중복 의심 키를 뺀다.

    register: {주소 PNU: [키…]}, names: 키 → 최빈 단지명, apartments_by_bjd: 법정동 → [(pnu, 이름)].
    반환: (남은 등록 계획, {거부된 키: 후보 PNU 목록}). 법정동 = 주소 PNU 앞 10자리.
    """
    kept: dict[str, list[str]] = {}
    vetoed: dict[str, list[str]] = {}
    for pnu, keys in register.items():
        apartments = apartments_by_bjd.get(pnu[:BJD_CODE_LEN], [])
        for key in keys:
            cands = duplicate_candidates(names.get(key, ""), apartments)
            if cands:
                vetoed[key] = cands
            else:
                kept.setdefault(pnu, []).append(key)
    return kept, vetoed
