"""needs_review 좌표 후보 중 안전 구간(Tier A)을 일괄 승인·반영한다.

배경
  batch/kakao_poi_coord_pipeline.py 의 자동승인 조건은
    address_score >= 1.0  AND  distance <= 1000m (아파트 POI 기준 total >= 82)
  인데, 이 중 address_score 게이트가 정상 후보를 대량으로 붙잡고 있다.
  Kakao POI 가 지번을 `산울동 산 14` 로, DB 는 `산울동 378-4` 로 적는 식의
  표기 차이만으로 address_mismatch(0.0) 가 되기 때문이다.

Tier A 정의 — 이름이 완전히 일치하는 아파트 POI 가 코앞에 있는 경우
  rank 1 · match_status='needs_review'
  · 아파트 카테고리(reason 에 apt_category)
  · name_score >= 1.0 (이름 완전일치)
  · distance <= 200m
  · bad_place_word 없음
  · 대상 아파트의 coord_source 가 PROTECTED_SOURCES 가 아님

  주소 표기 불일치만이 보류 사유이고, 반영해도 좌표 이동이 200m 를 넘지 않아
  최악의 경우에도 같은 단지 반경 안이다. 이동 상한이 곧 안전장치다.

  거리로만 보류된 원거리 건(주소는 완전일치, 현재 좌표가 틀린 케이스)은
  Tier B 로 분리되어 있으며 이 스크립트의 대상이 아니다.

반영 내용 (PNU 1건당)
  1. apt_coord_history 에 old→new 기록 (롤백 근거)
  2. apartments.lat/lng/coord_source 갱신
     coord_source 는 kakao_place_poi_verified — PROTECTED_SOURCES 에 포함되어
     자동 파이프라인이 다시 덮어쓰지 못한다
  3. 해당 후보 행의 match_status 를 bulk_verified 로 변경

사용
  .venv/bin/python scripts/approve_needs_review_coords.py                    # 리포트 (기본)
  .venv/bin/python scripts/approve_needs_review_coords.py --limit 20
  .venv/bin/python scripts/approve_needs_review_coords.py --apply            # 로컬 반영
  .venv/bin/python scripts/approve_needs_review_coords.py --target both --apply

롤백
  apt_coord_history 의 method='bulk_review_tier_a' 행으로 old_lat/old_lng 복원 가능.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from batch.config import KAKAO_RATE  # noqa: E402
from batch.kakao_poi_coord_pipeline import PROTECTED_SOURCES  # noqa: E402

# 채택 기준 — 변경 시 이 블록만 수정
MIN_NAME_SCORE = 1.0
TIER_A_MAX_DISTANCE_M = 200.0    # Tier A: 이동 상한이 곧 안전장치
TIER_B_MIN_DISTANCE_M = 1000.0   # Tier B: 거리 페널티로만 보류된 구간

# Tier B 지오코딩 판정 임계 — DB 주소를 독립 지오코딩한 지점 기준
GEO_NEAR_M = 300.0   # 이 이내면 "맞는 좌표"
GEO_FAR_M = 1000.0   # 이 초과면 "틀린 좌표"

NEW_COORD_SOURCE = "kakao_place_poi_verified"
NEW_MATCH_STATUS = "bulk_verified"
HISTORY_METHOD = {"a": "bulk_review_tier_a", "b": "bulk_review_tier_b"}

KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

_SELECT_COLS = """
    SELECT cd.pnu, cd.kakao_place_id, cd.place_name, cd.address_name,
           cd.road_address_name, cd.lat AS new_lat, cd.lng AS new_lng,
           cd.distance_m, cd.name_score, cd.address_score, cd.total_score, cd.reason,
           a.bld_nm, a.plat_plc, a.new_plat_plc,
           a.lat AS old_lat, a.lng AS old_lng, a.coord_source AS old_coord_source
    FROM apt_coord_candidates cd
    JOIN apartments a ON a.pnu = cd.pnu
    WHERE cd.match_status = 'needs_review'
      AND cd.rank = 1
      AND cd.reason LIKE '%%apt_category%%'
      AND cd.reason NOT LIKE '%%bad_place_word%%'
      AND cd.name_score >= %s
      AND cd.distance_m IS NOT NULL
      AND (a.coord_source IS NULL OR a.coord_source NOT IN %s)
"""

# Tier A — 주소 표기만 어긋난 근거리. 반영해도 좌표가 상한 이상 움직이지 않는다.
SELECT_SQL_A = _SELECT_COLS + """
      AND cd.distance_m <= %s
    ORDER BY cd.distance_m, cd.pnu
