"""아파트 정보 보정 배치.

Phase 1: 세대수 보정 (건축물대장 API) — 세대수 50이하 또는 NULL
Phase 2: 명칭+좌표 보정 (Kakao API) — 주소 있는 전체 아파트

사용법:
  python -m batch.fix_apartment_info --phase 1 --max-calls 10000
  python -m batch.fix_apartment_info --phase 2
  python -m batch.fix_apartment_info --phase 1 --dry-run
"""

import argparse
import math
import re
import time
import xml.etree.ElementTree as ET

import requests

from batch.config import KAKAO_API_KEY, DATA_GO_KR_API_KEY, KAKAO_RATE, DATA_GO_KR_RATE
from batch.db import get_connection, get_dict_cursor
from batch.fill_addresses import _address_to_bld_params
from batch.logger import setup_logger

BLD_TITLE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
CHECKPOINT_GROUP = "batch_checkpoint"


# ── 체크포인트 ──

def _load_checkpoint(cur, code: str) -> str:
    cur.execute(
        "SELECT extra FROM common_code WHERE group_id = %s AND code = %s",
        [CHECKPOINT_GROUP, code],
    )
    row = cur.fetchone()
    return row["extra"] if row else ""


def _save_checkpoint(cur, conn, code: str, value: str):
    cur.execute(
        """INSERT INTO common_code (group_id, code, name, extra)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (group_id, code) DO UPDATE SET extra = EXCLUDED.extra""",
        [CHECKPOINT_GROUP, code, f"보정 {code} 체크포인트", value],
    )
    conn.commit()


# ── Phase 1: 세대수 보정 ──

def _fetch_hhld_from_bld_api(bld_params: dict) -> dict:
    """건축물대장 API → 세대수/동수/최고층 합산."""
    try:
        resp = requests.get(BLD_TITLE_URL, params={
            "serviceKey": DATA_GO_KR_API_KEY,
            "sigunguCd": bld_params["sigungu_cd"],
            "bjdongCd": bld_params["bjdong_cd"],
            "platGbCd": bld_params.get("plat_gb_cd", "0"),
            "bun": bld_params["bun"],
            "ji": bld_params["ji"],
            "numOfRows": "100",
            "pageNo": "1",
        }, timeout=10)
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
            h = item.findtext("hhldCnt")
            if h and h.isdigit():
                total_hhld += int(h)
            d = item.findtext("dongNm")
            if d:
                dong_set.add(d)
            f = item.findtext("grndFlrCnt")
            if f and f.isdigit():
                max_flr = max(max_flr, int(f))
            a = item.findtext("useAprDay")
            if a and (not use_apr or a < use_apr):
                use_apr = a

        return {
            "total_hhld_cnt": total_hhld if total_hhld > 0 else None,
            "dong_count": len(dong_set) if dong_set else None,
            "max_floor": max_flr if max_flr > 0 else None,
            "use_apr_day": use_apr,
        }
    except Exception:
        return {}


def _pnu_to_bld_params(pnu: str) -> dict | None:
    """정규 19자리 PNU → 건축물대장 API 파라미터 분해."""
    if len(pnu) != 19 or not pnu.isdigit():
        return None
    return {
        "sigungu_cd": pnu[:5],
        "bjdong_cd": pnu[5:10],
        "plat_gb_cd": pnu[10:11],
        "bun": pnu[11:15],
        "ji": pnu[15:19],
    }


