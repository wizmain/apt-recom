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
