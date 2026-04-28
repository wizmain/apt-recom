"""K-APT 기본정보/면적 엑셀 → 신규 아파트 일괄 등록.

사용법:
  python -m batch.kapt.register_new_apartments --dry-run   # 건수만 확인
  python -m batch.kapt.register_new_apartments              # 실제 등록
  python -m batch.kapt.register_new_apartments --limit 100  # 100건만 테스트
  python -m batch.kapt.register_new_apartments --reset      # 체크포인트 초기화
"""

import argparse
import json
import math
import time
from pathlib import Path

import requests

from batch.config import KAKAO_API_KEY, KAKAO_RATE
from batch.db import get_connection, get_dict_cursor
from batch.logger import setup_logger

# ── 파일 경로 ──

DATA_DIR = Path(__file__).resolve().parents[2] / "apt_eda" / "data" / "관리비자료"
BASIC_XLSX = DATA_DIR / "20260403_단지_기본정보.xlsx"
AREA_XLSX = DATA_DIR / "20260403_단지_면적정보.xlsx"

CHECKPOINT_DIR = Path(__file__).resolve().parents[1] / "data"
CHECKPOINT_FILE = CHECKPOINT_DIR / "register_checkpoint.json"

# ── Kakao API ──

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_TIMEOUT = 5
MAX_RETRIES = 2
RETRY_BACKOFFS = [1, 2]


# 승강기 컬럼
def _safe_int(val, default=0):
    """NaN-safe 정수 변환."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


ELEVATOR_COLS = [
    "승강기(승객용)",
    "승강기(화물용)",
    "승강기(승객+화물)",
    "승강기(장애인)",
    "승강기(비상용)",
    "승강기(기타)",
]


def _kakao_get(url, params, headers):
    """Kakao API 호출 with rate limit + retry."""
    for attempt in range(1 + MAX_RETRIES):
        try:
            time.sleep(KAKAO_RATE)
            resp = requests.get(
                url, headers=headers, params=params, timeout=KAKAO_TIMEOUT
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503) and attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFFS[attempt])
                continue
            return None
        except requests.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFFS[attempt])
                continue
            return None
    return None


def geocode_address(address, name, headers):
    """주소 → {pnu, lat, lng, bjd_code, sigungu_code, plat_plc, new_plat_plc, kakao_name} 또는 None.

    kakao_name 은 keyword 검색이 성공했을 때 카카오의 place_name(사용자 친화 표기).
    address API fallback 으로 좌표만 얻은 경우에는 None.
    """
    lat, lng, new_plat, plat = None, None, None, None
    kakao_name = None

    # 1. 키워드 검색
    query = f"{address} {name} 아파트" if name else address
    data = _kakao_get(KAKAO_KEYWORD_URL, {"query": query, "size": 5}, headers)
    if data:
        docs = data.get("documents", [])
        if docs:
            apt_docs = [d for d in docs if "아파트" in (d.get("category_name") or "")]
            doc = apt_docs[0] if apt_docs else docs[0]
            new_plat = doc.get("road_address_name") or None
            plat = doc.get("address_name") or None
            lat = float(doc["y"]) if doc.get("y") else None
            lng = float(doc["x"]) if doc.get("x") else None
            kakao_name = doc.get("place_name") or None

    # fallback: 주소 검색
    if not lat:
        data2 = _kakao_get(KAKAO_ADDRESS_URL, {"query": address, "size": 1}, headers)
        if data2:
            docs2 = data2.get("documents", [])
            if docs2:
                doc = docs2[0]
                road = doc.get("road_address")
                new_plat = road["address_name"] if road else doc.get("address_name")
                plat = doc.get("address_name") or None
                lat = float(doc["y"]) if doc.get("y") else None
                lng = float(doc["x"]) if doc.get("x") else None

    if not lat or not lng:
        return None

    # 2. 주소 → b_code
    resolved = new_plat or plat
    if not resolved:
        return None

    data3 = _kakao_get(KAKAO_ADDRESS_URL, {"query": resolved, "size": 1}, headers)
    if not data3:
        return None
    docs3 = data3.get("documents", [])
    if not docs3:
        return None

    addr_info = docs3[0].get("address")
    if not addr_info:
        return None

    b_code = addr_info.get("b_code", "")
    if len(b_code) < 10:
        return None

    main_no = addr_info.get("main_address_no", "0")
    sub_no = addr_info.get("sub_address_no", "0") or "0"
    mountain = addr_info.get("mountain_yn", "N")

    # 3. PNU 조합
    sigungu = b_code[:5]
    bjdong = b_code[5:10]
    plat_gb = "1" if mountain == "Y" else "0"
    bun = str(main_no).zfill(4)
    ji = str(sub_no).zfill(4)
    pnu = sigungu + bjdong + plat_gb + bun + ji

    return {
        "pnu": pnu,
        "lat": lat,
        "lng": lng,
        "bjd_code": b_code[:10],
        "sigungu_code": sigungu,
        "plat_plc": plat,
        "new_plat_plc": new_plat,
        "kakao_name": kakao_name,
    }


def load_checkpoint():
    """체크포인트 파일에서 처리 완료된 kapt_code set 로드."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return set(json.load(f))
    return set()


