"""119안전센터 데이터 수집 (data.go.kr API + Kakao 지오코딩).

기존 DB의 소방서/119센터와 주소·이름 비교로 신규 건만 추가.

사용법:
  python -m batch.safety.collect_fire_centers
"""

import re
import time

import requests

from batch.config import DATA_GO_KR_API_KEY, KAKAO_API_KEY, DATA_GO_KR_RATE, KAKAO_RATE
from batch.db import get_connection, get_dict_cursor, query_all
from batch.logger import setup_logger
from batch.safety.load_safety_data import _make_fid

API_URL = "https://api.odcloud.kr/api/15065056/v1/uddi:25763362-233f-4fc1-b738-fc93010f752a"
PER_PAGE = 100
MAX_RETRIES = 3


def _normalize_address(addr: str) -> str:
    """주소 정규화: 공백·특수문자 제거, 비교용."""
    if not addr:
        return ""
    addr = re.sub(r"\s+", "", addr)
    addr = re.sub(r"[(),·]", "", addr)
    return addr


def _normalize_name(name: str) -> str:
    """센터명 정규화: 공백 제거, 비교용."""
    if not name:
        return ""
    return re.sub(r"\s+", "", name)


def fetch_all_centers(api_key: str, logger) -> list[dict]:
    """data.go.kr API에서 119안전센터 전체 목록 조회."""
    all_records = []
    page = 1

    while True:
        params = {"serviceKey": api_key, "page": page, "perPage": PER_PAGE}
        for attempt in range(MAX_RETRIES):
            try:
                r = requests.get(API_URL, params=params, timeout=30)
                r.raise_for_status()
                data = r.json()
                break
            except (requests.RequestException, ValueError) as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    logger.warning(f"  API 오류 (page={page}, retry {attempt+1}): {e}, {wait}초 대기")
                    time.sleep(wait)
                else:
                    logger.error(f"  API 실패 (page={page}): {e}")
                    return all_records

        records = data.get("data", [])
        all_records.extend(records)
        total_count = data.get("totalCount", 0)

        if page == 1:
            logger.info(f"  API 총 건수: {total_count:,}")

        if page * PER_PAGE >= total_count:
            break
        page += 1
        time.sleep(DATA_GO_KR_RATE)

    return all_records


def load_existing_fire_facilities(conn):
    """기존 소방 시설의 주소·이름 set 로드."""
    rows = query_all(conn,
        "SELECT name, address FROM facilities "
        "WHERE facility_subtype IN ('fire_station', 'fire_center') AND is_active = TRUE")

    addr_set = set()
    name_set = set()
    for r in rows:
        addr_set.add(_normalize_address(r["address"]))
        name_set.add(_normalize_name(r["name"]))

    return {"addresses": addr_set, "names": name_set, "count": len(rows)}


def find_new_centers(api_records: list[dict], existing: dict, logger) -> list[dict]:
    """기존 데이터와 비교하여 신규 건만 반환."""
    addr_set = existing["addresses"]
    name_set = existing["names"]
    new_records = []
    matched = 0

    for rec in api_records:
        api_addr = _normalize_address(rec.get("주소", ""))
        center_name = rec.get("119안전센터명", "")
        station_name = rec.get("소방서명", "")
        # 기존 이름 형식: "소방서명-센터명-119 안전센터"
        combined_name = _normalize_name(f"{station_name}-{center_name}-119안전센터")
        short_name = _normalize_name(center_name)

        # 매칭 1: 주소 일치
        if api_addr and api_addr in addr_set:
            matched += 1
            continue

        # 매칭 2: 이름 포함 매칭
        name_matched = False
        for existing_name in name_set:
            if short_name and short_name in existing_name:
                name_matched = True
                break
            if combined_name and combined_name in existing_name:
                name_matched = True
                break
        if name_matched:
            matched += 1
            continue

        new_records.append(rec)

    logger.info(f"  중복 매칭: {matched}건, 신규: {len(new_records)}건")
    return new_records


