"""신규 거래 아파트 자동 등록 + 건물정보 보충.

거래 배치의 4단계: recalc_price() 이후 실행.
미매핑 apt_seq → Kakao API로 PNU 확보 → 정규 PNU로 등록.
Kakao 검색 실패 시에만 TRADE_ PNU fallback.

검증:
  1. 시군구 일치: PNU 앞 5자리와 거래 sgg_cd 비교
  2. 이름 유사도: 기존 아파트에 매핑 시 거래명과 아파트명 2글자 이상 공통 부분 필요

v2: ThreadPoolExecutor 병렬화 (Phase 1 API / Phase 2 DB 분리)
"""

import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from batch.config import (
    DATA_GO_KR_API_KEY,
    ENRICH_WORKERS,
    KAKAO_API_KEY,
    KAKAO_RATE,
    DATA_GO_KR_RATE,
)
from batch.db import query_all, query_one
from batch.trade.collect_area_info import fetch_area_info, upsert_area_info, ensure_schema as ensure_area_schema

BLD_TITLE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

MAX_RETRIES = 2
RETRY_BACKOFFS = [1, 2]


# 2000년대 이후 런칭된 주요 브랜드 — 1995년 이전 준공 건물에 이 이름이 붙으면
# 매핑 오류(다른 건물에 유명 단지 이름이 덧씌워짐)로 본다.
_MODERN_BRANDS = (
    "자이", "래미안", "푸르지오", "블루밍", "힐스테이트", "e편한세상", "이편한세상",
    "아이파크", "롯데캐슬", "SK뷰", "SK뷰", "더샵", "꿈에그린", "데시앙",
    "스위첸", "해모로", "리슈빌", "한라비발디", "서희스타힐스", "호반베르디움",
    "금호어울림", "현대홈타운", "하이페리온", "에듀포레", "오투그란데",
    "센트라우스", "센트럴파크", "S-클래스", "센텀", "에코포레",
)

_MODERN_BRAND_CUTOFF = "19950101"


def _normalize_name(name: str) -> str:
    """이름 정규화 — 공백/특수문자 제거 후 소문자.

    주의: 숫자는 유지한다. `1단지`/`6단지` 같은 단지 번호가 구분 키이기 때문.
    """
    if not name:
        return ""
    return re.sub(r"[\s\-·()（）,.]", "", name).lower()


def _has_modern_brand(apt_nm: str) -> bool:
    if not apt_nm:
        return False
    compact = _normalize_name(apt_nm)
    return any(b.lower() in compact for b in _MODERN_BRANDS)


def _brand_year_consistent(apt_nm: str, use_apr_day: str | None) -> bool:
    """브랜드명-준공연도 일관성 체크.

    2000년대 브랜드 이름인데 건축물대장 준공일이 1995년 이전이면 불일치로 판정.
    use_apr_day가 없거나 포맷이 비정상이면 판단 불가(True 반환 — 기존 경로 유지).
    """
    if not _has_modern_brand(apt_nm):
        return True
    if not use_apr_day or not re.match(r"^[12][0-9]{7}$", use_apr_day):
        return True
    return use_apr_day >= _MODERN_BRAND_CUTOFF


def _name_similarity_ratio(trade_nm: str, bld_nm: str) -> float:
    """최장 공통 부분문자열 길이를 짧은 쪽 이름 길이로 나눈 비율 (0.0 ~ 1.0)."""
    a = _normalize_name(trade_nm)
    b = _normalize_name(bld_nm)
    if not a or not b:
        return 1.0  # 판단 불가 → 정상 취급
    if a == b:
        return 1.0
    # 최장 공통 부분문자열 탐색
    longest = 0
    for i in range(len(a)):
        for j in range(i + 1, len(a) + 1):
            if a[i:j] in b and (j - i) > longest:
                longest = j - i
    return longest / min(len(a), len(b))


# 이름 일치 허용 임계값 — 아래면 다른 단지로 판정
_NAME_SIM_THRESHOLD = 0.4


def _names_overlap(trade_nm: str, bld_nm: str) -> bool:
    """거래명과 아파트명이 같은 단지로 볼 만큼 유사한지.

    짧은 이름 기준 공통 부분문자열 비율이 임계값 이상이어야 통과.
    """
    return _name_similarity_ratio(trade_nm, bld_nm) >= _NAME_SIM_THRESHOLD


# ── Rate Limiter ──