def save_checkpoint(done_codes):
    """체크포인트 저장."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(list(done_codes), f)


def main():
    import pandas as pd

    parser = argparse.ArgumentParser(
        description="K-APT 기본정보/면적 엑셀 → 신규 아파트 등록"
    )
    parser.add_argument("--dry-run", action="store_true", help="건수만 확인")
    parser.add_argument("--limit", type=int, default=0, help="최대 N건 처리 (0=전체)")
    parser.add_argument("--reset", action="store_true", help="체크포인트 초기화")
    args = parser.parse_args()

    logger = setup_logger("register_apts")
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    if not KAKAO_API_KEY:
        logger.error("KAKAO_API_KEY 환경변수가 설정되지 않았습니다.")
        return

    if args.reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        logger.info("체크포인트 초기화됨")

    # 1. 엑셀 로드
    logger.info("엑셀 로드 중...")
    df_basic = pd.read_excel(BASIC_XLSX, header=1)
    df_area = pd.read_excel(AREA_XLSX, header=1)
    logger.info(f"  기본정보: {len(df_basic):,}건, 면적: {len(df_area):,}건")

    # 면적 → 세대수 매핑
    area_agg = df_area.groupby("단지코드").agg({"세대수": "sum"}).reset_index()
    area_map = {str(r["단지코드"]): int(r["세대수"]) for _, r in area_agg.iterrows()}

    # 2. DB 기존 매핑 조회
    conn = get_connection()
    cur = get_dict_cursor(conn)

    cur.execute("SELECT kapt_code FROM apt_kapt_info WHERE kapt_code IS NOT NULL")
    existing_kapt = {r["kapt_code"] for r in cur.fetchall()}
    logger.info(f"  DB 기존 kapt_code: {len(existing_kapt):,}건")

    # 3. 미등록 단지 필터
    checkpoint = load_checkpoint()
    targets = []
    for _, row in df_basic.iterrows():
        kc = str(row.get("단지코드", ""))
        if kc and kc not in existing_kapt and kc not in checkpoint:
            targets.append(row)

    logger.info(
        f"  신규 등록 대상: {len(targets):,}건 (체크포인트 제외: {len(checkpoint):,}건)"
    )

    if args.dry_run:
        logger.info("Dry-run 모드: DB 변경 없음")
        conn.close()
        return

    if args.limit > 0:
        targets = targets[: args.limit]
        logger.info(f"  --limit {args.limit}: {len(targets):,}건만 처리")

    # 4. 등록 실행
    registered = 0
    skipped = 0
    errors = []
    t0 = time.time()

    for i, row in enumerate(targets):
        kapt_code = str(row.get("단지코드", ""))
        name = str(row.get("단지명", ""))
        address = str(row.get("법정동주소", ""))
        road_address = str(row.get("도로명주소", ""))

        addr = road_address if road_address and road_address != "nan" else address
        if not addr or addr == "nan":
            errors.append(f"주소 없음: {name} ({kapt_code})")
            checkpoint.add(kapt_code)
            continue

        geo = geocode_address(addr, name, headers)
        if not geo:
            errors.append(f"지오코딩 실패: {name} ({kapt_code})")
            checkpoint.add(kapt_code)
            continue

        pnu = geo["pnu"]

        # PNU 충돌 확인
        cur.execute("SELECT kapt_code FROM apt_kapt_info WHERE pnu = %s", [pnu])
        existing = cur.fetchone()
        if existing and existing["kapt_code"] != kapt_code:
            errors.append(
                f"PNU 충돌: {name}({kapt_code}) vs 기존({existing['kapt_code']}) → {pnu}"
            )
            checkpoint.add(kapt_code)
            skipped += 1
            continue

        # apartments UPSERT
        hhld = area_map.get(kapt_code, 0) or _safe_int(row.get("세대수"))
        dong = _safe_int(row.get("동수"))
        max_floor = _safe_int(row.get("최고층수(건축물대장상)")) or _safe_int(
            row.get("최고층수")
        )
        use_apr = str(row.get("사용승인일", "") or "")
        if use_apr == "nan":
            use_apr = ""
        elevator_cnt = sum(_safe_int(row.get(c)) for c in ELEVATOR_COLS)

        cur.execute(
            """INSERT INTO apartments
               (pnu, bld_nm, display_name, total_hhld_cnt, dong_count, max_floor,
                use_apr_day, plat_plc, new_plat_plc, bjd_code,
                sigungu_code, lat, lng, group_pnu)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (pnu) DO UPDATE SET
                 bld_nm = COALESCE(NULLIF(EXCLUDED.bld_nm,''), apartments.bld_nm),
                 display_name = COALESCE(NULLIF(EXCLUDED.display_name,''), apartments.display_name),
                 total_hhld_cnt = COALESCE(NULLIF(EXCLUDED.total_hhld_cnt,0), apartments.total_hhld_cnt),
                 lat = COALESCE(EXCLUDED.lat, apartments.lat),
                 lng = COALESCE(EXCLUDED.lng, apartments.lng)""",
            [
                pnu,
                name,
                geo.get("kakao_name") or name,
                hhld,
                dong,
                max_floor,
                use_apr,
                geo["plat_plc"],
                geo["new_plat_plc"],
                geo["bjd_code"],
                geo["sigungu_code"],
                geo["lat"],
                geo["lng"],
                pnu,
            ],
        )

        # apt_kapt_info INSERT (PNU 충돌 없는 경우만 도달)
        cur.execute(
            """INSERT INTO apt_kapt_info
               (pnu, kapt_code, sale_type, heat_type, builder, developer,
                mgr_type, hall_type, structure, parking_cnt, cctv_cnt, elevator_cnt)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (pnu) DO UPDATE SET
                 kapt_code = EXCLUDED.kapt_code""",
            [
                pnu,
                kapt_code,
                str(row.get("분양형태", "") or ""),
                str(row.get("난방방식", "") or ""),
                str(row.get("시공사", "") or ""),
                str(row.get("시행사", "") or ""),
                str(row.get("관리방식", "") or ""),
                str(row.get("복도유형", "") or ""),
                str(row.get("건물구조", "") or ""),
                _safe_int(row.get("총주차대수")),
                _safe_int(row.get("CCTV대수")),
                elevator_cnt,
            ],
        )

        registered += 1
        checkpoint.add(kapt_code)

        if registered % 100 == 0:
            conn.commit()
            save_checkpoint(checkpoint)
            elapsed = time.time() - t0
            rate = registered / elapsed if elapsed > 0 else 0
            remaining = (len(targets) - i - 1) / rate if rate > 0 else 0
            logger.info(
                f"  진행: {registered:,}/{len(targets):,}건 등록 "
                f"(스킵 {skipped}, 에러 {len(errors)}, "
                f"{elapsed:.0f}초, 남은 ~{remaining:.0f}초)"
            )

    conn.commit()
    save_checkpoint(checkpoint)
    elapsed = time.time() - t0

    logger.info("")
    logger.info(f"등록 완료: {registered:,}건 ({elapsed:.0f}초)")
    logger.info(f"스킵 (PNU 충돌): {skipped:,}건")
    logger.info(f"에러: {len(errors):,}건")

    if errors:
        logger.info("에러 목록 (상위 20건):")
        for e in errors[:20]:
            logger.info(f"  - {e}")

    conn.close()


if __name__ == "__main__":
    main()
