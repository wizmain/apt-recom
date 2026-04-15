"""건축물대장 전유부(getBrExposPubuseAreaInfo) 수집 — 호별 전용/공급 면적 집계.

국토부 건축물대장 전유부 API는 호(dongNm + hoNm) 단위로 여러 row를 반환:
  - 전유 (expos='전유', atch='주건축물')        → 전용면적
  - 주거공용 (expos='공용', atch='주건축물')     → 주거공용면적 (복도·계단·EV홀·각층)
  - 기타공용 (expos='공용', atch='부속건축물')   → 지하주차장·관리동 등

한국 부동산 관례:
  공급면적 = 전용 + 주거공용
  계약면적 = 공급 + 기타공용

호별 집계 후 apt_area_info 에 전용/공급 각각의 min/max/avg 저장.
"""

from __future__ import annotations

import math
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Iterable

import requests

from batch.config import DATA_GO_KR_API_KEY, DATA_GO_KR_RATE

BLD_EXPOS_URL = (
    "http://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo"
)


def ensure_schema(conn) -> None:
    """apt_area_info 테이블과 신규 컬럼 보장 — 배치 시작 시 1회 호출.

    로컬·Railway 어디서 실행되더라도 누락 컬럼이 있으면 즉시 추가한다.
    """
    ddls = [
        """CREATE TABLE IF NOT EXISTS apt_area_info (
               pnu TEXT PRIMARY KEY,
               min_area DOUBLE PRECISION, max_area DOUBLE PRECISION, avg_area DOUBLE PRECISION,
               unit_count INTEGER, area_types INTEGER,
               cnt_under_40 INTEGER, cnt_40_60 INTEGER, cnt_60_85 INTEGER,
               cnt_85_115 INTEGER, cnt_115_135 INTEGER, cnt_over_135 INTEGER
           )""",
        "ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS source TEXT",
        "ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS last_refreshed TIMESTAMPTZ",
        "ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS min_supply_area DOUBLE PRECISION",
        "ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS max_supply_area DOUBLE PRECISION",
        "ALTER TABLE apt_area_info ADD COLUMN IF NOT EXISTS avg_supply_area DOUBLE PRECISION",
    ]
    cur = conn.cursor()
    for ddl in ddls:
        cur.execute(ddl)
    conn.commit()

ROWS_PER_PAGE = 500  # 호당 10 row 평균 → 50세대/page

# 면적 버킷 (전용면적 기준)
_BUCKETS = (
    ("cnt_under_40", 0, 40),
    ("cnt_40_60", 40, 60),
    ("cnt_60_85", 60, 85),
    ("cnt_85_115", 85, 115),
    ("cnt_115_135", 115, 135),
    ("cnt_over_135", 135, float("inf")),
)


def _bucket_counts(areas: Iterable[float]) -> dict:
    cnt = {name: 0 for name, _, _ in _BUCKETS}
    for a in areas:
        for name, lo, hi in _BUCKETS:
            if lo <= a < hi:
                cnt[name] += 1
                break
    return cnt


def _fetch_all_items(sigungu_cd: str, bjdong_cd: str, plat_gb: str,
                     bun: str, ji: str, timeout: int = 20) -> list[dict]:
    """페이지네이션 돌며 모든 item 수집."""
    base = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "sigunguCd": sigungu_cd, "bjdongCd": bjdong_cd,
        "platGbCd": plat_gb,
        "bun": str(bun).zfill(4), "ji": str(ji).zfill(4),
        "numOfRows": str(ROWS_PER_PAGE),
    }
    all_items: list[dict] = []
    try:
        resp = requests.get(BLD_EXPOS_URL, params={**base, "pageNo": "1"}, timeout=timeout)
        if not resp.ok:
            return []
        root = ET.fromstring(resp.text)
        if root.findtext(".//resultCode") not in ("00", None):
            return []
        total = int(root.findtext(".//totalCount") or "0")
        all_items.extend(_extract(root))

        if total > ROWS_PER_PAGE:
            pages = math.ceil(total / ROWS_PER_PAGE)
            for page in range(2, pages + 1):
                time.sleep(DATA_GO_KR_RATE)
                resp = requests.get(BLD_EXPOS_URL,
                                    params={**base, "pageNo": str(page)},
                                    timeout=timeout)
                if not resp.ok:
                    continue
                try:
                    all_items.extend(_extract(ET.fromstring(resp.text)))
                except ET.ParseError:
                    continue
    except (requests.RequestException, ET.ParseError):
        return []
    return all_items


