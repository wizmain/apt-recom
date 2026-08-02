"""물리적으로 성립하지 않는 거래 매핑을 찾아 올바른 진본으로 재매칭한다.

배경
  trade_apt_mapping 의 상당수가 이름만 보고 만들어졌고(exact_name, auto_create,
  trade_create 등), 이후 apartments.bld_nm 이 K-APT 적재로 갱신되면서
  (ingest_full_kapt.py) 대상이 어긋난 것들이 남았다. 이름 유사도만으로는
  정상 표기 차이(`목동신시가지14` ↔ `목동14단지`)와 구분되지 않아,
  batch/trade/mapping_checks.py 의 물리 지표로 판정한다.

절차 (apt_seq 1건당)
  1. 실적(매매+전월세) 집계와 현재 매핑 대상의 속성을 대조 — check_mapping
     정합하면 손대지 않는다.
  2. 어긋나면 같은 시군구에서 대체 진본을 찾는다.
       a. 거래명 변형(_name_variants)이 진본 이름과 정규화 일치
       b. Kakao 키워드 검색 주소가 진본 주소와 일치
  3. 찾은 후보를 다시 check_mapping 으로 검증한다. 통과한 것만 채택한다.
     현재 매핑을 끊는 것보다 잘못된 곳으로 다시 붙이는 편이 더 나쁘다.

분류
  OK          현재 매핑이 정합 — 조치 없음
  REMATCH     검증을 통과한 대체 진본을 찾음 → 재매핑 대상
  SAME        대체 후보가 현재 매핑과 동일 → 판정이 과했을 수 있음. 조치 없음
  NO_TARGET   대체 후보를 못 찾음 → 매핑 해제 검토 대상(본 스크립트는 건드리지 않음)
  REJECTED    후보를 찾았으나 그 후보도 검증 실패 → 조치 없음

사용
  .venv/bin/python scripts/rematch_bad_mappings.py                  # 리포트 (기본)
  .venv/bin/python scripts/rematch_bad_mappings.py --limit 100
  .venv/bin/python scripts/rematch_bad_mappings.py --apply          # REMATCH 반영
  .venv/bin/python scripts/rematch_bad_mappings.py --target railway --apply

주의
  --apply 는 trade_apt_mapping.pnu 만 바꾼다. 좌표·아파트 레코드는 건드리지 않는다.
  반영 후 가격점수 재계산이 필요하다 (12h 거래 배치가 recalc_price 수행).
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
from batch.trade.deal_stats import build_deal_stats_sql  # noqa: E402
from batch.trade.mapping_checks import check_mapping, mismatch_confirmed  # noqa: E402
from batch.trade.name_matching import _name_variants, _normalize_name  # noqa: E402

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
MATCH_METHOD = "rematch_verified"

# --limit 표본용. 실적 순 정렬은 전량 집계를 요구하므로, 표본은 apt_seq 순으로
# 뽑는다. 실적 상위만 보면 진본이 등록돼 있을 확률이 높은 구간에 치우쳐
# REMATCH 성공률이 과대평가된다.
SAMPLE_SEQ_SQL = "SELECT apt_seq FROM trade_apt_mapping ORDER BY apt_seq LIMIT %s"

CANDIDATE_SQL = """
SELECT a.pnu, a.bld_nm, a.sigungu_code, a.new_plat_plc, a.plat_plc,
       a.max_floor, a.use_apr_day,
       (SELECT ARRAY_AGG(exclusive_area) FROM apt_area_type t WHERE t.pnu = a.pnu) AS areas
