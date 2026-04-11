"""시설 데이터 수집 (9종: 병원, CCTV, 편의점, 약국, 대형마트, 동물병원, 가로등, 보안등, 어린이보호구역).

region 옵션으로 수집 지역을 지정:
  - "metro": 수도권 (서울/경기/인천) — 기존 동작
  - "all": 전국 (필터 없이 전체 수집)
  - "부산", "광주" 등: 특정 시도만
"""

import hashlib
import time
import requests
import xml.etree.ElementTree as ET

from batch.config import DATA_GO_KR_API_SECONDARY_KEY, DATA_GO_KR_RATE

# 짧은 이름 → 주소 접두어 매핑 (튜플: 신/구 명칭 모두 매칭)
# 전북: "전북특별자치도" + 구 명칭 "전라북도" 모두 매칭 필요
# 강원: "강원"은 "강원도"/"강원특별자치도" 양쪽 다 매칭되므로 단일값 OK
SIDO_SHORT_TO_PREFIXES = {
    "서울": ("서울",), "부산": ("부산",), "대구": ("대구",), "인천": ("인천",),
    "광주": ("광주",), "대전": ("대전",), "울산": ("울산",), "세종": ("세종",),
    "경기": ("경기",), "강원": ("강원",),
    "충북": ("충청북", "충북"), "충남": ("충청남", "충남"),
    "전북": ("전북", "전라북"), "전남": ("전라남", "전남"),
    "경북": ("경상북", "경북"), "경남": ("경상남", "경남"),
    "제주": ("제주",),
}

NUM_OF_ROWS = 1000


def _get_prefixes(region):
    """region 문자열을 주소 매칭용 접두어 튜플로 변환."""
    if region == "metro":
        return ("서울", "경기", "인천")
    return SIDO_SHORT_TO_PREFIXES.get(region, (region,))


def _fetch_page(api_url, page, extra_params=None):
    params = {
        "serviceKey": DATA_GO_KR_API_SECONDARY_KEY,
        "pageNo": str(page),
        "numOfRows": str(NUM_OF_ROWS),
        "type": "xml",
    }
    if extra_params:
        params.update(extra_params)
    try:
        resp = requests.get(api_url, params=params, timeout=30)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        total = int(root.findtext(".//totalCount") or "0")
        items = []
        for item in root.findall(".//item"):
            row = {child.tag: (child.text or "").strip() for child in item}
            items.append(row)
        return items, total
    except Exception:
        return [], 0


def _collect_via_api(api_url, label, extra_params=None):
    """data.go.kr XML API 페이지네이션 수집."""
    items, total = _fetch_page(api_url, 1, extra_params)
    if total == 0:
        return []
    all_items = list(items)
    total_pages = (total + NUM_OF_ROWS - 1) // NUM_OF_ROWS
    for page in range(2, total_pages + 1):
        page_items, _ = _fetch_page(api_url, page, extra_params)
        all_items.extend(page_items)
        time.sleep(DATA_GO_KR_RATE)
        if page % 10 == 0:
            print(f"  {label}: {page}/{total_pages} pages ({len(all_items):,} rows)")
    return all_items


