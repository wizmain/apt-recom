"""needs_review 좌표 후보를 구간별로 일괄 승인·폐기한다.

배경
  batch/kakao_poi_coord_pipeline.py 의 자동승인 조건은
    address_score >= 1.0  AND  distance <= 1000m (아파트 POI 기준 total >= 82)
  인데, 두 게이트가 각각 다른 방식으로 정상 후보를 붙잡는다.
    - address_score: Kakao 가 지번을 `산울동 산 14` 로, DB 는 `산울동 378-4` 로
      적는 표기 차이만으로 0.0 이 된다
    - distance: 현재 좌표가 틀려서 멀어진 경우까지 페널티(-20)를 받는다
  전자는 근거리 오탐(Tier A), 후자는 원거리 오좌표(Tier B/C)로 나타난다.

Tier A — 주소 표기만 어긋난 근거리
  아파트 POI · name_score >= 1.0 · distance <= 200m · bad_place_word 없음
  반영해도 좌표 이동이 200m 를 넘지 않아 이동 상한 자체가 안전장치다.

Tier B — 이름·주소 완전일치인데 거리로만 보류
  아파트 POI · name_score >= 1.0 · address_score >= 1.0 · distance > 1000m
  DB 주소를 독립 지오코딩해 현재 좌표와 POI 중 어느 쪽이 실제 주소 위치인지
  확인하고, 현재 좌표가 틀렸다고 확인된 건만 반영한다.

Tier C — 남은 원거리 전체를 지오코딩 판정만으로 정리
  distance > 1000m 인 rank1 전부. 이름/주소 점수를 조건에 걸지 않는다.
  Tier B 가 name_score >= 1.0 을 요구해 `서산 한성필하우스아파트` vs
  `석림한성필하우스아파트` 처럼 지번은 같고 표기만 다른 건을 놓쳤기 때문이다.
  판정 결과에 따라 두 방향으로 처리한다.
    POI_RIGHT     → 좌표 반영
    CURRENT_RIGHT → 후보를 rejected 로 닫는다(좌표 불변). 짧은 아파트명이
                    전국의 동명 지명·상호를 끌어온 경우로, 재검토해도 결론이
                    같아 큐에서 영구 제거한다
    AMBIGUOUS / NO_GEOCODE → 조치 없음

지오코딩 판정 (Tier B/C)
  DB 주소를 Kakao 주소검색으로 지오코딩해 제3의 기준점을 만든다.
    POI_RIGHT     지오코딩 지점이 POI 에 근접(<=GEO_NEAR_M)이고
                  현재 좌표와는 멀다(>GEO_FAR_M) → 현재 좌표가 틀림
    CURRENT_RIGHT 그 반대 → POI 가 동명의 다른 장소
  대상 DB 기준으로 반영 시점에 재검증하므로, 로컬에서 만든 판정 목록을
  프로덕션에 그대로 적용하지 않는다.

반영 내용 (좌표 반영 대상 1건당)
  1. apt_coord_history 에 old→new 기록 (롤백 근거)
  2. apartments.lat/lng/coord_source 갱신
     coord_source 는 kakao_place_poi_verified — PROTECTED_SOURCES 에 포함되어
     자동 파이프라인이 다시 덮어쓰지 못한다
  3. 해당 후보 행의 match_status 를 bulk_verified 로 변경

사용
  .venv/bin/python scripts/approve_needs_review_coords.py --tier a           # 리포트 (기본)
  .venv/bin/python scripts/approve_needs_review_coords.py --tier b --apply
  .venv/bin/python scripts/approve_needs_review_coords.py --tier c --target both --apply

롤백
  apt_coord_history 의 method='bulk_review_tier_a'/'_b'/'_c' 행으로
  old_lat/old_lng 복원 가능. rejected 처리는 좌표를 바꾸지 않으므로
  match_status 를 needs_review 로 되돌리면 원상복구된다.
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
HISTORY_METHOD = {"a": "bulk_review_tier_a", "b": "bulk_review_tier_b",
                  "c": "bulk_review_tier_c"}

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

# Tier C — Tier A/B 처리 후 남은 원거리 구간 전체를 지오코딩 판정만으로 정리한다.
# 이름·주소 점수를 조건에 걸지 않는다. Tier B 가 name_score >= 1.0 을 요구해
# `서산 한성필하우스아파트` vs `석림한성필하우스아파트` 처럼 지번은 같고 표기만
# 다른 건을 놓쳤기 때문이다. 판정 근거는 이름이 아니라 "DB 주소를 지오코딩한
# 지점이 어느 좌표에 붙는가" 하나로 통일한다.
#   POI_RIGHT     → 좌표 반영 (현재 좌표가 틀렸음이 확인됨)
#   CURRENT_RIGHT → 후보를 rejected 로 닫음. 좌표는 건드리지 않는다.
#                   짧은 아파트명이 전국의 동명 지명·상호를 끌어온 경우로,
#                   재검토해도 결론이 같아 큐에서 영구 제거한다.
SELECT_SQL_C = """
    SELECT cd.pnu, cd.kakao_place_id, cd.place_name, cd.address_name,
           cd.road_address_name, cd.lat AS new_lat, cd.lng AS new_lng,
           cd.distance_m, cd.name_score, cd.address_score, cd.total_score, cd.reason,
           a.bld_nm, a.plat_plc, a.new_plat_plc,
           a.lat AS old_lat, a.lng AS old_lng, a.coord_source AS old_coord_source
    FROM apt_coord_candidates cd
    JOIN apartments a ON a.pnu = cd.pnu
    WHERE cd.match_status = 'needs_review'
      AND cd.rank = 1
      AND cd.distance_m > %s
      AND (a.coord_source IS NULL OR a.coord_source NOT IN %s)
    ORDER BY cd.distance_m DESC, cd.pnu
