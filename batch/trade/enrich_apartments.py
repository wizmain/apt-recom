"""신규 거래 아파트 자동 등록 + 건물정보 보충.

거래 배치의 4단계: recalc_price() 이후 실행.
미매핑 apt_seq → Kakao API로 PNU 확보 → 정규 PNU로 등록.
Kakao 검색 실패 시에만 TRADE_ PNU fallback.

v2: ThreadPoolExecutor 병렬화 (Phase 1 API / Phase 2 DB 분리)
"""

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

BLD_TITLE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

MAX_RETRIES = 2
RETRY_BACKOFFS = [1, 2]


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
) -> dict:
    """단일 apt_seq에 대해 Kakao + 건축물대장 API 호출. DB 접근 없음."""
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


# ── 메인 ──

def enrich_new_apartments(conn, logger):
    """미매핑 apt_seq → 정규 PNU로 등록 (2-Phase 병렬 처리)."""
    if not KAKAO_API_KEY or not DATA_GO_KR_API_KEY:
        logger.warning("  KAKAO_API_KEY 또는 DATA_GO_KR_API_KEY 미설정, 보충 생략")
        return 0, []

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    # 시군구 코드→이름 매핑
    sgg_map = {}
    for r in query_all(conn, "SELECT code, name, extra FROM common_code WHERE group_id = 'sigungu'"):
        region = f"{r['extra']} {r['name']}" if r["extra"] and r["extra"] != r["name"] else r["name"]
        sgg_map[r["code"]] = region

    # 미매핑 apt_seq 조회
    unmapped = query_all(conn, """
        SELECT DISTINCT t.apt_seq, t.sgg_cd, t.apt_nm
        FROM trade_history t
        WHERE NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = t.apt_seq)
        UNION
        SELECT DISTINCT r.apt_seq, r.sgg_cd, r.apt_nm
        FROM rent_history r
        WHERE NOT EXISTS (SELECT 1 FROM trade_apt_mapping m WHERE m.apt_seq = r.apt_seq)
    """)

    if not unmapped:
        logger.info("  보충 대상 신규 아파트 없음")
        return 0, []

    logger.info(f"  미매핑 apt_seq {len(unmapped)}건 처리 시작 (workers={ENRICH_WORKERS})")

    # 기존 PNU 사전 로드 (Phase 1에서 read-only)
    existing_pnus = set(r["pnu"] for r in query_all(conn, "SELECT pnu FROM apartments"))

    # Rate limiters
    kakao_limiter = RateLimiter(KAKAO_RATE)
    data_go_limiter = RateLimiter(DATA_GO_KR_RATE)

    # ── Phase 1: 병렬 API 호출 ──
    logger.info(f"  Phase 1: API 병렬 호출 시작")
    results = []

    with ThreadPoolExecutor(max_workers=ENRICH_WORKERS) as executor:
        futures = {
            executor.submit(
                _resolve_one, row, headers, sgg_map,
                existing_pnus, kakao_limiter, data_go_limiter,
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
    cur = conn.cursor()
    created = 0
    matched = 0
    fallback = 0
    new_pnus = []
    created_pnus = set()  # 배치 내 중복 방지

    for idx, r in enumerate(results):
        if (idx + 1) % 200 == 0:
            conn.commit()
            logger.info(f"  Phase 2 진행: {idx + 1}/{len(results)} (신규={created}, 매칭={matched}, fallback={fallback})")

        apt_seq = r["apt_seq"]
        sgg_cd = r["sgg_cd"]
        apt_nm = r["apt_nm"]
        real_pnu = r["pnu"]

        if real_pnu:
            if real_pnu in existing_pnus or real_pnu in created_pnus:
                # 기존 아파트 또는 이번 배치에서 이미 생성
                pnu = real_pnu
                method = "kakao_pnu_existing"
                matched += 1
            else:
                # 신규 등록
                pnu = real_pnu
                method = "kakao_pnu_new"
                cur.execute(
                    "INSERT INTO apartments (pnu, bld_nm, sigungu_code, group_pnu, bjd_code, lat, lng, new_plat_plc, plat_plc) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (pnu) DO NOTHING",
                    [pnu, apt_nm, sgg_cd, pnu, r["bjd_code"], r["lat"], r["lng"], r["new_plat"], r["plat"]],
                )

                # 건축물대장 정보 업데이트
                bld_info = r.get("bld_info")
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

    return created + matched, new_pnus