def _fetch_json_page(api_url, page, per_page=100):
    """JSON API 단일 페이지 호출."""
    try:
        resp = requests.get(api_url, params={
            "serviceKey": DATA_GO_KR_API_KEY,
            "pageNo": str(page),
            "numOfRows": str(per_page),
            "type": "JSON",
        }, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        body = data["response"]["body"]
        total = int(body.get("totalCount", 0))
        items = body.get("items", {}).get("item", [])
        return items, total
    except Exception:
        return [], 0


def _collect_via_json_api(api_url, label, per_page=100):
    """data.go.kr JSON API 페이지네이션 수집."""
    items, total = _fetch_json_page(api_url, 1, per_page)
    if total == 0:
        return []
    all_items = list(items)
    total_pages = (total + per_page - 1) // per_page
    for page in range(2, total_pages + 1):
        page_items, _ = _fetch_json_page(api_url, page, per_page)
        all_items.extend(page_items)
        time.sleep(DATA_GO_KR_RATE)
        if page % 500 == 0:
            print(f"  {label}: {page:,}/{total_pages:,} pages ({len(all_items):,} rows)")
    return all_items


def _filter_region(items, addr_keys=("rdnmadr", "lnmadr"), region="metro"):
    """지역 필터.

    region="metro": 서울/경기/인천 (기존 동작)
    region="all": 필터 스킵 (전국)
    region="부산" 등: 해당 시도만
    """
    if region == "all":
        return items
    prefixes = _get_prefixes(region)
    result = []
    for item in items:
        for key in addr_keys:
            addr = item.get(key, "")
            if any(addr.startswith(p) for p in prefixes):
                result.append(item)
                break
    return result


def _make_facility_id(code_prefix, lat, lng, name):
    """좌표+이름 기반 안정적 facility_id 생성."""
    name_hash = hashlib.md5((name or "").encode()).hexdigest()[:8]
    return f"{code_prefix}_{lat:.4f}_{lng:.4f}_{name_hash}"


def _to_facility_row(item, ftype, fsubtype, code_prefix, idx,
                     name_key="bplcNm", lat_key="latitude", lng_key="longitude",
                     addr_key="rdnmadr"):
    """통일 스키마로 변환."""
    lat = item.get(lat_key, "")
    lng = item.get(lng_key, "")
    try:
        lat_f, lng_f = float(lat), float(lng)
        if not (33 < lat_f < 39 and 124 < lng_f < 132):
            return None
    except (ValueError, TypeError):
        return None

    name = (item.get(name_key, "") or "")[:200]
    fid = _make_facility_id(code_prefix, lat_f, lng_f, name)
    return {
        "facility_id": fid,
        "facility_type": ftype,
        "facility_subtype": fsubtype,
        "name": name,
        "lat": lat_f,
        "lng": lng_f,
        "address": (item.get(addr_key, "") or "")[:300],
    }


def collect_all_facilities(logger, dry_run=False, region="metro"):
    """9종 시설 수집. region으로 수집 지역 지정."""
    all_rows = []

    # 1. 병원
    logger.info("병원 수집 중...")
    try:
        items = _collect_via_api(
            "http://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList",
            "병원", {"sidoCd": ""}
        )
        items = _filter_region(items, ("addr",), region)
        idx = 1
        for item in items:
            row = _to_facility_row(item, "medical", "hospital", "HSP", idx,
                                   name_key="yadmNm", lat_key="YPos", lng_key="XPos", addr_key="addr")
            if row:
                all_rows.append(row)
                idx += 1
        logger.info(f"  병원: {idx - 1:,}건")
    except Exception as e:
        logger.error(f"  병원 수집 실패: {e}")

    # 2. CCTV (행안부 CCTV 통합관제 API — JSON, 페이지당 100건 제한)
    logger.info("CCTV 수집 중...")
    try:
        items = _collect_via_json_api(
            "http://apis.data.go.kr/1741000/cctv_info/info", "CCTV", per_page=100
        )
        items = _filter_region(items, ("LCTN_LOTNO_ADDR", "LCTN_ROAD_NM_ADDR"), region)
        idx = 1
        for item in items:
            row = _to_facility_row(item, "safety", "cctv", "CTV", idx,
                                   name_key="MNG_INST_NM", lat_key="WGS84_LAT",
                                   lng_key="WGS84_LOT", addr_key="LCTN_LOTNO_ADDR")
            if row:
                all_rows.append(row)
                idx += 1
        logger.info(f"  CCTV: {idx - 1:,}건")
    except Exception as e:
        logger.error(f"  CCTV 수집 실패: {e}")

    # 3. 편의점 (소상공인 상가업소)
    logger.info("편의점 수집 중...")
    try:
        items = _collect_via_api(
            "http://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong",
            "편의점", {"indsMclsCd": "Q12"}
        )
        items = _filter_region(items, ("roadNmAddr", "jibunAddr"), region)
        idx = 1
        for item in items:
            row = _to_facility_row(item, "living", "convenience_store", "CVS", idx,
                                   name_key="bizesNm", lat_key="lat", lng_key="lon",
                                   addr_key="roadNmAddr")
            if row:
                all_rows.append(row)
                idx += 1
        logger.info(f"  편의점: {idx - 1:,}건")
    except Exception as e:
        logger.error(f"  편의점 수집 실패: {e}")

    # 4. 약국
    logger.info("약국 수집 중...")
    try:
        items = _collect_via_api(
            "http://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong",
            "약국", {"indsMclsCd": "Q01"}
        )
        items = _filter_region(items, ("roadNmAddr", "jibunAddr"), region)
        idx = 1
        for item in items:
            row = _to_facility_row(item, "living", "pharmacy", "PHR", idx,
                                   name_key="bizesNm", lat_key="lat", lng_key="lon",
                                   addr_key="roadNmAddr")
            if row:
                all_rows.append(row)
                idx += 1
        logger.info(f"  약국: {idx - 1:,}건")
    except Exception as e:
        logger.error(f"  약국 수집 실패: {e}")

    # 5. 대형마트
    logger.info("대형마트 수집 중...")
    try:
        items = _collect_via_api(
            "http://api.data.go.kr/openapi/tn_pubr_public_lrgscl_stlmnt_api", "대형마트"
        )
        items = _filter_region(items, region=region)
        idx = 1
        for item in items:
            row = _to_facility_row(item, "commerce", "mart", "MRT", idx,
                                   name_key="bizplcNm")
            if row:
                all_rows.append(row)
                idx += 1
        logger.info(f"  대형마트: {idx - 1:,}건")
    except Exception as e:
        logger.error(f"  대형마트 수집 실패: {e}")

    # 6. 동물병원
    logger.info("동물병원 수집 중...")
    try:
        items = _collect_via_api(
            "http://apis.data.go.kr/1543061/animalHospService/getAnimalHospList",
            "동물병원"
        )
        items = _filter_region(items, ("roadNmAddr", "jibunAddr"), region)
        idx = 1
        for item in items:
            row = _to_facility_row(item, "medical", "animal_hospital", "AHP", idx,
                                   name_key="bizPlcNm", lat_key="lat", lng_key="lng",
                                   addr_key="roadNmAddr")
            if row:
                all_rows.append(row)
                idx += 1
        logger.info(f"  동물병원: {idx - 1:,}건")
    except Exception as e:
        logger.error(f"  동물병원 수집 실패: {e}")

    # 7. 가로등
    logger.info("가로등 수집 중...")
    try:
        items = _collect_via_api(
            "http://api.data.go.kr/openapi/tn_pubr_public_strplgc_api", "가로등"
        )
        items = _filter_region(items, ("rdnmadr", "lnmadr"), region)
        idx = 1
        for item in items:
            row = _to_facility_row(item, "safety", "streetlight", "STL", idx,
                                   name_key="lgtPrvNm")
            if row:
                all_rows.append(row)
                idx += 1
        logger.info(f"  가로등: {idx - 1:,}건")
    except Exception as e:
        logger.error(f"  가로등 수집 실패: {e}")

    # 8. 보안등
    logger.info("보안등 수집 중...")
    try:
        items = _collect_via_api(
            "http://api.data.go.kr/openapi/tn_pubr_public_securitylamp_api", "보안등"
        )
        items = _filter_region(items, ("rdnmadr", "lnmadr"), region)
        idx = 1
        for item in items:
            row = _to_facility_row(item, "safety", "security_light", "SCL", idx,
                                   name_key="instlPlcNm")
            if row:
                all_rows.append(row)
                idx += 1
        logger.info(f"  보안등: {idx - 1:,}건")
    except Exception as e:
        logger.error(f"  보안등 수집 실패: {e}")

    # 9. 어린이보호구역
    logger.info("어린이보호구역 수집 중...")
    try:
        items = _collect_via_api(
            "http://api.data.go.kr/openapi/tn_pubr_public_child_safety_zone_api", "어린이보호구역"
        )
        items = _filter_region(items, ("rdnmadr", "lnmadr"), region)
        idx = 1
        for item in items:
            row = _to_facility_row(item, "safety", "child_zone", "CZN", idx,
                                   name_key="fcltyNm")
            if row:
                all_rows.append(row)
                idx += 1
        logger.info(f"  어린이보호구역: {idx - 1:,}건")
    except Exception as e:
        logger.error(f"  어린이보호구역 수집 실패: {e}")

    logger.info(f"시설 수집 완료: 총 {len(all_rows):,}건")
    return all_rows