FROM apartments a
WHERE a.pnu NOT LIKE 'TRADE%%' AND a.lat IS NOT NULL AND a.bld_nm IS NOT NULL
"""


def _connect(target: str):
    key = "DATABASE_URL" if target == "local" else "RAILWAY_DATABASE_URL"
    url = os.environ.get(key)
    if not url:
        raise SystemExit(f"{key} 환경변수가 없습니다.")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def _norm_addr(addr: str) -> str:
    return " ".join((addr or "").split()).lower()


def _as_deal(row: dict) -> dict:
    return {
        "apt_nm": row["apt_nm"],
        "max_floor": row["max_floor"],
        "min_deal_year": row["min_deal_year"],
        "median_build_year": row["median_build_year"],
        "areas": row["areas"],
    }


def _as_apt(row: dict, prefix: str = "apt_") -> dict:
    return {
        "bld_nm": row["bld_nm"],
        "max_floor": row.get(f"{prefix}max_floor", row.get("max_floor")),
        "use_apr_day": row["use_apr_day"],
        "areas": row.get(f"{prefix}areas", row.get("areas")),
    }


def load_indexes(cur) -> tuple[dict, dict, dict]:
    """진본 인덱스 — 이름·주소로 찾고, pnu 로 속성을 본다."""
    cur.execute(CANDIDATE_SQL)
    by_name: dict[tuple[str, str], dict] = {}
    by_addr: dict[tuple[str, str], dict] = {}
    by_pnu: dict[str, dict] = {}
    for r in cur.fetchall():
        row = dict(r)
        sgg = str(row["sigungu_code"] or "")[:5]
        by_pnu[row["pnu"]] = row
        by_name.setdefault((sgg, _normalize_name(row["bld_nm"])), row)
        for col in ("new_plat_plc", "plat_plc"):
            if row[col]:
                by_addr.setdefault((sgg, _norm_addr(row[col])), row)
    return by_name, by_addr, by_pnu


def _kakao_addresses(headers: dict, region: str, apt_nm: str) -> list[str]:
    """거래명 변형으로 검색해 얻은 주소 목록 (도로명·지번)."""
    out = []
    for variant in _name_variants(apt_nm):
        try:
            resp = requests.get(KAKAO_KEYWORD_URL, headers=headers,
                                params={"query": f"{region} {variant} 아파트", "size": 5},
                                timeout=5)
        except requests.RequestException:
            continue
        finally:
            time.sleep(KAKAO_RATE)
        if not resp.ok:
            continue
        docs = [d for d in resp.json().get("documents", [])
                if "아파트" in (d.get("category_name") or "")]
        for d in docs[:3]:
            for key in ("road_address_name", "address_name"):
                if d.get(key):
                    out.append(d[key])
        if out:
            break
    return out


def find_replacement(row: dict, headers: dict, sgg_map: dict,
                     by_name: dict, by_addr: dict) -> tuple[dict | None, str]:
    """대체 진본 후보를 찾는다. (후보, 근거) 반환."""
    sgg = str(row["sgg_cd"])[:5]

    for variant in _name_variants(row["apt_nm"]):
        hit = by_name.get((sgg, _normalize_name(variant)))
        if hit:
            return hit, f"name:{variant}"

    for addr in _kakao_addresses(headers, sgg_map.get(sgg, ""), row["apt_nm"]):
        hit = by_addr.get((sgg, _norm_addr(addr)))
        if hit:
            return hit, f"address:{addr}"

    return None, ""


def classify(row: dict, headers: dict, sgg_map: dict,
             by_name: dict, by_addr: dict) -> dict:
    deal = _as_deal(row)
    cur_apt = _as_apt(row)
    result = {
        "apt_seq": row["apt_seq"], "apt_nm": row["apt_nm"],
        "current_pnu": row["pnu"], "current_nm": row["bld_nm"],
        "match_method": row["match_method"],
        "trades": row["trades"], "rents": row["rents"],
    }

    signals = check_mapping(deal, cur_apt)
    if not mismatch_confirmed(signals):
        result["status"] = "OK"
        if signals:
            # 신호는 있었으나 확정 기준(2개 이상 또는 strong)에 못 미친 경우.
            # 판정 보정이 실제로 무엇을 통과시켰는지 남긴다.
            result["weak_signals"] = [s.detail for s in signals]
        return result
    result["failures"] = [s.detail for s in signals]

    cand, why = find_replacement(row, headers, sgg_map, by_name, by_addr)
    if not cand:
        result["status"] = "NO_TARGET"
        return result
    if cand["pnu"] == row["pnu"]:
        result["status"] = "SAME"
        return result

    cand_signals = check_mapping(deal, _as_apt(cand, prefix=""))
    result.update({"new_pnu": cand["pnu"], "new_nm": cand["bld_nm"], "matched_by": why})
    if mismatch_confirmed(cand_signals):
        result["status"] = "REJECTED"
        result["new_failures"] = [s.detail for s in cand_signals]
    else:
        result["status"] = "REMATCH"
    return result


def apply_rematch(conn, rows: list[dict]) -> tuple[int, int]:
    """REMATCH 건을 반영한다. 전제조건이 깨진 건은 건너뛴다.

    반환: (반영, 건너뜀)
    """
    check = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    applied = skipped = 0
    for r in rows:
        # 리포트 생성 이후 매핑이 바뀌었거나 대상 진본이 사라졌으면 반영하지 않는다.
        check.execute("SELECT pnu FROM trade_apt_mapping WHERE apt_seq = %s", [r["apt_seq"]])
        row = check.fetchone()
        if not row or row["pnu"] != r["current_pnu"]:
            skipped += 1
            continue
        check.execute("SELECT 1 FROM apartments WHERE pnu = %s", [r["new_pnu"]])
        if not check.fetchone():
            skipped += 1
            continue
        cur.execute(
            "UPDATE trade_apt_mapping SET pnu = %s, match_method = %s WHERE apt_seq = %s",
            [r["new_pnu"], MATCH_METHOD, r["apt_seq"]],
        )
        applied += cur.rowcount
    conn.commit()
    return applied, skipped


def load_reviewed_rematches(path: str) -> list[dict]:
    """리포트 JSON 의 REMATCH 건만 읽는다.

    --apply 단독은 전 대상을 재분석하므로 Kakao 응답 변화에 따라 검토 시점과
    다른 집합이 반영될 수 있다. 검토한 결과를 그대로 적용하려면 이 경로를 쓴다.
    """
    data = json.loads(Path(path).read_text())
    return [r for r in data if r.get("status") == "REMATCH"]


def run(target: str, apply: bool, limit: int, out: str) -> int:
    if not KAKAO_API_KEY:
        raise SystemExit("KAKAO_API_KEY 환경변수가 없습니다.")
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    conn = _connect(target)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT code, name FROM common_code WHERE group_id = 'sigungu'")
    sgg_map = {r["code"]: r["name"] for r in cur.fetchall()}
    by_name, by_addr, _ = load_indexes(cur)

    seqs = None
    if limit > 0:
        cur.execute(SAMPLE_SEQ_SQL, [limit])
        seqs = [r["apt_seq"] for r in cur.fetchall()]
        print(f"표본 {len(seqs):,}건 (apt_seq 순) 집계 중...")
    else:
        print("전체 매핑 집계 중...")

    cur.execute(build_deal_stats_sql(by_seqs=seqs is not None),
                {"seqs": seqs} if seqs is not None else None)
    rows = [dict(r) for r in cur.fetchall()]
    print(f"[{target}] {'APPLY' if apply else 'REPORT'} — 실적 있는 매핑 {len(rows):,}건 검사\n")

    results = []
    for i, row in enumerate(rows, 1):
        results.append(classify(row, headers, sgg_map, by_name, by_addr))
        if i % 500 == 0:
            print(f"  진행 {i}/{len(rows)}")

    counts = Counter(r["status"] for r in results)
    print("\n=== 분류 ===")
    for s in ("OK", "REMATCH", "SAME", "REJECTED", "NO_TARGET"):
        print(f"  {s:11s} {counts.get(s, 0):6,d}")

    rematch = [r for r in results if r["status"] == "REMATCH"]
    if rematch:
        print(f"\n=== REMATCH {len(rematch)}건 (실적 상위 15) ===")
        for r in sorted(rematch, key=lambda x: -(x["trades"] + x["rents"]))[:15]:
            print(f"  {r['apt_nm'][:24]:26s} 매매{r['trades']:5d} 전월세{r['rents']:5d}")
            print(f"      {r['current_nm'][:22]:24s} → {r['new_nm'][:22]:24s} [{r['matched_by']}]")
            print(f"      기존 사유: {', '.join(r['failures'])}")

    if out:
        Path(out).write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str))
        print(f"\n결과 JSON: {out}")

    if apply and rematch:
        applied, skipped = apply_rematch(conn, rematch)
        print(f"\n재매핑 완료: {applied}건 (건너뜀 {skipped}건)")
        print("가격점수 재계산 필요 (12h 거래 배치가 recalc_price 수행)")
    elif not apply:
        conn.rollback()
        print(f"\nREPORT 모드 — DB 변경 없음 (재매핑 대상 {len(rematch)}건)")

    conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=["local", "railway"], default="local")
    ap.add_argument("--apply", action="store_true", help="REMATCH 건 반영 (기본은 리포트)")
    ap.add_argument("--limit", type=int, default=0, help="검사 건수 제한 (0=전체)")
    ap.add_argument("--out", default="", help="결과 JSON 저장 경로")
    ap.add_argument("--from-report", default="",
                    help="리포트 JSON 의 REMATCH 건을 재분석 없이 그대로 반영 (--apply 필요)")
    args = ap.parse_args()

    if args.from_report:
        if not args.apply:
            raise SystemExit("--from-report 는 --apply 와 함께 써야 합니다.")
        conn = _connect(args.target)
        rematch = load_reviewed_rematches(args.from_report)
        print(f"[{args.target}] APPLY (검토본) — REMATCH {len(rematch)}건")
        applied, skipped = apply_rematch(conn, rematch)
        print(f"\n재매핑 완료: {applied}건 (건너뜀 {skipped}건)")
        print("가격점수 재계산 필요 (12h 거래 배치가 recalc_price 수행)")
        conn.close()
        return 0

    return run(args.target, args.apply, args.limit, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
