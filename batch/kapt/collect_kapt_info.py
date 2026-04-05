"""K-APT 아파트 정보 수집 — CSV 기본정보 + V4 API 상세정보.

Phase 1: CSV(apt_detail_info_v4.csv) → apt_kapt_info 기본정보 적재
Phase 2: V4 상세정보 API → 주차/CCTV/충전기 등 보충

사용법:
  python -m batch.kapt.collect_kapt_info --phase 1    # CSV 적재
  python -m batch.kapt.collect_kapt_info --phase 2    # V4 상세 API
  python -m batch.kapt.collect_kapt_info --phase all   # 1+2 순차
"""

import argparse
import csv
import re
import time
from pathlib import Path

import requests

from batch.config import DATA_GO_KR_API_KEY, DATA_GO_KR_RATE
from batch.db import get_connection, get_dict_cursor, query_all
from batch.logger import setup_logger

V4_DETAIL_URL = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusDtlInfoV4"


def _norm_addr(addr: str) -> str:
    if not addr:
        return ""
    return re.sub(r"\(.*?\)", "", re.sub(r"\s+", " ", addr)).strip()


def _build_addr_index(conn) -> dict[str, str]:
    """전체 아파트의 도로명주소 → pnu 인덱스."""
    rows = query_all(conn,
        "SELECT pnu, new_plat_plc FROM apartments WHERE group_pnu = pnu AND new_plat_plc IS NOT NULL AND LENGTH(new_plat_plc) > 5")
    idx = {}
    for r in rows:
        na = _norm_addr(r["new_plat_plc"])
        if na:
            idx[na] = r["pnu"]
    return idx


# ── Phase 1: CSV 적재 ──

def phase1_csv(conn, logger):
    """CSV 기본정보 → apt_kapt_info 적재 + apartments 세대수 보정."""
    csv_path = Path(__file__).resolve().parents[2] / "apt_eda" / "data" / "raw" / "apt_detail_info_v4.csv"
    if not csv_path.exists():
        logger.error(f"CSV 없음: {csv_path}")
        return 0

    addr_idx = _build_addr_index(conn)
    cur = get_dict_cursor(conn)

    loaded = 0
    hhld_fixed = 0

    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            doro = _norm_addr(row.get("doroJuso", ""))
            pnu = addr_idx.get(doro)
            if not pnu:
                continue

            kapt_code = row.get("kaptCode", "")
            try:
                hhld = int(float(row.get("hoCnt") or 0))
                dong = int(float(row.get("kaptDongCnt") or 0))
                top_flr = int(float(row.get("ktownFlrNo") or 0))
                total_area = float(row.get("kaptTarea") or 0)
                priv_area = float(row.get("privArea") or 0)
                elevator = int(float(row.get("kaptdEcntp") or 0))
            except (ValueError, TypeError):
                hhld = dong = top_flr = elevator = 0
                total_area = priv_area = 0

            use_date = str(row.get("kaptUsedate", "")).split(".")[0]

            # apt_kapt_info UPSERT
            cur.execute("""
                INSERT INTO apt_kapt_info (pnu, kapt_code, sale_type, heat_type, builder, developer,
                    apt_type, mgr_type, hall_type, total_area, priv_area, elevator_cnt)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pnu) DO UPDATE SET
                    kapt_code = EXCLUDED.kapt_code, sale_type = EXCLUDED.sale_type,
                    heat_type = EXCLUDED.heat_type, builder = EXCLUDED.builder,
                    developer = EXCLUDED.developer, apt_type = EXCLUDED.apt_type,
                    mgr_type = EXCLUDED.mgr_type, hall_type = EXCLUDED.hall_type,
                    total_area = EXCLUDED.total_area, priv_area = EXCLUDED.priv_area,
                    elevator_cnt = EXCLUDED.elevator_cnt, updated_at = NOW()
            """, [pnu, kapt_code,
                  row.get("codeSaleNm", ""), row.get("codeHeatNm", ""),
                  row.get("kaptBcompany", ""), row.get("kaptAcompany", ""),
                  row.get("codeAptNm", ""), row.get("codeMgrNm", ""),
                  row.get("codeHallNm", ""),
                  total_area if total_area > 0 else None,
                  priv_area if priv_area > 0 else None,
                  elevator if elevator > 0 else None])
            loaded += 1

            # apartments 세대수 보정 (기존보다 큰 경우만)
            if hhld > 0:
                cur.execute("""
                    UPDATE apartments SET
                        total_hhld_cnt = GREATEST(COALESCE(total_hhld_cnt, 0), %s),
                        dong_count = GREATEST(COALESCE(dong_count, 0), %s),
                        max_floor = GREATEST(COALESCE(max_floor, 0), %s),
                        use_apr_day = COALESCE(NULLIF(use_apr_day, ''), %s)
                    WHERE pnu = %s AND COALESCE(total_hhld_cnt, 0) < %s
                """, [hhld, dong, top_flr, use_date, pnu, hhld])
                if cur.rowcount > 0:
                    hhld_fixed += 1

    conn.commit()
    logger.info(f"Phase 1 완료: kapt_info={loaded}건, 세대수 보정={hhld_fixed}건")
    return loaded


