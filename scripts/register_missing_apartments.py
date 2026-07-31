"""진본이 DB 에 없는 거래 단지를 건축물대장 검증을 거쳐 신규 등록한다.

배경
  오매핑 감사(PR #197)에서 확인된 잔여 문제의 공통 뿌리는 "옮겨갈 진본이
  DB 에 없다"는 것이다.
    - NO_TARGET 3,361건: 물리적으로 어긋난 매핑인데 대체 진본이 없음
    - TRADE_ 유령 매핑: 좌표 없는 자리표시 레코드에 실적이 묶여 있음
  재매칭·백필로는 해결되지 않고, 실체(정규 PNU 레코드)를 만들어야 한다.

절차 (apt_seq 1건당)
  1. 거래명 변형(_name_variants)으로 Kakao 아파트 POI 검색 → 좌표·주소
  2. 지번 주소 → Kakao 주소검색 → b_code/본번/부번/산여부 → 19자리 PNU 조합
     조합 PNU 앞 5자리가 거래 sgg_cd 와 다르면 동명 타지역 오매칭으로 보고 중단
  3. 조합 PNU 가 이미 apartments 에 있으면 → 재지정 후보 (REPOINT)
     없으면 → 건축물대장 표제부 조회 → 신규 등록 후보 (REGISTER)
  4. 어느 쪽이든 실적 통계와 물리 지표로 재검증(mapping_checks)한 뒤 채택.
     신규 등록은 브랜드-연도 게이트(_brand_year_consistent)도 통과해야 한다.
     면적 대조는 표제부에 전유면적이 없어 신규 등록 경로에는 적용되지 않는다
     (전유부 API 는 호출이 배로 늘어 제외 — 층·준공연도·단지번호로 방어).

분류
  REGISTER      건축물대장 검증 통과 → 신규 등록 + 매핑 재지정
  REPOINT       조합 PNU 가 기존 진본 → 검증 통과 시 매핑만 재지정
  REJECTED      후보는 찾았으나 물리 지표 위반 (사유 기록)
  SGG_MISMATCH  조합 PNU 시군구가 거래와 불일치 (동명 타지역)
  NO_REGISTRY   건축물대장에 해당 지번 건물이 없음
  NO_PNU        주소검색으로 PNU 를 조합하지 못함
  NOT_FOUND     Kakao 아파트 POI 검색 실패

사용
  .venv/bin/python scripts/register_missing_apartments.py                    # 리포트
  .venv/bin/python scripts/register_missing_apartments.py --limit 50
  .venv/bin/python scripts/register_missing_apartments.py --apply --max-calls 800
  .venv/bin/python scripts/register_missing_apartments.py --target railway --apply \
      --no-target-report <rematch_full.json>

쿼터·재실행
  건축물대장(data.go.kr)은 일일 한도가 있어 --max-calls (기본 800) 도달 시
  중단한다. --apply 반영분은 대상 쿼리에서 자연히 빠지므로(유령 매핑 해소,
  method 변경) 체크포인트 없이 재실행하면 남은 것부터 이어진다.

후속
  신규 등록 PNU 는 시설 요약(apt_facility_summary)·각종 점수가 없는 상태로
  시작한다. quarterly recalc 또는 recalc_for_new_apartments 대상에 포함시키는
  후속 실행이 필요하다. 가격점수는 12h 거래 배치의 recalc_price 가 채운다.
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
from batch.kakao_poi_coord_pipeline import (  # noqa: E402
    AUTO_APT_SOURCE,
    BAD_PLACE_WORDS,
)
from batch.trade.enrich_apartments import _fetch_building_info  # noqa: E402
from batch.trade.mapping_checks import check_mapping, mismatch_confirmed  # noqa: E402
from batch.trade.name_matching import (  # noqa: E402
    _brand_year_consistent,
    _name_variants,
)

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

METHOD_REGISTER = "registered_new"
METHOD_REPOINT = "registered_existing"

# 좌표 없는 TRADE_ 유령에 걸린 매핑 — 실적이 있는 것만 대상으로 한다.
GHOST_TARGETS_SQL = """
SELECT m.apt_seq, m.apt_nm, m.sgg_cd, m.pnu AS current_pnu, a.bld_nm AS current_nm
FROM trade_apt_mapping m
JOIN apartments a ON a.pnu = m.pnu
WHERE a.pnu LIKE 'TRADE%%' AND a.lat IS NULL
  AND EXISTS (SELECT 1 FROM trade_history t WHERE t.apt_seq = m.apt_seq
              UNION ALL
              SELECT 1 FROM rent_history r WHERE r.apt_seq = m.apt_seq)