"""

REJECTED_STATUS = "rejected"


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


def verify_by_geocode(rows: list[dict], headers: dict) -> list[dict]:
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
    elif tier == "b":
        sql, params = SELECT_SQL_B, [MIN_NAME_SCORE, PROTECTED_SOURCES, TIER_B_MIN_DISTANCE_M]
    else:
        sql, params = SELECT_SQL_C, [TIER_B_MIN_DISTANCE_M, PROTECTED_SOURCES]
    if limit > 0:
        sql += " LIMIT %s"
        params.append(limit)
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]

    if tier in ("b", "c"):
        print(f"  지오코딩 검증 {len(rows)}건...")
        rows = verify_by_geocode(rows, headers)
    return rows


def close_rejected(conn, rows: list[dict]) -> int:
    """CURRENT_RIGHT 후보를 rejected 로 닫는다. 좌표는 건드리지 않는다."""
    write = conn.cursor()
    closed = 0
    for r in rows:
        write.execute(
            "UPDATE apt_coord_candidates SET match_status=%s WHERE pnu=%s AND rank=1",
            [REJECTED_STATUS, r["pnu"]],
        )
        closed += write.rowcount
    conn.commit()
    return closed


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

    if tier in ("b", "c"):
        tally: dict[str, int] = {}
        for r in rows:
            tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
        print(f"  지오코딩 판정: {sorted(tally.items(), key=lambda x: -x[1])}")
        print(f"    POI_RIGHT     → 좌표 반영 {tally.get('POI_RIGHT', 0)}건")
        if tier == "c":
            print(f"    CURRENT_RIGHT → rejected 로 닫음 {tally.get('CURRENT_RIGHT', 0)}건 (좌표 불변)")
        print(f"    그 외          → 조치 없음 "
              f"{sum(v for k, v in tally.items() if k in ('AMBIGUOUS', 'NO_GEOCODE'))}건")

        if tier == "b":
            for r in [x for x in rows if x["verdict"] != "POI_RIGHT"]:
                print(f"    [제외] {r['verdict']} {(r['bld_nm'] or '')[:22]:24s} "
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

    # Tier B/C 는 지오코딩으로 현재 좌표가 틀렸다고 확인된 건만 반영한다.
    applicable = [r for r in rows if tier == "a" or r["verdict"] == "POI_RIGHT"]
    # Tier C 는 반대 판정(현재 좌표가 맞고 POI 가 동명 타 장소)을 큐에서 닫는다.
    rejectable = [r for r in rows if tier == "c" and r["verdict"] == "CURRENT_RIGHT"]

    if apply:
        applied = apply_one(conn, cur, applicable, tier) if applicable else 0
        closed = close_rejected(conn, rejectable) if rejectable else 0
        print(f"\n  좌표 반영: {applied}건 / rejected 처리: {closed}건 (후보 {len(rows)}건 중)")
    else:
        conn.rollback()
        print(f"\n  REPORT 모드 — DB 변경 없음 "
              f"(반영 대상 {len(applicable)}건, rejected 대상 {len(rejectable)}건)")

    if out:
        Path(out).write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        print(f"  결과 JSON: {out}")

    conn.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tier", choices=["a", "b", "c"], default="a")
    ap.add_argument("--target", choices=["local", "railway", "both"], default="local")
    ap.add_argument("--apply", action="store_true", help="실제 반영 (기본은 리포트)")
    ap.add_argument("--limit", type=int, default=0, help="처리 건수 제한 (0=전체)")
    ap.add_argument("--out", default="", help="결과 JSON 저장 경로 (타깃별로 접미사가 붙는다)")
    args = ap.parse_args()

    if args.tier == "a":
        print(f"Tier A: 아파트 POI · name >= {MIN_NAME_SCORE} · "
              f"distance <= {TIER_A_MAX_DISTANCE_M:.0f}m · bad_place_word 없음")
    elif args.tier == "b":
        print(f"Tier B: 아파트 POI · name >= {MIN_NAME_SCORE} · address_score >= 1.0 · "
              f"distance > {TIER_B_MIN_DISTANCE_M:.0f}m · DB 주소 지오코딩으로 재검증")
    else:
        print(f"Tier C: distance > {TIER_B_MIN_DISTANCE_M:.0f}m 전체 · 이름/주소 점수 무관 · "
              f"DB 주소 지오코딩 판정만으로 반영·폐기 결정")

    headers = {"Authorization": f"KakaoAK {os.environ.get('KAKAO_API_KEY', '')}"}
    if args.tier in ("b", "c") and not os.environ.get("KAKAO_API_KEY"):
        raise SystemExit(f"Tier {args.tier.upper()} 검증에는 KAKAO_API_KEY 가 필요합니다.")

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
