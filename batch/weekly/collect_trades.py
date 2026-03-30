"""거래 데이터 증분 수집 (매매 + 전월세)."""

import time
import xml.etree.ElementTree as ET
import requests
from datetime import datetime

from batch.config import DATA_GO_KR_API_KEY, TRADE_URL, RENT_URL, DATA_GO_KR_RATE
from batch.db import get_district_codes, query_one

TRADE_COL_MAP = {
    "dealAmount": "dealAmount", "buildYear": "buildYear",
    "dealYear": "dealYear", "dealMonth": "dealMonth", "dealDay": "dealDay",
    "aptNm": "aptNm", "excluUseAr": "excluUseAr",
    "sggCd": "sggCd", "floor": "floor",
}

RENT_COL_MAP = {
    "deposit": "deposit", "monthlyRent": "monthlyRent",
    "excluUseAr": "excluUseAr", "aptNm": "aptNm",
    "floor": "floor", "dealYear": "dealYear",
    "dealMonth": "dealMonth", "dealDay": "dealDay", "sggCd": "sggCd",
}


def _call_api(url, lawd_cd, deal_ymd, retries=3):
    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "pageNo": "1",
        "numOfRows": "10000",
    }
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                return None
    return None


def _parse_xml(xml_text, col_map):
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    result_code = root.findtext(".//resultCode")
    if result_code not in ("00", "000"):
        return []
    rows = []
    for item in root.findall(".//item"):
        row = {}
        for tag, col in col_map.items():
            el = item.find(tag)
            row[col] = el.text.strip() if el is not None and el.text else ""
        rows.append(row)
    return rows


def _get_collection_months(conn):
    """DB에서 마지막 수집월 조회 → 다음 월부터 현재월까지 목록 반환."""
    row = query_one(conn, "SELECT MAX(deal_year * 100 + deal_month) as last_ym FROM trade_history")
    last_ym = row["last_ym"] if row and row["last_ym"] else 201601

    now = datetime.now()
    cur_ym = now.year * 100 + now.month

    # 마지막 수집월부터 (이미 수집된 달도 증분 체크를 위해 포함)
    months = []
    y, m = int(str(last_ym)[:4]), int(str(last_ym)[4:])
    while y * 100 + m <= cur_ym:
        months.append(f"{y}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def collect_trades(conn, logger, dry_run=False):
    """거래 데이터 증분 수집. (trade_rows, rent_rows) 반환."""
    codes = get_district_codes(conn)
    months = _get_collection_months(conn)

    logger.info(f"수집 대상: {len(codes)}개 시군구 x {len(months)}개월 ({months[0]}~{months[-1]})")

    trade_rows = []
    rent_rows = []

    for month in months:
        for code in codes:
            # 매매
            xml = _call_api(TRADE_URL, code, month)
            rows = _parse_xml(xml, TRADE_COL_MAP)
            trade_rows.extend(rows)
            time.sleep(DATA_GO_KR_RATE)

            # 전월세
            xml = _call_api(RENT_URL, code, month)
            rows = _parse_xml(xml, RENT_COL_MAP)
            rent_rows.extend(rows)
            time.sleep(DATA_GO_KR_RATE)

        logger.info(f"  {month}: 매매 누적 {len(trade_rows):,}건, 전월세 누적 {len(rent_rows):,}건")

    logger.info(f"수집 완료: 매매 {len(trade_rows):,}건, 전월세 {len(rent_rows):,}건")
    return trade_rows, rent_rows