ORDER BY m.apt_seq
"""

# 면적은 건수 가중으로 수집한다(mapping_checks.area_match_ratio 참조).
# REPOINT 판정에서 면적 게이트가 비활성이면 같은 부지의 임대동이 분양 단지로
# 흡수된다 — 금호벽산(임대) 29.87㎡ vs 진본 59.9/84.82/114.57㎡ 가 그 사례다.
DEAL_STATS_SQL = """
WITH raw AS (
    SELECT t.apt_seq, 't' src, t.floor, t.deal_year, t.build_year, t.exclu_use_ar area
      FROM trade_history t WHERE t.apt_seq = ANY(%(seqs)s)
    UNION ALL
    SELECT r.apt_seq, 'r', r.floor, r.deal_year, NULL, r.exclu_use_ar
      FROM rent_history r WHERE r.apt_seq = ANY(%(seqs)s)
)
SELECT apt_seq,
       COUNT(*) FILTER (WHERE src = 't') trades,
       COUNT(*) FILTER (WHERE src = 'r') rents,
       MAX(floor) max_floor,
       MIN(deal_year) min_deal_year,
       PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY build_year) median_build_year,
       (SELECT ARRAY_AGG(ARRAY[x.area::float8, x.cnt::float8])
          FROM (SELECT ROUND(r2.area::numeric, 2) area, COUNT(*) cnt
                  FROM raw r2 WHERE r2.apt_seq = raw.apt_seq AND r2.area > 0
                 GROUP BY 1) x) AS areas
