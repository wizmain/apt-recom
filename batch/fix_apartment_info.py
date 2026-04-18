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
from batch.trade.enrich_apartments import _name_similarity_ratio, _NAME_SIM_THRESHOLD

BLD_TITLE_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
CHECKPOINT_GROUP = "batch_checkpoint"

# Phase 2 검증 상수
KEYWORD_DIST_MAX_M = 2000  # 이름 일치 후보라도 이 거리 넘으면 오매칭 판정
KEYWORD_DIST_MIN_M = 100   # 이 거리 이하면 업데이트 불필요
ADDR_DIST_MIN_M = 100      # address API 결과도 동일


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


def _load_sigungu_name_index(cur) -> dict[tuple[str, str], str]:
    """(시도, 시군구명) → sgg_code 매핑. Kakao address_name 파싱 결과와 매칭용."""
    cur.execute("SELECT code, name, extra FROM common_code WHERE group_id='sigungu'")
    idx: dict[tuple[str, str], str] = {}
    for r in cur.fetchall():
        sido = (r["extra"] or "").strip()
        sgg = (r["name"] or "").strip()
        if not sido or not sgg:
            continue
        # 시도 다양한 표기 흡수 (예: "대구" ↔ "대구광역시")
        for sido_variant in {sido, _sido_full_name(sido)}:
            idx[(sido_variant, sgg)] = r["code"]
    return idx


def _sido_full_name(short: str) -> str:
    """짧은 시도명 → 전체명. 예: '대구' → '대구광역시'."""
    _MAP = {
        "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
        "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
        "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
        "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
        "제주": "제주특별자치도",
    }
    return _MAP.get(short, short)


def _parse_sgg_from_address(address_name: str, sgg_name_to_code: dict) -> str | None:
    """Kakao address_name → sgg_code.
    예: '대구 달서구 본리동 1224' → '27290'
        '서울특별시 강남구 역삼동 123' → '11680'
    """
    if not address_name:
        return None
    parts = address_name.split()
    if len(parts) < 2:
        return None
    sido = parts[0]
    sgg = parts[1]
    # 3depth 이상일 때 일부 도의 "OO시 OO구" 케이스: "경기 수원시 영통구" → sgg="수원시 영통구" 형태로 결합
    if len(parts) >= 3 and (parts[1].endswith("시") and parts[2].endswith("구")):
        # 수원시/성남시/안양시/안산시/고양시/용인시/청주시/천안시/전주시/포항시/창원시 등
        combined = f"{parts[1]} {parts[2]}"
        code = sgg_name_to_code.get((sido, combined))
        if code:
            return code
    return sgg_name_to_code.get((sido, sgg))


