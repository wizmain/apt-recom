"""V-World 항공영상(정사영상) 이미지 조회 유틸리티.

V-World Image API(`/req/image`, getmap)로 좌표 기준 항공/위성 정사영상을
바이트로 가져온다. 지도 위 오버레이가 아닌 "부가 정보" 성격이므로,
실패 시 예외를 던지지 않고 None 을 반환해 호출측이 이미지 영역을
생략하거나 자체 에러 처리를 하도록 한다 (VWorldImageError 없음).
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

VWORLD_API_KEY = os.getenv("VWORLD_API_KEY", "")

BASE_URL = "https://api.vworld.kr/req/image"
DEFAULT_BASEMAP = "PHOTO_HYBRID"
DEFAULT_ZOOM = 18
DEFAULT_SIZE = "512,384"
DEFAULT_FORMAT = "jpeg"
TIMEOUT = 5


def build_request_params(
    lat: float,
    lng: float,
    *,
    basemap: str = DEFAULT_BASEMAP,
    zoom: int = DEFAULT_ZOOM,
) -> dict[str, str | int]:
    """V-World Image API 요청 파라미터 조립 (네트워크 호출 없음, 테스트 대상 분리).

    center 는 V-World 규격상 "경도,위도"(lng,lat) 순서.
    """
    return {
        "service": "image",
        "request": "getmap",
        "key": VWORLD_API_KEY,
        "format": DEFAULT_FORMAT,
        "basemap": basemap,
        "center": f"{lng},{lat}",
        "crs": "EPSG:4326",
        "zoom": zoom,
        "size": DEFAULT_SIZE,
    }


def fetch_aerial_image(
    lat: float,
    lng: float,
    *,
    basemap: str = DEFAULT_BASEMAP,
    zoom: int = DEFAULT_ZOOM,
) -> bytes | None:
    """좌표 기준 항공영상 바이트를 반환. 실패 시 None.

    실패(None 반환) 조건: V-World 키 미설정, 네트워크 오류/타임아웃,
    HTTP 오류 응답, content-type 이 image/* 가 아닌 응답(예: 에러 XML/JSON).
    이미지는 상세페이지의 부가 정보이므로 예외를 전파하지 않고 경고 로그만
    남긴 뒤 None 을 반환한다 — 호출측(라우터)이 503 등으로 매핑.
    """
    if not VWORLD_API_KEY:
        logger.warning("vworld_image: VWORLD_API_KEY 미설정 — 항공영상 조회 생략")
        return None

    params = build_request_params(lat, lng, basemap=basemap, zoom=zoom)
    try:
        resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT)
    except requests.RequestException as e:
        logger.warning(f"vworld_image: 요청 실패 ({type(e).__name__})")
        return None

    if resp.status_code != 200:
        logger.warning(f"vworld_image: HTTP {resp.status_code} 응답")
        return None

    content_type = resp.headers.get("Content-Type", "")
    if not content_type.startswith("image/"):
        logger.warning(f"vworld_image: 예상치 못한 content-type '{content_type}'")
        return None

    return resp.content
