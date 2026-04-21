"""K-APT 관리비 수집 — API(V2) 자동 수집 + 엑셀 파일 수동 적재.

사용법:
  python -m batch.kapt.collect_mgmt_cost                          # API 전월 수집
  python -m batch.kapt.collect_mgmt_cost --source api --date 202502 --limit 10
  python -m batch.kapt.collect_mgmt_cost --source xlsx            # 엑셀 적재
"""

import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from batch.config import DATA_GO_KR_API_KEY, DATA_GO_KR_RATE
from batch.db import get_connection, get_dict_cursor, query_all
from batch.logger import setup_logger

# ── API 설정 ──

MGMT_API_BASE = "http://apis.data.go.kr/1613000/AptRepairsCostServiceV2"
MGMT_API_TIMEOUT = 10

# ── 엑셀 설정 ──

DATA_DIR = Path(__file__).resolve().parents[2] / "apt_eda" / "data" / "관리비자료"
COST_FILES = [
    DATA_DIR / "20260403_단지_관리비정보_2025.xlsx",  # 2025년 12개월
    DATA_DIR / "20260403_단지_관리비정보.xlsx",        # 2026년 1~3월
]
AREA_XLSX = DATA_DIR / "20260403_단지_면적정보.xlsx"

# 공용관리비 항목
COMMON_COLS = [
    "인건비", "제사무비", "제세공과금", "피복비", "교육훈련비", "차량유지비",
    "그밖의부대비용", "청소비", "경비비", "소독비", "승강기유지비",
    "지능형네트워크유지비", "수선비", "시설유지비", "안전점검비", "재해예방비", "위탁관리수수료",
]

# 개별사용료 항목
INDIV_COLS = [
    "난방비(공용)", "난방비(전용)", "급탕비(공용)", "급탕비(전용)",
    "가스사용료(공용)", "가스사용료(전용)", "전기료(공용)", "전기료(전용)",
    "수도료(공용)", "수도료(전용)", "TV수신료", "정화조오물수수료", "생활폐기물수수료",
]

# 기타 항목
ETC_COLS = ["입대의운영비", "건물보험료", "선관위운영비", "기타"]

# 장기수선충당금
REPAIR_COLS = ["장충금 월부과액", "장충금 월사용액", "장충금 총적립금액"]


# ── API 수집 ──

def _prev_month_yyyymm() -> str:
    """전월 YYYYMM 반환."""
    today = datetime.now()
    first_of_month = today.replace(day=1)
    prev = first_of_month - timedelta(days=1)
    return prev.strftime("%Y%m")


def _fetch_mgmt_cost(kapt_code: str, search_date: str) -> int | None:
    """K-APT V2 API로 월 관리비 총 사용액(sUse) 조회. 실패 시 None."""
    url = f"{MGMT_API_BASE}/getHsmpMonthRetalFeeInfoV2"
    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "kaptCode": kapt_code,
        "searchDate": search_date,
        "type": "json",
    }
    try:
        r = requests.get(url, params=params, timeout=MGMT_API_TIMEOUT)
        r.raise_for_status()
        item = r.json().get("response", {}).get("body", {}).get("item", {})
        s_use = item.get("sUse")
        if s_use is None or item.get("kaptCode") is None:
            return None
        return int(s_use)
    except Exception:
        return None


