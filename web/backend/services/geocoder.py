"""Kakao 지오코딩 + PNU 생성 유틸리티.

주소 → Kakao API → lat/lng + b_code → PNU(19자리) 생성.
기존 batch/trade/enrich_apartments.py의 패턴을 web/backend용으로 재구현.
"""

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

KAKAO_API_KEY = os.getenv("KAKAO_API_KEY", "")
KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_RATE = 0.1  # 초당 10건 제한
KAKAO_TIMEOUT = 5
MAX_RETRIES = 2
RETRY_BACKOFFS = [1, 2]


def _kakao_headers() -> dict[str, str]:
    return {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}


def _kakao_get(url: str, params: dict) -> dict | None:
    """Kakao API 호출 with rate limit + retry."""
    headers = _kakao_headers()
    for attempt in range(1 + MAX_RETRIES):
        try:
            time.sleep(KAKAO_RATE)
            resp = requests.get(
                url, headers=headers, params=params, timeout=KAKAO_TIMEOUT
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503):
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFFS[attempt])
                    continue
            return None
        except requests.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFFS[attempt])
                continue
            return None
    return None


def lookup_coord_by_name(
    name: str,
    expected_bjd_code: str | None = None,
    expected_plat_plc: str | None = None,
) -> dict | None:
    """단지명으로 Kakao 키워드 검색 후 **주소 검증**을 거친 좌표를 반환.

    목적:
      - 기존에 등록된 아파트 좌표 보정용.
      - "같은 이름의 다른 지역 아파트"가 엉뚱하게 매칭되는 것을 방지하기 위해
        반드시 bjd_code(10자리) 또는 plat_plc(지번 주소) 일치를 확인한 결과만 반환.

    검증 규칙(둘 중 하나라도 일치하면 유효):
      - expected_bjd_code: 키워드 결과의 주소에서 Kakao address 검색으로 구한 b_code 앞 10자리와 일치
      - expected_plat_plc: 키워드 결과의 address_name과 문자열 일치 (공백/번지 포맷 허용)

    반환: {lat, lng, matched_address, category} 또는 None
    """
    if not KAKAO_API_KEY or not name:
        return None
    if not expected_bjd_code and not expected_plat_plc:
        # 검증 기준 미제공 시 안전상 None 반환 — 정책: 반드시 주소 확인
        logger.warning("lookup_coord_by_name: 주소 검증 기준(bjd_code/plat_plc)이 필요합니다.")
        return None

    data = _kakao_get(KAKAO_KEYWORD_URL, {"query": name, "size": 15})
    if not data:
        return None

    # 아파트 카테고리 우선
    docs = data.get("documents", [])
    apt_docs = [d for d in docs if "아파트" in (d.get("category_name") or "")]
    candidates = apt_docs or docs

    def _norm(s: str | None) -> str:
        return (s or "").replace(" ", "").replace("번지", "")

    name_norm = _norm(name)
    expected_plat_norm = _norm(expected_plat_plc) if expected_plat_plc else None

    for doc in candidates:
        addr_name = doc.get("address_name") or ""
        place_name = doc.get("place_name") or ""
        # 이름 검증: 키워드의 단지명이 place_name에 실질 포함되어야 함
        # (예: "서울숲힐스테이트" 요청에 "힐스테이트서울숲리버" 결과가 통과되지 않도록)
        if name_norm and name_norm not in _norm(place_name):
            continue
        # 주소 검증 (plat_plc 또는 bjd_code)
        addr_match = False
        if expected_plat_norm and expected_plat_norm in _norm(addr_name):
            addr_match = True
        elif expected_bjd_code and addr_name:
            addr_data = _kakao_get(KAKAO_ADDRESS_URL, {"query": addr_name, "size": 1})
            docs2 = (addr_data or {}).get("documents", [])
            if docs2:
                b_code = (docs2[0].get("address") or {}).get("b_code", "")
                if b_code[:10] == expected_bjd_code:
                    addr_match = True
        if addr_match:
            return {
                "lat": float(doc["y"]),
                "lng": float(doc["x"]),
                "matched_address": addr_name,
                "matched_place": place_name,
                "category": doc.get("category_name", ""),
            }

    logger.info(f"lookup_coord_by_name: '{name}' 키워드 결과 {len(candidates)}건 중 이름·주소 모두 일치하는 항목 없음")
    return None


def geocode_address(address: str, name: str = "") -> dict | None:
    """주소 → {lat, lng, pnu, bjd_code, sigungu_code, plat_plc, new_plat_plc} 또는 None.

    3단계:
    1. Kakao keyword search (단지명 + 아파트) → lat/lng + 주소
    2. Kakao address search → b_code + main_no/sub_no/mountain_yn
    3. PNU 조합: sigungu(5) + bjdong(5) + plat_gb(1) + bun(4) + ji(4) = 19자리
    """
    if not KAKAO_API_KEY:
        return None

    lat, lng = None, None
    new_plat, plat = None, None

    # 1단계: 키워드 검색 (단지명 포함)
    query = f"{address} {name} 아파트" if name else address
    data = _kakao_get(KAKAO_KEYWORD_URL, {"query": query, "size": 5})
    if data:
        docs = data.get("documents", [])
        if docs:
            apt_docs = [d for d in docs if "아파트" in (d.get("category_name") or "")]
            doc = apt_docs[0] if apt_docs else docs[0]
            new_plat = doc.get("road_address_name") or None
            plat = doc.get("address_name") or None
            lat = float(doc["y"]) if doc.get("y") else None
            lng = float(doc["x"]) if doc.get("x") else None

    # 키워드 실패 → 주소 검색 fallback
    if not lat:
        data2 = _kakao_get(KAKAO_ADDRESS_URL, {"query": address, "size": 1})
        if data2:
            docs2 = data2.get("documents", [])
            if docs2:
                doc = docs2[0]
                road = doc.get("road_address")
                new_plat = road["address_name"] if road else doc.get("address_name")
                plat = doc.get("address_name") or None
                lat = float(doc["y"]) if doc.get("y") else None
                lng = float(doc["x"]) if doc.get("x") else None

    if not lat or not lng:
        return None

    # 2단계: 주소 → b_code, main_no, sub_no
    resolved_addr = new_plat or plat
    if not resolved_addr:
        return None

    data3 = _kakao_get(KAKAO_ADDRESS_URL, {"query": resolved_addr, "size": 1})
    if not data3:
        return None

    docs3 = data3.get("documents", [])
    if not docs3:
        return None

    addr_info = docs3[0].get("address")
    if not addr_info:
        return None

    b_code = addr_info.get("b_code", "")
    if len(b_code) < 10:
        return None

    main_no = addr_info.get("main_address_no", "0")
    sub_no = addr_info.get("sub_address_no", "0") or "0"
    mountain = addr_info.get("mountain_yn", "N")

    # 3단계: PNU 조합
    sigungu_code = b_code[:5]
    bjdong_code = b_code[5:10]
    plat_gb = "1" if mountain == "Y" else "0"
    bun = str(main_no).zfill(4)
    ji = str(sub_no).zfill(4)
    pnu = sigungu_code + bjdong_code + plat_gb + bun + ji

    return {
        "pnu": pnu,
        "lat": lat,
        "lng": lng,
        "bjd_code": b_code[:10],
        "sigungu_code": sigungu_code,
        "plat_plc": plat,
        "new_plat_plc": new_plat,
    }
