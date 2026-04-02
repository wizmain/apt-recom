"""누락된 아파트 주소 데이터 보충.

Phase 1: Kakao 역지오코딩 — 좌표 있는 TRADE PNU 아파트 주소 복원
Phase 2: 건축물대장 API — 정상 PNU 아파트 주소/건물정보 보충

사용법:
  python -m batch.fill_addresses --phase 1          # Kakao 역지오코딩
  python -m batch.fill_addresses --phase 2          # 건축물대장 API
  python -m batch.fill_addresses --phase 1 --dry-run  # DB 반영 없이 확인
"""

import argparse
import time
import requests
import xml.etree.ElementTree as ET

from batch.config import KAKAO_API_KEY, DATA_GO_KR_API_KEY, KAKAO_RATE, DATA_GO_KR_RATE
from batch.db import get_connection, get_dict_cursor
from batch.logger import setup_logger

BLD_TITLE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"


def phase1_kakao_reverse_geocode(dry_run: bool = False, batch_size: int = 100):
    """Phase 1: TRADE PNU + 좌표 있는 아파트 → Kakao 역지오코딩으로 주소 복원."""
    logger = setup_logger("fill_addresses_p1")
    conn = get_connection()
    cur = get_dict_cursor(conn)

    # 대상 조회
    cur.execute("""
        SELECT pnu, bld_nm, lat, lng
        FROM apartments
        WHERE new_plat_plc IS NULL
          AND lat IS NOT NULL
          AND pnu LIKE 'TRADE%%'
        ORDER BY pnu
    """)
    targets = cur.fetchall()
    logger.info(f"Phase 1 대상: {len(targets)}건 (TRADE PNU + 좌표)")

    if not KAKAO_API_KEY:
        logger.error("KAKAO_API_KEY 환경변수 필요")
        conn.close()
        return

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    updated = 0
    failed = 0

    for i, apt in enumerate(targets):
        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/local/geo/coord2address.json",
                headers=headers,
                params={"x": str(apt["lng"]), "y": str(apt["lat"])},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()

            docs = data.get("documents", [])
            if not docs:
                failed += 1
                if failed <= 5:
                    logger.warning(f"  역지오코딩 결과 없음: {apt['bld_nm']} ({apt['lat']}, {apt['lng']})")
                continue

            doc = docs[0]
            road = doc.get("road_address")
            addr = doc.get("address")

            new_plat_plc = road["address_name"] if road else None
            plat_plc = addr["address_name"] if addr else None

            if not new_plat_plc and not plat_plc:
                failed += 1
                continue

            if not dry_run:
                cur.execute(
                    "UPDATE apartments SET new_plat_plc = %s, plat_plc = %s WHERE pnu = %s",
                    [new_plat_plc, plat_plc, apt["pnu"]],
                )
                if (updated + 1) % batch_size == 0:
                    conn.commit()

            updated += 1
            if updated <= 3 or updated % 200 == 0:
                logger.info(f"  [{updated}] {apt['bld_nm']} → {new_plat_plc or plat_plc}")

        except Exception as e:
            failed += 1
            if failed <= 5:
                logger.warning(f"  오류: {apt['bld_nm']} — {e}")

        time.sleep(KAKAO_RATE)

        if (i + 1) % 500 == 0:
            logger.info(f"  진행: {i+1}/{len(targets)} (성공={updated}, 실패={failed})")

    if not dry_run:
        conn.commit()
        logger.info(f"Phase 1 완료: {updated}건 업데이트, {failed}건 실패")
    else:
        logger.info(f"Phase 1 Dry-run: {updated}건 성공, {failed}건 실패 (DB 미반영)")

    conn.close()


