"""K-APT 관리비 엑셀 파싱 서비스.

관리비 엑셀(단지_관리비정보_*.xlsx) + 면적 엑셀(선택) + 기본정보 엑셀(선택)을
파싱하여 apt_mgmt_cost 테이블 형식으로 변환. 신규 아파트 자동 등록 지원.
"""

import json
import logging
from typing import Callable

import pandas as pd

from database import DictConnection, get_connection
from services.geocoder import geocode_address

logger = logging.getLogger(__name__)

# ── K-APT 엑셀 컬럼 분류 ──

COMMON_COLS = [
    "인건비",
    "제사무비",
    "제세공과금",
    "피복비",
    "교육훈련비",
    "차량유지비",
    "그밖의부대비용",
    "청소비",
    "경비비",
    "소독비",
    "승강기유지비",
    "지능형네트워크유지비",
    "수선비",
    "시설유지비",
    "안전점검비",
    "재해예방비",
    "위탁관리수수료",
]

INDIV_COLS = [
    "난방비(공용)",
    "난방비(전용)",
    "급탕비(공용)",
    "급탕비(전용)",
    "가스사용료(공용)",
    "가스사용료(전용)",
    "전기료(공용)",
    "전기료(전용)",
    "수도료(공용)",
    "수도료(전용)",
    "TV수신료",
    "정화조오물수수료",
    "생활폐기물수수료",
]

ETC_COLS = ["입대의운영비", "건물보험료", "선관위운영비", "기타"]

REPAIR_COLS = ["장충금 월부과액", "장충금 월사용액", "장충금 총적립금액"]

ALL_DETAIL_COLS = COMMON_COLS + INDIV_COLS + ETC_COLS + REPAIR_COLS

# 기본정보 엑셀 → apt_kapt_info 매핑에 사용할 승강기 컬럼
ELEVATOR_COLS = [
    "승강기(승객용)",
    "승강기(화물용)",
    "승강기(승객+화물)",
    "승강기(장애인)",
    "승강기(비상용)",
    "승강기(기타)",
]


def _load_kapt_pnu_map() -> dict[str, tuple[str, str, int, int]]:
    """apt_kapt_info에서 kapt_code → (pnu, bld_nm, kapt_ho_cnt, total_hhld_cnt) 매핑 로드.

    반환값의 세대수는 두 출처를 모두 포함:
      - kapt_ho_cnt: apt_kapt_info.ho_cnt (K-APT 공식)
      - total_hhld_cnt: apartments.total_hhld_cnt (건축물대장 + K-APT 갱신본)
    세대당 관리비 계산 시 K-APT를 최우선으로 사용한다.
    """
    conn = DictConnection()
    rows = conn.execute(
        """SELECT k.kapt_code, k.pnu, COALESCE(a.bld_nm, '') AS bld_nm,
                  COALESCE(k.ho_cnt, 0) AS kapt_ho_cnt,
                  COALESCE(a.total_hhld_cnt, 0) AS hhld
           FROM apt_kapt_info k
           JOIN apartments a ON k.pnu = a.pnu
           WHERE k.kapt_code IS NOT NULL"""
    ).fetchall()
    conn.close()
    return {
        r["kapt_code"]: (r["pnu"], r["bld_nm"], r["kapt_ho_cnt"], r["hhld"])
        for r in rows
    }


