"""신규 거래 아파트 자동 등록 + 건물정보 보충.

거래 배치의 4단계: recalc_price() 이후 실행.
미매핑 apt_seq → Kakao API로 PNU 확보 → 정규 PNU로 등록.
Kakao 검색 실패 시에만 TRADE_ PNU fallback.
"""

import time
import xml.etree.ElementTree as ET
import requests

from batch.config import KAKAO_API_KEY, DATA_GO_KR_API_KEY, KAKAO_RATE, DATA_GO_KR_RATE
from batch.db import query_all, query_one
from batch.fill_addresses import _kakao_keyword_search, _address_to_bld_params

BLD_TITLE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"


# ── PNU 변환 ──

def _resolve_pnu(headers: dict, sgg_cd: str, apt_nm: str, region: str):
    """Kakao API로 주소 확보 → 19자리 정규 PNU 조합.

    반환: (pnu, lat, lng, new_plat_plc, plat_plc, bjd_code, bld_params) or fallback.
    """
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

    # 19자리 PNU 조합: bjd_code(10) + plat_gb(1) + bun(4) + ji(4)
    real_pnu = (
        bld_params["sigungu_cd"]
        + bld_params["bjdong_cd"]
        + bld_params.get("plat_gb_cd", "0")
        + bld_params["bun"]
        + bld_params["ji"]
    )
    bjd_code = bld_params["sigungu_cd"] + bld_params["bjdong_cd"]

    return real_pnu, lat, lng, new_plat, plat, bjd_code, bld_params


# ── 건축물대장 조회 ──

def _fetch_building_info(bld_params: dict) -> dict:
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


# ── 메인 ──

def enrich_new_apartments(conn, logger):
    """미매핑 apt_seq → 정규 PNU로 등록 (TRADE_는 최후 fallback)."""
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

    logger.info(f"  미매핑 apt_seq {len(unmapped)}건 처리 시작")

    cur = conn.cursor()
    created = 0
    matched = 0
    fallback = 0
    failed = 0
    new_pnus = []  # 신규 등록된 PNU (시설집계/벡터 재생성용)

    for idx, row in enumerate(unmapped):
        if (idx + 1) % 200 == 0:
            conn.commit()
            logger.info(f"  진행: {idx+1}/{len(unmapped)} (신규={created}, 매칭={matched}, fallback={fallback}, 실패={failed})")

        apt_seq = row["apt_seq"]
        sgg_cd = str(row["sgg_cd"])[:5]
        apt_nm = str(row["apt_nm"])
        region = sgg_map.get(sgg_cd, "")

        # 1. Kakao API → PNU 변환 시도
        real_pnu, lat, lng, new_plat, plat, bjd_code, bld_params = _resolve_pnu(
            headers, sgg_cd, apt_nm, region
        )

        # 2. PNU 결정
        if real_pnu:
            existing = query_one(conn, "SELECT pnu FROM apartments WHERE pnu = %s", [real_pnu])
            if existing:
                # 기존 아파트에 매핑
                pnu = real_pnu
                method = "kakao_pnu_existing"
                matched += 1
            else:
                # 정규 PNU로 신규 등록
                pnu = real_pnu
                method = "kakao_pnu_new"
                cur.execute(
                    "INSERT INTO apartments (pnu, bld_nm, sigungu_code, group_pnu, bjd_code, lat, lng, new_plat_plc, plat_plc) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (pnu) DO NOTHING",
                    [pnu, apt_nm, sgg_cd, pnu, bjd_code, lat, lng, new_plat, plat],
                )
                # 건축물대장으로 세대수 보충
                if bld_params:
                    bld_info = _fetch_building_info(bld_params)
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
        else:
            # Kakao 검색 실패 → TRADE_ fallback
            pnu = f"TRADE_{sgg_cd}_{apt_nm}"
            method = "trade_fallback"
            cur.execute(
                "INSERT INTO apartments (pnu, bld_nm, sigungu_code, group_pnu, lat, lng, new_plat_plc, plat_plc) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (pnu) DO NOTHING",
                [pnu, apt_nm, sgg_cd, pnu, lat, lng, new_plat, plat],
            )
            fallback += 1

        # 3. trade_apt_mapping 등록
        cur.execute(
            "INSERT INTO trade_apt_mapping (apt_seq, pnu, apt_nm, sgg_cd, match_method) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (apt_seq) DO NOTHING",
            [apt_seq, pnu, apt_nm, sgg_cd, method],
        )

    conn.commit()
    logger.info(f"  아파트 보충 완료: 신규={created}, 기존매칭={matched}, fallback={fallback}, 실패={failed}")

    return created + matched, new_pnus