def phase2_building_registry(dry_run: bool = False, max_calls: int = 1000, batch_size: int = 50):
    """Phase 2: 정상 PNU 아파트 → 건축물대장 API로 주소/건물정보 보충."""
    logger = setup_logger("fill_addresses_p2")
    conn = get_connection()
    cur = get_dict_cursor(conn)

    if not DATA_GO_KR_API_KEY:
        logger.error("DATA_GO_KR_API_KEY 환경변수 필요")
        conn.close()
        return

    # 체크포인트 로드 (common_code에 마지막 처리 PNU 저장)
    cur.execute(
        "SELECT extra FROM common_code WHERE group_id = %s AND code = %s",
        ["batch_checkpoint", "fill_addr_p2"],
    )
    cp_row = cur.fetchone()
    last_pnu = cp_row["extra"] if cp_row else ""

    # 대상 조회 — 정상 PNU(19자리) + 주소 없음
    cur.execute("""
        SELECT pnu, bld_nm, sigungu_code
        FROM apartments
        WHERE new_plat_plc IS NULL
          AND pnu NOT LIKE 'TRADE%%'
          AND LENGTH(pnu) = 19
          AND pnu > %s
        ORDER BY pnu
    """, [last_pnu])
    targets = cur.fetchall()
    logger.info(f"Phase 2 대상: {len(targets)}건 (정상PNU+주소없음, 체크포인트 이후)")

    updated = 0
    failed = 0
    api_calls = 0

    for i, apt in enumerate(targets):
        if api_calls >= max_calls:
            logger.info(f"일일 API 호출 한도 도달: {max_calls}건")
            break

        pnu = apt["pnu"]
        # PNU 분해: 시도시군구(5) + 읍면동(5) + 대지구분(1) + 본번(4) + 부번(4)
        sigungu_cd = pnu[:5]
        bjdong_cd = pnu[5:10]
        plat_gb_cd = pnu[10:11]  # 0=대지, 1=산
        bun = str(int(pnu[11:15]))  # 본번 (앞 0 제거)
        ji = str(int(pnu[15:19]))   # 부번 (앞 0 제거)

        try:
            params = {
                "serviceKey": DATA_GO_KR_API_KEY,
                "sigunguCd": sigungu_cd,
                "bjdongCd": bjdong_cd,
                "platGbCd": plat_gb_cd,
                "bun": bun.zfill(4),
                "ji": ji.zfill(4),
                "numOfRows": "10",
                "pageNo": "1",
            }
            resp = requests.get(BLD_TITLE_URL, params=params, timeout=10)
            resp.raise_for_status()
            api_calls += 1

            root = ET.fromstring(resp.text)

            # 에러 체크
            result_code = root.findtext(".//resultCode")
            if result_code and result_code != "00":
                result_msg = root.findtext(".//resultMsg", "")
                failed += 1
                if failed <= 5:
                    logger.warning(f"  API 오류: {apt['bld_nm']} — {result_code}: {result_msg}")
                continue

            items = root.findall(".//item")
            if not items:
                failed += 1
                continue

            # 첫 번째 item에서 주소/건물정보 추출
            item = items[0]
            new_plat_plc = item.findtext("newPlatPlc") or None
            plat_plc = item.findtext("platPlc") or None
            use_apr_day = item.findtext("useAprDay") or None
            hhld_cnt_str = item.findtext("hhldCnt")
            grnd_flr_cnt_str = item.findtext("grndFlrCnt")

            if not new_plat_plc and not plat_plc:
                failed += 1
                continue

            # DB 업데이트
            update_fields = []
            update_params = []

            if new_plat_plc:
                update_fields.append("new_plat_plc = %s")
                update_params.append(new_plat_plc)
            if plat_plc:
                update_fields.append("plat_plc = %s")
                update_params.append(plat_plc)
            if use_apr_day and not apt.get("use_apr_day"):
                update_fields.append("use_apr_day = %s")
                update_params.append(use_apr_day)
            if hhld_cnt_str and hhld_cnt_str.isdigit():
                hhld = int(hhld_cnt_str)
                if hhld > 0:
                    update_fields.append("total_hhld_cnt = COALESCE(total_hhld_cnt, %s)")
                    update_params.append(hhld)
            if grnd_flr_cnt_str and grnd_flr_cnt_str.isdigit():
                flr = int(grnd_flr_cnt_str)
                if flr > 0:
                    update_fields.append("max_floor = COALESCE(max_floor, %s)")
                    update_params.append(flr)

            if update_fields and not dry_run:
                update_params.append(pnu)
                cur.execute(
                    f"UPDATE apartments SET {', '.join(update_fields)} WHERE pnu = %s",
                    update_params,
                )

            updated += 1
            if updated <= 3 or updated % 100 == 0:
                logger.info(f"  [{updated}] {apt['bld_nm']} → {new_plat_plc or plat_plc}")

        except Exception as e:
            failed += 1
            if failed <= 5:
                logger.warning(f"  오류: {apt['bld_nm']} (pnu={pnu}) — {e}")

        # 체크포인트 저장 (50건마다)
        if (i + 1) % batch_size == 0 and not dry_run:
            _save_checkpoint(cur, conn, pnu)

        time.sleep(DATA_GO_KR_RATE)

        if (i + 1) % 200 == 0:
            logger.info(f"  진행: {i+1}/{len(targets)} (성공={updated}, 실패={failed}, API={api_calls})")

    # 마지막 체크포인트 저장
    if not dry_run and targets and api_calls > 0:
        last_processed = targets[min(i, len(targets) - 1)]["pnu"]
        _save_checkpoint(cur, conn, last_processed)
        conn.commit()
        logger.info(f"Phase 2 완료: {updated}건 업데이트, {failed}건 실패, API {api_calls}건 호출")
    else:
        logger.info(f"Phase 2 Dry-run: {updated}건 성공, {failed}건 실패 (DB 미반영)")

    conn.close()