"""

# Tier B — 이름·주소가 모두 완전일치인데 거리 페널티(-20)로 총점이 깎여 보류된 건.
# 주소가 일치하는데 좌표가 멀다는 것은 현재 좌표 쪽이 틀렸다는 신호다.
# 다만 그것만으로는 확정할 수 없어, 반영 직전 DB 주소를 독립 지오코딩해
# 현재 좌표와 POI 중 어느 쪽이 실제 주소 위치인지 확인한다.
SELECT_SQL_B = _SELECT_COLS + """
      AND cd.address_score >= 1.0
      AND cd.distance_m > %s
    ORDER BY cd.distance_m DESC, cd.pnu
"""


def _connect(target: str):
    key = "DATABASE_URL" if target == "local" else "RAILWAY_DATABASE_URL"
    url = os.environ.get(key)
    if not url:
        raise SystemExit(f"{key} 환경변수가 없습니다.")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def _distance_m(lat1, lng1, lat2, lng2) -> float | None:
    if None in (lat1, lng1, lat2, lng2):
        return None
    r = 6371000.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lng2) - float(lng1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _geocode(addr: str, headers: dict) -> tuple[float, float] | None:
    if not addr:
        return None
    try:
        resp = requests.get(KAKAO_ADDRESS_URL, headers=headers,
                            params={"query": addr, "size": 1}, timeout=5)
    except requests.RequestException:
        return None
    finally:
        time.sleep(KAKAO_RATE)
    if not resp.ok:
        return None
    docs = resp.json().get("documents", [])
    return (float(docs[0]["y"]), float(docs[0]["x"])) if docs else None


def verify_tier_b(rows: list[dict], headers: dict) -> list[dict]:
    """DB 주소를 독립 지오코딩해 현재 좌표와 POI 중 어느 쪽이 맞는지 판정한다.

    주소가 지오코딩된 지점이 POI 에 붙어 있고 현재 좌표와는 멀면 현재 좌표가
    틀린 것이다(POI_RIGHT). 그 반대면 POI 가 동명의 다른 건물이다.
    판단이 서지 않으면 반영하지 않는다.
    """
    for r in rows:
        geo = _geocode(r["plat_plc"] or r["new_plat_plc"], headers)
        r["geo_lat"], r["geo_lng"] = (geo or (None, None))
        d_poi = _distance_m(r["geo_lat"], r["geo_lng"], r["new_lat"], r["new_lng"])
        d_cur = _distance_m(r["geo_lat"], r["geo_lng"], r["old_lat"], r["old_lng"])
        r["d_geo_poi"], r["d_geo_cur"] = d_poi, d_cur
        if d_poi is None or d_cur is None:
            r["verdict"] = "NO_GEOCODE"
        elif d_poi <= GEO_NEAR_M and d_cur > GEO_FAR_M:
            r["verdict"] = "POI_RIGHT"
        elif d_cur <= GEO_NEAR_M and d_poi > GEO_FAR_M:
            r["verdict"] = "CURRENT_RIGHT"
        else:
            r["verdict"] = "AMBIGUOUS"
    return rows


def select_targets(cur, tier: str, limit: int, headers: dict) -> list[dict]:
    if tier == "a":
        sql, params = SELECT_SQL_A, [MIN_NAME_SCORE, PROTECTED_SOURCES, TIER_A_MAX_DISTANCE_M]
    else:
        sql, params = SELECT_SQL_B, [MIN_NAME_SCORE, PROTECTED_SOURCES, TIER_B_MIN_DISTANCE_M]
    if limit > 0:
        sql += " LIMIT %s"
        params.append(limit)
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]

    if tier == "b":
        print(f"  지오코딩 검증 {len(rows)}건...")
        rows = verify_tier_b(rows, headers)
    return rows


def apply_one(conn, cur, rows: list[dict], tier: str) -> int:
    write = conn.cursor()
    applied = 0
    for r in rows:
        write.execute(
            """
            INSERT INTO apt_coord_history (
                pnu, old_lat, old_lng, old_coord_source,
                new_lat, new_lng, new_coord_source,
                kakao_place_id, place_name, match_status, total_score, method
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                r["pnu"], r["old_lat"], r["old_lng"], r["old_coord_source"],
                r["new_lat"], r["new_lng"], NEW_COORD_SOURCE,
                r["kakao_place_id"], r["place_name"], NEW_MATCH_STATUS,
                r["total_score"], HISTORY_METHOD[tier],
            ],
        )
        write.execute(
            "UPDATE apartments SET lat=%s, lng=%s, coord_source=%s WHERE pnu=%s",
            [r["new_lat"], r["new_lng"], NEW_COORD_SOURCE, r["pnu"]],
        )
        write.execute(
            """UPDATE apt_coord_candidates
                  SET match_status=%s, coord_source=%s
                WHERE pnu=%s AND rank=1""",
            [NEW_MATCH_STATUS, NEW_COORD_SOURCE, r["pnu"]],
        )
        applied += 1
    conn.commit()
    return applied


