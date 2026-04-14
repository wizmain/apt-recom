"""인구 + 범죄 통계 수집."""

import re
import time
import requests
from batch.config import (
    DATA_GO_KR_API_KEY,
    KOSIS_API_KEY,
    KOSIS_RATE,
    KOSIS_SIDO_CODES,
)


def _latest_yyyymm():
    """최근 완료된 월 YYYYMM 문자열 (이번 달은 미집계이므로 지난달 사용)."""
    from datetime import date
    today = date.today()
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"{y:04d}{m:02d}"


# KOSIS DT_1B04005N 항목 ID (ITM_ID → 테이블 컬럼 매핑)
#   T2: 총인구수, T3: 남자인구수, T4: 여자인구수
_ITM_MAP = {"T2": "total_pop", "T3": "male_pop", "T4": "female_pop"}


def _normalize_age_group(raw):
    """KOSIS `"0 - 4세"` → 프론트 기대 포맷 `"0-4"`로 정규화.

    프론트는 `{age_group}세`로 렌더링하므로 접미 "세"와 공백을 제거해야
    "0-4세" 형태로 표시된다. "계"와 "100+" 같은 특수값은 그대로 유지.
    """
    if not raw:
        return "계"
    s = raw.strip()
    if s in ("계", "100+"):
        return s
    # "0 - 4세", "10 - 14세" → "0-4", "10-14"
    s = s.replace(" ", "").rstrip("세")
    return s or "계"

# KOSIS API 셀 제한(40,000) 회피를 위해 시군구 리스트를 청크로 분할.
# 시군구당 21연령 × 3항목 = 63 셀 → 400 시군구 = 25,200 셀로 안전.
_KOSIS_CELL_LIMIT_CHUNK = 400

# 전국 시군구 코드 캐시 — getMeta 응답은 수 MB 규모이므로 1회만 호출해 재사용
_sigungu_cache = {}


_SIGUNGU_META_RE = re.compile(
    r'\{OBJ_ID:"A"(?:,UP_ITM_ID:"([^"]*)")?[^}]*ITM_ID:"([^"]+)"[^}]*\}'
)


def _fetch_sigungu_codes(kosis_key, logger):
    """KOSIS DT_1B04005N 메타에서 시도→시군구(5자리) 코드 매핑을 로드.

    KOSIS getMeta 응답은 JSON 키가 따옴표로 감싸지지 않은 비표준 형식이므로
    표준 json 파서 대신 정규식으로 (UP_ITM_ID, ITM_ID) 쌍을 추출한다.
    """
    if _sigungu_cache:
        return _sigungu_cache
    logger.info("  시군구 코드 메타 조회 중 (최초 1회)...")
    r = requests.get(
        "https://kosis.kr/openapi/statisticsData.do",
        params={
            "method": "getMeta", "apiKey": kosis_key, "type": "ITM",
            "format": "json", "orgId": "101", "tblId": "DT_1B04005N",
        },
        timeout=90,
    )
    if r.status_code != 200:
        logger.warning(f"  시군구 메타 HTTP {r.status_code}")
        return {}
    for up, code in _SIGUNGU_META_RE.findall(r.text):
        # 시군구 = 5자리 + 부모가 2자리 시도
        if len(code) == 5 and len(up) == 2:
            _sigungu_cache.setdefault(up, []).append(code)
    time.sleep(KOSIS_RATE)
    return _sigungu_cache


def _call_kosis(url, params, retries=1, timeout=60):
    """KOSIS 호출 — 타임아웃 시 1회 재시도."""
    last_exc = None
    for _ in range(retries + 1):
        try:
            return requests.get(url, params=params, timeout=timeout)
        except requests.exceptions.Timeout as e:
            last_exc = e
            time.sleep(KOSIS_RATE)
    raise last_exc