def parse_cost_excel(
    cost_file_path: str,
    area_file_path: str | None = None,
    basic_file_path: str | None = None,
) -> tuple[list[dict], list[str], list[dict]]:
    """K-APT 관리비 엑셀을 파싱하여 apt_mgmt_cost 형식으로 변환.

    Args:
        cost_file_path: 관리비 엑셀 경로 (필수)
        area_file_path: 면적 엑셀 경로 (선택)
        basic_file_path: 기본정보 엑셀 경로 (선택, 신규 등록용)

    Returns:
        (rows, errors, new_apts)
        - rows: 매핑 성공한 관리비 데이터
        - errors: 매핑 실패 + 기본정보도 없는 오류
        - new_apts: 신규 등록 가능 단지 목록
    """
    df_cost = pd.read_excel(cost_file_path, header=1)

    # 면적 파일 (선택)
    area_map: dict[str, int] = {}
    if area_file_path:
        df_area = pd.read_excel(area_file_path, header=1)
        area_agg = df_area.groupby("단지코드").agg({"세대수": "sum"}).reset_index()
        area_map = {
            str(row["단지코드"]): int(row["세대수"]) for _, row in area_agg.iterrows()
        }

    # 기본정보 파일 (선택, 신규 등록용)
    basic_map: dict[str, dict] = {}
    if basic_file_path:
        df_basic = pd.read_excel(basic_file_path, header=1)
        for _, brow in df_basic.iterrows():
            kc = str(brow.get("단지코드", ""))
            if kc:
                basic_map[kc] = {
                    "kapt_code": kc,
                    "kapt_name": str(brow.get("단지명", "")),
                    "address": str(brow.get("법정동주소", "")),
                    "road_address": str(brow.get("도로명주소", "")),
                    "hhld": int(brow.get("세대수") or 0),
                    "dong_count": int(brow.get("동수") or 0),
                    "max_floor": int(
                        brow.get("최고층수(건축물대장상)") or brow.get("최고층수") or 0
                    ),
                    "use_apr_day": str(brow.get("사용승인일", "")),
                    "sale_type": str(brow.get("분양형태", "")),
                    "heat_type": str(brow.get("난방방식", "")),
                    "builder": str(brow.get("시공사", "")),
                    "developer": str(brow.get("시행사", "")),
                    "mgr_type": str(brow.get("관리방식", "")),
                    "hall_type": str(brow.get("복도유형", "")),
                    "structure": str(brow.get("건물구조", "")),
                    "parking_cnt": int(brow.get("총주차대수") or 0),
                    "cctv_cnt": int(brow.get("CCTV대수") or 0),
                    "elevator_cnt": sum(int(brow.get(c) or 0) for c in ELEVATOR_COLS),
                }

    kapt_pnu_map = _load_kapt_pnu_map()

    rows: list[dict] = []
    errors: list[str] = []
    new_apts_set: dict[str, dict] = {}  # kapt_code → 기본정보
    seen_missing: set[str] = set()

    for _, row in df_cost.iterrows():
        kapt_code = str(row.get("단지코드", ""))
        kapt_name = str(row.get("단지명", ""))

        pnu_info = kapt_pnu_map.get(kapt_code)
        if not pnu_info:
            if kapt_code not in seen_missing:
                seen_missing.add(kapt_code)
                if kapt_code in basic_map:
                    new_apts_set[kapt_code] = basic_map[kapt_code]
                else:
                    errors.append(
                        f"PNU 매핑 실패 (기본정보 없음): {kapt_name} ({kapt_code})"
                    )
            continue

        pnu, bld_nm, kapt_ho_cnt, db_hhld = pnu_info

        ym_raw = row.get("발생년월(YYYYMM)", 0)
        ym = str(int(ym_raw)) if pd.notna(ym_raw) else ""
        if len(ym) != 6:
            continue

        # 공용관리비·개별사용료는 엑셀의 "계" 집계 컬럼을 우선 사용.
        # 일부 단지(직영·단순표기)는 세부 항목이 NaN이고 "계"에만 합계가 들어있어
        # 세부 합산만으로는 과소집계됨(경희궁의아침4단지 등).
        # 반대로 세부합이 계보다 크면(반올림/입력오류) 큰 쪽을 사용.
        common_sum = sum(int(row.get(c) or 0) for c in COMMON_COLS)
        indiv_sum = sum(int(row.get(c) or 0) for c in INDIV_COLS)
        common = max(int(row.get("공용관리비계") or 0), common_sum)
        indiv = max(int(row.get("개별사용료계") or 0), indiv_sum)
        repair = int(row.get("장충금 월부과액") or 0)
        total = common + indiv + repair

        # 세대수 우선순위: K-APT 공식(ho_cnt) → 면적 엑셀 합 → apartments.total_hhld_cnt.
        # Sanity check: K-APT ho_cnt 가 apartments 값의 5배 이상이면 K-APT 엑셀 오입력
        # (예: 평택지제역자이 1052→10052)으로 판단, apartments 값 사용.
        if kapt_ho_cnt and db_hhld and kapt_ho_cnt >= db_hhld * 5:
            hhld = db_hhld
        else:
            hhld = kapt_ho_cnt or area_map.get(kapt_code, 0) or db_hhld or 0
        per_unit = total // hhld if hhld > 0 else 0

        detail = {}
        for c in ALL_DETAIL_COLS:
            v = int(row.get(c) or 0)
            if v > 0:
                detail[c] = v

        rows.append(
            {
                "pnu": pnu,
                "year_month": ym,
                "common_cost": common,
                "individual_cost": indiv,
                "repair_fund": repair,
                "total_cost": total,
                "cost_per_unit": per_unit,
                "detail": detail,
                "kapt_name": bld_nm or kapt_name,
            }
        )

    new_apts = list(new_apts_set.values())
    logger.info(
        f"관리비 파싱 완료: {len(rows)}건 매핑, {len(new_apts)}건 신규, {len(errors)}건 오류"
    )
    return rows, errors, new_apts


