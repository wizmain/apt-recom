"""아파트 좌표 drift 보정 — kakao_keyword 계열 오매칭 정정.

진단(`scripts.diagnose_coord_drift`)에서 식별된 의심 단지를 PNU 지번주소(`plat_plc`)
기반으로 재 geocoding 하여 좌표를 정정한다.

안전장치:
  - TRADE_* 접두 PNU 제외 (plat_plc 정확도 부족)
  - 카카오 응답 b_code(법정동) 앞 5자리가 DB sigungu_code와 일치해야 적용
  - drift < threshold 인 단지는 건드리지 않음

대상: coord_source IN ('kakao_keyword', 'kakao_keyword_v2')
적용 후: coord_source = 'fix_pnu_jibun'

사용 예:
  # 로컬 dry-run (변경 없이 결과만 표시)
  .venv/bin/python -m batch.fix_coord_drift --target local --dry-run

  # 로컬에 적용
  .venv/bin/python -m batch.fix_coord_drift --target local

  # Railway에 적용 (로컬 적용 후 동일 변경 반영)
  .venv/bin/python -m batch.fix_coord_drift --target railway

  # 한번에 양쪽
  .venv/bin/python -m batch.fix_coord_drift --target both
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

from batch.config import KAKAO_API_KEY, KAKAO_RATE
from batch.fix_apartment_info import _distance_m
from batch.logger import setup_logger

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_REVERSE_URL = "https://dapi.kakao.com/v2/local/geo/coord2address.json"
NEW_COORD_SOURCE = "fix_pnu_jibun"


def _kakao_reverse(lat: float, lng: float, headers: dict, logger) -> tuple[str, str, str] | None:
    """좌표 역지오코딩 → (region_3depth, main_no, sub_no). 실패 시 None."""
    try:
        r = requests.get(KAKAO_REVERSE_URL, headers=headers,
                         params={"x": lng, "y": lat}, timeout=5)
        r.raise_for_status()
        time.sleep(KAKAO_RATE)
        docs = r.json().get("documents", [])
        if not docs:
            return None
        a = docs[0].get("address") or {}
        region = (a.get("region_3depth_name") or "").strip()
        if not region:
            return None
        main_no = str(a.get("main_address_no") or "").strip()
        sub_no = str(a.get("sub_address_no") or "").strip()
        return (region, main_no, sub_no)
    except Exception as e:
        logger.warning(f"reverse 실패 ({lat},{lng}): {e}")
        return None


def _parse_plat_jibun(plat: str) -> tuple[str, str, str]:
    """plat_plc → (region_3depth, main_no, sub_no)."""
    if not plat:
        return "", "", ""
    s = plat.replace("번지", "").strip()
    parts = s.split()
    region, bonbun = "", ""
    for i, t in enumerate(parts):
        if t.endswith("동") or t.endswith("리") or t.endswith("가"):
            region = t
            if i + 1 < len(parts):
                bonbun = parts[i + 1]
            break
    if "-" in bonbun:
        main_no, _, sub_no = bonbun.partition("-")
    else:
        main_no, sub_no = bonbun, ""
    return region, main_no, sub_no


def _kakao_address(addr: str, headers: dict, logger) -> dict | None:
    """plat_plc → {lat, lng, b_code, address_name}. 실패 시 None."""
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
        addr_info = d.get("address") or {}
        return {
            "lat": float(d["y"]),
            "lng": float(d["x"]),
            "b_code": addr_info.get("b_code") or "",
            "address_name": addr_info.get("address_name") or "",
        }
    except Exception as e:
        logger.warning(f"kakao address 실패 addr='{addr}': {e}")
        return None


def _select_targets(conn, limit: int | None, from_csv: Path | None,
                    csv_min_drift_m: float) -> list[dict]:
    """보정 대상(원본). 진단과 동일 조건 + TRADE_* 제외.

    from_csv 가 주어지면 진단 CSV(coord_drift.csv) 의 PNU 만 대상으로 좁힌다 (시간 단축).
    csv_min_drift_m 이상의 단지만 후보로 사용.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    base_sql = """
        SELECT pnu, bld_nm, sigungu_code, plat_plc, new_plat_plc,
               lat AS db_lat, lng AS db_lng, coord_source
        FROM apartments
        WHERE coord_source IN ('kakao_keyword', 'kakao_keyword_v2')
          AND lat IS NOT NULL AND lng IS NOT NULL
          AND plat_plc IS NOT NULL AND LENGTH(plat_plc) > 5
          AND pnu NOT LIKE 'TRADE\\_%%' ESCAPE '\\'
    """

    if from_csv:
        with from_csv.open() as f:
            pnus = [r["pnu"] for r in csv.DictReader(f)
                    if not r["pnu"].startswith("TRADE_")
                    and float(r["drift_m"]) >= csv_min_drift_m]
        if not pnus:
            return []
        ph = ",".join(["%s"] * len(pnus))
        sql = base_sql + f" AND pnu IN ({ph}) ORDER BY pnu"
        if limit:
            sql += f" LIMIT {int(limit)}"
        cur.execute(sql, pnus)
        return cur.fetchall()

    sql = base_sql + " ORDER BY pnu"
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql)
    return cur.fetchall()