def _kakao_address_search(addr: str, headers: dict, logger) -> dict | None:
    """Address API — 정확한 주소 매칭으로 좌표만 획득 (이름 변경 없음)."""
    if not addr:
        return None
    try:
        r = requests.get(
            "https://dapi.kakao.com/v2/local/search/address.json",
            headers=headers, params={"query": addr}, timeout=5,
        )
        r.raise_for_status()
        time.sleep(KAKAO_RATE)
        docs = r.json().get("documents", [])
    except Exception as e:
        logger.debug(f"address API 실패: {addr} ({e})")
        return None

    if not docs:
        return None
    doc = docs[0]
    try:
        return {
            "lat": float(doc["y"]),
            "lng": float(doc["x"]),
            "address_name": doc.get("address_name"),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _kakao_keyword_validated(
    addr: str,
    apt: dict,
    sgg_name_to_code: dict,
    headers: dict,
    logger,
) -> dict | None:
    """Keyword API + 엄격 검증.

    검증:
      (1) category_name에 "아파트"
      (2) 시군구 일치 (Kakao address_name 파싱)
      (3) 이름 유사도 ≥ _NAME_SIM_THRESHOLD (0.4)
      (4) 기존 좌표와의 거리 ≤ KEYWORD_DIST_MAX_M (2km)
      (5) 검증 통과 후보가 정확히 1개 (애매하면 거부)

    통과시 {name, lat, lng, sim}, 실패시 None.
    """
    apt_nm = (apt.get("bld_nm") or "").strip()
    if not apt_nm:
        return None

    query = f"{addr} {apt_nm}".strip()
    try:
        r = requests.get(
            "https://dapi.kakao.com/v2/local/search/keyword.json",
            headers=headers, params={"query": query, "size": 5}, timeout=5,
        )
        r.raise_for_status()
        time.sleep(KAKAO_RATE)
        docs = r.json().get("documents", [])
    except Exception as e:
        logger.debug(f"keyword API 실패: {query} ({e})")
        return None

    apt_sgg = (apt.get("sigungu_code") or "")[:5]

    accepted = []
    for d in docs:
        # (1) 카테고리
        if "아파트" not in (d.get("category_name") or ""):
            continue

        # (2) 시군구 일치
        kk_sgg = _parse_sgg_from_address(d.get("address_name") or "", sgg_name_to_code)
        if not kk_sgg or (apt_sgg and kk_sgg != apt_sgg):
            continue

        # (3) 이름 유사도
        kakao_name = re.sub(r"아파트$", "", (d.get("place_name") or "").strip()).strip()
        if not kakao_name:
            continue
        sim = _name_similarity_ratio(kakao_name, apt_nm)
        if sim < _NAME_SIM_THRESHOLD:
            continue

        # (4) 좌표
        try:
            kk_lat = float(d["y"])
            kk_lng = float(d["x"])
        except (KeyError, TypeError, ValueError):
            continue

        if apt.get("lat") and apt.get("lng"):
            dist = _distance_m(apt["lat"], apt["lng"], kk_lat, kk_lng)
            if dist > KEYWORD_DIST_MAX_M:
                continue

        accepted.append({"name": kakao_name, "lat": kk_lat, "lng": kk_lng, "sim": sim})

    # (5) 단일 후보
    if len(accepted) == 1:
        return accepted[0]
    return None


def phase2_fix_name_coord(dry_run: bool = False):
    """Kakao API로 좌표/명칭 보정 — 엄격 검증.

    전략:
      1차) address API로 주소→좌표 (이름은 안 건드림) → coord_source='kakao_address'
      2차) keyword API 결과를 이름·시군구·거리·단일성 4중 검증 후 수용
           → coord_source='kakao_keyword_v2'

    거부 사유별로 카운트해서 투명성 확보.
    """
    logger = setup_logger("fix_name_coord")
    conn = get_connection()
    cur = get_dict_cursor(conn)

    if not KAKAO_API_KEY:
        logger.error("KAKAO_API_KEY 미설정")
        conn.close()
        return

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    sgg_name_to_code = _load_sigungu_name_index(cur)
    logger.info(f"시군구 매핑: {len(sgg_name_to_code)}건 로드")

    last_pnu = _load_checkpoint(cur, "fix_name_coord")

    cur.execute("""
        SELECT pnu, bld_nm, plat_plc, new_plat_plc, sigungu_code, lat, lng
        FROM apartments
        WHERE group_pnu = pnu
          AND (
            (new_plat_plc IS NOT NULL AND LENGTH(new_plat_plc) > 5)
            OR (plat_plc IS NOT NULL AND LENGTH(plat_plc) > 5)
          )
          AND pnu > %s
        ORDER BY pnu
    """, [last_pnu])
    targets = cur.fetchall()
    logger.info(f"Phase 2 대상: {len(targets)}건")

    name_fixed = 0
    coord_fixed_addr = 0
    coord_fixed_kw = 0
    skipped_no_result = 0

    for i, apt in enumerate(targets):
        pnu = apt["pnu"]
        addr = apt.get("new_plat_plc") or apt.get("plat_plc")

        # 1차: address API
        addr_result = _kakao_address_search(addr, headers, logger)
        # 2차: keyword API + 검증
        kw_result = _kakao_keyword_validated(addr, apt, sgg_name_to_code, headers, logger)

        if not addr_result and not kw_result:
            skipped_no_result += 1
            if (i + 1) % 1000 == 0:
                logger.info(f"  진행: {i+1}/{len(targets)} (명칭={name_fixed}, 좌표addr={coord_fixed_addr}, 좌표kw={coord_fixed_kw}, 결과없음={skipped_no_result})")
            continue

        updates = []
        params = []

        # 이름 업데이트: keyword 검증 통과한 경우만
        if kw_result and kw_result["name"] != apt["bld_nm"]:
            updates.append("bld_nm = %s")
            params.append(kw_result["name"])
            name_fixed += 1
            if name_fixed <= 5 or name_fixed % 500 == 0:
                logger.info(f"  명칭: {apt['bld_nm']} → {kw_result['name']} (sim={kw_result['sim']:.2f})")

        # 좌표 업데이트: keyword 우선, 없으면 address
        if kw_result:
            new_lat, new_lng = kw_result["lat"], kw_result["lng"]
            new_src = "kakao_keyword_v2"
        else:
            new_lat, new_lng = addr_result["lat"], addr_result["lng"]
            new_src = "kakao_address"

        need_coord_update = False
        if not apt.get("lat") or not apt.get("lng"):
            need_coord_update = True
        else:
            dist = _distance_m(apt["lat"], apt["lng"], new_lat, new_lng)
            if dist > KEYWORD_DIST_MIN_M:
                need_coord_update = True

        if need_coord_update:
            updates.extend(["lat = %s", "lng = %s", "coord_source = %s"])
            params.extend([new_lat, new_lng, new_src])
            if kw_result:
                coord_fixed_kw += 1
            else:
                coord_fixed_addr += 1

        if updates and not dry_run:
            params.append(pnu)
            cur.execute(f"UPDATE apartments SET {', '.join(updates)} WHERE pnu = %s", params)

        if (i + 1) % 50 == 0 and not dry_run:
            _save_checkpoint(cur, conn, "fix_name_coord", pnu)

        if (i + 1) % 1000 == 0:
            logger.info(f"  진행: {i+1}/{len(targets)} (명칭={name_fixed}, 좌표addr={coord_fixed_addr}, 좌표kw={coord_fixed_kw}, 결과없음={skipped_no_result})")

    if not dry_run and targets:
        _save_checkpoint(cur, conn, "fix_name_coord", targets[-1]["pnu"])
        conn.commit()

    logger.info(
        f"Phase 2 {'Dry-run' if dry_run else '완료'}: "
        f"명칭={name_fixed}, 좌표(address)={coord_fixed_addr}, 좌표(keyword)={coord_fixed_kw}, "
        f"결과없음={skipped_no_result}"
    )
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
