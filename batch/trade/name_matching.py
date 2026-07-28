"""거래명↔아파트명 매칭 규칙 — 순수 함수만 모은다.

enrich_apartments 에서 분리했다. DB·네트워크에 의존하지 않아야
scripts/tests 의 CI(psycopg2 미설치, DB·네트워크 불요)에서 검증할 수 있다.
여기에 I/O 를 추가하면 그 테스트가 다시 깨진다.

규칙은 크게 셋이다.
  이름 정규화·변형  거래명과 POI/아파트명 표기 차이를 흡수
  이름 유사도       다른 단지에 잘못 붙는 것을 막는 하한
  타임라인·브랜드   준공연도와 거래연도의 물리적 정합성
"""

import re

# 2000년대 이후 런칭된 주요 브랜드 — 1995년 이전 준공 건물에 이 이름이 붙으면
# 매핑 오류(다른 건물에 유명 단지 이름이 덧씌워짐)로 본다.
_MODERN_BRANDS = (
    "자이", "래미안", "푸르지오", "블루밍", "힐스테이트", "e편한세상", "이편한세상",
    "아이파크", "롯데캐슬", "SK뷰", "SK뷰", "더샵", "꿈에그린", "데시앙",
    "스위첸", "해모로", "리슈빌", "한라비발디", "서희스타힐스", "호반베르디움",
    "금호어울림", "현대홈타운", "하이페리온", "에듀포레", "오투그란데",
    "센트라우스", "센트럴파크", "S-클래스", "센텀", "에코포레",
)

_MODERN_BRAND_CUTOFF = "19950101"


def _normalize_name(name: str) -> str:
    """이름 정규화 — 공백/특수문자 제거 후 소문자.

    주의: 숫자는 유지한다. `1단지`/`6단지` 같은 단지 번호가 구분 키이기 때문.
    """
    if not name:
        return ""
    return re.sub(r"[\s\-·()（）,.]", "", name).lower()


# 괄호 별칭 후보의 최소 길이. `세종마루(CB5-3BL)` 처럼 괄호가 별칭이 아니라
# 블록/동 코드인 경우가 있어, 너무 짧은 조각은 오매칭 위험이 커 제외한다.
_MIN_ALIAS_LEN = 3

_PAREN_BLOCK_RE = re.compile(r"[(（]([^)）]*)[)）]")


def _name_variants(apt_nm: str) -> list[str]:
    """거래명에서 검색·조회용 이름 변형을 우선순위대로 생성.

    국토부 거래명은 `세종리첸시아파밀리에H3블록(산울마을6단지)` 처럼 괄호 안에
    실제 단지명(별칭)을 담는 경우가 있다. 이 형태를 그대로 쓰면 Kakao POI
    (`산울마을6단지세종리첸시아파밀리에H3아파트`)와 완전 불일치해 검색이 0건이 되고,
    K-APT 진본 이름 인덱스 조회도 빗나간다.

    반환 순서:
      1) 원본
      2) 괄호 블록을 제거한 본명
      3) 괄호 안 별칭 (짧은 조각은 _MIN_ALIAS_LEN 으로 제외)

    중복과 빈 문자열은 제거한다. 괄호가 없으면 원본 1개만 반환하므로
    기존 동작과 동일하다.
    """
    if not apt_nm:
        return []

    variants = [apt_nm.strip()]

    stripped = _PAREN_BLOCK_RE.sub("", apt_nm).strip()
    if stripped:
        variants.append(stripped)

    for alias in _PAREN_BLOCK_RE.findall(apt_nm):
        alias = alias.strip()
        if len(alias) >= _MIN_ALIAS_LEN:
            variants.append(alias)

    seen: set[str] = set()
    result = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            result.append(v)
    return result


def _has_modern_brand(apt_nm: str) -> bool:
    if not apt_nm:
        return False
    compact = _normalize_name(apt_nm)
    return any(b.lower() in compact for b in _MODERN_BRANDS)


def _brand_year_consistent(apt_nm: str, use_apr_day: str | None) -> bool:
    """브랜드명-준공연도 일관성 체크.

    2000년대 브랜드 이름인데 건축물대장 준공일이 1995년 이전이면 불일치로 판정.
    use_apr_day가 없거나 포맷이 비정상이면 판단 불가(True 반환 — 기존 경로 유지).
    """
    if not _has_modern_brand(apt_nm):
        return True
    if not use_apr_day or not re.match(r"^[12][0-9]{7}$", use_apr_day):
        return True
    return use_apr_day >= _MODERN_BRAND_CUTOFF


def _name_similarity_ratio(trade_nm: str, bld_nm: str) -> float:
    """최장 공통 부분문자열 길이를 짧은 쪽 이름 길이로 나눈 비율 (0.0 ~ 1.0)."""
    a = _normalize_name(trade_nm)
    b = _normalize_name(bld_nm)
    if not a or not b:
        return 1.0  # 판단 불가 → 정상 취급
    if a == b:
        return 1.0
    # 최장 공통 부분문자열 탐색
    longest = 0
    for i in range(len(a)):
        for j in range(i + 1, len(a) + 1):
            if a[i:j] in b and (j - i) > longest:
                longest = j - i
    return longest / min(len(a), len(b))


# 이름 일치 허용 임계값 — 아래면 다른 단지로 판정
_NAME_SIM_THRESHOLD = 0.4


def _names_overlap(trade_nm: str, bld_nm: str) -> bool:
    """거래명과 아파트명이 같은 단지로 볼 만큼 유사한지.

    짧은 이름 기준 공통 부분문자열 비율이 임계값 이상이어야 통과.
    """
    return _name_similarity_ratio(trade_nm, bld_nm) >= _NAME_SIM_THRESHOLD


_BUILD_YEAR_TOLERANCE = 3  # 거래 기재 건축연도와 준공연도 허용 오차


def _timeline_consistent(use_apr_day: str | None,
                         min_deal_year: int | None,
                         median_build_year: int | None) -> bool:
    """apt_seq의 거래·건축 연도와 매칭 대상 아파트 준공일 정합성 검증.

    규칙:
      1) 거래일 < 준공일 → 물리적 불가능 → 오매칭
      2) 거래서 기재 건축연도 vs 준공연도 차이 > 3년 → 오매칭
    판단 불가(값 누락)면 True.
    """
    if not use_apr_day or len(use_apr_day) < 4 or not use_apr_day[:4].isdigit():
        return True
    apt_year = int(use_apr_day[:4])

    # [강] 시간역전
    if min_deal_year is not None and min_deal_year < apt_year:
        return False
    # [중] 거래서 build_year 불일치
    if median_build_year is not None and abs(median_build_year - apt_year) > _BUILD_YEAR_TOLERANCE:
        return False
    return True
