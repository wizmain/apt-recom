"""K-APT 관리비 수집 — 엑셀 파일 기반.

사용법:
  python -m batch.kapt.collect_mgmt_cost
"""

import json
from pathlib import Path

import pandas as pd

from batch.db import get_connection, get_dict_cursor, query_all
from batch.logger import setup_logger

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


def collect_from_xlsx():
    """엑셀 파일 → apt_mgmt_cost 적재."""
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

    # 2. DB 연결 + kapt_code → pnu 매핑
    conn = get_connection()
    cur = get_dict_cursor(conn)

    kapt_pnu = {}
    for r in query_all(conn, "SELECT pnu, kapt_code FROM apt_kapt_info WHERE kapt_code IS NOT NULL"):
        kapt_pnu[r["kapt_code"]] = r["pnu"]
    logger.info(f"  kapt_code→pnu 매핑: {len(kapt_pnu):,}건")

    # 3. 적재
    loaded = 0
    skipped = 0

    for _, row in df_cost.iterrows():
        kapt_code = row.get("단지코드")
        pnu = kapt_pnu.get(kapt_code)
        if not pnu:
            skipped += 1
            continue

        ym = str(int(row.get("발생년월(YYYYMM)", 0)))
        if len(ym) != 6:
            skipped += 1
            continue

        # 금액 합산
        common = sum(int(row.get(c) or 0) for c in COMMON_COLS)
        indiv = sum(int(row.get(c) or 0) for c in INDIV_COLS)
        repair = int(row.get("장충금 월부과액") or 0)
        total = common + indiv + repair

        # 면적/세대수
        area_info = area_map.get(kapt_code, {})
        hhld = int(area_info.get("세대수", 0)) or 1
        charge_area = float(area_info.get("관리비부과면적", 0)) or None

        per_unit = total // hhld if hhld > 0 else 0
        per_m2 = round(total / charge_area) if charge_area and charge_area > 0 else None

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
    collect_from_xlsx()