# ── Phase 2: V4 상세정보 API ──

def phase2_api(conn, logger):
    """kapt_code가 있는 아파트 → V4 상세정보 API로 주차/CCTV 등 보충."""
    if not DATA_GO_KR_API_KEY:
        logger.error("DATA_GO_KR_API_KEY 미설정")
        return 0

    cur = get_dict_cursor(conn)
    targets = query_all(conn,
        "SELECT pnu, kapt_code FROM apt_kapt_info WHERE kapt_code IS NOT NULL AND kapt_code != '' AND parking_cnt IS NULL")

    logger.info(f"Phase 2 대상: {len(targets)}건")
    updated = 0
    failed = 0

    for i, row in enumerate(targets):
        try:
            resp = requests.get(V4_DETAIL_URL, params={
                "serviceKey": DATA_GO_KR_API_KEY,
                "kaptCode": row["kapt_code"],
                "type": "json",
            }, timeout=10)
            resp.raise_for_status()
            item = resp.json().get("response", {}).get("body", {}).get("item", {})
        except Exception:
            failed += 1
            time.sleep(DATA_GO_KR_RATE)
            continue

        time.sleep(DATA_GO_KR_RATE)

        if not item:
            failed += 1
            continue

        parking = int(item.get("kaptdPcntu") or 0)
        cctv = int(item.get("kaptdCccnt") or 0)
        ev_ground = int(item.get("groundElChargerCnt") or 0)
        ev_under = int(item.get("undergroundElChargerCnt") or 0)
        structure = item.get("codeStr", "")
        subway_line = item.get("subwayLine") or ""
        subway_station = item.get("subwayStation") or ""
        subway_info = f"{subway_line} {subway_station}".strip() if subway_line or subway_station else None
        bus_time = item.get("kaptdWtimebus", "")
        welfare = item.get("welfareFacility", "")

        cur.execute("""
            UPDATE apt_kapt_info SET
                parking_cnt = %s, cctv_cnt = %s, ev_charger_cnt = %s,
                structure = %s, subway_info = %s, bus_time = %s, welfare = %s,
                updated_at = NOW()
            WHERE pnu = %s
        """, [parking or None, cctv or None, (ev_ground + ev_under) or None,
              structure or None, subway_info, bus_time or None, welfare or None,
              row["pnu"]])
        updated += 1

        if (i + 1) % 500 == 0:
            conn.commit()
            logger.info(f"  진행: {i+1}/{len(targets)} (보충={updated}, 실패={failed})")

    conn.commit()
    logger.info(f"Phase 2 완료: 보충={updated}, 실패={failed}")
    return updated


# ── 신규 아파트 K-APT 매칭 (trade 배치 연동) ──

V4_BASIC_URL = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusBassInfoV4"
APT_LIST_URL = "https://apis.data.go.kr/1613000/AptListService3/getTotalAptList3"


def _load_kapt_list() -> list[dict]:
    """K-APT 전체 목록 조회 (캐시 없이 매번 API 호출)."""
    all_items = []
    page = 1
    while True:
        try:
            resp = requests.get(APT_LIST_URL, params={
                "serviceKey": DATA_GO_KR_API_KEY, "numOfRows": "1000",
                "pageNo": str(page), "type": "json",
            }, timeout=30)
            data = resp.json().get("response", {}).get("body", {})
            items = data.get("items", [])
            if not items:
                break
            if isinstance(items, dict):
                items = [items]
            all_items.extend(items)
            if len(all_items) >= (data.get("totalCount") or 0):
                break
            page += 1
            time.sleep(DATA_GO_KR_RATE)
        except Exception:
            break
    return all_items


def _fetch_kapt_basic(kapt_code: str) -> dict:
    """V4 기본정보 API 호출."""
    try:
        resp = requests.get(V4_BASIC_URL, params={
            "serviceKey": DATA_GO_KR_API_KEY, "kaptCode": kapt_code, "type": "json",
        }, timeout=10)
        return resp.json().get("response", {}).get("body", {}).get("item", {})
    except Exception:
        return {}


def _fetch_kapt_detail(kapt_code: str) -> dict:
    """V4 상세정보 API 호출."""
    try:
        resp = requests.get(V4_DETAIL_URL, params={
            "serviceKey": DATA_GO_KR_API_KEY, "kaptCode": kapt_code, "type": "json",
        }, timeout=10)
        return resp.json().get("response", {}).get("body", {}).get("item", {})
    except Exception:
        return {}


