"""건축물대장(BldRgstHubService) 응답 해석 — 순수 함수만 모은다.

기존 _fetch_building_info 는 실패 경로 5개를 모두 빈 dict 로 뭉갰다.
  요청 실패 / HTTP 오류 / resultCode 에러(쿼터 포함) / item 없음 / 파싱 예외
호출부는 "이 지번에 건물이 없다"와 "쿼터가 소진됐다"를 구분할 수 없었고,
register_missing_apartments 가 쿼터 소진분을 NO_REGISTRY 로 기록해
재시도 대상에서 빠뜨렸다 — 리하우스(LEEHAUS)가 1차에서 그렇게 누락됐다가
2차 실행에서 정상 등록됐다(준공 20111230, 98세대, 10층).

응답 텍스트만 다루므로 DB·네트워크에 의존하지 않는다. 여기에 I/O 를 넣으면
scripts/tests 의 CI 에서 검증할 수 없게 된다.
"""

import xml.etree.ElementTree as ET
from typing import NamedTuple

# data.go.kr 표준 에러 — 일일 트래픽 초과. 키가 살아 있어도 응답이 비므로
# "건물 없음"과 구분하지 못하면 재시도 대상을 영구히 놓친다.
QUOTA_RESULT_CODES = frozenset({"22"})
QUOTA_MSG_KEYWORDS = ("LIMITED_NUMBER_OF_SERVICE_REQUESTS", "REQUESTS_EXCEEDS")

OK = "ok"                # 건물 정보 확보
EMPTY = "empty"          # 응답 정상, 해당 지번에 건물 없음 → NO_REGISTRY
QUOTA = "quota"          # 일일 한도 초과 → 중단하고 다음 날 재시도
API_ERROR = "api_error"  # 그 밖의 resultCode 오류 → 재시도 대상
PARSE_ERROR = "parse_error"
REQUEST_FAILED = "request_failed"  # HTTP·네트워크 실패 → 재시도 대상

# 재시도하면 결과가 달라질 수 있는 상태. EMPTY 만이 확정적 "건물 없음"이다.
RETRYABLE = frozenset({QUOTA, API_ERROR, PARSE_ERROR, REQUEST_FAILED})


class RegistryResponse(NamedTuple):
    """(정보, 상태, 상세). status 가 OK 일 때만 info 에 값이 있다."""

    info: dict
    status: str
    detail: str = ""


def _is_quota(code: str | None, msg: str | None) -> bool:
    if code and code.strip() in QUOTA_RESULT_CODES:
        return True
    upper = (msg or "").upper()
    return any(k in upper for k in QUOTA_MSG_KEYWORDS)


def summarize_items(items: list) -> dict:
    """표제부 item 목록에서 세대수·동수·최고층·준공일을 집계한다.

    준공일은 가장 이른 값을 쓴다 — 증축 동이 섞여도 단지 준공 시점을 잡기 위함.
    """
    total_hhld = 0
    dong_set: set[str] = set()
    max_flr = 0
    use_apr = None

    for item in items:
        hhld = item.findtext("hhldCnt")
        if hhld and hhld.isdigit():
            total_hhld += int(hhld)
        dong = item.findtext("dongNm")
        if dong:
            dong_set.add(dong)
        flr = item.findtext("grndFlrCnt")
        if flr and flr.isdigit():
            max_flr = max(max_flr, int(flr))
        apr = item.findtext("useAprDay")
        if apr and (not use_apr or apr < use_apr):
            use_apr = apr

    return {
        "total_hhld_cnt": total_hhld if total_hhld > 0 else None,
        "dong_count": len(dong_set) if dong_set else None,
        "max_floor": max_flr if max_flr > 0 else None,
        "use_apr_day": use_apr,
    }


def parse_registry_response(xml_text: str) -> RegistryResponse:
    """건축물대장 XML 응답을 (정보, 상태)로 해석한다."""
    try:
        root = ET.fromstring(xml_text or "")
    except ET.ParseError as e:
        return RegistryResponse({}, PARSE_ERROR, str(e))

    code = root.findtext(".//resultCode")
    msg = root.findtext(".//resultMsg")
    if _is_quota(code, msg):
        return RegistryResponse({}, QUOTA, f"{code}: {msg}")
    if code is not None and code.strip() not in ("00", "0"):
        return RegistryResponse({}, API_ERROR, f"{code}: {msg}")

    items = root.findall(".//item")
    if not items:
        return RegistryResponse({}, EMPTY, "표제부 item 없음")

    return RegistryResponse(summarize_items(items), OK)