def register_new_apartments(
    new_apts: list[dict],
    on_progress: Callable[[int, int, str], None] | None = None,
) -> tuple[int, list[str]]:
    """신규 아파트 지오코딩 + DB 등록.

    1. 법정동주소(or 도로명주소)로 geocode_address() 호출
    2. 성공 시 apartments INSERT + apt_kapt_info INSERT
    3. 100건마다 commit + on_progress

    Returns: (registered_count, errors)
    """
    conn = get_connection()
    registered = 0
    reg_errors: list[str] = []

    try:
        cur = conn.cursor()

        for i, apt in enumerate(new_apts):
            kapt_code = apt["kapt_code"]
            name = apt["kapt_name"]
            address = apt.get("road_address") or apt.get("address", "")

            if on_progress:
                on_progress(i + 1, len(new_apts), f"지오코딩: {name}")

            if not address:
                reg_errors.append(f"주소 없음: {name} ({kapt_code})")
                continue

            # 이미 등록된 kapt_code인지 확인
            cur.execute("SELECT 1 FROM apt_kapt_info WHERE kapt_code = %s", [kapt_code])
            if cur.fetchone():
                continue  # 이미 등록됨 (다른 프로세스가 먼저 등록)

            geo = geocode_address(address, name)
            if not geo:
                reg_errors.append(f"지오코딩 실패: {name} ({kapt_code})")
                continue

            pnu = geo["pnu"]

            # apartments UPSERT
            cur.execute(
                """INSERT INTO apartments
                   (pnu, bld_nm, total_hhld_cnt, dong_count, max_floor,
                    use_apr_day, plat_plc, new_plat_plc, bjd_code,
                    sigungu_code, lat, lng, group_pnu)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (pnu) DO UPDATE SET
                     bld_nm = COALESCE(NULLIF(EXCLUDED.bld_nm,''), apartments.bld_nm),
                     total_hhld_cnt = COALESCE(NULLIF(EXCLUDED.total_hhld_cnt,0), apartments.total_hhld_cnt),
                     lat = COALESCE(EXCLUDED.lat, apartments.lat),
                     lng = COALESCE(EXCLUDED.lng, apartments.lng)""",
                [
                    pnu,
                    name,
                    apt.get("hhld", 0),
                    apt.get("dong_count", 0),
                    apt.get("max_floor", 0),
                    apt.get("use_apr_day", ""),
                    geo["plat_plc"],
                    geo["new_plat_plc"],
                    geo["bjd_code"],
                    geo["sigungu_code"],
                    geo["lat"],
                    geo["lng"],
                    pnu,
                ],
            )

            # apt_kapt_info UPSERT
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
                    apt.get("sale_type", ""),
                    apt.get("heat_type", ""),
                    apt.get("builder", ""),
                    apt.get("developer", ""),
                    apt.get("mgr_type", ""),
                    apt.get("hall_type", ""),
                    apt.get("structure", ""),
                    apt.get("parking_cnt", 0),
                    apt.get("cctv_cnt", 0),
                    apt.get("elevator_cnt", 0),
                ],
            )

            registered += 1

            if registered % 100 == 0:
                conn.commit()

        conn.commit()
        logger.info(f"신규 아파트 등록 완료: {registered}건, 실패: {len(reg_errors)}건")
        return registered, reg_errors

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_mgmt_costs(rows: list[dict]) -> int:
    """파싱된 관리비 데이터를 apt_mgmt_cost에 UPSERT."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        count = 0
        for r in rows:
            cur.execute(
                """INSERT INTO apt_mgmt_cost
                   (pnu, year_month, common_cost, individual_cost, repair_fund,
                    total_cost, cost_per_unit, detail)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (pnu, year_month) DO UPDATE SET
                     common_cost=EXCLUDED.common_cost,
                     individual_cost=EXCLUDED.individual_cost,
                     repair_fund=EXCLUDED.repair_fund,
                     total_cost=EXCLUDED.total_cost,
                     cost_per_unit=EXCLUDED.cost_per_unit,
                     detail=EXCLUDED.detail""",
                [
                    r["pnu"],
                    r["year_month"],
                    r["common_cost"],
                    r["individual_cost"],
                    r["repair_fund"],
                    r["total_cost"],
                    r["cost_per_unit"],
                    json.dumps(r["detail"], ensure_ascii=False),
                ],
            )
            count += 1
            if count % 5000 == 0:
                conn.commit()

        conn.commit()
        logger.info(f"관리비 적재 완료: {count}건")
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