def phase1_fix_hhld(dry_run: bool = False, max_calls: int = 10000):
    """세대수 50이하 또는 NULL인 아파트 → 건축물대장 재조회."""
    logger = setup_logger("fix_hhld")
    conn = get_connection()
    cur = get_dict_cursor(conn)

    if not DATA_GO_KR_API_KEY:
        logger.error("DATA_GO_KR_API_KEY 미설정")
        conn.close()
        return

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"} if KAKAO_API_KEY else {}

    last_pnu = _load_checkpoint(cur, "fix_hhld")

    cur.execute("""
        SELECT pnu, bld_nm, new_plat_plc, total_hhld_cnt, dong_count, max_floor
        FROM apartments
        WHERE group_pnu = pnu
          AND (total_hhld_cnt IS NULL OR total_hhld_cnt <= 50)
          AND pnu > %s
        ORDER BY pnu
    """, [last_pnu])
    targets = cur.fetchall()
    logger.info(f"Phase 1 대상: {len(targets)}건 (체크포인트 이후)")

    updated = 0
    skipped = 0
    failed = 0
    api_calls = 0

    for i, apt in enumerate(targets):
        if api_calls >= max_calls:
            logger.info(f"API 호출 한도 도달: {max_calls}")
            break

        pnu = apt["pnu"]

        # PNU → 건축물대장 파라미터
        if pnu.startswith("TRADE_"):
            addr = apt.get("new_plat_plc")
            if not addr or not headers:
                failed += 1
                continue
            bld_params = _address_to_bld_params(headers, addr, apt.get("bld_nm", ""))
            time.sleep(KAKAO_RATE)
        else:
            bld_params = _pnu_to_bld_params(pnu)

        if not bld_params:
            failed += 1
            continue

        info = _fetch_hhld_from_bld_api(bld_params)
        api_calls += 1

        if not info or not info.get("total_hhld_cnt"):
            skipped += 1
            continue

        # 기존보다 나은 경우에만 UPDATE
        old_hhld = apt.get("total_hhld_cnt") or 0
        new_hhld = info["total_hhld_cnt"] or 0
        if new_hhld <= old_hhld:
            skipped += 1
            continue

        if not dry_run:
            updates = ["total_hhld_cnt = %s"]
            params = [new_hhld]
            if info.get("dong_count") and (not apt.get("dong_count") or info["dong_count"] > apt["dong_count"]):
                updates.append("dong_count = %s")
                params.append(info["dong_count"])
            if info.get("max_floor") and (not apt.get("max_floor") or info["max_floor"] > apt["max_floor"]):
                updates.append("max_floor = %s")
                params.append(info["max_floor"])
            if info.get("use_apr_day"):
                updates.append("use_apr_day = COALESCE(NULLIF(use_apr_day, ''), %s)")
                params.append(info["use_apr_day"])
            params.append(pnu)
            cur.execute(f"UPDATE apartments SET {', '.join(updates)} WHERE pnu = %s", params)

        updated += 1
        if updated <= 5 or updated % 200 == 0:
            logger.info(f"  [{updated}] {apt['bld_nm']} | {old_hhld}→{new_hhld}세대, 동={info.get('dong_count')}, 층={info.get('max_floor')}")

        if (i + 1) % 50 == 0 and not dry_run:
            _save_checkpoint(cur, conn, "fix_hhld", pnu)

        if (i + 1) % 500 == 0:
            logger.info(f"  진행: {i+1}/{len(targets)} (보정={updated}, 스킵={skipped}, 실패={failed}, API={api_calls})")

    if not dry_run and targets and api_calls > 0:
        _save_checkpoint(cur, conn, "fix_hhld", targets[min(i, len(targets) - 1)]["pnu"])
        conn.commit()

    logger.info(f"Phase 1 {'Dry-run' if dry_run else '완료'}: 보정={updated}, 스킵={skipped}, 실패={failed}, API={api_calls}")
    conn.close()


# ── Phase 2+3: 명칭+좌표 보정 ──