def enrich_kapt_for_new(conn, logger, pnu_list: list[str]):
    """신규 등록 아파트에 대해 K-APT 정보 매칭 + 적재."""
    if not DATA_GO_KR_API_KEY or not pnu_list:
        return 0

    # 신규 아파트 주소 조회
    ph = ",".join(["%s"] * len(pnu_list))
    new_apts = query_all(conn,
        f"SELECT pnu, new_plat_plc FROM apartments WHERE pnu IN ({ph}) AND new_plat_plc IS NOT NULL",
        pnu_list)
    if not new_apts:
        return 0

    new_addr = {_norm_addr(r["new_plat_plc"]): r["pnu"] for r in new_apts if r["new_plat_plc"]}

    # K-APT 전체 목록에서 도로명주소 매칭용 인덱스 구축
    logger.info(f"  K-APT 목록 조회 중...")
    kapt_list = _load_kapt_list()
    logger.info(f"  K-APT 목록: {len(kapt_list)}건")

    # kaptCode별 doroJuso 매칭을 위해 기본정보 API로 주소 확인
    cur = get_dict_cursor(conn)
    matched = 0

    for kapt in kapt_list:
        kapt_code = kapt.get("kaptCode")
        if not kapt_code:
            continue

        # 기본정보 조회
        basic = _fetch_kapt_basic(kapt_code)
        time.sleep(DATA_GO_KR_RATE)
        if not basic:
            continue

        doro = _norm_addr(basic.get("doroJuso", ""))
        pnu = new_addr.get(doro)
        if not pnu:
            continue

        # 이미 apt_kapt_info에 있으면 스킵
        existing = query_all(conn, "SELECT pnu FROM apt_kapt_info WHERE pnu = %s", [pnu])
        if existing:
            continue

        # 상세정보 조회
        detail = _fetch_kapt_detail(kapt_code)
        time.sleep(DATA_GO_KR_RATE)

        # 기본정보 적재
        try:
            hhld = int(basic.get("hoCnt") or 0)
            dong = int(basic.get("kaptDongCnt") or 0)
            top_flr = int(basic.get("ktownFlrNo") or 0)
            total_area = float(basic.get("kaptTarea") or 0)
            priv_area = float(basic.get("privArea") or 0)
            elevator = int(basic.get("kaptdEcntp") or 0)
        except (ValueError, TypeError):
            hhld = dong = top_flr = elevator = 0
            total_area = priv_area = 0

        parking = int(detail.get("kaptdPcntu") or 0) if detail else 0
        cctv = int(detail.get("kaptdCccnt") or 0) if detail else 0
        ev_g = int(detail.get("groundElChargerCnt") or 0) if detail else 0
        ev_u = int(detail.get("undergroundElChargerCnt") or 0) if detail else 0
        structure = detail.get("codeStr", "") if detail else ""
        subway = f"{detail.get('subwayLine','')} {detail.get('subwayStation','')}".strip() if detail else None
        bus_time = detail.get("kaptdWtimebus", "") if detail else ""
        welfare = detail.get("welfareFacility", "") if detail else ""

        cur.execute("""
            INSERT INTO apt_kapt_info (pnu, kapt_code, sale_type, heat_type, builder, developer,
                apt_type, mgr_type, hall_type, structure, total_area, priv_area,
                parking_cnt, cctv_cnt, elevator_cnt, ev_charger_cnt, subway_info, bus_time, welfare)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (pnu) DO UPDATE SET
                kapt_code=EXCLUDED.kapt_code, sale_type=EXCLUDED.sale_type,
                heat_type=EXCLUDED.heat_type, builder=EXCLUDED.builder, developer=EXCLUDED.developer,
                parking_cnt=EXCLUDED.parking_cnt, cctv_cnt=EXCLUDED.cctv_cnt,
                elevator_cnt=EXCLUDED.elevator_cnt, ev_charger_cnt=EXCLUDED.ev_charger_cnt,
                structure=EXCLUDED.structure, updated_at=NOW()
        """, [pnu, kapt_code,
              basic.get("codeSaleNm",""), basic.get("codeHeatNm",""),
              basic.get("kaptBcompany",""), basic.get("kaptAcompany",""),
              basic.get("codeAptNm",""), basic.get("codeMgrNm",""),
              basic.get("codeHallNm",""), structure or None,
              total_area or None, priv_area or None,
              parking or None, cctv or None, elevator or None,
              (ev_g + ev_u) or None, subway, bus_time or None, welfare or None])

        # apartments 세대수 보정
        if hhld > 0:
            cur.execute("""
                UPDATE apartments SET
                    total_hhld_cnt = GREATEST(COALESCE(total_hhld_cnt,0), %s),
                    dong_count = GREATEST(COALESCE(dong_count,0), %s),
                    max_floor = GREATEST(COALESCE(max_floor,0), %s)
                WHERE pnu = %s
            """, [hhld, dong, top_flr, pnu])

        matched += 1
        if matched <= 3 or matched % 10 == 0:
            logger.info(f"  K-APT 매칭: {basic.get('kaptName','')} → {pnu}")

    conn.commit()
    logger.info(f"  K-APT 신규 매칭: {matched}건")
    return matched


def main():
    parser = argparse.ArgumentParser(description="K-APT 아파트 정보 수집")
    parser.add_argument("--phase", required=True, choices=["1", "2", "all"], help="1: CSV 적재, 2: V4 상세 API, all: 1+2")
    args = parser.parse_args()

    logger = setup_logger("kapt_info")
    conn = get_connection()

    try:
        if args.phase in ("1", "all"):
            phase1_csv(conn, logger)
        if args.phase in ("2", "all"):
            phase2_api(conn, logger)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