def _extract(root) -> list[dict]:
    items = []
    for item in root.findall(".//item"):
        try:
            area = float(item.findtext("area") or 0)
        except ValueError:
            area = 0.0
        items.append({
            "dong": (item.findtext("dongNm") or "").strip(),
            "ho": (item.findtext("hoNm") or "").strip(),
            "expos": item.findtext("exposPubuseGbCdNm") or "",
            "atch": item.findtext("mainAtchGbCdNm") or "",
            "purps": item.findtext("mainPurpsCdNm") or "",
            "area": area,
        })
    return items


def _is_residential_purps(purps: str) -> bool:
    if not purps:
        return True  # 값 누락 시 수용 (주상복합 등)
    return any(k in purps for k in ("아파트", "공동주택", "다세대주택", "연립주택", "도시형생활주택"))


def fetch_area_info(sigungu_cd: str, bjdong_cd: str, plat_gb: str,
                    bun: str, ji: str) -> dict | None:
    """주소 기반 호별 전유부 조회 → apt_area_info 컬럼 dict.

    반환: 전용/공급 min·max·avg + 전용 기준 면적 버킷 6종 + unit_count/area_types
    주거용도 필터를 통과한 호수 기준. 호가 없으면 None.
    """
    items = _fetch_all_items(sigungu_cd, bjdong_cd, plat_gb, bun, ji)
    if not items:
        return None

    # (dong, ho) 별로 전용 / 주거공용 집계
    per_ho: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"exclu": 0.0, "pub_main": 0.0, "is_residential": False}
    )
    for it in items:
        if not _is_residential_purps(it["purps"]):
            continue
        key = (it["dong"], it["ho"])
        rec = per_ho[key]
        rec["is_residential"] = True
        if it["expos"] == "전유" and it["atch"] == "주건축물":
            rec["exclu"] += it["area"]
        elif it["expos"] == "공용" and it["atch"] == "주건축물":
            rec["pub_main"] += it["area"]

    # 전용 면적 > 0 인 호만 유효 — 주거 호수
    exclu_vals: list[float] = []
    supply_vals: list[float] = []
    for rec in per_ho.values():
        if rec["exclu"] <= 0:
            continue
        exclu_vals.append(rec["exclu"])
        supply_vals.append(rec["exclu"] + rec["pub_main"])

    if not exclu_vals:
        return None

    area_types = len({round(a, 2) for a in exclu_vals})
    buckets = _bucket_counts(exclu_vals)

    result = {
        "min_area": min(exclu_vals),
        "max_area": max(exclu_vals),
        "avg_area": round(sum(exclu_vals) / len(exclu_vals), 1),
        "min_supply_area": min(supply_vals),
        "max_supply_area": max(supply_vals),
        "avg_supply_area": round(sum(supply_vals) / len(supply_vals), 1),
        "unit_count": len(exclu_vals),
        "area_types": area_types,
        **buckets,
        "source": "bld_expos",
    }
    return result


def upsert_area_info(conn, pnu: str, info: dict) -> None:
    """apt_area_info UPSERT (전용 + 공급 면적 포함)."""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO apt_area_info (
            pnu, min_area, max_area, avg_area,
            min_supply_area, max_supply_area, avg_supply_area,
            unit_count, area_types,
            cnt_under_40, cnt_40_60, cnt_60_85, cnt_85_115, cnt_115_135, cnt_over_135,
            source, last_refreshed
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (pnu) DO UPDATE SET
            min_area = EXCLUDED.min_area,
            max_area = EXCLUDED.max_area,
            avg_area = EXCLUDED.avg_area,
            min_supply_area = EXCLUDED.min_supply_area,
            max_supply_area = EXCLUDED.max_supply_area,
            avg_supply_area = EXCLUDED.avg_supply_area,
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
            info["min_supply_area"], info["max_supply_area"], info["avg_supply_area"],
            info["unit_count"], info["area_types"],
            info["cnt_under_40"], info["cnt_40_60"], info["cnt_60_85"],
            info["cnt_85_115"], info["cnt_115_135"], info["cnt_over_135"],
            info.get("source", "bld_expos"),
        ],
    )