def collect_from_api(conn=None, logger=None, search_date=None, dry_run=False, limit=0):
    """K-APT V2 API로 관리비 월별 총액 수집 → apt_mgmt_cost UPSERT.

    Returns:
        수집(UPSERT) 건수.
    """
    if logger is None:
        logger = setup_logger("mgmt_cost_api")

    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = get_dict_cursor(conn)

    ym = search_date or _prev_month_yyyymm()
    logger.info(f"관리비 API 수집 시작: searchDate={ym}, limit={limit}, dry_run={dry_run}")

    # kapt_code + pnu + 세대수 매핑.
    # 세대당 관리비 분모: K-APT 공식(ho_cnt) 최우선, Sanity check 로 K-APT 오입력(>5배) 방어.
    rows = query_all(conn, """
        SELECT k.kapt_code, k.pnu,
               CASE
                 WHEN k.ho_cnt > 0 AND a.total_hhld_cnt > 0
                      AND k.ho_cnt::float / a.total_hhld_cnt >= 5
                   THEN a.total_hhld_cnt
                 ELSE COALESCE(NULLIF(k.ho_cnt, 0), a.total_hhld_cnt, 1)
               END AS hhld
        FROM apt_kapt_info k
        JOIN apartments a ON k.pnu = a.pnu
        WHERE k.kapt_code IS NOT NULL
    """)
    targets = [(r["kapt_code"], r["pnu"], max(r["hhld"], 1)) for r in rows]
    if limit > 0:
        targets = targets[:limit]
    logger.info(f"  수집 대상: {len(targets):,}건")

    loaded = 0
    skipped = 0
    failed = 0

    for i, (kapt_code, pnu, hhld) in enumerate(targets):
        s_use = _fetch_mgmt_cost(kapt_code, ym)
        time.sleep(DATA_GO_KR_RATE)

        if s_use is None or s_use == 0:
            skipped += 1
            continue

        cost_per_unit = s_use // hhld

        if not dry_run:
            try:
                cur.execute("""
                    INSERT INTO apt_mgmt_cost (pnu, year_month, total_cost, cost_per_unit)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (pnu, year_month) DO UPDATE SET
                        total_cost = EXCLUDED.total_cost,
                        cost_per_unit = EXCLUDED.cost_per_unit
                """, [pnu, ym, s_use, cost_per_unit])
            except Exception as e:
                logger.warning(f"  UPSERT 실패 ({pnu}): {e}")
                failed += 1
                continue

        loaded += 1

        if loaded % 5000 == 0:
            if not dry_run:
                conn.commit()
            logger.info(f"  진행: {loaded:,}건 적재 (스킵 {skipped:,}, 실패 {failed:,})")

        if (i + 1) % 1000 == 0:
            logger.info(f"  API 호출: {i + 1:,}/{len(targets):,}")

    if not dry_run:
        conn.commit()

    logger.info(f"관리비 API 수집 완료: {loaded:,}건 적재 (스킵 {skipped:,}, 실패 {failed:,})")

    if own_conn:
        conn.close()

    return loaded


# ── 엑셀 적재 ──