class RateLimiter:
    """스레드 안전 rate limiter — 최소 간격 보장."""

    def __init__(self, min_interval: float):
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()


# ── API 호출 헬퍼 ──

def _api_get_with_retry(url: str, limiter: RateLimiter, **kwargs) -> requests.Response | None:
    """rate limit + bounded retry가 적용된 requests.get 래퍼.

    retry 대상: 429, 5xx, Timeout, ConnectionError.
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            limiter.wait()
            resp = requests.get(url, **kwargs)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFFS[attempt])
                    continue
            return resp
        except (requests.Timeout, requests.ConnectionError):
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFFS[attempt])
                continue
            return None
    return None


# ── 병렬 워커: API 호출만 수행, DB 접근 없음 ──

def _resolve_one(
    row: dict,
    headers: dict,
    sgg_map: dict,
    existing_pnus: set,
    kakao_limiter: RateLimiter,
    data_go_limiter: RateLimiter,
    known_pnu: str | None = None,
) -> dict:
    """단일 apt_seq에 대해 Kakao + 건축물대장 API 호출. DB 접근 없음.

    known_pnu가 주어지면 PNU 조합 단계를 건너뛰고 좌표/주소만 Kakao로 확보.
    """
    apt_seq = row["apt_seq"]
    sgg_cd = str(row["sgg_cd"])[:5]
    apt_nm = str(row["apt_nm"])
    region = sgg_map.get(sgg_cd, "")

    result = {
        "apt_seq": apt_seq, "sgg_cd": sgg_cd, "apt_nm": apt_nm,
        "pnu": None, "lat": None, "lng": None,
        "new_plat": None, "plat": None,
        "bjd_code": None, "bld_params": None, "bld_info": None,
    }

    # 1. Kakao 키워드 검색
    query = f"{region} {apt_nm} 아파트"
    resp = _api_get_with_retry(
        KAKAO_KEYWORD_URL, kakao_limiter,
        headers=headers, params={"query": query, "size": 5}, timeout=5,
    )
    new_plat, plat, lat, lng = None, None, None, None

    if resp and resp.ok:
        docs = resp.json().get("documents", [])
        if docs:
            apt_docs = [d for d in docs if "아파트" in (d.get("category_name") or "")]
            doc = apt_docs[0] if apt_docs else docs[0]
            new_plat = doc.get("road_address_name") or None
            plat = doc.get("address_name") or None
            lat = float(doc["y"]) if doc.get("y") else None
            lng = float(doc["x"]) if doc.get("x") else None
        else:
            # 키워드 검색 실패 → 주소 검색 fallback
            resp2 = _api_get_with_retry(
                KAKAO_ADDRESS_URL, kakao_limiter,
                headers=headers, params={"query": query, "size": 1}, timeout=5,
            )
            if resp2 and resp2.ok:
                docs2 = resp2.json().get("documents", [])
                if docs2:
                    doc = docs2[0]
                    road = doc.get("road_address")
                    new_plat = road["address_name"] if road else doc.get("address_name")
                    plat = doc.get("address_name") or None
                    lat = float(doc["y"]) if doc.get("y") else None
                    lng = float(doc["x"]) if doc.get("x") else None

    result["lat"] = lat
    result["lng"] = lng
    result["new_plat"] = new_plat
    result["plat"] = plat

    # known_pnu가 있으면 PNU 조합 단계 스킵, bld_params 역산
    if known_pnu:
        result["pnu"] = known_pnu
        result["bjd_code"] = known_pnu[:10]
        bld_params = {
            "sigungu_cd": known_pnu[:5],
            "bjdong_cd": known_pnu[5:10],
            "plat_gb_cd": known_pnu[10],
            "bun": known_pnu[11:15],
            "ji": known_pnu[15:19],
        }
        result["bld_params"] = bld_params
        result["bld_info"] = _fetch_building_info(bld_params, data_go_limiter)
        return result

    address = new_plat or plat
    if not address:
        return result

    # 2. 주소 → 건축물대장 파라미터 (Kakao 주소검색)
    resp3 = _api_get_with_retry(
        KAKAO_ADDRESS_URL, kakao_limiter,
        headers=headers, params={"query": address, "size": 1}, timeout=5,
    )
    if not resp3 or not resp3.ok:
        return result

    docs3 = resp3.json().get("documents", [])
    if not docs3:
        return result

    addr = docs3[0].get("address")
    if not addr:
        return result

    b_code = addr.get("b_code", "")
    if len(b_code) < 10:
        return result

    main_no = addr.get("main_address_no", "0")
    sub_no = addr.get("sub_address_no", "0") or "0"
    mountain = addr.get("mountain_yn", "N")

    bld_params = {
        "sigungu_cd": b_code[:5],
        "bjdong_cd": b_code[5:10],
        "plat_gb_cd": "1" if mountain == "Y" else "0",
        "bun": str(main_no).zfill(4),
        "ji": str(sub_no).zfill(4),
    }

    real_pnu = (
        bld_params["sigungu_cd"]
        + bld_params["bjdong_cd"]
        + bld_params["plat_gb_cd"]
        + bld_params["bun"]
        + bld_params["ji"]
    )

    result["pnu"] = real_pnu
    result["bjd_code"] = bld_params["sigungu_cd"] + bld_params["bjdong_cd"]
    result["bld_params"] = bld_params

    # 3. 기존 PNU가 아닐 때만 건축물대장 API 호출
    if real_pnu not in existing_pnus:
        result["bld_info"] = _fetch_building_info(bld_params, data_go_limiter)

    return result


# ── 건축물대장 조회 ──

def _fetch_building_info(bld_params: dict, limiter: RateLimiter | None = None) -> dict:
    """건축물대장 API로 세대수/동수/최고층/준공일 조회."""
    try:
        params = {
            "serviceKey": DATA_GO_KR_API_KEY,
            "sigunguCd": bld_params["sigungu_cd"],
            "bjdongCd": bld_params["bjdong_cd"],
            "platGbCd": bld_params.get("plat_gb_cd", "0"),
            "bun": bld_params["bun"],
            "ji": bld_params["ji"],
            "numOfRows": "50",
            "pageNo": "1",
        }

        if limiter:
            resp = _api_get_with_retry(BLD_TITLE_URL, limiter, params=params, timeout=10)
            if not resp or not resp.ok:
                return {}
        else:
            resp = requests.get(BLD_TITLE_URL, params=params, timeout=10)
            resp.raise_for_status()
            time.sleep(DATA_GO_KR_RATE)

        root = ET.fromstring(resp.text)
        if root.findtext(".//resultCode") not in ("00", None):
            return {}

        items = root.findall(".//item")
        if not items:
            return {}

        total_hhld = 0
        dong_set = set()
        max_flr = 0
        use_apr = None

        for item in items:
            hhld_str = item.findtext("hhldCnt")
            if hhld_str and hhld_str.isdigit():
                total_hhld += int(hhld_str)
            dong_nm = item.findtext("dongNm")
            if dong_nm:
                dong_set.add(dong_nm)
            flr_str = item.findtext("grndFlrCnt")
            if flr_str and flr_str.isdigit():
                max_flr = max(max_flr, int(flr_str))
            apr = item.findtext("useAprDay")
            if apr and (not use_apr or apr < use_apr):
                use_apr = apr

        return {
            "total_hhld_cnt": total_hhld if total_hhld > 0 else None,
            "dong_count": len(dong_set) if dong_set else None,
            "max_floor": max_flr if max_flr > 0 else None,
            "use_apr_day": use_apr,
        }
    except Exception:
        return {}


# ── 하위 호환용: 기존 _resolve_pnu (다른 모듈에서 사용 시) ──

def _resolve_pnu(headers: dict, sgg_cd: str, apt_nm: str, region: str):
    """Kakao API로 주소 확보 → 19자리 정규 PNU 조합 (레거시 호환)."""
    from batch.fill_addresses import _kakao_keyword_search, _address_to_bld_params

    query = f"{region} {apt_nm} 아파트"
    new_plat, plat, lat, lng = _kakao_keyword_search(headers, query)
    time.sleep(KAKAO_RATE)

    address = new_plat or plat
    if not address:
        return None, lat, lng, new_plat, plat, None, None

    bld_params = _address_to_bld_params(headers, address, apt_nm)
    time.sleep(KAKAO_RATE)

    if not bld_params:
        return None, lat, lng, new_plat, plat, None, None

    real_pnu = (
        bld_params["sigungu_cd"]
        + bld_params["bjdong_cd"]
        + bld_params.get("plat_gb_cd", "0")
        + bld_params["bun"]
        + bld_params["ji"]
    )
    bjd_code = bld_params["sigungu_cd"] + bld_params["bjdong_cd"]

    return real_pnu, lat, lng, new_plat, plat, bjd_code, bld_params


# ── K-APT 타겟 보완 ──

def _enrich_kapt_targeted(conn, logger, new_pnus: list[str]) -> int:
    """신규 아파트에 대해 K-APT 정보 보완.

    ① apt_kapt_info DB에서 PNU 조회 (월 1회 refresh 데이터)
    ② 없으면 → apt_kapt_info DB에서 시군구+이름 검색
    ③ DB에도 없으면 → K-APT API 타겟 호출
    ④ 건축물대장에서 못 채운 세대수/동수/최고층/준공일도 K-APT로 보완
    """
    from batch.kapt.collect_kapt_info import (
        _fetch_kapt_basic,
        _fetch_detail,
        _load_kapt_list,
        _parse_detail_item,
    )
    from batch.trade.recalc_price import _normalize_name, _core_name
    from batch.config import DATA_GO_KR_API_KEY, DATA_GO_KR_RATE

    if not DATA_GO_KR_API_KEY or not new_pnus:
        return 0

    cur = conn.cursor()

    # ① DB에서 이미 있는 PNU 확인
    ph = ",".join(["%s"] * len(new_pnus))
    existing_kapt = set(
        r["pnu"] for r in query_all(conn,
            f"SELECT pnu FROM apt_kapt_info WHERE pnu IN ({ph})", new_pnus)
    )

    # 이미 kapt_info가 있는 건: apartments 빈 값만 보완
    for pnu in existing_kapt:
        kapt = query_one(conn,
            "SELECT * FROM apt_kapt_info WHERE pnu = %s", [pnu])
        if not kapt:
            continue
        _fill_apartments_from_kapt_basic(cur, pnu, {
            "hoCnt": kapt.get("total_hhld_cnt") or 0,
            "kaptDongCnt": kapt.get("dong_count") or 0,
            "ktownFlrNo": kapt.get("max_floor") or 0,
        })

    need_kapt = [p for p in new_pnus if p not in existing_kapt]
    if not need_kapt:
        conn.commit()
        return 0

    logger.info(f"  K-APT 타겟 매칭 시작 ({len(need_kapt)}건)")

    # 신규 아파트 정보 조회
    ph2 = ",".join(["%s"] * len(need_kapt))
    new_apts = query_all(conn,
        f"SELECT pnu, bld_nm, sigungu_code FROM apartments WHERE pnu IN ({ph2})",
        need_kapt)

    matched = 0
    api_fallback = 0

    for apt in new_apts:
        norm = _normalize_name(apt["bld_nm"])
        core = _core_name(apt["bld_nm"])
        sgg = (apt["sigungu_code"] or "")[:5]
        kapt_code = None
        kapt_name_val = None

        # ② apt_kapt_info DB에서 시군구+이름 검색
        db_matches = query_all(conn,
            "SELECT kapt_code, kapt_name FROM apt_kapt_info "
            "WHERE sigungu_code = %s AND kapt_name IS NOT NULL",
            [sgg])

        for row in db_matches:
            if _normalize_name(row["kapt_name"]) == norm:
                kapt_code = row["kapt_code"]
                kapt_name_val = row["kapt_name"]
                break

        if not kapt_code and core and len(core) >= 2:
            for row in db_matches:
                if _core_name(row["kapt_name"]) == core:
                    kapt_code = row["kapt_code"]
                    kapt_name_val = row["kapt_name"]
                    break

        # ③ DB에도 없으면 → K-APT 목록 API로 매칭
        if not kapt_code:
            if api_fallback == 0:
                kapt_list = _load_kapt_list()
                kapt_api_index: dict[tuple[str, str], dict] = {}
                for item in kapt_list:
                    kname = _normalize_name(item.get("kaptName", ""))
                    bjd = item.get("bjdCode") or ""
                    k_sgg = bjd[:5] if len(bjd) >= 5 else ""
                    if kname and k_sgg:
                        key = (kname, k_sgg)
                        if key not in kapt_api_index:
                            kapt_api_index[key] = item
                logger.info(f"  K-APT API 목록 로드: {len(kapt_list)}건")

            api_match = kapt_api_index.get((norm, sgg))
            if not api_match and core and len(core) >= 2:
                for (k_name, k_sgg), item in kapt_api_index.items():
                    if k_sgg == sgg and _core_name(k_name) == core:
                        api_match = item
                        break

            if api_match:
                kapt_code = api_match["kaptCode"]
                kapt_name_val = api_match.get("kaptName", "")
            api_fallback += 1

        if not kapt_code:
            continue

        # K-APT 기본정보 → apartments 빈 값 보완
        basic = _fetch_kapt_basic(kapt_code)
        time.sleep(DATA_GO_KR_RATE)

        if basic:
            _fill_apartments_from_kapt_basic(cur, apt["pnu"], basic)
            if not kapt_name_val:
                kapt_name_val = basic.get("kaptName", "")

        # K-APT 상세정보 → apt_kapt_info INSERT
        detail_item = _fetch_detail(kapt_code)
        time.sleep(DATA_GO_KR_RATE)

        vals = _parse_detail_item(detail_item) if detail_item else {}

        cur.execute("""
            INSERT INTO apt_kapt_info (pnu, kapt_code, kapt_name, sigungu_code,
                sale_type, heat_type, builder, developer,
                apt_type, mgr_type, hall_type, structure, total_area, priv_area,
                parking_cnt, cctv_cnt, elevator_cnt, ev_charger_cnt, subway_info, bus_time, welfare)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (pnu) DO UPDATE SET
                kapt_code=EXCLUDED.kapt_code,
                kapt_name=COALESCE(EXCLUDED.kapt_name, apt_kapt_info.kapt_name),
                sigungu_code=COALESCE(EXCLUDED.sigungu_code, apt_kapt_info.sigungu_code),
                parking_cnt=EXCLUDED.parking_cnt,
                cctv_cnt=EXCLUDED.cctv_cnt, ev_charger_cnt=EXCLUDED.ev_charger_cnt,
                structure=EXCLUDED.structure, updated_at=NOW()
        """, [
            apt["pnu"], kapt_code, kapt_name_val, sgg,
            basic.get("codeSaleNm", "") if basic else "",
            basic.get("codeHeatNm", "") if basic else "",
            basic.get("kaptBcompany", "") if basic else "",
            basic.get("kaptAcompany", "") if basic else "",
            basic.get("codeAptNm", "") if basic else "",
            basic.get("codeMgrNm", "") if basic else "",
            basic.get("codeHallNm", "") if basic else "",
            vals.get("structure"),
            float(basic.get("kaptTarea") or 0) or None if basic else None,
            float(basic.get("privArea") or 0) or None if basic else None,
            vals.get("parking_cnt"), vals.get("cctv_cnt"),
            int(basic.get("kaptdEcntp") or 0) or None if basic else None,
            vals.get("ev_charger_cnt"), vals.get("subway_info"),
            vals.get("bus_time"), vals.get("welfare"),
        ])
        matched += 1

    conn.commit()
    if api_fallback > 0:
        logger.info(f"  K-APT DB 매칭 후 API fallback: {api_fallback}건")
    return matched


def _fill_apartments_from_kapt_basic(cur, pnu: str, basic: dict):
    """K-APT 기본정보로 apartments 테이블의 빈 값 보완."""
    try:
        hhld = int(basic.get("hoCnt") or 0)
        dong = int(basic.get("kaptDongCnt") or 0)
        top_flr = int(basic.get("ktownFlrNo") or 0)
    except (ValueError, TypeError):
        return

    if hhld > 0 or dong > 0 or top_flr > 0:
        cur.execute("""
            UPDATE apartments SET
                total_hhld_cnt = GREATEST(COALESCE(total_hhld_cnt, 0), %s),
                dong_count = GREATEST(COALESCE(dong_count, 0), %s),
                max_floor = GREATEST(COALESCE(max_floor, 0), %s)
            WHERE pnu = %s AND (
                COALESCE(total_hhld_cnt, 0) < %s
                OR COALESCE(dong_count, 0) < %s
                OR COALESCE(max_floor, 0) < %s
            )
        """, [hhld, dong, top_flr, pnu, hhld, dong, top_flr])


# ── 메인 ──

def enrich_new_apartments(conn, logger):
    """미매핑 apt_seq → 정규 PNU로 등록 (2-Phase 병렬 처리)."""
    if not KAKAO_API_KEY or not DATA_GO_KR_API_KEY:
        logger.warning("  KAKAO_API_KEY 또는 DATA_GO_KR_API_KEY 미설정, 보충 생략")
        return 0, []

    # apt_area_info 스키마 보장 — 신규 컬럼 누락 방지 (Railway 최초 실행 시)
    try:
        ensure_area_schema(conn)
    except Exception as e:
        logger.warning(f"  apt_area_info 스키마 체크 실패: {e}")

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    # 시군구 코드→이름 매핑
    sgg_map = {}
    for r in query_all(conn, "SELECT code, name, extra FROM common_code WHERE group_id = 'sigungu'"):
        region = f"{r['extra']} {r['name']}" if r["extra"] and r["extra"] != r["name"] else r["name"]
        sgg_map[r["code"]] = region

    # 미매핑 apt_seq 조회 (PNU 조합용 필드 포함)
    unmapped = query_all(conn, """
        SELECT DISTINCT ON (apt_seq) apt_seq, sgg_cd, apt_nm, umd_cd, bonbun, bubun, land_cd, umd_nm
        FROM (
            SELECT t.apt_seq, t.sgg_cd, t.apt_nm, t.umd_cd, t.bonbun, t.bubun, t.land_cd, t.umd_nm
            FROM trade_history t
            WHERE NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = t.apt_seq)
              AND t.umd_cd IS NOT NULL
            UNION ALL
            SELECT t.apt_seq, t.sgg_cd, t.apt_nm, t.umd_cd, t.bonbun, t.bubun, t.land_cd, t.umd_nm
            FROM trade_history t
            WHERE NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = t.apt_seq)
              AND t.umd_cd IS NULL
            UNION ALL
            SELECT r.apt_seq, r.sgg_cd, r.apt_nm, NULL, NULL, NULL, NULL, r.umd_nm
            FROM rent_history r
            WHERE NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = r.apt_seq)
        ) sub
        ORDER BY apt_seq, umd_cd NULLS LAST
    """)

    if not unmapped:
        logger.info("  보충 대상 신규 아파트 없음")
        return 0, []

    logger.info(f"  미매핑 apt_seq {len(unmapped)}건 처리 시작 (workers={ENRICH_WORKERS})")

    # 기존 PNU + 이름 사전 로드 (Phase 1에서 read-only, Phase 2에서 이름 유사도 검증)
    apt_rows = query_all(conn, "SELECT pnu, bld_nm, sigungu_code FROM apartments")
    existing_pnus = set(r["pnu"] for r in apt_rows)
    existing_names = {r["pnu"]: r["bld_nm"] or "" for r in apt_rows}

    # K-APT 연동된 "진본" 아파트 (sigungu_code, normalized_name) → pnu 인덱스
    # 동일 시군구·동일 이름의 Kakao 오매칭을 사전에 진본으로 리다이렉트한다.
    kapt_rows = query_all(conn,
        "SELECT a.pnu, a.bld_nm, a.sigungu_code FROM apartments a "
        "JOIN apt_kapt_info k ON a.pnu = k.pnu "
        "WHERE a.bld_nm IS NOT NULL AND a.bld_nm != '' AND a.sigungu_code IS NOT NULL")
    kapt_name_index: dict[tuple[str, str], str] = {}
    for r in kapt_rows:
        key = (str(r["sigungu_code"])[:5], _normalize_name(r["bld_nm"]))
        kapt_name_index.setdefault(key, r["pnu"])

    # ── Phase 0: PNU 직접 조합으로 신규 아파트 후보 식별 ──
    # _update_mapping에서 기존 PNU 매핑은 이미 처리됨.
    # 여기서는 "PNU 조합 가능하지만 기존 apartments에 없는" 신규 건만 식별.
    cur = conn.cursor()
    new_pnus = []
    created_pnus = set()
    pnu_known_map: dict[str, str] = {}  # apt_seq → known_pnu (Phase 1에 전달)

    remaining_unmapped = []
    for row in unmapped:
        sgg_cd = str(row["sgg_cd"])[:5]
        umd_cd = row.get("umd_cd") or ""
        bonbun = (row.get("bonbun") or "").strip()
        bubun = (row.get("bubun") or "").strip()

        if umd_cd and bonbun:
            pnu = f"{sgg_cd}{umd_cd}0{bonbun.zfill(4)}{(bubun or '0').zfill(4)}"
            if len(pnu) == 19 and pnu not in existing_pnus and pnu not in created_pnus:
                pnu_known_map[row["apt_seq"]] = pnu
                created_pnus.add(pnu)

        remaining_unmapped.append(row)

    if pnu_known_map:
        logger.info(f"  Phase 0: PNU 직접 조합 {len(pnu_known_map)}건 (신규 아파트 후보)")

    unmapped = remaining_unmapped

    if not unmapped:
        logger.info("  보충 대상 없음")
        return 0, new_pnus

    # Rate limiters
    kakao_limiter = RateLimiter(KAKAO_RATE)
    data_go_limiter = RateLimiter(DATA_GO_KR_RATE)

    # ── Phase 1: 병렬 API 호출 (known_pnu 전달) ──
    logger.info(f"  Phase 1: API 병렬 호출 시작 ({len(unmapped)}건)")
    results = []

    with ThreadPoolExecutor(max_workers=ENRICH_WORKERS) as executor:
        futures = {
            executor.submit(
                _resolve_one, row, headers, sgg_map,
                existing_pnus, kakao_limiter, data_go_limiter,
                known_pnu=pnu_known_map.get(row["apt_seq"]),
            ): row
            for row in unmapped
        }

        for i, future in enumerate(as_completed(futures)):
            try:
                results.append(future.result())
            except Exception as e:
                row = futures[future]
                logger.warning(f"  API 오류: {row['apt_nm']} — {e}")
                results.append({
                    "apt_seq": row["apt_seq"],
                    "sgg_cd": str(row["sgg_cd"])[:5],
                    "apt_nm": str(row["apt_nm"]),
                    "pnu": None, "lat": None, "lng": None,
                    "new_plat": None, "plat": None,
                    "bjd_code": None, "bld_params": None, "bld_info": None,
                })

            if (i + 1) % 200 == 0:
                logger.info(f"  Phase 1 진행: {i + 1}/{len(unmapped)}")

    logger.info(f"  Phase 1 완료: {len(results)}건 API 호출 완료")

    # ── Phase 2: 순차 DB 기록 ──
    created = 0
    matched = 0
    fallback = 0

    for idx, r in enumerate(results):
        if (idx + 1) % 200 == 0:
            conn.commit()
            logger.info(f"  Phase 2 진행: {idx + 1}/{len(results)} (신규={created}, 매칭={matched}, fallback={fallback})")

        apt_seq = r["apt_seq"]
        sgg_cd = r["sgg_cd"]
        apt_nm = r["apt_nm"]
        real_pnu = r["pnu"]

        # [3] K-APT 진본 우선 바인딩 — 같은 시군구에 K-APT 연동 + 이름 일치 단지가
        # 이미 존재하면 Kakao 결과보다 우선 사용 (오매칭으로 유령 생성 방지)
        canonical_pnu = kapt_name_index.get((sgg_cd, _normalize_name(apt_nm)))
        if canonical_pnu:
            pnu = canonical_pnu
            method = "kapt_canonical"
            matched += 1
            cur.execute(
                "INSERT INTO trade_apt_mapping (apt_seq, pnu, apt_nm, sgg_cd, match_method) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (apt_seq) DO NOTHING",
                [apt_seq, pnu, apt_nm, sgg_cd, method],
            )
            continue

        if real_pnu:
            # PNU 앞 5자리(sigungu_code)와 거래 sgg_cd 일치 확인
            pnu_sgg = real_pnu[:5]
            if pnu_sgg != sgg_cd:
                # 시군구 불일치 → Kakao가 동명 다른 지역 아파트를 반환
                pnu = f"TRADE_{sgg_cd}_{apt_nm}"
                method = "trade_fallback_sgg_mismatch"
                cur.execute(
                    "INSERT INTO apartments (pnu, bld_nm, sigungu_code, group_pnu, lat, lng, new_plat_plc, plat_plc) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (pnu) DO NOTHING",
                    [pnu, apt_nm, sgg_cd, pnu, r["lat"], r["lng"], r["new_plat"], r["plat"]],
                )
                fallback += 1
            elif real_pnu in existing_pnus or real_pnu in created_pnus:
                # 기존 아파트 + 시군구 일치 → 이름 유사도 검증
                existing_name = existing_names.get(real_pnu, "")
                if existing_name and not _names_overlap(apt_nm, existing_name):
                    # 이름 불일치 → Kakao가 인근 다른 아파트를 반환
                    pnu = f"TRADE_{sgg_cd}_{apt_nm}"
                    method = "trade_fallback_name_mismatch"
                    cur.execute(
                        "INSERT INTO apartments (pnu, bld_nm, sigungu_code, group_pnu, lat, lng, new_plat_plc, plat_plc) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (pnu) DO NOTHING",
                        [pnu, apt_nm, sgg_cd, pnu, r["lat"], r["lng"], r["new_plat"], r["plat"]],
                    )
                    fallback += 1
                else:
                    pnu = real_pnu
                    method = "kakao_pnu_existing"
                    matched += 1
            else:
                # 신규 등록 후보 — 브랜드-연도 게이트 선행 검증
                bld_info = r.get("bld_info") or {}
                bld_use_apr = bld_info.get("use_apr_day") if bld_info else None
                if not _brand_year_consistent(apt_nm, bld_use_apr):
                    # 2000년대 브랜드 이름인데 건축물대장 준공일이 1995년 이전
                    # → Kakao 오매칭으로 판단, TRADE_ fallback 으로 회피
                    pnu = f"TRADE_{sgg_cd}_{apt_nm}"
                    method = "trade_fallback_brand_year"
                    cur.execute(
                        "INSERT INTO apartments (pnu, bld_nm, sigungu_code, group_pnu, lat, lng, new_plat_plc, plat_plc) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (pnu) DO NOTHING",
                        [pnu, apt_nm, sgg_cd, pnu, r["lat"], r["lng"], r["new_plat"], r["plat"]],
                    )
                    fallback += 1
                else:
                    pnu = real_pnu
                    method = "kakao_pnu_new"
                    cur.execute(
                        "INSERT INTO apartments (pnu, bld_nm, sigungu_code, group_pnu, bjd_code, lat, lng, new_plat_plc, plat_plc) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (pnu) DO NOTHING",
                        [pnu, apt_nm, sgg_cd, pnu, r["bjd_code"], r["lat"], r["lng"], r["new_plat"], r["plat"]],
                    )

                    # 건축물대장 정보 업데이트
                    if bld_info:
                        updates = []
                        params = []
                        for col in ("total_hhld_cnt", "dong_count", "max_floor"):
                            if bld_info.get(col):
                                updates.append(f"{col} = %s")
                                params.append(bld_info[col])
                        if bld_info.get("use_apr_day"):
                            updates.append("use_apr_day = COALESCE(NULLIF(use_apr_day, ''), %s)")
                            params.append(bld_info["use_apr_day"])
                        if updates:
                            params.append(pnu)
                            cur.execute(f"UPDATE apartments SET {', '.join(updates)} WHERE pnu = %s", params)

                    # 건축물대장 전유부 → apt_area_info 적재 (호별 전용면적 ground truth)
                    bld_params = r.get("bld_params")
                    if bld_params:
                        try:
                            area_info = fetch_area_info(
                                bld_params["sigungu_cd"],
                                bld_params["bjdong_cd"],
                                bld_params.get("plat_gb_cd", "0"),
                                bld_params["bun"],
                                bld_params["ji"],
                            )
                            if area_info:
                                upsert_area_info(conn, pnu, area_info)
                        except Exception as e:
                            logger.warning(f"  area_info 실패 ({pnu}): {e}")

                    created += 1
                    new_pnus.append(pnu)
                    created_pnus.add(pnu)
        else:
            # Kakao 검색 실패 → TRADE_ fallback
            pnu = f"TRADE_{sgg_cd}_{apt_nm}"
            method = "trade_fallback"
            cur.execute(
                "INSERT INTO apartments (pnu, bld_nm, sigungu_code, group_pnu, lat, lng, new_plat_plc, plat_plc) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (pnu) DO NOTHING",
                [pnu, apt_nm, sgg_cd, pnu, r["lat"], r["lng"], r["new_plat"], r["plat"]],
            )
            fallback += 1

        # trade_apt_mapping 등록
        cur.execute(
            "INSERT INTO trade_apt_mapping (apt_seq, pnu, apt_nm, sgg_cd, match_method) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (apt_seq) DO NOTHING",
            [apt_seq, pnu, apt_nm, sgg_cd, method],
        )

    conn.commit()
    logger.info(f"  아파트 보충 완료: 신규={created}, 기존매칭={matched}, fallback={fallback}")

    # ── Phase 3: K-APT 보완 ──
    if new_pnus:
        kapt_cnt = _enrich_kapt_targeted(conn, logger, new_pnus)
        logger.info(f"  K-APT 보완: {kapt_cnt}건")

    return created + matched, new_pnus
