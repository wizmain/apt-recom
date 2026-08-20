"""추천 모집단에서 제외할 단지 유형 정책.

넛지 추천은 "실제로 선택할 수 있는 단지"를 전제한다. 임대전용 단지(K-APT
`sale_type='임대'`)는 매수가 불가능하고 임대차도 자격 요건이 있어 대부분의 사용자에게
실행 가능한 선택지가 아니다.

발단은 2026-08-19·20 인스타 파일럿 검수다. 노원 신혼육아 추천 상위10에 `청년주택
와이엔타워`(270세대·거래 0건)와 `공덕동 크로시티 행복주택`(350세대·거래 0건)이 올라왔다.

**세대수·면적 하한으로는 걸러지지 않는다.** 두 사례가 전용 16~24㎡라 면적 하한에 우연히
걸렸을 뿐이다. 실측(`min_hhld` 100 + `min_smallest_area` 59 통과 모집단 14,917곳):
임대전용 318곳이 두 하한을 모두 통과하고, 그중 294곳은 매매 거래가 0건이다
(수원권선꿈에그린 2,400세대·전용 59.9~85.0 등). 걸러내는 대상이 다른 별개의 가드다.

## K-APT 미보유 단지는 제외하지 않는다
`apt_kapt_info` 커버리지는 전체 41,938곳 중 50.6% 뿐이라, 데이터가 없다는 이유로 제외하면
절반이 사라진다. 분양형태를 "알 수 없음"으로 두고 통과시킨다. 다만 위 가드 통과 모집단
기준으로는 커버리지가 97.2% 라 실제 판정 대상에서는 대부분 값이 존재한다.

## 상가동은 이 가드의 대상이 아니다
같은 검수에서 `풍림아파트 상가`(280세대)도 나왔지만 K-APT 레코드가 없어 분양형태로
판별되지 않는다. 이름 매칭은 오탐이 난다 — `e편한세상가평퍼스트원아파트` 가 '상가'에
걸린다(정상 단지 다수: 동보상가맨션·부민상가빌라 등). 상가동 PNU 가 모단지 세대수를
물려받은 데이터 오류(신현대아파트상가에 1,924세대)라 런타임 필터가 아니라 데이터 교정
대상이며, 별도 작업으로 분리했다.
"""

from database import DictConnection

COMMON_CODE_GROUP = "apt_population_exclude"

# common_code 에 행이 없을 때 쓰는 값. 가드는 조용히 약해지면 안 되므로 기본값도
# "제외하는" 쪽이다 — 시드 전에 배포돼도 임대전용은 걸러진다.
_DEFAULT_EXCLUDED_SALE_TYPES: tuple[str, ...] = ("임대",)

# 모듈 레벨 캐시 (서버 프로세스 내 1회 로드) — scoring.py 와 같은 패턴.
_excluded_sale_types: tuple[str, ...] | None = None


def get_excluded_sale_types() -> tuple[str, ...]:
    """추천 모집단에서 제외할 K-APT 분양형태 목록.

    출처는 common_code(group_id='apt_population_exclude', code='sale_type').
    `name` 에 콤마 구분 문자열로 둔다 (예: '임대' 또는 '임대,사택 및 관사 등').
    """
    global _excluded_sale_types
    if _excluded_sale_types is not None:
        return _excluded_sale_types

    conn = DictConnection()
    rows = conn.execute(
        "SELECT name FROM common_code WHERE group_id = %s AND code = %s",
        [COMMON_CODE_GROUP, "sale_type"],
    ).fetchall()
    conn.close()

    if rows and rows[0]["name"]:
        values = tuple(v.strip() for v in rows[0]["name"].split(",") if v.strip())
        _excluded_sale_types = values or _DEFAULT_EXCLUDED_SALE_TYPES
    else:
        _excluded_sale_types = _DEFAULT_EXCLUDED_SALE_TYPES
    return _excluded_sale_types


def invalidate_cache() -> None:
    """common_code 수정 후 캐시 무효화 (scoring.invalidate_cache 와 같은 용도)."""
    global _excluded_sale_types
    _excluded_sale_types = None


def sale_type_condition(kapt_alias: str = "k") -> tuple[str, list[str]]:
    """제외 조건 SQL 과 파라미터를 반환.

    전제: 호출부가 `LEFT JOIN apt_kapt_info {kapt_alias} ON a.pnu = {kapt_alias}.pnu` 를
    이미 걸어 두었을 것. K-APT 레코드가 없으면(`IS NULL`) 통과시킨다 — 모듈 docstring 참고.
    """
    excluded = get_excluded_sale_types()
    placeholders = ", ".join(["%s"] * len(excluded))
    sql = (
        f"({kapt_alias}.sale_type IS NULL "
        f"OR {kapt_alias}.sale_type NOT IN ({placeholders}))"
    )
    return sql, list(excluded)
