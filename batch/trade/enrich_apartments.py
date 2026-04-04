"""신규 거래 아파트 자동 등록 + 건물정보 보충.

거래 배치의 4단계: recalc_price() 이후 실행.
미매핑 apt_seq → TRADE_ PNU 생성 → 좌표/주소/세대수/동수/층수 보충.
"""

import time
import xml.etree.ElementTree as ET
import requests

from batch.config import KAKAO_API_KEY, DATA_GO_KR_API_KEY, KAKAO_RATE, DATA_GO_KR_RATE
from batch.db import query_all, execute_values_chunked
from batch.fill_addresses import _kakao_keyword_search, _address_to_bld_params

BLD_TITLE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"


def enrich_new_apartments(conn, logger):
    """미매핑 apt_seq를 apartments에 등록하고 건물정보를 보충."""
    if not KAKAO_API_KEY or not DATA_GO_KR_API_KEY:
        logger.warning("  KAKAO_API_KEY 또는 DATA_GO_KR_API_KEY 미설정, 보충 생략")
        return 0

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    # 시군구 코드→이름 매핑
    sgg_rows = query_all(conn, "SELECT code, name, extra FROM common_code WHERE group_id = 'sigungu'")
    sgg_map = {}
    for r in sgg_rows:
        region = f"{r['extra']} {r['name']}" if r["extra"] and r["extra"] != r["name"] else r["name"]
        sgg_map[r["code"]] = region

    # --- Phase A: 벌크 등록 + 매핑 ---
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
        return 0

    logger.info(f"  미매핑 apt_seq {len(unmapped)}건 처리 시작")

    # 기존 apartments PNU + 세대수 한번에 조회
    existing_apts = {}
    for r in query_all(conn, "SELECT pnu, total_hhld_cnt FROM apartments WHERE pnu LIKE 'TRADE_%%'"):
        existing_apts[r["pnu"]] = r["total_hhld_cnt"] or 0

    # 신규 아파트 INSERT + 매핑 INSERT 준비
    new_apt_rows = []
    new_mapping_rows = []
    needs_enrich = []  # API 보충이 필요한 (pnu, sgg_cd, apt_nm) 목록

    for row in unmapped:
        sgg_cd = str(row["sgg_cd"])[:5]
        apt_nm = str(row["apt_nm"])
        pnu = f"TRADE_{sgg_cd}_{apt_nm}"

        # apartments 등록
        if pnu not in existing_apts:
            new_apt_rows.append((pnu, apt_nm, sgg_cd, pnu))
            existing_apts[pnu] = 0

        # 매핑 등록
        new_mapping_rows.append((row["apt_seq"], pnu, apt_nm, sgg_cd, "auto_create"))

        # 세대수가 없으면 보충 대상
        if existing_apts[pnu] == 0:
            needs_enrich.append({"pnu": pnu, "sgg_cd": sgg_cd, "apt_nm": apt_nm})

    # 벌크 INSERT
    created = 0
    if new_apt_rows:
        created = execute_values_chunked(conn,
            "INSERT INTO apartments (pnu, bld_nm, sigungu_code, group_pnu) VALUES %s ON CONFLICT (pnu) DO NOTHING",
            new_apt_rows)
        logger.info(f"  아파트 신규 등록: {created}건")

    if new_mapping_rows:
        mapped = execute_values_chunked(conn,
            "INSERT INTO trade_apt_mapping (apt_seq, pnu, apt_nm, sgg_cd, match_method) VALUES %s ON CONFLICT (apt_seq) DO NOTHING",
            new_mapping_rows)
        logger.info(f"  매핑 추가: {mapped}건")

    # 중복 제거 (같은 PNU에 여러 apt_seq가 있을 수 있음)
    seen_pnus = set()
    unique_enrich = []
    for item in needs_enrich:
        if item["pnu"] not in seen_pnus:
            seen_pnus.add(item["pnu"])
            unique_enrich.append(item)

    logger.info(f"  건물정보 보충 대상: {len(unique_enrich)}건")

    # --- Phase B: API로 건물정보 보충 ---
    cur = conn.cursor()
    enriched = 0
    failed = 0

    for idx, apt in enumerate(unique_enrich):
        if (idx + 1) % 200 == 0:
            conn.commit()
            logger.info(f"  진행: {idx+1}/{len(unique_enrich)} (보충={enriched}, 실패={failed})")

        pnu = apt["pnu"]
        sgg_cd = apt["sgg_cd"]
        apt_nm = apt["apt_nm"]

        # Kakao 키워드 검색 → 좌표/주소
        region = sgg_map.get(sgg_cd, "")
        query = f"{region} {apt_nm} 아파트"
        new_plat, plat, lat, lng = _kakao_keyword_search(headers, query)
        time.sleep(KAKAO_RATE)

        addr_updates = []
        addr_params = []
        if new_plat:
            addr_updates.append("new_plat_plc = %s")
            addr_params.append(new_plat)
        if plat:
            addr_updates.append("plat_plc = %s")
            addr_params.append(plat)
        if lat and lng:
            addr_updates.append("lat = %s")
            addr_params.append(lat)
            addr_updates.append("lng = %s")
            addr_params.append(lng)

        if addr_updates:
            addr_params.append(pnu)
            cur.execute(f"UPDATE apartments SET {', '.join(addr_updates)} WHERE pnu = %s", addr_params)

        address = new_plat or plat
        if not address:
            failed += 1
            continue

        # 건축물대장 API
        bld_params = _address_to_bld_params(headers, address, apt_nm)
        time.sleep(KAKAO_RATE)

        if not bld_params:
            failed += 1
            continue

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
            result_code = root.findtext(".//resultCode")
            if result_code and result_code != "00":
                failed += 1
                continue

            items = root.findall(".//item")
            if not items:
                failed += 1
                continue

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

            bld_updates = []
            bld_params_list = []
            if total_hhld > 0:
                bld_updates.append("total_hhld_cnt = %s")
                bld_params_list.append(total_hhld)
            if dong_set:
                bld_updates.append("dong_count = %s")
                bld_params_list.append(len(dong_set))
            if max_flr > 0:
                bld_updates.append("max_floor = %s")
                bld_params_list.append(max_flr)
            if use_apr:
                bld_updates.append("use_apr_day = COALESCE(NULLIF(use_apr_day, ''), %s)")
                bld_params_list.append(use_apr)

            if bld_updates:
                bld_params_list.append(pnu)
                cur.execute(
                    f"UPDATE apartments SET {', '.join(bld_updates)} WHERE pnu = %s",
                    bld_params_list,
                )
                enriched += 1

        except Exception as e:
            failed += 1
            if failed <= 5:
                logger.warning(f"  건축물대장 오류: {apt_nm} — {e}")

    conn.commit()
    logger.info(f"  신규 아파트 보충 완료: 등록={created}, 정보보충={enriched}, 실패={failed}")

    # 좌표가 확보된 신규 아파트에 대해 시설 집계 + 안전점수 계산
    all_new_pnus = [item["pnu"] for item in unique_enrich]
    if all_new_pnus:
        ph = ",".join(["%s"] * len(all_new_pnus))
        with_coords = query_all(conn,
            f"SELECT pnu FROM apartments WHERE pnu IN ({ph}) AND lat IS NOT NULL",
            all_new_pnus)
        pnus_with_coords = [r["pnu"] for r in with_coords]
        if pnus_with_coords:
            from batch.quarterly.recalc_summary import recalc_for_new_apartments
            recalc_for_new_apartments(conn, logger, pnus_with_coords)

    # 신규 아파트가 등록되었으면 유사도 벡터 전체 재생성
    if created > 0:
        from batch.ml.build_vectors import build_all_vectors
        build_all_vectors(conn, logger)

    return created + enriched
