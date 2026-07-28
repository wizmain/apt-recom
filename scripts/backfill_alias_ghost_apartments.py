"""괄호 별칭 때문에 생성된 기존 TRADE_ 유령 레코드를 진본으로 되돌리는 백필.

배경
  batch/trade/enrich_apartments.py 의 _name_variants() 수정으로 앞으로 들어오는
  신규 apt_seq 는 괄호 별칭형 이름도 정상 매칭된다. 그러나 enrich 는 미매핑
  apt_seq 만 처리하므로, 이미 만들어진 유령 레코드는 자동 복구되지 않는다.
  본 스크립트가 그 잔여분을 처리한다.

판정 절차 (유령 1건당)
  1. _name_variants() 의 변형으로 Kakao 키워드 검색 (원본은 이미 실패한 이름이라 제외)
  2. 검색 성공 시 좌표·주소 확보
  3. 진본 후보 탐색 — (a) 별칭 정규화 이름이 같은 시군구 진본과 일치
                      (b) 검색된 도로명/지번 주소가 진본 주소와 일치
  4. 게이트 4종을 모두 통과해야 REMAP 후보로 채택

게이트
  names_overlap  거래명과 진본명의 공통 부분문자열 비율 (enrich 와 동일 기준)
  timeline       거래 연도·build_year 와 진본 준공일 정합 (enrich 와 동일 기준)
  max_floor      거래 최고층 <= 진본 최고층
  area           거래 면적의 과반이 진본 주택형(apt_area_type)과 ±0.3㎡ 이내

  뒤의 두 개는 enrich 에 없는 추가 검증이다. 수동 검증 사례에서 이 둘이
  결정적이었다 — apt_seq `29200_부영애시앙1차` 는 Kakao 주소가 진본과 같지만
  거래에 진본에 없는 84.28㎡ 주택형과 21층이 있어 병합 대상이 아니었다.
  이름·주소만으로는 이런 건을 걸러내지 못한다.

분류
  REMAP         진본 존재 + 게이트 전체 통과 → --apply 반영 대상
  REJECTED      진본 후보는 찾았으나 게이트 탈락 (사유 기록)
  NO_CANONICAL  검색은 됐으나 대응하는 진본 레코드가 없음 (신규 등록 대상, 본 스크립트 범위 밖)
  NOT_FOUND     모든 변형으로 검색 실패

사용
  .venv/bin/python scripts/backfill_alias_ghost_apartments.py                 # 리포트만 (기본)
  .venv/bin/python scripts/backfill_alias_ghost_apartments.py --limit 50
  .venv/bin/python scripts/backfill_alias_ghost_apartments.py --apply         # REMAP 건 반영
  .venv/bin/python scripts/backfill_alias_ghost_apartments.py --target railway --apply

주의
  --target railway 는 production 에 직접 쓴다. 반드시 리포트를 먼저 검토하고,
  --apply 전에 결과 JSON 의 REMAP 목록을 확인할 것.
  --apply 후에는 가격점수 재계산이 필요하다 (12h 거래 배치가 수행).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from batch.config import KAKAO_API_KEY, KAKAO_RATE  # noqa: E402
from batch.trade.enrich_apartments import (  # noqa: E402
    _name_variants,
    _names_overlap,
    _normalize_name,
    _timeline_consistent,
)

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

MATCH_METHOD = "alias_backfill"
AREA_TOLERANCE = 0.3           # ㎡ — 거래 면적과 진본 주택형의 허용 오차
AREA_MATCH_MIN_RATIO = 0.5     # 거래 중 면적이 일치해야 하는 최소 비율


def _connect(target: str):
    key = "DATABASE_URL" if target == "local" else "RAILWAY_DATABASE_URL"
    url = os.environ.get(key)
    if not url:
        raise SystemExit(f"{key} 환경변수가 없습니다.")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def _rows(cur, sql, params=None):
    cur.execute(sql, params or [])
    return [dict(r) for r in cur.fetchall()]


def _load_context(cur):
    """진본 인덱스와 시군구 지역명을 미리 적재한다."""
    sgg_map = {r["code"]: r["name"] for r in
               _rows(cur, "SELECT code, name FROM common_code WHERE group_id = 'sigungu'")}

    canon_rows = _rows(cur, """
        SELECT pnu, bld_nm, sigungu_code, new_plat_plc, plat_plc,
               use_apr_day, max_floor
        FROM apartments
        WHERE pnu NOT LIKE 'TRADE%%' AND lat IS NOT NULL AND bld_nm IS NOT NULL
    """)

    by_name: dict[tuple[str, str], dict] = {}
    by_addr: dict[tuple[str, str], dict] = {}
    for r in canon_rows:
        sgg = str(r["sigungu_code"] or "")[:5]
        by_name.setdefault((sgg, _normalize_name(r["bld_nm"])), r)
        for col in ("new_plat_plc", "plat_plc"):
            if r[col]:
                by_addr.setdefault((sgg, _norm_addr(r[col])), r)

    areas: dict[str, list[float]] = {}
    for r in _rows(cur, "SELECT pnu, exclusive_area FROM apt_area_type"):
        areas.setdefault(r["pnu"], []).append(float(r["exclusive_area"]))

    return sgg_map, by_name, by_addr, areas


def _norm_addr(addr: str) -> str:
    return " ".join((addr or "").split()).lower()


def _search_variants(headers, region: str, apt_nm: str) -> dict | None:
    """원본을 제외한 변형으로 Kakao 키워드 검색. 첫 성공 결과를 반환한다.

    원본 이름은 유령을 만든 시점에 이미 0건이었으므로 재시도하지 않는다.
    """
    for variant in _name_variants(apt_nm)[1:]:
        try:
            resp = requests.get(
                KAKAO_KEYWORD_URL, headers=headers,
                params={"query": f"{region} {variant} 아파트", "size": 5}, timeout=5,
            )
        except requests.RequestException:
            continue
        finally:
            time.sleep(KAKAO_RATE)

        if not resp.ok:
            continue
        docs = [d for d in resp.json().get("documents", [])
                if "아파트" in (d.get("category_name") or "")]
        if not docs:
            continue
        d = docs[0]
        return {
            "variant": variant,
            "place_name": d.get("place_name"),
            "road_address": d.get("road_address_name") or None,
            "address": d.get("address_name") or None,
        }
    return None


def _deal_stats(cur, ghost_pnu: str) -> dict:
    """유령에 매핑된 실적(매매+전월세)의 층·면적·연도 요약.

    임대 단지는 실적이 rent_history 에만 있는 경우가 많다. 매매만 집계하면
    층·면적·타임라인 게이트가 검증할 데이터 없이 공허하게 통과해, 사실상
    이름 일치만으로 REMAP 이 되어 버린다. 두 테이블을 함께 본다.
    build_year 는 trade_history 에만 있어 매매가 없으면 None 이 된다.
    """
    stat = _rows(cur, """
        SELECT COUNT(*) FILTER (WHERE src = 'trade') trade_count,
               COUNT(*) FILTER (WHERE src = 'rent') rent_count,
               MAX(floor) max_floor,
               MIN(deal_year) min_deal_year,
               PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY build_year) median_build_year
        FROM (
            SELECT 'trade' src, t.floor, t.deal_year, t.build_year
            FROM trade_apt_mapping m JOIN trade_history t ON t.apt_seq = m.apt_seq
            WHERE m.pnu = %s
            UNION ALL
            SELECT 'rent' src, r.floor, r.deal_year, NULL
            FROM trade_apt_mapping m JOIN rent_history r ON r.apt_seq = m.apt_seq
            WHERE m.pnu = %s
        ) d
    """, [ghost_pnu, ghost_pnu])[0]

    stat["areas"] = [float(r["area"]) for r in _rows(cur, """
        SELECT t.exclu_use_ar area FROM trade_apt_mapping m
        JOIN trade_history t ON t.apt_seq = m.apt_seq
        WHERE m.pnu = %s AND t.exclu_use_ar > 0
        UNION ALL
        SELECT r.exclu_use_ar area FROM trade_apt_mapping m
        JOIN rent_history r ON r.apt_seq = m.apt_seq
        WHERE m.pnu = %s AND r.exclu_use_ar > 0
    """, [ghost_pnu, ghost_pnu])]

    stat["record_count"] = (stat["trade_count"] or 0) + (stat["rent_count"] or 0)
    return stat


def _check_gates(ghost_nm: str, canon: dict, stat: dict, canon_areas: list[float]) -> list[str]:
    """게이트 검증. 통과하지 못한 사유 목록을 반환한다 (빈 목록이면 통과)."""
    failures = []

    if not _names_overlap(ghost_nm, canon["bld_nm"]):
        failures.append("names_overlap")

    if not _timeline_consistent(canon.get("use_apr_day"),
                                stat.get("min_deal_year"),
                                stat.get("median_build_year")):
        failures.append("timeline")

    canon_floor, trade_floor = canon.get("max_floor"), stat.get("max_floor")
    if canon_floor and trade_floor and trade_floor > canon_floor:
        failures.append(f"max_floor(거래 {trade_floor} > 진본 {canon_floor})")

    if canon_areas and stat["areas"]:
        matched = sum(1 for a in stat["areas"]
                      if any(abs(a - ca) <= AREA_TOLERANCE for ca in canon_areas))
        ratio = matched / len(stat["areas"])
        if ratio < AREA_MATCH_MIN_RATIO:
            uniq = sorted({round(a, 2) for a in stat["areas"]})
            failures.append(
                f"area(일치 {ratio:.0%} < {AREA_MATCH_MIN_RATIO:.0%}; "
                f"거래 {uniq} vs 진본 {sorted(canon_areas)})"
            )

    return failures


def classify(cur, headers, ghost: dict, sgg_map, by_name, by_addr, areas) -> dict:
    sgg = str(ghost["sigungu_code"] or "")[:5]
    region = sgg_map.get(sgg, "")
    result = {"ghost_pnu": ghost["pnu"], "ghost_nm": ghost["bld_nm"], "sgg_cd": sgg}

    found = _search_variants(headers, region, ghost["bld_nm"])
    if not found:
        result["status"] = "NOT_FOUND"
        return result
    result["search"] = found

    canon = None
    for alias in _name_variants(ghost["bld_nm"])[1:]:
        canon = by_name.get((sgg, _normalize_name(alias)))
        if canon:
            result["matched_by"] = f"name:{alias}"
            break
    if not canon:
        for addr in (found["road_address"], found["address"]):
            if addr:
                canon = by_addr.get((sgg, _norm_addr(addr)))
                if canon:
                    result["matched_by"] = f"address:{addr}"
                    break

    if not canon:
        result["status"] = "NO_CANONICAL"
        return result

    stat = _deal_stats(cur, ghost["pnu"])
    failures = _check_gates(ghost["bld_nm"], canon, stat, areas.get(canon["pnu"], []))

    if failures:
        status = "REJECTED"
    elif stat["record_count"] == 0:
        # 검증할 실적이 하나도 없어 게이트가 공허하게 통과한 경우.
        # 근거가 이름/주소 일치뿐이라 자동 반영 대상에서 제외한다.
        status = "REMAP_WEAK"
    else:
        status = "REMAP"

    result.update({
        "canonical_pnu": canon["pnu"],
        "canonical_nm": canon["bld_nm"],
        "canonical_addr": canon["new_plat_plc"] or canon["plat_plc"],
        "trade_count": stat["trade_count"],
        "rent_count": stat["rent_count"],
        "status": status,
    })
    if failures:
        result["failures"] = failures
    return result


def apply_remaps(conn, cur, remaps: list[dict], logger_print) -> tuple[int, int]:
    """REMAP 건을 반영한다. 전제조건이 깨진 건은 건너뛴다.

    반환: (반영 건수, 건너뛴 건수)
    """
    applied = skipped = 0
    for r in remaps:
        ghost, canon = r["ghost_pnu"], r["canonical_pnu"]

        cur.execute("SELECT 1 FROM apartments WHERE pnu = %s", [ghost])
        if not cur.fetchone():
            logger_print(f"  건너뜀(유령 없음): {r['ghost_nm']}")
            skipped += 1
            continue
        cur.execute("SELECT lat FROM apartments WHERE pnu = %s", [canon])
        row = cur.fetchone()
        if not row or row["lat"] is None:
            logger_print(f"  건너뜀(진본 없음/좌표 없음): {r['ghost_nm']} → {canon}")
            skipped += 1
            continue

        cur.execute(
            "UPDATE trade_apt_mapping SET pnu = %s, match_method = %s WHERE pnu = %s",
            [canon, MATCH_METHOD, ghost],
        )
        cur.execute("DELETE FROM apt_price_score WHERE pnu = %s", [ghost])
        cur.execute("DELETE FROM apartments WHERE pnu = %s", [ghost])
        applied += 1
    conn.commit()
    return applied, skipped


def load_reviewed_remaps(path: str) -> list[dict]:
    """리포트 JSON 에서 REMAP 건만 읽는다.

    --apply 는 전 대상을 재분석하므로 Kakao 응답 변화에 따라 검토 시점과 다른
    집합이 반영될 수 있다. 검토한 결과를 그대로 적용하려면 이 경로를 쓴다.
    """
    data = json.loads(Path(path).read_text())
    return [r for r in data if r.get("status") == "REMAP"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=["local", "railway"], default="local")
    ap.add_argument("--limit", type=int, default=0, help="처리할 유령 수 (0=전체)")
    ap.add_argument("--apply", action="store_true", help="REMAP 건 실제 반영 (기본은 리포트만)")
    ap.add_argument("--out", default="", help="결과 JSON 저장 경로")
    ap.add_argument("--from-report", default="",
                    help="리포트 JSON 의 REMAP 건을 재분석 없이 그대로 반영 (--apply 필요)")
    args = ap.parse_args()

    if args.from_report:
        if not args.apply:
            raise SystemExit("--from-report 는 --apply 와 함께 써야 합니다.")
        conn = _connect(args.target)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        remaps = load_reviewed_remaps(args.from_report)
        print(f"[{args.target}] APPLY (검토본) — REMAP {len(remaps)}건\n")
        applied, skipped = apply_remaps(conn, cur, remaps, print)
        print(f"\n반영 완료: {applied}건 (건너뜀 {skipped}건)")
        print("가격점수 재계산 필요 (12h 거래 배치가 recalc_price 수행)")
        conn.close()
        return 0

    if not KAKAO_API_KEY:
        raise SystemExit("KAKAO_API_KEY 환경변수가 없습니다.")

    conn = _connect(args.target)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    sgg_map, by_name, by_addr, areas = _load_context(cur)

    ghosts = _rows(cur, """
        SELECT pnu, bld_nm, sigungu_code FROM apartments
        WHERE pnu LIKE 'TRADE%%' AND lat IS NULL AND bld_nm ~ '\\([^)]+\\)'
        ORDER BY pnu
    """)
    if args.limit > 0:
        ghosts = ghosts[:args.limit]

    mode = "APPLY" if args.apply else "REPORT"
    print(f"[{args.target}] {mode} — 괄호 별칭 유령 {len(ghosts)}건 분석\n")

    results = []
    for i, ghost in enumerate(ghosts, 1):
        results.append(classify(cur, headers, ghost, sgg_map, by_name, by_addr, areas))
        if i % 50 == 0:
            print(f"  진행 {i}/{len(ghosts)}")

    counts = Counter(r["status"] for r in results)
    print("\n=== 분류 결과 ===")
    for status in ("REMAP", "REMAP_WEAK", "REJECTED", "NO_CANONICAL", "NOT_FOUND"):
        print(f"  {status:14s} {counts.get(status, 0):5d}건")

    remaps = [r for r in results if r["status"] == "REMAP"]
    if remaps:
        print(f"\n=== REMAP 후보 {len(remaps)}건 (게이트 전체 통과) ===")
        for r in remaps[:30]:
            print(f"  {r['ghost_nm']}")
            print(f"     → {r['canonical_pnu']} | {r['canonical_nm']} | {r['canonical_addr']} "
                  f"| 매매 {r['trade_count']} 전월세 {r['rent_count']} | {r.get('matched_by')}")
        if len(remaps) > 30:
            print(f"  ... 외 {len(remaps) - 30}건")

    weak = [r for r in results if r["status"] == "REMAP_WEAK"]
    if weak:
        print(f"\n=== REMAP_WEAK {len(weak)}건 — 실적 0건이라 이름/주소만으로 판정, 자동 반영 제외 ===")
        for r in weak[:15]:
            print(f"  {r['ghost_nm']} → {r['canonical_nm']} ({r.get('matched_by')})")
        if len(weak) > 15:
            print(f"  ... 외 {len(weak) - 15}건")

    rejected = [r for r in results if r["status"] == "REJECTED"]
    if rejected:
        print(f"\n=== 게이트 탈락 {len(rejected)}건 (상위 15) ===")
        for r in rejected[:15]:
            print(f"  {r['ghost_nm']} → {r['canonical_nm']}: {', '.join(r['failures'])}")

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"\n결과 JSON: {args.out}")

    if args.apply and remaps:
        print(f"\n=== 반영 {len(remaps)}건 ===")
        applied, skipped = apply_remaps(conn, cur, remaps, print)
        print(f"\n반영 완료: {applied}건 (건너뜀 {skipped}건)")
        print("가격점수 재계산 필요 (12h 거래 배치가 recalc_price 수행)")
    elif args.apply:
        print("\n반영할 REMAP 건이 없습니다.")
    else:
        conn.rollback()
        print("\nREPORT 모드 — DB 변경 없음. 반영하려면 --apply")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
