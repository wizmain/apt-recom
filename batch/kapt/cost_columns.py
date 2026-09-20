"""K-APT 관리비 엑셀의 열 이름 정규화.

K-APT 가 게시 자료의 열 이름을 바꾸면 로더(`collect_mgmt_cost`)와 검증기
(`validate_kapt_files`)가 같은 방식으로 따라가야 한다. 한쪽만 고치면 검증은 통과하는데
적재가 합계를 못 읽거나 그 반대가 된다 — 그래서 별칭 표를 이 모듈 한 곳에 둔다.

별칭 해소는 **정식 열이 없을 때만** 발동한다. 정식 열이 있으면 원본을 그대로 쓴다.
"""

from __future__ import annotations

from collections.abc import Iterable

COMMON_COST_TOTAL_COLUMN = "공용관리비계"

# 정식 열 이름 → K-APT 가 같은 값을 다른 이름으로 게시한 사례.
# 2026-09 자료부터 공용관리비 합계 열이 "공용관리비(합계)" 로 게시된다.
COST_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    COMMON_COST_TOTAL_COLUMN: ("공용관리비(합계)",),
}


def resolve_cost_column_aliases(columns: Iterable[str]) -> dict[str, str]:
    """rename 매핑(별칭 → 정식명)을 반환. 정식 열이 이미 있으면 그 항목은 비운다."""
    present = set(columns)
    renames: dict[str, str] = {}
    for canonical, aliases in COST_COLUMN_ALIASES.items():
        if canonical in present:
            continue
        for alias in aliases:
            if alias in present:
                renames[alias] = canonical
                break
    return renames


def normalize_cost_columns(df):
    """관리비 DataFrame 의 별칭 열을 정식 이름으로 바꾼 DataFrame 을 반환."""
    renames = resolve_cost_column_aliases(df.columns)
    return df.rename(columns=renames) if renames else df
