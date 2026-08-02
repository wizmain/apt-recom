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
from batch.region_codes import canonical_addr, load_aliases, normalize_pnu
from batch.trade.registry import (
    REQUEST_FAILED,
    pnu_to_bld_params,
    RegistryResponse,
    parse_registry_response,
)
from batch.trade.collect_area_info import fetch_area_info, upsert_area_info, ensure_schema as ensure_area_schema

BLD_TITLE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

MAX_RETRIES = 2
RETRY_BACKOFFS = [1, 2]


# 거래명↔아파트명 매칭 규칙은 batch/trade/name_matching.py 로 분리했다.
# 순수 함수라 DB 없이 검증할 수 있어야 scripts/tests CI 에서 돌릴 수 있다.
# 기존 호출부 호환을 위해 여기서 다시 노출한다.
from batch.trade.name_matching import (  # noqa: E402,F401
    _BUILD_YEAR_TOLERANCE,
    _MIN_ALIAS_LEN,
    _MODERN_BRAND_CUTOFF,
    _MODERN_BRANDS,
    _NAME_SIM_THRESHOLD,
    _brand_year_consistent,
    _has_modern_brand,
    _name_similarity_ratio,
    _name_variants,
    _names_overlap,
    _normalize_name,
    _timeline_consistent,
)


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
    aliases: dict | None = None,
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

    # 1. Kakao 키워드 검색 — 이름 변형을 우선순위대로 시도하고 첫 성공에서 중단.
    #    괄호 별칭형 거래명(`...H3블록(산울마을6단지)`)은 원본으로는 0건이라
    #    변형 없이는 좌표 없는 TRADE_ fallback 으로 빠진다.
    #    변형이 1개(괄호 없는 이름)면 호출 수는 기존과 동일하다.
    query = f"{region} {apt_nm} 아파트"
    new_plat, plat, lat, lng = None, None, None, None

    for variant in _name_variants(apt_nm):
        resp = _api_get_with_retry(
            KAKAO_KEYWORD_URL, kakao_limiter,
            headers=headers,
            params={"query": f"{region} {variant} 아파트", "size": 5},
            timeout=5,
        )
        if not (resp and resp.ok):
            continue
        docs = resp.json().get("documents", [])
        if not docs:
            continue
        apt_docs = [d for d in docs if "아파트" in (d.get("category_name") or "")]
        doc = apt_docs[0] if apt_docs else docs[0]
        new_plat = doc.get("road_address_name") or None
        plat = doc.get("address_name") or None
        lat = float(doc["y"]) if doc.get("y") else None
        lng = float(doc["x"]) if doc.get("x") else None
        break

    if lat is None and lng is None:
        # 모든 변형의 키워드 검색 실패 → 주소 검색 fallback (원본 질의 기준)
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

    raw_pnu = (
        b_code[:10]
        + ("1" if mountain == "Y" else "0")
        + str(main_no).zfill(4)
        + str(sub_no).zfill(4)
    )
    # Kakao b_code 는 행정구역 개편 후 신코드를 쓴다(광주 29170 → 12300).
    # 신코드 PNU 가 저장되면 같은 단지가 두 정체성으로 갈라지고, 건축물대장은
    # 구코드에만 응답한다. 경계에서 표준 코드로 정규화한다 (ADR-013).
    real_pnu = normalize_pnu(raw_pnu, aliases or {})
    bld_params = pnu_to_bld_params(real_pnu)

    result["pnu"] = real_pnu
    result["bjd_code"] = bld_params["sigungu_cd"] + bld_params["bjdong_cd"]
    result["bld_params"] = bld_params

    # 3. 기존 PNU가 아닐 때만 건축물대장 API 호출
    if real_pnu not in existing_pnus:
        result["bld_info"] = _fetch_building_info(bld_params, data_go_limiter)

    return result


# ── 건축물대장 조회 ──

def fetch_building_info_with_status(
    bld_params: dict, limiter: RateLimiter | None = None
) -> RegistryResponse:
    """건축물대장 조회 — 정보와 함께 실패 사유를 구분해 반환한다.

    "해당 지번에 건물 없음"(EMPTY)과 "쿼터 소진"(QUOTA)·"요청 실패"를 구분해야
    재시도 대상을 놓치지 않는다. 뭉뚱그리면 쿼터 소진분이 영구 미처리로 남는다
    (batch/trade/registry.py 주석 참조).
    """
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

    try:
        if limiter:
            resp = _api_get_with_retry(BLD_TITLE_URL, limiter, params=params, timeout=10)
            if not resp:
                return RegistryResponse({}, REQUEST_FAILED, "응답 없음(재시도 소진)")
        else:
            resp = requests.get(BLD_TITLE_URL, params=params, timeout=10)
            time.sleep(DATA_GO_KR_RATE)
        if not resp.ok:
            return RegistryResponse({}, REQUEST_FAILED, f"HTTP {resp.status_code}")
    except requests.RequestException as e:
        return RegistryResponse({}, REQUEST_FAILED, f"{type(e).__name__}: {e}")

    return parse_registry_response(resp.text)