def collect_population(logger, dry_run=False):
    """KOSIS API에서 전국 시군구별 주민등록인구 수집 (연령대·성별).

    - 통계표: DT_1B04005N (행정구역(읍면동)별/5세별 주민등록인구)
    - 시도(C1=2자리) / 시군구(5자리) / 동(10자리) 중 시군구(5자리)만 적재.
    - 항목 T2(총)/T3(남)/T4(여)를 (sigungu_code, age_group) 키로 병합.
    """
    logger.info("인구 데이터 수집 중 (KOSIS, 전국 17개 시도)...")

    KOSIS_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

    KOSIS_KEY = KOSIS_API_KEY or DATA_GO_KR_API_KEY
    if not KOSIS_API_KEY:
        logger.warning("KOSIS_API_KEY 미설정 → DATA_GO_KR_API_KEY 로 fallback")

    period = _latest_yyyymm()
    logger.info(f"  기준월: {period}")

    merged = {}  # (sigungu_code, age_group) → row dict
    sido_counts = {}

    def _ingest(items, sido_name_):
        """응답 items에서 시군구(5자리)만 추출해 merged에 누적."""
        for item in items:
            c1 = item.get("C1", "")
            if len(c1) != 5:
                continue
            col = _ITM_MAP.get(item.get("ITM_ID", ""))
            if not col:
                continue
            try:
                value = int(float(item.get("DT", 0) or 0))
            except (TypeError, ValueError):
                value = 0
            age_group = _normalize_age_group(item.get("C2_NM"))
            key = (c1, age_group)
            if key not in merged:
                merged[key] = {
                    "sigungu_code": c1,
                    "sigungu_name": item.get("C1_NM", ""),
                    "sido_name": sido_name_,
                    "age_group": age_group,
                    "total_pop": 0,
                    "male_pop": 0,
                    "female_pop": 0,
                }
            merged[key][col] = value

    base_params = {
        "method": "getList", "apiKey": KOSIS_KEY,
        "itmId": "T2+T3+T4", "objL2": "ALL",
        "format": "json", "jsonVD": "Y", "prdSe": "M",
        "startPrdDe": period, "endPrdDe": period,
        "orgId": "101", "tblId": "DT_1B04005N",
    }

    def _request_obj(obj_l1_value):
        """단일 objL1 값으로 KOSIS 호출 → list(items) 또는 None."""
        resp = _call_kosis(KOSIS_URL, {**base_params, "objL1": obj_l1_value}, retries=1)
        time.sleep(KOSIS_RATE)
        if resp.status_code != 200:
            return ("http_error", resp.status_code, None)
        data = resp.json()
        if isinstance(data, dict) and data.get("err"):
            return ("api_error", data.get("err"), data.get("errMsg"))
        if not isinstance(data, list):
            return ("invalid", None, None)
        return ("ok", None, data)

    for sido_code, sido_name in KOSIS_SIDO_CODES.items():
        count_before = len(merged)
        try:
            status, err_code, payload = _request_obj(f"{sido_code}*")

            if status == "api_error" and err_code == "31":
                # 40,000셀 초과 → 시군구 코드 리스트로 청크 재시도
                logger.info(f"  {sido_name} 셀 제한 → 시군구 청크 재시도")
                sigungu_map = _fetch_sigungu_codes(KOSIS_KEY, logger)
                codes = sigungu_map.get(sido_code, [])
                if not codes:
                    logger.error(f"  {sido_name} 시군구 코드 없음 (메타 실패)")
                    sido_counts[sido_name] = 0
                    continue
                for i in range(0, len(codes), _KOSIS_CELL_LIMIT_CHUNK):
                    chunk = codes[i:i + _KOSIS_CELL_LIMIT_CHUNK]
                    obj_val = "+".join(chunk)
                    s2, e2, p2 = _request_obj(obj_val)
                    if s2 == "ok":
                        _ingest(p2, sido_name)
                    else:
                        logger.warning(f"  {sido_name} 청크 {i//_KOSIS_CELL_LIMIT_CHUNK+1} 실패: {s2} {e2}")
            elif status == "ok":
                _ingest(payload, sido_name)
            elif status == "api_error":
                logger.error(f"  {sido_name} KOSIS err={err_code} {payload}")
            elif status == "http_error":
                logger.warning(f"  {sido_name} HTTP {err_code}")
            else:
                logger.warning(f"  {sido_name} 응답 형식 비정상")

            added = len(merged) - count_before
            sido_counts[sido_name] = added
            logger.info(f"  {sido_name}: {added:,}건")
        except Exception as e:
            logger.error(f"  {sido_name} 인구 수집 실패: {e}")
            sido_counts[sido_name] = 0

    rows = list(merged.values())
    logger.info(f"인구 수집 완료: {len(rows):,}건 ({len(sido_counts)}개 시도)")
    return rows


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