FROM raw GROUP BY apt_seq
"""


def _connect(target: str):
    key = "DATABASE_URL" if target == "local" else "RAILWAY_DATABASE_URL"
    url = os.environ.get(key)
    if not url:
        raise SystemExit(f"{key} 환경변수가 없습니다.")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def _kakao_get(url: str, headers: dict, params: dict) -> dict | None:
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=5)
    except requests.RequestException:
        return None
    finally:
        time.sleep(KAKAO_RATE)
    return resp.json() if resp.ok else None


def _find_poi(headers: dict, region: str, apt_nm: str) -> dict | None:
    """변형 검색으로 아파트 POI 를 찾는다. 첫 성공 결과."""
    for variant in _name_variants(apt_nm):
        data = _kakao_get(KAKAO_KEYWORD_URL, headers,
                          {"query": f"{region} {variant} 아파트", "size": 5})
        docs = [d for d in (data or {}).get("documents", [])
                if "아파트" in (d.get("category_name") or "")]
        if docs:
            d = docs[0]
            return {
                "place_name": d.get("place_name") or "",
                "road_address": d.get("road_address_name") or "",
                "jibun_address": d.get("address_name") or "",
                "lat": float(d["y"]),
                "lng": float(d["x"]),
                "variant": variant,
            }
    return None


def _compose_pnu(headers: dict, address: str) -> tuple[str, dict] | None:
    """주소검색으로 19자리 PNU 와 건축물대장 파라미터를 조합한다."""
    data = _kakao_get(KAKAO_ADDRESS_URL, headers, {"query": address, "size": 1})
    docs = (data or {}).get("documents", [])
    addr = docs[0].get("address") if docs else None
    if not addr:
        return None
    b_code = addr.get("b_code") or ""
    if len(b_code) < 10:
        return None
    bun = str(addr.get("main_address_no") or "0").zfill(4)
    ji = str(addr.get("sub_address_no") or "0").zfill(4)
    gb = "1" if addr.get("mountain_yn") == "Y" else "0"
    bld_params = {
        "sigungu_cd": b_code[:5], "bjdong_cd": b_code[5:10],
        "plat_gb_cd": gb, "bun": bun, "ji": ji,
    }
    return b_code[:10] + gb + bun + ji, bld_params


def _as_deal(stat: dict, apt_nm: str) -> dict:
    return {
        "apt_nm": apt_nm,
        "max_floor": stat.get("max_floor"),
        "min_deal_year": stat.get("min_deal_year"),
        "median_build_year": stat.get("median_build_year"),
        # REPOINT 판정용. 신규 등록 경로는 진본 쪽 면적이 없어(표제부 한계)
        # 이 값이 있어도 비교가 성립하지 않는다.
        "areas": stat.get("areas"),
    }


def classify(row: dict, stat: dict, headers: dict, sgg_map: dict,
             existing: dict, budget: dict) -> dict:
    """대상 1건을 판정한다. budget["registry"] 는 남은 건축물대장 호출 수."""
    apt_seq, apt_nm = row["apt_seq"], row["apt_nm"]
    sgg = str(row["sgg_cd"])[:5]
    result = {
        "apt_seq": apt_seq, "apt_nm": apt_nm, "sgg_cd": sgg,
        "current_pnu": row["current_pnu"],
        "trades": stat.get("trades", 0), "rents": stat.get("rents", 0),
    }

    poi = _find_poi(headers, sgg_map.get(sgg, ""), apt_nm)
    if not poi:
        result["status"] = "NOT_FOUND"
        return result
    result["poi"] = poi

    composed = _compose_pnu(headers, poi["jibun_address"] or poi["road_address"])
    if not composed:
        result["status"] = "NO_PNU"
        return result
    pnu, bld_params = composed
    result["pnu"] = pnu

    if pnu[:5] != sgg:
        result["status"] = "SGG_MISMATCH"
        return result

    deal = _as_deal(stat, apt_nm)

    hit = existing.get(pnu)
    if hit:
        # 같은 지번에 관리사무소·상가 등이 별도 레코드로 있을 수 있다.
        # 그런 대상으로의 재지정은 어떤 지표가 통과해도 무의미하다.
        if any(w in (hit["bld_nm"] or "") for w in BAD_PLACE_WORDS):
            result["status"] = "REJECTED"
            result["target_nm"] = hit["bld_nm"]
            result["failures"] = ["부적절 대상명"]
            return result
        signals = check_mapping(deal, {
            "bld_nm": hit["bld_nm"], "max_floor": hit["max_floor"],
            "use_apr_day": hit["use_apr_day"], "areas": hit["areas"],
        })
        result["target_nm"] = hit["bld_nm"]
        if mismatch_confirmed(signals):
            result["status"] = "REJECTED"
            result["failures"] = [s.detail for s in signals]
        else:
            result["status"] = "REPOINT"
        return result

    if budget["registry"] <= 0:
        result["status"] = "BUDGET_EXHAUSTED"
        return result
    budget["registry"] -= 1
    info = _fetch_building_info(bld_params)
    if not info:
        result["status"] = "NO_REGISTRY"
        return result
    result["registry"] = info

    bld_nm = poi["place_name"]
    use_apr = info.get("use_apr_day")
    if not _brand_year_consistent(apt_nm, use_apr):
        result["status"] = "REJECTED"
        result["failures"] = ["브랜드-연도"]
        return result
    signals = check_mapping(deal, {
        "bld_nm": bld_nm, "max_floor": info.get("max_floor"),
        "use_apr_day": use_apr, "areas": None,
    })
    if mismatch_confirmed(signals):
        result["status"] = "REJECTED"
        result["failures"] = [s.detail for s in signals]
        return result

    result["status"] = "REGISTER"
    result["new"] = {
        "pnu": pnu, "bld_nm": bld_nm, "sigungu_code": sgg,
        "bjd_code": pnu[:10], "lat": poi["lat"], "lng": poi["lng"],
        "new_plat_plc": poi["road_address"] or None,
        "plat_plc": poi["jibun_address"] or None,
        "use_apr_day": use_apr,
        "total_hhld_cnt": info.get("total_hhld_cnt"),
        "max_floor": info.get("max_floor"),
    }
    return result


def apply_results(conn, results: list[dict]) -> dict:
    """REGISTER/REPOINT 를 반영한다. 유령은 참조가 다 사라진 경우에만 지운다."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    write = conn.cursor()
    stats = Counter()

    for r in results:
        if r["status"] == "REGISTER":
            n = r["new"]
            write.execute(
                """INSERT INTO apartments
                   (pnu, bld_nm, sigungu_code, group_pnu, bjd_code, lat, lng,
                    new_plat_plc, plat_plc, coord_source,
                    use_apr_day, total_hhld_cnt, max_floor)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (pnu) DO NOTHING""",
                [n["pnu"], n["bld_nm"], n["sigungu_code"], n["pnu"], n["bjd_code"],
                 n["lat"], n["lng"], n["new_plat_plc"], n["plat_plc"],
                 AUTO_APT_SOURCE, n["use_apr_day"], n["total_hhld_cnt"],
                 n["max_floor"]],
            )
            stats["registered"] += write.rowcount
        if r["status"] not in ("REGISTER", "REPOINT"):
            continue

        write.execute(
            "UPDATE trade_apt_mapping SET pnu = %s, match_method = %s "
            "WHERE apt_seq = %s AND pnu = %s",
            [r["pnu"],
             METHOD_REGISTER if r["status"] == "REGISTER" else METHOD_REPOINT,
             r["apt_seq"], r["current_pnu"]],
        )
        stats["remapped"] += write.rowcount

        # 유령 정리 — 다른 apt_seq 가 아직 걸려 있으면 남겨둔다
        ghost = r["current_pnu"]
        if ghost.startswith("TRADE"):
            cur.execute("SELECT 1 FROM trade_apt_mapping WHERE pnu = %s LIMIT 1", [ghost])
            if not cur.fetchone():
                write.execute("DELETE FROM apt_price_score WHERE pnu = %s", [ghost])
                write.execute("DELETE FROM apartments WHERE pnu = %s", [ghost])
                stats["ghosts_deleted"] += 1

    conn.commit()
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=["local", "railway"], default="local")
    ap.add_argument("--apply", action="store_true", help="반영 (기본은 리포트)")
    ap.add_argument("--limit", type=int, default=0, help="대상 수 제한 (0=전체)")
    ap.add_argument("--max-calls", type=int, default=800,
                    help="건축물대장 API 호출 상한 (일일 쿼터 방어)")
    ap.add_argument("--no-target-report", default="",
                    help="rematch 리포트 JSON — NO_TARGET 건을 대상에 추가")
    ap.add_argument("--out", default="", help="결과 JSON 저장 경로")
    ap.add_argument("--from-report", default="",
                    help="리포트 JSON 의 REGISTER/REPOINT 를 재분석 없이 반영 (--apply 필요)")
    args = ap.parse_args()

    if args.from_report:
        if not args.apply:
            raise SystemExit("--from-report 는 --apply 와 함께 써야 합니다.")
        conn = _connect(args.target)
        results = [r for r in json.loads(Path(args.from_report).read_text())
                   if r.get("status") in ("REGISTER", "REPOINT")]
        print(f"[{args.target}] APPLY (검토본) — REGISTER/REPOINT {len(results)}건")
        stats = apply_results(conn, results)
        print(f"\n반영 — 신규 등록 {stats['registered']}건 / 매핑 재지정 "
              f"{stats['remapped']}건 / 유령 삭제 {stats['ghosts_deleted']}건")
        print("후속: 신규 PNU 는 시설요약·점수 미보유 — quarterly recalc 대상 포함 필요")
        conn.close()
        return 0

    if not KAKAO_API_KEY:
        raise SystemExit("KAKAO_API_KEY 환경변수가 없습니다.")
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    conn = _connect(args.target)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT code, name FROM common_code WHERE group_id = 'sigungu'")
    sgg_map = {r["code"]: r["name"] for r in cur.fetchall()}

    # 진본 인덱스 — REPOINT 판정과 중복 등록 방지에 쓴다
    cur.execute("""
        SELECT a.pnu, a.bld_nm, a.max_floor, a.use_apr_day,
               (SELECT ARRAY_AGG(exclusive_area) FROM apt_area_type t
                 WHERE t.pnu = a.pnu) AS areas
        FROM apartments a WHERE a.pnu NOT LIKE 'TRADE%%'
    """)
    existing = {r["pnu"]: dict(r) for r in cur.fetchall()}

    cur.execute(GHOST_TARGETS_SQL)
    targets = [dict(r) for r in cur.fetchall()]

    if args.no_target_report:
        report = json.loads(Path(args.no_target_report).read_text())
        seen = {t["apt_seq"] for t in targets}
        for r in report:
            if r.get("status") == "NO_TARGET" and r["apt_seq"] not in seen:
                targets.append({
                    "apt_seq": r["apt_seq"], "apt_nm": r["apt_nm"],
                    "sgg_cd": r["apt_seq"].split("_", 1)[0],
                    "current_pnu": r["current_pnu"], "current_nm": r.get("current_nm"),
                })

    if args.limit > 0:
        targets = targets[:args.limit]
    print(f"[{args.target}] {'APPLY' if args.apply else 'REPORT'} — "
          f"대상 {len(targets):,}건 (건축물대장 호출 상한 {args.max_calls})\n")

    seqs = [t["apt_seq"] for t in targets]
    cur.execute(DEAL_STATS_SQL, {"seqs": seqs})
    stats_by_seq = {r["apt_seq"]: dict(r) for r in cur.fetchall()}

    budget = {"registry": args.max_calls}
    results = []
    for i, row in enumerate(targets, 1):
        results.append(classify(row, stats_by_seq.get(row["apt_seq"], {}),
                                headers, sgg_map, existing, budget))
        if i % 100 == 0:
            print(f"  진행 {i}/{len(targets)} (건축물대장 잔여 {budget['registry']})")

    counts = Counter(r["status"] for r in results)
    print("\n=== 분류 ===")
    for s in ("REGISTER", "REPOINT", "REJECTED", "SGG_MISMATCH",
              "NO_REGISTRY", "NO_PNU", "NOT_FOUND", "BUDGET_EXHAUSTED"):
        if counts.get(s):
            print(f"  {s:16s} {counts[s]:6,d}")

    registers = [r for r in results if r["status"] == "REGISTER"]
    if registers:
        print(f"\n=== REGISTER 후보 {len(registers)}건 (실적 상위 10) ===")
        for r in sorted(registers, key=lambda x: -(x["trades"] + x["rents"]))[:10]:
            n = r["new"]
            print(f"  {r['apt_nm'][:26]:28s} 매매{r['trades']:5d} 전월세{r['rents']:5d}")
            print(f"      → {n['pnu']} | {n['bld_nm'][:30]} | 준공={n['use_apr_day']} "
                  f"세대={n['total_hhld_cnt']} 층={n['max_floor']}")

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False,
                                             indent=2, default=str))
        print(f"\n결과 JSON: {args.out}")

    if args.apply:
        stats = apply_results(conn, results)
        print(f"\n반영 — 신규 등록 {stats['registered']}건 / 매핑 재지정 "
              f"{stats['remapped']}건 / 유령 삭제 {stats['ghosts_deleted']}건")
        print("후속: 신규 PNU 는 시설요약·점수 미보유 — quarterly recalc 대상 포함 필요")
        print("가격점수는 12h 거래 배치(recalc_price)가 재계산")
    else:
        conn.rollback()
        print(f"\nREPORT 모드 — DB 변경 없음 "
              f"(REGISTER {counts.get('REGISTER', 0)} / REPOINT {counts.get('REPOINT', 0)})")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