def _build_corrections(targets: list[dict], threshold_m: float,
                       require_jibun_mismatch: bool, logger) -> list[dict]:
    """카카오 address API로 재검증 → 적용 후보 반환.

    require_jibun_mismatch=True 면 추가로 DB 좌표를 역지오코딩하여 그 지번이
    plat_plc 지번과 다를 때만 보정 후보로 채택한다 (작은 drift 영역에서 단지
    내부 좌표 차이를 자동 제외).
    """
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    corrections: list[dict] = []
    rejected_no_geo = 0
    rejected_sgg_mismatch = 0
    rejected_jibun_match = 0
    skipped_within_threshold = 0

    for i, apt in enumerate(targets, 1):
        geo = _kakao_address(apt["plat_plc"], headers, logger)
        if not geo:
            rejected_no_geo += 1
            continue

        # 안전장치 1: b_code 시군구 prefix가 DB sigungu_code 와 일치
        b_sgg = (geo["b_code"] or "")[:5]
        if not b_sgg or b_sgg != apt["sigungu_code"]:
            rejected_sgg_mismatch += 1
            logger.info(f"  [reject sgg-mismatch] pnu={apt['pnu']} bld='{apt['bld_nm']}' "
                        f"db_sgg={apt['sigungu_code']} → kakao_sgg={b_sgg}")
            continue

        dist = _distance_m(apt["db_lat"], apt["db_lng"], geo["lat"], geo["lng"])
        if dist < threshold_m:
            skipped_within_threshold += 1
            continue

        # 안전장치 2 (옵션): DB 좌표 역지오코딩 지번 == plat_plc 지번 이면 단지 내부
        # 좌표 차이일 뿐이므로 보정에서 제외. C단계(작은 drift)에서 권장.
        if require_jibun_mismatch:
            db_jibun = _kakao_reverse(apt["db_lat"], apt["db_lng"], headers, logger)
            plat_jibun = _parse_plat_jibun(apt["plat_plc"])
            if db_jibun and plat_jibun and db_jibun == plat_jibun:
                rejected_jibun_match += 1
                if rejected_jibun_match <= 5 or rejected_jibun_match % 20 == 0:
                    logger.info(f"  [skip jibun-match] pnu={apt['pnu']} bld='{apt['bld_nm']}' "
                                f"jibun={'/'.join(plat_jibun)} (단지 내부 좌표 차이)")
                continue

        corrections.append({
            "pnu": apt["pnu"],
            "bld_nm": apt["bld_nm"],
            "sigungu_code": apt["sigungu_code"],
            "old_lat": apt["db_lat"],
            "old_lng": apt["db_lng"],
            "old_source": apt["coord_source"],
            "new_lat": geo["lat"],
            "new_lng": geo["lng"],
            "drift_m": round(dist, 1),
            "matched_addr": geo["address_name"],
        })

        if i % 20 == 0 or i == len(targets):
            logger.info(f"  진단 진행 {i}/{len(targets)} | apply: {len(corrections)} | "
                        f"reject(sgg): {rejected_sgg_mismatch} | reject(jibun-match): {rejected_jibun_match} | "
                        f"reject(geo): {rejected_no_geo} | skip(<thresh): {skipped_within_threshold}")

    logger.info(f"보정 후보: {len(corrections)}건 (rejected: sgg={rejected_sgg_mismatch}, "
                f"jibun-match={rejected_jibun_match}, geo={rejected_no_geo}, "
                f"within-threshold={skipped_within_threshold})")
    return corrections


