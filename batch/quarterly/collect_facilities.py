"""시설 데이터 수집 (변동 잦은 6종: 병원, CCTV, 편의점, 약국, 대형마트, 동물병원)."""

import hashlib
import time
import requests
import xml.etree.ElementTree as ET

from batch.config import DATA_GO_KR_API_KEY, DATA_GO_KR_RATE, METRO_SIDO_PREFIXES

NUM_OF_ROWS = 1000


def _fetch_page(api_url, page, extra_params=None):
    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
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
    """data.go.kr API 페이지네이션 수집."""
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


def _filter_metro(items, addr_keys=("rdnmadr", "lnmadr")):
    """수도권 필터 (주소에서 시도 코드 확인)."""
    metro_prefixes = ("서울", "경기", "인천")
    result = []
    for item in items:
        for key in addr_keys:
            addr = item.get(key, "")
            if any(addr.startswith(p) for p in metro_prefixes):
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


def collect_all_facilities(logger, dry_run=False):
    """변동 잦은 6종 시설 수집."""
    all_rows = []

    # 1. 병원
    logger.info("병원 수집 중...")
    try:
        items = _collect_via_api(
            "http://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList",
            "병원", {"sidoCd": ""}
        )
        items = _filter_metro(items, ("addr",))
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

    # 2. CCTV
    logger.info("CCTV 수집 중...")
    try:
        items = _collect_via_api(
            "http://api.data.go.kr/openapi/tn_pubr_public_cctv_api", "CCTV"
        )
        items = _filter_metro(items, ("rdnmadr", "lnmadr"))
        idx = 1
        for item in items:
            row = _to_facility_row(item, "safety", "cctv", "CTV", idx,
                                   name_key="institutionNm")
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
        items = _filter_metro(items, ("roadNmAddr", "jibunAddr"))
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
        items = _filter_metro(items, ("roadNmAddr", "jibunAddr"))
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
        items = _filter_metro(items)
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
        items = _filter_metro(items, ("roadNmAddr", "jibunAddr"))
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
        items = _filter_metro(items, ("rdnmadr", "lnmadr"))
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
        items = _filter_metro(items, ("rdnmadr", "lnmadr"))
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
        items = _filter_metro(items, ("rdnmadr", "lnmadr"))
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