def phase3_kakao_fallback(dry_run: bool = False):
    """Phase 3: Phase 1~2에서 처리 못한 잔여분 → Kakao API 보완.

    A) 좌표 있는데 주소 없는 아파트 → 역지오코딩 재시도
    B) 좌표 없는 아파트 → Kakao 키워드 검색 (건물명 + 시군구명)
    """
    logger = setup_logger("fill_addresses_p3")
    conn = get_connection()
    cur = get_dict_cursor(conn)

    if not KAKAO_API_KEY:
        logger.error("KAKAO_API_KEY 환경변수 필요")
        conn.close()
        return

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    # 시군구 코드→이름 매핑 로드
    cur.execute("SELECT code, name, extra FROM common_code WHERE group_id = 'sigungu'")
    sgg_map = {}
    for r in cur.fetchall():
        region = f"{r['extra']} {r['name']}" if r["extra"] and r["extra"] != r["name"] else r["name"]
        sgg_map[r["code"]] = region

    # A) 좌표 있는데 주소 없는 아파트 → 역지오코딩
    cur.execute("""
        SELECT pnu, bld_nm, lat, lng, sigungu_code
        FROM apartments
        WHERE new_plat_plc IS NULL AND lat IS NOT NULL
        ORDER BY pnu
    """)
    with_coord = cur.fetchall()
    logger.info(f"Phase 3A: 좌표 있음+주소 없음 {len(with_coord)}건 → 역지오코딩")

    updated = 0
    failed = 0
    for apt in with_coord:
        new_plat, plat = _kakao_reverse_geocode(headers, apt["lat"], apt["lng"])
        if new_plat or plat:
            if not dry_run:
                cur.execute(
                    "UPDATE apartments SET new_plat_plc = %s, plat_plc = %s WHERE pnu = %s",
                    [new_plat, plat, apt["pnu"]],
                )
            updated += 1
        else:
            failed += 1
        time.sleep(KAKAO_RATE)

    if not dry_run and updated:
        conn.commit()
    logger.info(f"  3A 결과: {updated}건 성공, {failed}건 실패")

    # B) 좌표 없는 아파트 → Kakao 키워드 검색
    cur.execute("""
        SELECT pnu, bld_nm, sigungu_code
        FROM apartments
        WHERE new_plat_plc IS NULL AND lat IS NULL
        ORDER BY pnu
    """)
    no_coord = cur.fetchall()
    logger.info(f"Phase 3B: 좌표+주소 없음 {len(no_coord)}건 → Kakao 키워드 검색")

    updated_b = 0
    failed_b = 0
    for apt in no_coord:
        region = sgg_map.get(apt["sigungu_code"], "")
        query = f"{region} {apt['bld_nm']}"

        new_plat, plat, lat, lng = _kakao_keyword_search(headers, query)
        if new_plat or plat:
            update_fields = []
            update_params = []
            if new_plat:
                update_fields.append("new_plat_plc = %s")
                update_params.append(new_plat)
            if plat:
                update_fields.append("plat_plc = %s")
                update_params.append(plat)
            if lat and lng:
                update_fields.append("lat = %s")
                update_params.append(lat)
                update_fields.append("lng = %s")
                update_params.append(lng)

            if update_fields and not dry_run:
                update_params.append(apt["pnu"])
                cur.execute(
                    f"UPDATE apartments SET {', '.join(update_fields)} WHERE pnu = %s",
                    update_params,
                )
            updated_b += 1
        else:
            failed_b += 1
            if failed_b <= 10:
                logger.warning(f"  검색 실패: {query}")
        time.sleep(KAKAO_RATE)

    if not dry_run and updated_b:
        conn.commit()
    logger.info(f"  3B 결과: {updated_b}건 성공, {failed_b}건 실패")
    logger.info(f"Phase 3 합계: {updated + updated_b}건 업데이트")

    conn.close()


