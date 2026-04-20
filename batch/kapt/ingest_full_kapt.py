"""K-APT 기본정보 + 면적정보 엑셀 전체 재적재.

두 엑셀을 권위 있는 소스로 삼아 다음 테이블을 갱신:
  - apt_kapt_info  : 기본정보 엑셀 전 컬럼 UPSERT
  - apartments     : total_hhld_cnt / dong_count / max_floor / use_apr_day 덮어쓰기
  - apt_area_type  : 면적 엑셀 주택형별 row UPSERT (신규 테이블)
  - apt_area_info  : 주택형별 집계로 구간·평균·min/max 재계산

사용법:
  python -m batch.kapt.ingest_full_kapt \\
      --basic-file apt_eda/data/k-apt/20260417_단지_기본정보.xlsx \\
      --area-file  apt_eda/data/k-apt/20260417_단지_면적정보.xlsx
  python -m batch.kapt.ingest_full_kapt ... --dry-run           # 건수만
  python -m batch.kapt.ingest_full_kapt ... --register-new      # 미매핑 단지 자동 등록
  python -m batch.kapt.ingest_full_kapt ... --limit 100         # 테스트용
  python -m batch.kapt.ingest_full_kapt ... --reset             # 체크포인트 초기화

Railway 적재:
  python -m batch.push_table_to_railway apt_kapt_info
  python -m batch.push_table_to_railway apt_area_type
  python -m batch.push_table_to_railway apt_area_info
  python -m batch.push_apartments_to_railway --upsert
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from batch.config import KAKAO_API_KEY
from batch.db import get_connection, get_dict_cursor
from batch.kapt.register_new_apartments import geocode_address
from batch.logger import setup_logger

CHECKPOINT_DIR = Path(__file__).resolve().parents[1] / "data"
CHECKPOINT_FILE = CHECKPOINT_DIR / "ingest_full_kapt_checkpoint.json"
ERRORS_FILE = CHECKPOINT_DIR / "ingest_full_kapt_errors.log"

BATCH_COMMIT = 500

# 기본정보 엑셀 → apt_kapt_info 컬럼 매핑.
# (엑셀 컬럼, DB 컬럼, 변환기) — 변환기는 str/int 선택.
_STR = "str"
_INT = "int"

KAPT_INFO_MAPPING: list[tuple[str, str, str]] = [
    ("단지분류", "apt_type", _STR),
    ("분양형태", "sale_type", _STR),
    ("사용승인일", "use_date", _STR),
    ("가입일", "joined_date", _STR),
    ("동수", "dong_cnt", _INT),
    ("세대수", "ho_cnt", _INT),
    ("분양세대수", "sale_ho_cnt", _INT),
    ("임대세대수", "rent_ho_cnt", _INT),
    ("임대세대수(공공)", "rent_public_cnt", _INT),
    ("임대세대수(민간)", "rent_private_cnt", _INT),
    ("관리방식", "mgr_type", _STR),
    ("난방방식", "heat_type", _STR),
    ("복도유형", "hall_type", _STR),
    ("시공사", "builder", _STR),
    ("시행사", "developer", _STR),
    ("주택관리업자", "mgmt_company", _STR),
    ("일반관리-관리방식", "general_mgmt_type", _STR),
    ("일반관리-인원", "general_mgmt_staff", _INT),
    ("경비관리-관리방식", "security_type", _STR),
    ("경비관리-인원", "security_staff", _INT),
    ("경비관리-계약업체", "security_company", _STR),
    ("청소관리-인원", "cleaning_staff", _INT),
    ("음식물 처리방법", "food_waste_method", _STR),
    ("건물구조", "structure", _STR),
    ("최고층수", "top_floor", _INT),
    ("최고층수(건축물대장상)", "top_floor_official", _INT),
    ("지하층수", "base_floor", _INT),
    ("승강기관리-관리방식", "elevator_mgr_type", _STR),
    ("승강기(승객용)", "elevator_passenger", _INT),
    ("승강기(화물용)", "elevator_freight", _INT),
    ("승강기(승객+화물)", "elevator_mixed", _INT),
    ("승강기(장애인)", "elevator_disabled", _INT),
    ("승강기(비상용)", "elevator_emergency", _INT),
    ("총주차대수", "parking_cnt", _INT),
    ("지상주차대수", "parking_ground", _INT),
    ("지하주차대수", "parking_underground", _INT),
    ("차량보유대수(전체)", "total_car_cnt", _INT),
    ("차량보유대수(전기차)", "ev_car_cnt", _INT),
    ("전기차 충전시설 설치대수(지상)", "ev_charger_ground", _INT),
    ("전기차 충전시설 설치대수(지하)", "ev_charger_underground", _INT),
    ("전기차전용주차면수(지상)", "ev_parking_ground", _INT),
    ("전기차전용주차면수(지하)", "ev_parking_underground", _INT),
    ("CCTV대수", "cctv_cnt", _INT),
    ("홈네트워크", "home_network", _STR),
    ("부대복리시설", "welfare", _STR),
    ("입주편의시설", "convenience_facilities", _STR),
    ("법정동주소", "jibun_addr", _STR),
    ("도로명주소", "road_addr", _STR),
    ("관리사무소 연락처", "tel", _STR),
    ("관리사무소 팩스", "fax", _STR),
    ("우편번호", "zipcode", _STR),
]

# 엘리베이터 6종(총합 → elevator_cnt)
ELEVATOR_COLS = [
    "승강기(승객용)", "승강기(화물용)", "승강기(승객+화물)",
    "승강기(장애인)", "승강기(비상용)", "승강기(기타)",
]

# apt_area_info 재계산용 구간 경계 (㎡)
AREA_BUCKETS = [
    ("cnt_under_40", 0, 40),
    ("cnt_40_60", 40, 60),
    ("cnt_60_85", 60, 85),
    ("cnt_85_115", 85, 115),
    ("cnt_115_135", 115, 135),
    ("cnt_over_135", 135, float("inf")),
]


def _safe_int(val, default=0):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_float(val, default=None):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_str(val, default=""):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    s = str(val).strip()
    return default if s in ("", "nan", "None") else s


def _convert(val, kind: str):
    if kind == _INT:
        return _safe_int(val)
    v = _safe_str(val)
    return v if v else None


def load_checkpoint() -> set[str]:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return set(json.load(f))
    return set()


def save_checkpoint(done: set[str]) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(list(done), f)


def append_error(msg: str) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    with open(ERRORS_FILE, "a") as f:
        f.write(msg + "\n")


# ── Phase A: apt_kapt_info + apartments UPSERT ──

def build_kapt_row(row, kapt_code: str, pnu: str) -> dict:
    """엑셀 row → apt_kapt_info INSERT 파라미터 dict."""
    out = {"pnu": pnu, "kapt_code": kapt_code, "kapt_name": _safe_str(row.get("단지명"))}
    for excel_col, db_col, kind in KAPT_INFO_MAPPING:
        out[db_col] = _convert(row.get(excel_col), kind)
    out["elevator_cnt"] = sum(_safe_int(row.get(c)) for c in ELEVATOR_COLS)
    # sigungu_code는 pnu 앞 5자리
    out["sigungu_code"] = pnu[:5] if pnu else None
    return out


def phase_a_kapt_info(conn, logger, basic_rows, kapt_pnu_map, area_hhld_map, checkpoint, limit):
    """기본정보 엑셀 → apt_kapt_info UPSERT + apartments 핵심 컬럼 덮어쓰기."""
    cur = conn.cursor()
    upsert_kapt = _build_kapt_upsert_sql()

    targets = []
    for row in basic_rows:
        kc = _safe_str(row.get("단지코드"))
        if kc and kc in kapt_pnu_map and kc not in checkpoint:
            targets.append(row)
    logger.info(f"[Phase A] 대상 {len(targets):,}건 (매핑된 kapt_code 기준)")

    if limit > 0:
        targets = targets[:limit]
        logger.info(f"  --limit {limit}: {len(targets):,}건만 처리")

    processed = 0
    apt_updated = 0
    errors = 0
    t0 = time.time()

    for row in targets:
        kapt_code = _safe_str(row.get("단지코드"))
        pnu = kapt_pnu_map[kapt_code]
        try:
            params = build_kapt_row(row, kapt_code, pnu)
            cur.execute(upsert_kapt, params)

            # apartments 핵심 컬럼 덮어쓰기. K-APT가 권위.
            hhld = area_hhld_map.get(kapt_code, 0) or params.get("ho_cnt") or 0
            dong = params.get("dong_cnt") or 0
            max_fl = params.get("top_floor_official") or params.get("top_floor") or 0
            use_day = params.get("use_date") or ""

            if hhld or dong or max_fl or use_day:
                cur.execute(
                    """
                    UPDATE apartments SET
                      total_hhld_cnt = CASE WHEN %s > 0 THEN %s ELSE total_hhld_cnt END,
                      dong_count    = CASE WHEN %s > 0 THEN %s ELSE dong_count END,
                      max_floor     = CASE WHEN %s > 0 THEN %s ELSE max_floor END,
                      use_apr_day   = CASE WHEN %s <> '' THEN %s ELSE use_apr_day END
                    WHERE pnu = %s
                    """,
                    [hhld, hhld, dong, dong, max_fl, max_fl, use_day, use_day, pnu],
                )
                if cur.rowcount:
                    apt_updated += 1

            checkpoint.add(kapt_code)
            processed += 1
        except Exception as e:
            errors += 1
            append_error(f"[PhaseA] {kapt_code}: {e}")

        if processed % BATCH_COMMIT == 0 and processed > 0:
            conn.commit()
            save_checkpoint(checkpoint)
            elapsed = time.time() - t0
            logger.info(
                f"  진행: {processed:,}/{len(targets):,}건 "
                f"(apartments 갱신 {apt_updated:,}, 에러 {errors}, {elapsed:.0f}초)"
            )

    conn.commit()
    save_checkpoint(checkpoint)
    logger.info(f"[Phase A] 완료: kapt_info UPSERT {processed:,}건, apartments 갱신 {apt_updated:,}건, 에러 {errors}건")


def _build_kapt_upsert_sql() -> str:
    """apt_kapt_info UPSERT SQL 생성."""
    cols = ["pnu", "kapt_code", "kapt_name", "sigungu_code"]
    cols += [db_col for _, db_col, _ in KAPT_INFO_MAPPING]
    cols.append("elevator_cnt")
    cols.append("updated_at")

    placeholders = ", ".join(
        "NOW()" if c == "updated_at" else f"%({c})s" for c in cols
    )
    col_list = ", ".join(cols)
    non_pk = [c for c in cols if c != "pnu"]
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_pk)

    return f"""
        INSERT INTO apt_kapt_info ({col_list}) VALUES ({placeholders})
        ON CONFLICT (pnu) DO UPDATE SET {update_set}
    """


# ── Phase B: apt_area_type UPSERT + apt_area_info 재계산 ──

def phase_b_area(conn, logger, area_rows, kapt_pnu_map, limit):
    """면적 엑셀 → apt_area_type UPSERT + apt_area_info 재계산."""
    cur = conn.cursor()

    # 1) apt_area_type UPSERT
    targets = []
    for row in area_rows:
        kc = _safe_str(row.get("단지코드"))
        pnu = kapt_pnu_map.get(kc)
        if not pnu:
            continue
        ea = _safe_float(row.get("주거전용면적(세부)"))
        uc = _safe_int(row.get("세대수"))
        if ea is None or ea <= 0 or uc <= 0:
            continue
        targets.append((pnu, ea, uc,
                        _safe_float(row.get("관리비부과면적")),
                        _safe_float(row.get("주거전용면적(단지합계)"))))
    logger.info(f"[Phase B] apt_area_type 대상 {len(targets):,}건")

    if limit > 0:
        targets = targets[:limit]

    # 재계산 대상 pnu 집합
    affected_pnus: set[str] = set()
    upserted = 0
    for pnu, ea, uc, mgmt, priv in targets:
        try:
            cur.execute(
                """
                INSERT INTO apt_area_type
                  (pnu, exclusive_area, unit_count, mgmt_area_total, priv_area_total, last_refreshed)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (pnu, exclusive_area) DO UPDATE SET
                  unit_count = EXCLUDED.unit_count,
                  mgmt_area_total = EXCLUDED.mgmt_area_total,
                  priv_area_total = EXCLUDED.priv_area_total,
                  last_refreshed = EXCLUDED.last_refreshed
                """,
                [pnu, ea, uc, mgmt, priv],
            )
            upserted += 1
            affected_pnus.add(pnu)
        except Exception as e:
            append_error(f"[PhaseB:area_type] pnu={pnu} ea={ea}: {e}")

        if upserted % BATCH_COMMIT == 0 and upserted > 0:
            conn.commit()
            logger.info(f"  area_type 진행: {upserted:,}/{len(targets):,}건")

    conn.commit()
    logger.info(f"[Phase B] apt_area_type 완료: {upserted:,}건 UPSERT, {len(affected_pnus):,}개 pnu")

    # 2) apt_area_info 재계산 (affected_pnus)
    recalc = 0
    for pnu in affected_pnus:
        try:
            rows = cur.execute if False else None  # placeholder for type checker
            dict_cur = get_dict_cursor(conn)
            dict_cur.execute(
                "SELECT exclusive_area, unit_count FROM apt_area_type WHERE pnu = %s",
                [pnu],
            )
            types = dict_cur.fetchall()
            if not types:
                continue

            total_units = sum(r["unit_count"] for r in types)
            if total_units == 0:
                continue

            areas = [r["exclusive_area"] for r in types]
            min_a, max_a = min(areas), max(areas)
            weighted_avg = sum(r["exclusive_area"] * r["unit_count"] for r in types) / total_units

            bucket_cnt = {name: 0 for name, _, _ in AREA_BUCKETS}
            for r in types:
                ea = r["exclusive_area"]
                for name, lo, hi in AREA_BUCKETS:
                    if lo <= ea < hi:
                        bucket_cnt[name] += r["unit_count"]
                        break

            cur.execute(
                """
                INSERT INTO apt_area_info
                  (pnu, min_area, max_area, avg_area, unit_count, area_types,
                   cnt_under_40, cnt_40_60, cnt_60_85, cnt_85_115, cnt_115_135, cnt_over_135,
                   source, last_refreshed)
                VALUES (%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s, 'kapt_area', NOW())
                ON CONFLICT (pnu) DO UPDATE SET
                  min_area = EXCLUDED.min_area,
                  max_area = EXCLUDED.max_area,
                  avg_area = EXCLUDED.avg_area,
                  unit_count = EXCLUDED.unit_count,
                  area_types = EXCLUDED.area_types,
                  cnt_under_40 = EXCLUDED.cnt_under_40,
                  cnt_40_60 = EXCLUDED.cnt_40_60,
                  cnt_60_85 = EXCLUDED.cnt_60_85,
                  cnt_85_115 = EXCLUDED.cnt_85_115,
                  cnt_115_135 = EXCLUDED.cnt_115_135,
                  cnt_over_135 = EXCLUDED.cnt_over_135,
                  source = 'kapt_area',
                  last_refreshed = NOW()
                """,
                [
                    pnu, min_a, max_a, round(weighted_avg, 2), total_units, len(types),
                    bucket_cnt["cnt_under_40"], bucket_cnt["cnt_40_60"], bucket_cnt["cnt_60_85"],
                    bucket_cnt["cnt_85_115"], bucket_cnt["cnt_115_135"], bucket_cnt["cnt_over_135"],
                ],
            )
            recalc += 1
        except Exception as e:
            append_error(f"[PhaseB:area_info] pnu={pnu}: {e}")

        if recalc % BATCH_COMMIT == 0 and recalc > 0:
            conn.commit()
            logger.info(f"  area_info 재계산: {recalc:,}/{len(affected_pnus):,}건")

    conn.commit()
    logger.info(f"[Phase B] apt_area_info 재계산 완료: {recalc:,}건")


# ── Phase C: 미매핑 단지 자동 등록 ──

def phase_c_register_new(conn, logger, basic_rows, kapt_pnu_map, limit):
    """미매핑 kapt_code → 지오코딩 후 apartments + apt_kapt_info INSERT."""
    if not KAKAO_API_KEY:
        logger.warning("[Phase C] KAKAO_API_KEY 없음 → 스킵")
        return {}

    cur = conn.cursor()
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    unmapped = []
    for row in basic_rows:
        kc = _safe_str(row.get("단지코드"))
        if kc and kc not in kapt_pnu_map:
            unmapped.append(row)
    logger.info(f"[Phase C] 미매핑 단지 {len(unmapped):,}건")

    if limit > 0:
        unmapped = unmapped[:limit]

    registered = 0
    skipped = 0
    errors = 0
    new_mapping: dict[str, str] = {}
    t0 = time.time()

    for row in unmapped:
        kapt_code = _safe_str(row.get("단지코드"))
        name = _safe_str(row.get("단지명"))
        addr = _safe_str(row.get("도로명주소")) or _safe_str(row.get("법정동주소"))

        if not addr:
            errors += 1
            append_error(f"[PhaseC] 주소 없음: {name}({kapt_code})")
            continue

        geo = geocode_address(addr, name, headers)
        if not geo:
            errors += 1
            append_error(f"[PhaseC] 지오코딩 실패: {name}({kapt_code})")
            continue

        pnu = geo["pnu"]

        # PNU 충돌 체크
        cur.execute("SELECT kapt_code FROM apt_kapt_info WHERE pnu = %s", [pnu])
        existing = cur.fetchone()
        if existing and existing[0] and existing[0] != kapt_code:
            skipped += 1
            append_error(
                f"[PhaseC] PNU 충돌: {name}({kapt_code}) vs 기존({existing[0]}) pnu={pnu}"
            )
            continue

        try:
            cur.execute(
                """
                INSERT INTO apartments
                  (pnu, bld_nm, plat_plc, new_plat_plc, bjd_code,
                   sigungu_code, lat, lng, group_pnu)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (pnu) DO UPDATE SET
                  bld_nm = COALESCE(NULLIF(EXCLUDED.bld_nm,''), apartments.bld_nm),
                  lat = COALESCE(EXCLUDED.lat, apartments.lat),
                  lng = COALESCE(EXCLUDED.lng, apartments.lng)
                """,
                [pnu, name, geo["plat_plc"], geo["new_plat_plc"], geo["bjd_code"],
                 geo["sigungu_code"], geo["lat"], geo["lng"], pnu],
            )

            # 먼저 껍데기 row를 만들어 Phase A에서 UPSERT가 ON CONFLICT(pnu)에 걸리게
            cur.execute(
                """
                INSERT INTO apt_kapt_info (pnu, kapt_code, kapt_name, sigungu_code, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (pnu) DO UPDATE SET kapt_code = EXCLUDED.kapt_code
                """,
                [pnu, kapt_code, name, geo["sigungu_code"]],
            )

            new_mapping[kapt_code] = pnu
            registered += 1
        except Exception as e:
            errors += 1
            append_error(f"[PhaseC] INSERT 실패 {kapt_code}: {e}")

        if registered % 100 == 0 and registered > 0:
            conn.commit()
            elapsed = time.time() - t0
            logger.info(f"  신규 등록 진행: {registered:,}/{len(unmapped):,} ({elapsed:.0f}초)")

    conn.commit()
    logger.info(
        f"[Phase C] 완료: 신규 {registered:,}건, PNU 충돌 {skipped:,}건, 에러 {errors:,}건"
    )
    return new_mapping


# ── 메인 ──

def main():
    import pandas as pd

    parser = argparse.ArgumentParser(description="K-APT 기본+면적 엑셀 전체 재적재")
    parser.add_argument("--basic-file", required=True, help="기본정보 엑셀 경로")
    parser.add_argument("--area-file", required=True, help="면적정보 엑셀 경로")
    parser.add_argument("--register-new", action="store_true", help="미매핑 단지 자동 등록(지오코딩)")
    parser.add_argument("--dry-run", action="store_true", help="건수만 확인")
    parser.add_argument("--limit", type=int, default=0, help="각 Phase 최대 N건")
    parser.add_argument("--reset", action="store_true", help="체크포인트 초기화")
    args = parser.parse_args()

    logger = setup_logger("ingest_full_kapt")

    if args.reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        logger.info("체크포인트 초기화됨")

    # 엑셀 로드
    logger.info("엑셀 로드 중...")
    df_basic = pd.read_excel(args.basic_file, header=1)
    df_area = pd.read_excel(args.area_file, header=1)
    logger.info(f"  기본정보: {len(df_basic):,}행, 면적: {len(df_area):,}행")

    # 면적 엑셀의 단지별 세대수 합 (ho_cnt fallback)
    area_agg = df_area.groupby("단지코드").agg({"세대수": "sum"}).reset_index()
    area_hhld_map = {_safe_str(r["단지코드"]): int(r["세대수"]) for _, r in area_agg.iterrows()}

    basic_rows = list(df_basic.to_dict("records"))
    area_rows = list(df_area.to_dict("records"))

    # DB 매핑 조회
    conn = get_connection()
    cur = get_dict_cursor(conn)
    cur.execute("SELECT kapt_code, pnu FROM apt_kapt_info WHERE kapt_code IS NOT NULL")
    kapt_pnu_map = {r["kapt_code"]: r["pnu"] for r in cur.fetchall()}
    logger.info(f"  DB 기존 매핑: {len(kapt_pnu_map):,}건")

    unmapped_cnt = sum(1 for r in basic_rows if _safe_str(r.get("단지코드")) not in kapt_pnu_map)
    logger.info(f"  미매핑 단지: {unmapped_cnt:,}건")

    if args.dry_run:
        logger.info("Dry-run: 적재 생략")
        conn.close()
        return

    # Phase C (신규 등록) 먼저 실행해 Phase A/B가 새 pnu도 처리할 수 있게
    if args.register_new and unmapped_cnt > 0:
        new_mapping = phase_c_register_new(conn, logger, basic_rows, kapt_pnu_map, args.limit)
        kapt_pnu_map.update(new_mapping)

    # Phase A
    checkpoint = load_checkpoint()
    logger.info(f"체크포인트 제외: {len(checkpoint):,}건")
    phase_a_kapt_info(
        conn, logger, basic_rows, kapt_pnu_map, area_hhld_map, checkpoint, args.limit
    )

    # Phase B
    phase_b_area(conn, logger, area_rows, kapt_pnu_map, args.limit)

    conn.close()
    logger.info("전체 완료.")


if __name__ == "__main__":
    main()