def _distance_m(lat1, lng1, lat2, lng2) -> float:
    """두 좌표 간 거리 (미터)."""
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def phase2_fix_name_coord(dry_run: bool = False):
    """Kakao 키워드 검색으로 명칭+좌표 동시 보정."""
    logger = setup_logger("fix_name_coord")
    conn = get_connection()
    cur = get_dict_cursor(conn)

    if not KAKAO_API_KEY:
        logger.error("KAKAO_API_KEY 미설정")
        conn.close()
        return

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    last_pnu = _load_checkpoint(cur, "fix_name_coord")

    cur.execute("""
        SELECT pnu, bld_nm, new_plat_plc, lat, lng
        FROM apartments
        WHERE group_pnu = pnu
          AND new_plat_plc IS NOT NULL AND LENGTH(new_plat_plc) > 5
          AND pnu > %s
        ORDER BY pnu
    """, [last_pnu])
    targets = cur.fetchall()
    logger.info(f"Phase 2+3 대상: {len(targets)}건")

    name_fixed = 0
    coord_fixed = 0
    skipped = 0

    for i, apt in enumerate(targets):
        pnu = apt["pnu"]
        addr = apt["new_plat_plc"]

        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                headers=headers,
                params={"query": f"{addr} 아파트", "size": 5},
                timeout=5,
            )
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
        except Exception:
            skipped += 1
            time.sleep(KAKAO_RATE)
            continue

        time.sleep(KAKAO_RATE)

        # 아파트 카테고리 우선 선택
        apt_docs = [d for d in docs if "아파트" in (d.get("category_name") or "")]
        doc = apt_docs[0] if apt_docs else None

        if not doc:
            skipped += 1
            continue

        updates = []
        params = []

        # 명칭 보정
        kakao_name = (doc.get("place_name") or "").strip()
        kakao_name = re.sub(r"아파트$", "", kakao_name).strip()
        if kakao_name and kakao_name != apt["bld_nm"] and len(kakao_name) >= 2:
            updates.append("bld_nm = %s")
            params.append(kakao_name)
            name_fixed += 1
            if name_fixed <= 5 or name_fixed % 500 == 0:
                logger.info(f"  명칭: {apt['bld_nm']} → {kakao_name}")

        # 좌표 보정
        kakao_lat = float(doc["y"]) if doc.get("y") else None
        kakao_lng = float(doc["x"]) if doc.get("x") else None

        if kakao_lat and kakao_lng:
            if not apt["lat"] or not apt["lng"]:
                updates.append("lat = %s")
                params.append(kakao_lat)
                updates.append("lng = %s")
                params.append(kakao_lng)
                coord_fixed += 1
            else:
                dist = _distance_m(apt["lat"], apt["lng"], kakao_lat, kakao_lng)
                if dist > 100:
                    updates.append("lat = %s")
                    params.append(kakao_lat)
                    updates.append("lng = %s")
                    params.append(kakao_lng)
                    coord_fixed += 1
                    if coord_fixed <= 5 or coord_fixed % 500 == 0:
                        logger.info(f"  좌표: {apt['bld_nm']} | {dist:.0f}m 보정")

        if updates and not dry_run:
            params.append(pnu)
            cur.execute(f"UPDATE apartments SET {', '.join(updates)} WHERE pnu = %s", params)

        if (i + 1) % 50 == 0 and not dry_run:
            _save_checkpoint(cur, conn, "fix_name_coord", pnu)

        if (i + 1) % 1000 == 0:
            logger.info(f"  진행: {i+1}/{len(targets)} (명칭={name_fixed}, 좌표={coord_fixed}, 스킵={skipped})")

    if not dry_run and targets:
        _save_checkpoint(cur, conn, "fix_name_coord", targets[-1]["pnu"])
        conn.commit()

    logger.info(f"Phase 2+3 {'Dry-run' if dry_run else '완료'}: 명칭={name_fixed}, 좌표={coord_fixed}, 스킵={skipped}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="아파트 정보 보정")
    parser.add_argument("--phase", type=int, required=True, choices=[1, 2], help="1: 세대수, 2: 명칭+좌표")
    parser.add_argument("--dry-run", action="store_true", help="DB 반영 없이 확인")
    parser.add_argument("--max-calls", type=int, default=10000, help="Phase 1: API 호출 한도")
    args = parser.parse_args()

    if args.phase == 1:
        phase1_fix_hhld(dry_run=args.dry_run, max_calls=args.max_calls)
    elif args.phase == 2:
        phase2_fix_name_coord(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
