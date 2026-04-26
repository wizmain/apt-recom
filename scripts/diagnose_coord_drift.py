"""아파트 좌표 drift 진단 (read-only).

저장된 좌표가 카카오 키워드 검색에서 인근 다른 단지로 잘못 끌려 들어온 케이스를
PNU 지번주소(`plat_plc`) 기반으로 재검증하여 식별한다.

대상: 기본값 coord_source IN ('kakao_keyword', 'kakao_keyword_v2')
검증: plat_plc → Kakao address API → 좌표 → DB 좌표와의 거리 측정
보고: threshold 초과 건만 CSV/표로 출력. **DB 변경 없음.**

사용 예:
  # 서울 중구 (시군구 코드 11140) 만 진단, 200m 초과만 보고
  .venv/bin/python -m scripts.diagnose_coord_drift --sigungu 11140 --threshold-m 200

  # 전체 kakao_keyword 계열, 100m 초과 → CSV
  .venv/bin/python -m scripts.diagnose_coord_drift --out coord_drift.csv

  # 작은 표본만 빠르게 확인
  .venv/bin/python -m scripts.diagnose_coord_drift --limit 50 --threshold-m 150
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import requests

from batch.config import KAKAO_API_KEY, KAKAO_RATE
from batch.db import get_connection, get_dict_cursor
from batch.fix_apartment_info import _distance_m
from batch.logger import setup_logger


KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"


def _kakao_address_lookup(addr: str, headers: dict, logger) -> tuple[float, float] | None:
    """plat_plc(지번주소) → (lat, lng). 실패 시 None."""
    if not addr:
        return None
    try:
        r = requests.get(KAKAO_ADDRESS_URL, headers=headers, params={"query": addr, "size": 1}, timeout=5)
        r.raise_for_status()
        time.sleep(KAKAO_RATE)
        docs = r.json().get("documents", [])
        if not docs:
            return None
        d = docs[0]
        if not d.get("y") or not d.get("x"):
            return None
        return float(d["y"]), float(d["x"])
    except Exception as e:
        logger.warning(f"kakao address 실패 addr='{addr}': {e}")
        return None


def diagnose(
    coord_sources: list[str],
    sigungu_prefix: str | None,
    limit: int | None,
    threshold_m: float,
    out_path: Path | None,
) -> None:
    logger = setup_logger("diagnose_coord_drift")
    if not KAKAO_API_KEY:
        logger.error("KAKAO_API_KEY 미설정")
        sys.exit(1)

    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    conn = get_connection()
    cur = get_dict_cursor(conn)

    where = ["lat IS NOT NULL", "lng IS NOT NULL", "plat_plc IS NOT NULL", "LENGTH(plat_plc) > 5"]
    params: list = []
    placeholders = ",".join(["%s"] * len(coord_sources))
    where.append(f"coord_source IN ({placeholders})")
    params.extend(coord_sources)
    if sigungu_prefix:
        where.append("sigungu_code LIKE %s")
        params.append(f"{sigungu_prefix}%")

    sql = f"""
        SELECT pnu, bld_nm, sigungu_code, plat_plc, new_plat_plc,
               lat AS db_lat, lng AS db_lng, coord_source, total_hhld_cnt
        FROM apartments
        WHERE {" AND ".join(where)}
        ORDER BY pnu
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql, params)
    targets = cur.fetchall()
    logger.info(f"진단 대상: {len(targets)}건 (sources={coord_sources}, sigungu_prefix={sigungu_prefix}, threshold={threshold_m}m)")

    drifts: list[dict] = []
    no_geocode = 0
    within_threshold = 0

    for i, apt in enumerate(targets, 1):
        coord = _kakao_address_lookup(apt["plat_plc"], headers, logger)
        if not coord:
            no_geocode += 1
            continue
        new_lat, new_lng = coord
        dist = _distance_m(apt["db_lat"], apt["db_lng"], new_lat, new_lng)
        if dist < threshold_m:
            within_threshold += 1
            continue
        drifts.append({
            "pnu": apt["pnu"],
            "bld_nm": apt["bld_nm"],
            "sigungu_code": apt["sigungu_code"],
            "total_hhld_cnt": apt["total_hhld_cnt"],
            "coord_source": apt["coord_source"],
            "plat_plc": apt["plat_plc"],
            "new_plat_plc": apt["new_plat_plc"],
            "db_lat": apt["db_lat"],
            "db_lng": apt["db_lng"],
            "geocoded_lat": new_lat,
            "geocoded_lng": new_lng,
            "drift_m": round(dist, 1),
        })

        if i % 200 == 0 or i == len(targets):
            logger.info(f"  진행 {i}/{len(targets)} | drift>={threshold_m}m: {len(drifts)} | <threshold: {within_threshold} | geocode실패: {no_geocode}")

    drifts.sort(key=lambda r: -r["drift_m"])

    print()
    print("=" * 90)
    print(f"진단 완료: 총 {len(targets)}건 중 drift≥{threshold_m}m: {len(drifts)}건 "
          f"(임계 미만 {within_threshold}, geocode실패 {no_geocode})")
    print("=" * 90)
    if drifts:
        print(f"{'pnu':<22} {'시군구':<7} {'세대':<5} {'drift(m)':>9}  {'단지명'}")
        print("-" * 90)
        for r in drifts[:30]:
            print(f"{r['pnu']:<22} {r['sigungu_code']:<7} {str(r['total_hhld_cnt'] or '-'):<5} {r['drift_m']:>9.1f}  {r['bld_nm']}")
        if len(drifts) > 30:
            print(f"... ({len(drifts) - 30}건 더)")

    if out_path and drifts:
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(drifts[0].keys()))
            writer.writeheader()
            writer.writerows(drifts)
        print()
        print(f"CSV 저장: {out_path} ({len(drifts)}건)")

    conn.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="kakao_keyword,kakao_keyword_v2",
                   help="검사 대상 coord_source (콤마 구분, 기본 kakao_keyword,kakao_keyword_v2)")
    p.add_argument("--sigungu", help="시군구 코드 prefix (예: 11140 = 서울 중구)")
    p.add_argument("--limit", type=int, help="최대 검사 건수 (테스트용)")
    p.add_argument("--threshold-m", type=float, default=100.0,
                   help="이 거리(m) 이상 차이만 보고 (기본 100)")
    p.add_argument("--out", type=Path, help="CSV 출력 경로 (생략 시 표만 출력)")
    args = p.parse_args()

    sources = [s.strip() for s in args.source.split(",") if s.strip()]
    diagnose(
        coord_sources=sources,
        sigungu_prefix=args.sigungu,
        limit=args.limit,
        threshold_m=args.threshold_m,
        out_path=args.out,
    )


if __name__ == "__main__":
    main()
