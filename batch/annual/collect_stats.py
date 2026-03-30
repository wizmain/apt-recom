"""인구 + 범죄 통계 수집."""

import time
import requests
from batch.config import DATA_GO_KR_API_KEY, KOSIS_RATE


def collect_population(logger, dry_run=False):
    """KOSIS API에서 수도권 시군구별 인구 데이터 수집."""
    logger.info("인구 데이터 수집 중 (KOSIS)...")

    # KOSIS 통계표 ID: 주민등록인구 시군구/성/연령(5세)별
    KOSIS_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    KOSIS_KEY = DATA_GO_KR_API_KEY  # KOSIS도 동일 키 사용 가능한 경우

    # 수도권 시도 코드
    SIDO_CODES = {"11": "서울특별시", "41": "경기도", "28": "인천광역시"}

    all_rows = []
    for sido_code, sido_name in SIDO_CODES.items():
        try:
            params = {
                "method": "getList",
                "apiKey": KOSIS_KEY,
                "itmId": "T20+T21+T22",  # 총인구+남+여
                "objL1": "ALL",
                "objL2": "ALL",
                "format": "json",
                "jsonVD": "Y",
                "prdSe": "M",
                "startPrdDe": "202501",
                "endPrdDe": "202512",
                "orgId": "101",
                "tblId": "DT_1B04005N",
            }
            resp = requests.get(KOSIS_URL, params=params, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data:
                        c1 = item.get("C1", "")
                        if c1.startswith(sido_code):
                            all_rows.append({
                                "sigungu_code": c1[:5],
                                "sigungu_name": item.get("C1_NM", ""),
                                "sido_name": sido_name,
                                "age_group": item.get("C2_NM", "계"),
                                "total_pop": int(float(item.get("DT", 0) or 0)),
                                "male_pop": 0,
                                "female_pop": 0,
                            })
            time.sleep(KOSIS_RATE)
        except Exception as e:
            logger.error(f"  {sido_name} 인구 수집 실패: {e}")

    logger.info(f"인구 수집 완료: {len(all_rows):,}건")
    return all_rows


def collect_crime(logger, dry_run=False):
    """경찰청 5대범죄 데이터 수집."""
    logger.info("범죄 데이터 수집 중...")

    CRIME_URL = "http://api.data.go.kr/openapi/tn_pubr_public_polic_crime_stats_api"
    all_rows = []

    try:
        params = {
            "serviceKey": DATA_GO_KR_API_KEY,
            "pageNo": "1",
            "numOfRows": "500",
            "type": "json",
        }
        resp = requests.get(CRIME_URL, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("response", {}).get("body", {}).get("items", [])
            if isinstance(items, list):
                for item in items:
                    all_rows.append(item)
    except Exception as e:
        logger.error(f"  범죄 데이터 수집 실패: {e}")

    logger.info(f"범죄 수집 완료: {len(all_rows):,}건")
    return all_rows
