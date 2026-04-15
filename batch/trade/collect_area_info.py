"""건축물대장 전유부(getBrExposPubuseAreaInfo) 수집 — 호별 전용면적 집계.

아파트 PNU 에 대응되는 주소(sigunguCd / bjdongCd / platGbCd / bun / ji)로
호별 전유/공용 면적 리스트를 조회하고, 전용(exposPubuseGbCdNm='전유')
& 주건축물(mainAtchGbCdNm='주건축물') 중 주거용도 호수만 추려
min/max/avg/타입수/면적 버킷별 세대수를 계산한다.

반환 dict 구조는 `apt_area_info` 테이블 컬럼과 1:1 대응.
"""

from __future__ import annotations

import math
import time
import xml.etree.ElementTree as ET
from typing import Iterable

import requests

from batch.config import DATA_GO_KR_API_KEY, DATA_GO_KR_RATE

BLD_EXPOS_URL = (
    "http://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo"
)

# 주거용도 판정 — mainPurpsCdNm 에 나타나는 키워드
_RESIDENTIAL_KEYWORDS = ("아파트", "공동주택", "다세대주택", "연립주택", "도시형생활주택", "주상복합")

# 면적 버킷 컬럼 매핑
_BUCKETS = (
    ("cnt_under_40", 0, 40),
    ("cnt_40_60", 40, 60),
    ("cnt_60_85", 60, 85),
    ("cnt_85_115", 85, 115),
    ("cnt_115_135", 115, 135),
    ("cnt_over_135", 135, float("inf")),
)


def _is_residential(main_purps_cd_nm: str | None, main_atch_gb_cd_nm: str | None,
                    expos_pubuse_gb_cd_nm: str | None) -> bool:
    """전유 & 주건축물 & 주거용도 필터."""
    if expos_pubuse_gb_cd_nm != "전유":
        return False
    if main_atch_gb_cd_nm not in (None, "", "주건축물"):
        # 부속건물(주차·관리동)은 제외
        return False
    if not main_purps_cd_nm:
        # 용도가 비어있을 수 있음 — 전유+주건축물이면 수용 (주상복합 등)
        return True
    return any(k in main_purps_cd_nm for k in _RESIDENTIAL_KEYWORDS)


def _bucket_counts(areas: Iterable[float]) -> dict:
    cnt = {name: 0 for name, _, _ in _BUCKETS}
    for a in areas:
        for name, lo, hi in _BUCKETS:
            if lo <= a < hi:
                cnt[name] += 1
                break
    return cnt


def _parse_items(xml_text: str) -> list[dict]:
    """응답 XML → item dict 리스트."""
    root = ET.fromstring(xml_text)
    if root.findtext(".//resultCode") not in ("00", None):
        return []
    items = []
    for item in root.findall(".//item"):
        items.append({
            "expos": item.findtext("exposPubuseGbCdNm") or "",
            "atch": item.findtext("mainAtchGbCdNm") or "",
            "purps": item.findtext("mainPurpsCdNm") or "",
            "dong": item.findtext("dongNm") or "",
            "ho": item.findtext("hoNm") or "",
            "area_raw": item.findtext("area") or "",
        })
    return items


def _fetch_page(sigungu_cd: str, bjdong_cd: str, plat_gb: str,
                bun: str, ji: str, page: int, rows: int,
                timeout: int = 15) -> tuple[list[dict], int]:
    """단일 페이지 호출 → (items, total_count)."""
    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "platGbCd": plat_gb,
        "bun": str(bun).zfill(4),
        "ji": str(ji).zfill(4),
        "numOfRows": str(rows),
        "pageNo": str(page),
    }
    resp = requests.get(BLD_EXPOS_URL, params=params, timeout=timeout)
    if not resp.ok:
        return [], 0
    total_str = ""
    try:
        root = ET.fromstring(resp.text)
        total_str = root.findtext(".//totalCount") or "0"
    except ET.ParseError:
        return [], 0
    try:
        total = int(total_str)
    except ValueError:
        total = 0
    items = _parse_items(resp.text)
    return items, total


def fetch_area_info(sigungu_cd: str, bjdong_cd: str, plat_gb: str,
                    bun: str, ji: str) -> dict | None:
    """주소 기반 전유부 조회 → apt_area_info 컬럼 dict.

    성공 시 min/max/avg/unit_count/area_types/cnt_* 채운 dict (+ source='bld_expos')
    실패 또는 전유 0건이면 None.
    """
    rows_per_page = 200
    all_items: list[dict] = []
    try:
        items, total = _fetch_page(sigungu_cd, bjdong_cd, plat_gb, bun, ji, 1, rows_per_page)
        all_items.extend(items)
        if total > rows_per_page:
            pages = math.ceil(total / rows_per_page)
            for page in range(2, pages + 1):
                time.sleep(DATA_GO_KR_RATE)
                more, _ = _fetch_page(sigungu_cd, bjdong_cd, plat_gb, bun, ji, page, rows_per_page)
                all_items.extend(more)
    except Exception:
        return None

    # 전용·주거·주건축물 필터 + area 파싱
    areas: list[float] = []
    for it in all_items:
        if not _is_residential(it["purps"], it["atch"], it["expos"]):
            continue
        try:
            a = float(it["area_raw"])
        except (TypeError, ValueError):
            continue
        if a <= 0:
            continue
        areas.append(a)

    if not areas:
        return None

    types = len({round(a, 2) for a in areas})
    buckets = _bucket_counts(areas)
    return {
        "min_area": min(areas),
        "max_area": max(areas),
        "avg_area": round(sum(areas) / len(areas), 1),
        "unit_count": len(areas),
        "area_types": types,
        **buckets,
        "source": "bld_expos",
    }


def upsert_area_info(conn, pnu: str, info: dict) -> None:
    """apt_area_info UPSERT."""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO apt_area_info (
            pnu, min_area, max_area, avg_area, unit_count, area_types,
            cnt_under_40, cnt_40_60, cnt_60_85, cnt_85_115, cnt_115_135, cnt_over_135,
            source, last_refreshed
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
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
            source = EXCLUDED.source,
            last_refreshed = NOW()
        """,
        [
            pnu,
            info["min_area"], info["max_area"], info["avg_area"],
            info["unit_count"], info["area_types"],
            info["cnt_under_40"], info["cnt_40_60"], info["cnt_60_85"],
            info["cnt_85_115"], info["cnt_115_135"], info["cnt_over_135"],
            info.get("source", "bld_expos"),
        ],
    )