def report(rows: list[dict], tier: str) -> None:
    if not rows:
        print("  대상 없음")
        return
    dists = [r["distance_m"] for r in rows]
    print(f"  후보 {len(rows)}건 — 현재좌표↔POI 최소 {min(dists):.1f}m / "
          f"중앙 {sorted(dists)[len(dists)//2]:.1f}m / 최대 {max(dists):.1f}m")

    srcs: dict[str, int] = {}
    for r in rows:
        srcs[r["old_coord_source"] or "(없음)"] = srcs.get(r["old_coord_source"] or "(없음)", 0) + 1
    print(f"  기존 coord_source: {sorted(srcs.items(), key=lambda x: -x[1])}")

    if tier == "b":
        tally: dict[str, int] = {}
        for r in rows:
            tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
        print(f"  지오코딩 판정: {sorted(tally.items(), key=lambda x: -x[1])}")
        skipped = [r for r in rows if r["verdict"] != "POI_RIGHT"]
        if skipped:
            print("  [반영 제외]")
            for r in skipped:
                print(f"    {r['verdict']} {(r['bld_nm'] or '')[:22]:24s} "
                      f"주소={r['plat_plc'] or r['new_plat_plc']}")
                print(f"        지오코딩→POI {r['d_geo_poi'] and round(r['d_geo_poi'])}m "
                      f"/ →현재좌표 {r['d_geo_cur'] and round(r['d_geo_cur'])}m")

    print("\n  표본 (현재좌표와 가장 멀리 떨어진 10건)")
    for r in sorted(rows, key=lambda x: -x["distance_m"])[:10]:
        print(f"    {(r['bld_nm'] or '')[:22]:24s} {r['distance_m']:9.1f}m  "
              f"{r['old_coord_source']} → {NEW_COORD_SOURCE}")
        print(f"        DB  ={r['plat_plc'] or r['new_plat_plc']}")
        print(f"        POI ={r['place_name']} | {r['address_name']}")


def run(target: str, tier: str, apply: bool, limit: int, out: str, headers: dict) -> list[dict]:
    conn = _connect(target)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print(f"\n[{target}] {'APPLY' if apply else 'REPORT'} tier={tier}")
    rows = select_targets(cur, tier, limit, headers)
    report(rows, tier)

    # Tier B 는 지오코딩으로 현재 좌표가 틀렸다고 확인된 건만 반영한다.
    applicable = [r for r in rows if tier == "a" or r["verdict"] == "POI_RIGHT"]

    if apply and applicable:
        applied = apply_one(conn, cur, applicable, tier)
        print(f"\n  반영 완료: {applied}건 (후보 {len(rows)}건 중)")
    elif not apply:
        conn.rollback()
        print(f"\n  REPORT 모드 — DB 변경 없음 (반영 대상 {len(applicable)}건)")

    if out:
        Path(out).write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        print(f"  결과 JSON: {out}")

    conn.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tier", choices=["a", "b"], default="a")
    ap.add_argument("--target", choices=["local", "railway", "both"], default="local")
    ap.add_argument("--apply", action="store_true", help="실제 반영 (기본은 리포트)")
    ap.add_argument("--limit", type=int, default=0, help="처리 건수 제한 (0=전체)")
    ap.add_argument("--out", default="", help="결과 JSON 저장 경로 (타깃별로 접미사가 붙는다)")
    args = ap.parse_args()

    if args.tier == "a":
        print(f"Tier A: 아파트 POI · name >= {MIN_NAME_SCORE} · "
              f"distance <= {TIER_A_MAX_DISTANCE_M:.0f}m · bad_place_word 없음")
    else:
        print(f"Tier B: 아파트 POI · name >= {MIN_NAME_SCORE} · address_score >= 1.0 · "
              f"distance > {TIER_B_MIN_DISTANCE_M:.0f}m · DB 주소 지오코딩으로 재검증")

    headers = {"Authorization": f"KakaoAK {os.environ.get('KAKAO_API_KEY', '')}"}
    if args.tier == "b" and not os.environ.get("KAKAO_API_KEY"):
        raise SystemExit("Tier B 검증에는 KAKAO_API_KEY 가 필요합니다.")

    targets = ["local", "railway"] if args.target == "both" else [args.target]
    for target in targets:
        out = ""
        if args.out:
            p = Path(args.out)
            out = str(p.with_name(f"{p.stem}_{target}{p.suffix}")) if len(targets) > 1 else args.out
        run(target, args.tier, args.apply, args.limit, out, headers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