def _apply_to(conn, name: str, corrections: list[dict], dry_run: bool, logger) -> int:
    """대상 DB에 UPDATE 적용. 적용 건수 반환."""
    if not corrections:
        return 0
    cur = conn.cursor()
    applied = 0
    for c in corrections:
        if dry_run:
            applied += 1
            continue
        cur.execute(
            "UPDATE apartments SET lat = %s, lng = %s, coord_source = %s WHERE pnu = %s",
            [c["new_lat"], c["new_lng"], NEW_COORD_SOURCE, c["pnu"]],
        )
        if cur.rowcount == 1:
            applied += 1
        else:
            logger.warning(f"  [{name}] pnu={c['pnu']} UPDATE rowcount={cur.rowcount} (대상 없음?)")
    if not dry_run:
        conn.commit()
    logger.info(f"[{name}] {'(dry-run) ' if dry_run else ''}UPDATE 적용: {applied}/{len(corrections)}")
    return applied


def _print_summary(corrections: list[dict]) -> None:
    if not corrections:
        return
    print()
    print(f"{'pnu':<22} {'시군구':<6} {'drift(m)':>9}  {'단지명'}")
    print("-" * 80)
    for c in sorted(corrections, key=lambda r: -r["drift_m"])[:20]:
        print(f"{c['pnu']:<22} {c['sigungu_code']:<6} {c['drift_m']:>9.1f}  {c['bld_nm']}")
    if len(corrections) > 20:
        print(f"... ({len(corrections) - 20}건 더)")
    print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", choices=["local", "railway", "both"], default="local",
                   help="적용 대상 DB (기본: local)")
    p.add_argument("--threshold-m", type=float, default=1000.0,
                   help="이 거리(m) 이상 차이만 보정 (기본 1000)")
    p.add_argument("--limit", type=int, help="대상 최대 건수 (테스트용)")
    p.add_argument("--dry-run", action="store_true", help="UPDATE 실행 없이 결과만 표시")
    p.add_argument("--from-csv", type=Path, default=None,
                   help="진단 CSV (예: coord_drift.csv) 의 PNU 만 대상으로 좁히기")
    p.add_argument("--csv-min-drift-m", type=float, default=1000.0,
                   help="--from-csv 사용 시 CSV에서 이 거리 이상만 후보로 사용 (기본 1000)")
    p.add_argument("--require-jibun-mismatch", action="store_true",
                   help="DB 좌표 역지오코딩 지번이 plat_plc 지번과 다를 때만 보정 (작은 drift 영역에서 권장)")
    args = p.parse_args()

    logger = setup_logger("fix_coord_drift")
    if not KAKAO_API_KEY:
        logger.error("KAKAO_API_KEY 미설정")
        sys.exit(1)

    local_url = os.getenv("DATABASE_URL")
    railway_url = os.getenv("RAILWAY_DATABASE_URL")
    if not local_url:
        logger.error("DATABASE_URL 미설정")
        sys.exit(1)
    if args.target in ("railway", "both") and not railway_url:
        logger.error("RAILWAY_DATABASE_URL 미설정")
        sys.exit(1)

    # DB 연결
    local = psycopg2.connect(local_url)
    railway = psycopg2.connect(railway_url) if args.target in ("railway", "both") else None

    # 후보 선정 기준 DB: target=railway 일 땐 Railway 기준 (로컬에 이미 적용된 경우 대응)
    src_conn, src_name = (railway, "railway") if args.target == "railway" else (local, "local")

    targets = _select_targets(src_conn, args.limit, args.from_csv, args.csv_min_drift_m)
    src_label = f"from_csv={args.from_csv}" if args.from_csv else "DB 전수"
    logger.info(f"대상 단지({src_name} 기준): {len(targets)}건 ({src_label}, "
                f"threshold={args.threshold_m}m, TRADE_* 제외)")

    corrections = _build_corrections(targets, args.threshold_m,
                                     args.require_jibun_mismatch, logger)
    _print_summary(corrections)

    # 적용
    apply_dbs: list[tuple[str, "psycopg2.extensions.connection"]] = []
    if args.target in ("local", "both"):
        apply_dbs.append(("local", local))
    if args.target in ("railway", "both"):
        apply_dbs.append(("railway", railway))

    try:
        for name, conn in apply_dbs:
            _apply_to(conn, name, corrections, args.dry_run, logger)
    finally:
        local.close()
        if railway is not None:
            railway.close()


if __name__ == "__main__":
    main()