def _fetch_building_info(bld_params: dict, limiter: RateLimiter | None = None) -> dict:
    """건축물대장 API로 세대수/동수/최고층/준공일 조회.

    실패 사유가 필요하면 fetch_building_info_with_status 를 쓴다.
    """
    return fetch_building_info_with_status(bld_params, limiter).info


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

    # 기존 PNU + 이름 + 준공일 사전 로드 (Phase 2에서 이름 유사도·타임라인 검증)
    apt_rows = query_all(conn, "SELECT pnu, bld_nm, sigungu_code, use_apr_day FROM apartments")
    existing_pnus = set(r["pnu"] for r in apt_rows)
    existing_names = {r["pnu"]: r["bld_nm"] or "" for r in apt_rows}
    existing_use_apr_index = {r["pnu"]: r["use_apr_day"] for r in apt_rows if r.get("use_apr_day")}

    # K-APT 연동된 "진본" 아파트 (sigungu_code, normalized_name) → pnu 인덱스
    # 동일 시군구·동일 이름의 Kakao 오매칭을 사전에 진본으로 리다이렉트한다.
    kapt_rows = query_all(conn,
        "SELECT a.pnu, a.bld_nm, a.sigungu_code, a.use_apr_day "
        "FROM apartments a JOIN apt_kapt_info k ON a.pnu = k.pnu "
        "WHERE a.bld_nm IS NOT NULL AND a.bld_nm != '' AND a.sigungu_code IS NOT NULL")
    kapt_name_index: dict[tuple[str, str], str] = {}
    for r in kapt_rows:
        key = (str(r["sigungu_code"])[:5], _normalize_name(r["bld_nm"]))
        kapt_name_index.setdefault(key, r["pnu"])

    # [L2] K-APT 연동된 진본 아파트의 주소 인덱스 — 같은 주소의 진본이 이미
    #      있으면 TRADE_ fallback 생성 대신 진본 PNU에 매핑
    # 행정구역 코드 별칭 — Kakao b_code 정규화용 (ADR-013)
    aliases = load_aliases(conn)

    kapt_addr_rows = query_all(conn,
        "SELECT a.pnu, a.plat_plc, a.new_plat_plc, a.sigungu_code "
        "FROM apartments a JOIN apt_kapt_info k ON a.pnu = k.pnu "
        "WHERE (a.plat_plc IS NOT NULL OR a.new_plat_plc IS NOT NULL)")

    def _addr_key(sgg_cd: str, addr: str) -> str:
        if not addr:
            return ""
        # 시도 표기를 canonical 토큰으로 접는다 — DB 의 "광주 …"와 Kakao 의
        # "전남광주통합특별시 …"가 같은 키가 되어야 [L2] 주소 매칭이 성립한다.
        folded = canonical_addr(addr, aliases)
        return f"{sgg_cd}|{re.sub(r'[\\s,]+', ' ', folded).strip().lower()}"

    kapt_addr_index: dict[str, str] = {}
    for ar in kapt_addr_rows:
        sgg5 = str(ar["sigungu_code"])[:5] if ar["sigungu_code"] else ""
        for addr_col in ("plat_plc", "new_plat_plc"):
            k = _addr_key(sgg5, ar[addr_col] or "")
            if k:
                kapt_addr_index.setdefault(k, ar["pnu"])

    # [L1.5] apt_seq 단위 거래·준공연도 집계 — Kakao 매칭 수락 전 정합성 검증에 사용
    #   min_deal_year: 거래 최소 연도 (준공 이전이면 오매칭)
    #   median_build_year: 거래서 기재된 건축연도 (건축물대장 use_apr_day 와 비교)
    ts_rows = query_all(conn, """
        SELECT apt_seq,
               MIN(deal_year) AS min_deal_year,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY build_year) AS median_build_year
        FROM trade_history
        WHERE deal_year IS NOT NULL
        GROUP BY apt_seq
    """)
    apt_seq_timeline: dict[str, tuple[int | None, int | None]] = {}
    for r in ts_rows:
        mby = int(r["median_build_year"]) if r.get("median_build_year") else None
        apt_seq_timeline[r["apt_seq"]] = (r.get("min_deal_year"), mby)

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
                aliases=aliases,
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

        # apt_seq 거래 타임라인 조회 (L1.5 build-year / deal-year 검증에 사용)
        min_dy, med_by = apt_seq_timeline.get(apt_seq, (None, None))

        # [L2] 주소 공유 진본이 있는지 사전 조회 (Kakao 반환 주소 기준)
        addr_canonical_pnu = None
        for addr in (r.get("plat") or "", r.get("new_plat") or ""):
            k = _addr_key(sgg_cd, addr)
            if k and k in kapt_addr_index:
                addr_canonical_pnu = kapt_addr_index[k]
                break

        # [L2-우선] 주소 공유 K-APT 진본이 있으면 그쪽으로 먼저 매핑
        # (같은 주소에 진본 존재 → TRADE_ 생성 자체를 차단)
        if addr_canonical_pnu:
            pnu = addr_canonical_pnu
            method = "kapt_address_canonical"
            matched += 1
            cur.execute(
                "INSERT INTO trade_apt_mapping (apt_seq, pnu, apt_nm, sgg_cd, match_method) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (apt_seq) DO NOTHING",
                [apt_seq, pnu, apt_nm, sgg_cd, method],
            )
            continue

        # [3] K-APT 진본 우선 바인딩 — 같은 시군구에 K-APT 연동 + 이름 일치 단지가
        # 이미 존재하면 Kakao 결과보다 우선 사용 (오매칭으로 유령 생성 방지)
        #
        # 원본 이름은 완전일치라 그대로 수락한다. 괄호 별칭 변형은 그보다 느슨한
        # 매칭이므로(`세종마루(CB5-3BL)` 처럼 괄호가 블록 코드인 경우가 있다)
        # 거래 타임라인 정합성을 통과한 경우에만 수락한다.
        canonical_pnu = None
        method = None
        for variant_idx, variant in enumerate(_name_variants(apt_nm)):
            hit = kapt_name_index.get((sgg_cd, _normalize_name(variant)))
            if not hit:
                continue
            if variant_idx == 0:
                canonical_pnu, method = hit, "kapt_canonical"
                break
            if _timeline_consistent(existing_use_apr_index.get(hit), min_dy, med_by):
                canonical_pnu, method = hit, "kapt_canonical_alias"
                break

        if canonical_pnu:
            pnu = canonical_pnu
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
                # 기존 아파트 + 시군구 일치 → 이름 유사도 + 타임라인 검증
                existing_name = existing_names.get(real_pnu, "")
                existing_use_apr = existing_use_apr_index.get(real_pnu)
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
                elif not _timeline_consistent(existing_use_apr, min_dy, med_by):
                    # 거래 연도 < 준공일 또는 build_year 불일치 → 다른 단지
                    pnu = f"TRADE_{sgg_cd}_{apt_nm}"
                    method = "trade_fallback_timeline"
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
                # 신규 등록 후보 — 브랜드-연도 + 거래 타임라인 게이트 선행 검증
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
                elif not _timeline_consistent(bld_use_apr, min_dy, med_by):
                    # 거래일이 건축물대장 준공일보다 이전이거나 build_year 큰 차이
                    pnu = f"TRADE_{sgg_cd}_{apt_nm}"
                    method = "trade_fallback_timeline"
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


# ── CLI 진입점 ──

def main():
    """독립 실행용 CLI. GitHub Actions 워크플로에서 호출.

    사용법:
      python -m batch.trade.enrich_apartments
    """
    from batch.db import get_connection
    from batch.logger import setup_logger

    logger = setup_logger("enrich")
    conn = get_connection()
    try:
        logger.info("신규 아파트 보충 시작 (독립 실행)")
        enriched, new_pnus = enrich_new_apartments(conn, logger)
        logger.info(f"신규 아파트 등록: {enriched}건 (신규 PNU {len(new_pnus)})")

        # 신규 PNU가 있으면 시설집계/안전점수/벡터 재생성
        if new_pnus:
            from batch.quarterly.recalc_summary import recalc_for_new_apartments
            recalc_for_new_apartments(conn, logger, new_pnus)
            logger.info(f"시설집계/안전점수 재계산: {len(new_pnus)}건")

        if enriched > 0:
            from batch.ml.build_vectors import build_all_vectors
            build_all_vectors(conn, logger)
            logger.info("벡터 재생성 완료")

    except Exception as e:
        logger.error(f"신규 아파트 보충 실패: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
