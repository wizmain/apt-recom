"""행정구역 코드 정규화 — 신코드를 내부 표준(구코드)으로 변환한다.

배경
  이 시스템의 시군구 코드는 세 역할을 동시에 맡는다. PNU(PK) 앞 5자리,
  통계 조인 키, 외부 API 파라미터. 내부는 구코드 체계로 일관되지만 외부는
  행정구역 개편으로 신코드를 쓰기 시작했다 — Kakao b_code 가 광주 북구를
  29170 이 아닌 12300(전남광주통합특별시)으로 돌려주고, 건축물대장·국토부
  API 는 여전히 구코드에만 응답한다(2026-08 실측).

  원칙: 내부 표준은 구코드로 유지하고, 외부에서 들어오는 코드는 경계에서
  이 모듈로 정규화한다. 신코드 PNU 가 저장되면 같은 단지가 두 정체성으로
  갈라진다. 결정 배경은 docs/adr 참조.

별칭 저장
  common_code group 'sigungu_alias'
    code  = 신코드 (5자리, 또는 재편으로 법정동별 대응이 갈리면 10자리)
    name  = 표준(구) 시군구 코드 5자리
    extra = 근거 (신 행정구역 명칭 등)
  common_code group 'sido_alias'
    code  = 신 시도명 (예: 전남광주통합특별시)
    name  = 표준 시도명 (common_code sigungu 의 extra 와 같은 표기)

  인천 중구+동구 → 제물포구+영종구 같은 재편은 5자리만으로 역방향이
  정해지지 않는다. 법정동 코드는 개편 전후 보존되므로(실측 — 오치동 11500),
  그런 경우 10자리(신시군구+법정동) 항목으로 등록해 법정동 단위로 푼다.

이 모듈은 DB 드라이버를 import 하지 않는다. 순수 변환 함수는 별칭 dict 를
인자로 받아 scripts/tests 의 CI(psycopg2 미설치)에서 검증할 수 있고,
로더는 호출부가 넘긴 커넥션만 쓴다.
"""

from __future__ import annotations

SIGUNGU_ALIAS_GROUP = "sigungu_alias"
SIDO_ALIAS_GROUP = "sido_alias"


def load_aliases(conn) -> dict:
    """common_code 에서 별칭을 읽는다. {"sigungu": {...}, "sido": {...}}"""
    cur = conn.cursor()
    cur.execute(
        "SELECT group_id, code, name FROM common_code WHERE group_id IN (%s, %s)",
        [SIGUNGU_ALIAS_GROUP, SIDO_ALIAS_GROUP],
    )
    out: dict = {"sigungu": {}, "sido": {}}
    for group_id, code, name in cur.fetchall():
        key = "sigungu" if group_id == SIGUNGU_ALIAS_GROUP else "sido"
        out[key][code] = name
    return out


def normalize_sigungu(code: str, aliases: dict, bjdong: str | None = None) -> str:
    """신 시군구 코드를 표준(구)코드로 바꾼다. 별칭이 없으면 그대로 반환한다.

    재편 지역은 10자리(신시군구+법정동) 항목이 5자리보다 우선한다.
    """
    if not code:
        return code
    sgg = aliases.get("sigungu", {})
    if bjdong and len(bjdong) == 5:
        hit = sgg.get(code + bjdong)
        if hit:
            return hit
    return sgg.get(code, code)


def normalize_pnu(pnu: str, aliases: dict) -> str:
    """신코드로 조합된 19자리 PNU 를 표준 코드 기반으로 바꾼다.

    법정동 이하(6~19자리)는 개편 전후 보존되므로 앞 5자리만 치환한다.
    별칭이 없으면 원본을 반환한다 — 이미 표준이거나 미지의 코드다.
    """
    if not pnu or len(pnu) != 19:
        return pnu
    canonical = normalize_sigungu(pnu[:5], aliases, bjdong=pnu[5:10])
    return canonical + pnu[5:] if canonical != pnu[:5] else pnu


def normalize_sido_name(name: str, aliases: dict) -> str:
    """신 시도명을 표준 표기로 바꾼다. 매칭 키 용도 — 저장된 주소 원문은 건드리지 않는다."""
    if not name:
        return name
    return aliases.get("sido", {}).get(name, name)


def is_known_sigungu(code: str, registry: set, aliases: dict) -> bool:
    """레지스트리에도 별칭에도 없는 코드인지 — 새 행정구역 개편의 감지 신호다."""
    if code in registry:
        return True
    return code in aliases.get("sigungu", {})


# 미등록 코드 유입을 감시할 지점. 정상 상태에서는 두 컬럼 모두 레지스트리
# 코드만 담는다 — 수집은 레지스트리를 순회하고, Kakao 유입은 경계에서
# 정규화되기 때문이다. 여기서 미지의 코드가 나타나면 뚫린 경로가 있거나
# 새 행정구역 개편이 시작된 것이다.
_WATCH_SQL = """
SELECT DISTINCT LEFT(pnu, 5) AS code, 'apartments.pnu' AS source
FROM apartments WHERE pnu NOT LIKE 'TRADE%%' AND LENGTH(pnu) = 19
UNION
SELECT DISTINCT sgg_cd, 'trade_apt_mapping.sgg_cd'
FROM trade_apt_mapping WHERE sgg_cd IS NOT NULL
"""


def audit_unknown_codes(conn, logger) -> list[dict]:
    """레지스트리에도 별칭에도 없는 시군구 코드를 찾는다. 데이터는 바꾸지 않는다.

    2026-08 개편(광주·전남 → 12xxx)은 SGG_MISMATCH 808건이 쌓인 뒤에야
    발견됐다. 이 감사가 배치마다 돌면 다음 개편은 첫 유입 시점에 드러난다.
    비용은 DISTINCT 두 번 — 수만 행 테이블이라 무시할 수준이다.
    """
    cur = conn.cursor()
    cur.execute("SELECT code FROM common_code WHERE group_id = 'sigungu'")
    registry = {r[0] for r in cur.fetchall()}
    aliases = load_aliases(conn)

    cur.execute(_WATCH_SQL)
    unknown = [
        {"code": code, "source": source}
        for code, source in cur.fetchall()
        if not is_known_sigungu(code, registry, aliases)
    ]

    if unknown:
        logger.warning(
            f"미등록 시군구 코드 {len(unknown)}건 유입 — 행정구역 개편 가능성. "
            f"scripts/seed_sigungu_aliases.py 로 별칭을 갱신할 것"
        )
        for u in unknown[:10]:
            logger.warning(f"  {u['code']} ({u['source']})")
    else:
        logger.info("지역코드 감사 — 미등록 코드 없음")
    return unknown