def collect_from_xlsx():
    """엑셀 파일 → apt_mgmt_cost 적재."""
    import pandas as pd

    logger = setup_logger("mgmt_cost")

    if not AREA_XLSX.exists():
        logger.error(f"면적 엑셀 없음: {AREA_XLSX}")
        return

    # 1. 엑셀 로드 (여러 파일 병합)
    logger.info("엑셀 로드 중...")
    dfs = []
    for f in COST_FILES:
        if f.exists():
            df = pd.read_excel(f, header=1)
            dfs.append(df)
            logger.info(f"  {f.name}: {len(df):,}건")
    if not dfs:
        logger.error("관리비 엑셀 파일 없음")
        return
    df_cost = pd.concat(dfs, ignore_index=True)
    df_area = pd.read_excel(AREA_XLSX, header=1)
    logger.info(f"  관리비 합계: {len(df_cost):,}건, 면적: {len(df_area):,}건")

    # 면적 단지별 집약 (관리비부과면적, 세대수)
    area_agg = df_area.groupby("단지코드").agg({
        "관리비부과면적": "first",
        "주거전용면적(단지합계)": "first",
        "세대수": "sum",
    }).reset_index()
    area_map = area_agg.set_index("단지코드").to_dict("index")

    # 2. DB 연결 + kapt_code → (pnu, K-APT 세대수, apts 세대수) 매핑
    conn = get_connection()
    cur = get_dict_cursor(conn)

    kapt_pnu: dict[str, tuple[str, int, int]] = {}
    for r in query_all(
        conn,
        """SELECT k.kapt_code, k.pnu,
                  COALESCE(k.ho_cnt, 0) AS kapt_hhld,
                  COALESCE(a.total_hhld_cnt, 0) AS apts_hhld
           FROM apt_kapt_info k
           JOIN apartments a ON k.pnu = a.pnu
           WHERE k.kapt_code IS NOT NULL""",
    ):
        kapt_pnu[r["kapt_code"]] = (r["pnu"], r["kapt_hhld"], r["apts_hhld"])
    logger.info(f"  kapt_code→pnu 매핑: {len(kapt_pnu):,}건")

    # 3. 적재
    loaded = 0
    skipped = 0

    for _, row in df_cost.iterrows():
        kapt_code = row.get("단지코드")
        pnu_info = kapt_pnu.get(kapt_code)
        if not pnu_info:
            skipped += 1
            continue
        pnu, kapt_hhld, apts_hhld = pnu_info

        ym = str(int(row.get("발생년월(YYYYMM)", 0)))
        if len(ym) != 6:
            skipped += 1
            continue

        # 금액 합산 — 엑셀의 "계" 집계 컬럼을 우선 사용.
        # 일부 단지는 세부 항목이 NaN이고 계 컬럼에만 합계가 있어 세부합만으로는 과소집계됨.
        common_sum = sum(int(row.get(c) or 0) for c in COMMON_COLS)
        indiv_sum = sum(int(row.get(c) or 0) for c in INDIV_COLS)
        common = max(int(row.get("공용관리비계") or 0), common_sum)
        indiv = max(int(row.get("개별사용료계") or 0), indiv_sum)
        repair = int(row.get("장충금 월부과액") or 0)
        total = common + indiv + repair

        # 세대수 우선순위: K-APT 공식(ho_cnt) → 면적 엑셀 합 → apts
        # Sanity check: K-APT ho_cnt 가 apts 의 5배 이상이면 엑셀 오입력으로 apts 사용.
        area_info = area_map.get(kapt_code, {})
        if kapt_hhld and apts_hhld and kapt_hhld >= apts_hhld * 5:
            hhld = apts_hhld
        else:
            hhld = kapt_hhld or int(area_info.get("세대수", 0)) or apts_hhld or 1
        charge_area = float(area_info.get("관리비부과면적", 0)) or None

        per_unit = total // hhld if hhld > 0 else 0

        # 상세 항목
        detail = {}
        for c in COMMON_COLS + INDIV_COLS + ETC_COLS + REPAIR_COLS:
            v = int(row.get(c) or 0)
            if v > 0:
                detail[c] = v

        cur.execute("""
            INSERT INTO apt_mgmt_cost (pnu, year_month, common_cost, individual_cost, repair_fund,
                total_cost, cost_per_unit, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (pnu, year_month) DO UPDATE SET
                common_cost=EXCLUDED.common_cost, individual_cost=EXCLUDED.individual_cost,
                repair_fund=EXCLUDED.repair_fund, total_cost=EXCLUDED.total_cost,
                cost_per_unit=EXCLUDED.cost_per_unit, detail=EXCLUDED.detail
        """, [pnu, ym, common, indiv, repair, total, per_unit,
              json.dumps(detail, ensure_ascii=False)])
        loaded += 1

        if loaded % 5000 == 0:
            conn.commit()
            logger.info(f"  진행: {loaded:,}건 적재")

    conn.commit()

    cnt = query_all(conn, "SELECT COUNT(*) as cnt FROM apt_mgmt_cost")[0]["cnt"]
    logger.info(f"관리비 적재 완료: {loaded:,}건 (스킵 {skipped:,}, 총 {cnt:,}건)")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="K-APT 관리비 수집")
    parser.add_argument("--source", choices=["xlsx", "api"], default="api",
                        help="수집 소스: api(V2 API) 또는 xlsx(엑셀)")
    parser.add_argument("--date", help="수집 대상 년월 YYYYMM (기본: 전월)")
    parser.add_argument("--limit", type=int, default=0,
                        help="테스트용 최대 수집 건수 (0=전체)")
    args = parser.parse_args()

    if args.source == "xlsx":
        collect_from_xlsx()
    else:
        collect_from_api(search_date=args.date, limit=args.limit)