def geocode_address(headers: dict, address: str, keyword_query: str, logger) -> tuple:
    """Kakao API로 주소 → 좌표 변환. fallback: 키워드 검색."""
    # 1단계: 주소 검색
    if address:
        try:
            r = requests.get(
                "https://dapi.kakao.com/v2/local/search/address.json",
                headers=headers, params={"query": address, "size": 1}, timeout=5)
            docs = r.json().get("documents", [])
            if docs:
                lat, lng = float(docs[0]["y"]), float(docs[0]["x"])
                if 33 < lat < 39 and 124 < lng < 132:
                    return lat, lng
        except Exception:
            pass

    # 2단계: 키워드 검색
    if keyword_query:
        try:
            time.sleep(KAKAO_RATE)
            r = requests.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                headers=headers, params={"query": keyword_query, "size": 1}, timeout=5)
            docs = r.json().get("documents", [])
            if docs:
                lat, lng = float(docs[0]["y"]), float(docs[0]["x"])
                if 33 < lat < 39 and 124 < lng < 132:
                    return lat, lng
        except Exception:
            pass

    return None, None


def collect_fire_centers(conn, logger) -> int:
    """119안전센터 수집 메인 로직."""
    if not DATA_GO_KR_API_KEY:
        logger.error("DATA_GO_KR_API_KEY 미설정")
        return 0
    if not KAKAO_API_KEY:
        logger.error("KAKAO_API_KEY 미설정")
        return 0

    # 1) API 전체 조회
    logger.info("119안전센터 API 조회 시작")
    api_records = fetch_all_centers(DATA_GO_KR_API_KEY, logger)
    if not api_records:
        logger.warning("API 조회 결과 없음")
        return 0
    logger.info(f"  API 조회 완료: {len(api_records):,}건")

    # 2) 기존 데이터 로드 + 신규 필터
    existing = load_existing_fire_facilities(conn)
    logger.info(f"  기존 소방 시설: {existing['count']}건")
    new_records = find_new_centers(api_records, existing, logger)

    if not new_records:
        logger.info("신규 119안전센터 없음 (모두 기존 데이터와 매칭)")
        return 0

    # 3) 신규 건만 지오코딩
    logger.info(f"신규 {len(new_records)}건 지오코딩 시작")
    kakao_headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    rows = []
    geocode_ok = 0
    geocode_fail = 0

    for i, rec in enumerate(new_records):
        address = rec.get("주소", "")
        center_name = rec.get("119안전센터명", "")
        station_name = rec.get("소방서명", "")
        keyword = f"{center_name} 119안전센터" if center_name else f"{station_name} 119안전센터"

        lat, lng = geocode_address(kakao_headers, address, keyword, logger)
        time.sleep(KAKAO_RATE)

        if lat and lng:
            geocode_ok += 1
            name = f"{station_name}-{center_name}-119 안전센터" if center_name else station_name
            fid = _make_fid("FIR", lat, lng, name[:200])
            rows.append((fid, "safety", "fire_center", name[:200], lat, lng, address[:300]))
        else:
            geocode_fail += 1
            if geocode_fail <= 10:
                logger.warning(f"  지오코딩 실패: {center_name} ({address[:40]})")

        if (i + 1) % 50 == 0:
            logger.info(f"  진행: {i+1}/{len(new_records)} (성공={geocode_ok}, 실패={geocode_fail})")

    logger.info(f"  지오코딩 완료: 성공={geocode_ok}, 실패={geocode_fail}")

    # 4) DB INSERT (ON CONFLICT DO NOTHING)
    if rows:
        cur = get_dict_cursor(conn)
        from psycopg2.extras import execute_values
        execute_values(cur,
            "INSERT INTO facilities (facility_id, facility_type, facility_subtype, name, lat, lng, address) "
            "VALUES %s ON CONFLICT (facility_id) DO NOTHING",
            rows, page_size=500)
        conn.commit()
        logger.info(f"119안전센터 적재 완료: {len(rows)}건 INSERT")

    return len(rows)


def main():
    logger = setup_logger("collect_fire_centers")
    conn = get_connection()
    try:
        result = collect_fire_centers(conn, logger)
        logger.info(f"최종 결과: {result}건 추가")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