def _kakao_reverse_geocode(headers: dict, lat: float, lng: float) -> tuple[str | None, str | None]:
    """Kakao 역지오코딩 → (도로명주소, 지번주소)."""
    try:
        resp = requests.get(
            "https://dapi.kakao.com/v2/local/geo/coord2address.json",
            headers=headers,
            params={"x": str(lng), "y": str(lat)},
            timeout=5,
        )
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
        if not docs:
            return None, None
        doc = docs[0]
        road = doc.get("road_address")
        addr = doc.get("address")
        return (road["address_name"] if road else None, addr["address_name"] if addr else None)
    except Exception:
        return None, None


def _kakao_keyword_search(headers: dict, query: str) -> tuple[str | None, str | None, float | None, float | None]:
    """Kakao 키워드 검색 → (도로명주소, 지번주소, lat, lng)."""
    try:
        # 먼저 키워드 검색
        resp = requests.get(
            "https://dapi.kakao.com/v2/local/search/keyword.json",
            headers=headers,
            params={"query": query, "size": 1, "category_group_code": "AP4"},
            timeout=5,
        )
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
        if docs:
            doc = docs[0]
            return (
                doc.get("road_address_name") or None,
                doc.get("address_name") or None,
                float(doc["y"]) if doc.get("y") else None,
                float(doc["x"]) if doc.get("x") else None,
            )

        # 키워드 검색 실패 시 주소 검색 시도
        resp2 = requests.get(
            "https://dapi.kakao.com/v2/local/search/address.json",
            headers=headers,
            params={"query": query, "size": 1},
            timeout=5,
        )
        resp2.raise_for_status()
        docs2 = resp2.json().get("documents", [])
        if docs2:
            doc = docs2[0]
            road = doc.get("road_address")
            return (
                road["address_name"] if road else doc.get("address_name"),
                doc.get("address_name") or None,
                float(doc["y"]) if doc.get("y") else None,
                float(doc["x"]) if doc.get("x") else None,
            )

        return None, None, None, None
    except Exception:
        return None, None, None, None


def _save_checkpoint(cur, conn, pnu: str):
    """체크포인트를 common_code에 저장."""
    cur.execute(
        """INSERT INTO common_code (group_id, code, name, extra)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (group_id, code)
           DO UPDATE SET extra = EXCLUDED.extra""",
        ["batch_checkpoint", "fill_addr_p2", "주소보충 Phase2 체크포인트", pnu],
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="아파트 주소 데이터 보충")
    parser.add_argument("--phase", type=int, required=True, choices=[1, 2, 3], help="실행 단계")
    parser.add_argument("--dry-run", action="store_true", help="DB 반영 없이 확인")
    parser.add_argument("--max-calls", type=int, default=1000, help="Phase 2: 일일 API 호출 한도")
    args = parser.parse_args()

    if args.phase == 1:
        phase1_kakao_reverse_geocode(dry_run=args.dry_run)
    elif args.phase == 2:
        phase2_building_registry(dry_run=args.dry_run, max_calls=args.max_calls)
    elif args.phase == 3:
        phase3_kakao_fallback(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
