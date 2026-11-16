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
  NO_TARGET   대체 후보를 못 찾음 → --unmap-no-target 일 때만 매핑 해제(ADR-017).
              해제한 행은 trade_apt_mapping_removed 에 보존한다. 잘못된 단지에 붙어 있는 것보다
              미매핑이 낫다 — 그 단지의 가격·점수를 다른 단지 거래가 오염시키기 때문이다.
  REJECTED    후보를 찾았으나 그 후보도 검증 실패 → 조치 없음
  MIXED_KEY   어긋났지만 여러 단지 거래가 섞인 이름 키(고유번호 2개 이상) → 조치 없음, 사람 검토

사용
  .venv/bin/python scripts/rematch_bad_mappings.py                  # 리포트 (기본)
  .venv/bin/python scripts/rematch_bad_mappings.py --limit 100
  .venv/bin/python scripts/rematch_bad_mappings.py --apply          # REMATCH 반영
  .venv/bin/python scripts/rematch_bad_mappings.py --apply --unmap-no-target  # + NO_TARGET 해제
  .venv/bin/python scripts/rematch_bad_mappings.py --target railway --apply
  # 검토한 리포트 그대로 반영 (재분석 없음)
  .venv/bin/python scripts/rematch_bad_mappings.py --out r.json
  .venv/bin/python scripts/rematch_bad_mappings.py --from-report r.json --apply --unmap-no-target

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
# 고유번호(api_apt_seq)가 2개 이상 관측된 이름 키 — mixed_name_keys
MIXED_KEY_SQL = """
SELECT COALESCE(legacy_apt_seq, apt_seq) AS k
FROM trade_history
WHERE api_apt_seq IS NOT NULL
  AND (apt_seq = ANY(%(s)s) OR legacy_apt_seq = ANY(%(s)s))
GROUP BY 1
HAVING COUNT(DISTINCT btrim(api_apt_seq)) >= 2
"""
# 해제한 매핑의 원본 보존 테이블 — 스키마는 web/backend/database.py create_tables() (ADR-017)
REMOVED_TABLE = "trade_apt_mapping_removed"

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
        "max_deal_year": row.get("max_deal_year"),
        "median_build_year": row["median_build_year"],
        "areas": row["areas"],
        # 지번 대조 근거 — 후보 검증에도 같은 신호가 걸려야 엉뚱한 곳으로 옮기지 않는다
        "jibun_pnus": row.get("jibun_pnus"),
        "jibun_owner_pnus": row.get("jibun_owner_pnus"),
    }


def _as_apt(row: dict, prefix: str = "apt_") -> dict:
    return {
        "pnu": row["pnu"],
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


def mixed_name_keys(cur, seqs: list[str]) -> set[str]:
    """국토부 고유번호가 2개 이상 관측된 이름 키 — 여러 단지 거래가 섞인 키 (ADR-015).

    이런 키는 어느 단지로 옮겨도 틀린다. 2026-11-16 리허설에서 `26230_동원`(고유번호 3개, 1980~1985
    여러 동원)이 이름으로 당감동 동원(45세대)에 재매핑돼 그 단지 ㎡당 가격이 230만→754만이 됐다.
    REMATCH 284건 중 36건이 이런 키였다(하나·동아·동남·한국 등 흔한 이름).
    """
    if not seqs:
        return set()
    cur.execute(MIXED_KEY_SQL, {"s": seqs})
    return {r["k"] for r in cur.fetchall()}


def classify(row: dict, headers: dict, sgg_map: dict,
             by_name: dict, by_addr: dict, mixed_keys: frozenset[str] = frozenset()) -> dict:
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

    if row["apt_seq"] in mixed_keys:
        # 혼입 키는 옮기지도 해제하지도 않는다 — 사람 검토 대상(mixed_name_keys 참조)
        result["status"] = "MIXED_KEY"
        return result

    cand, why = find_replacement(row, headers, sgg_map, by_name, by_addr)
    if not cand:
        result["status"] = "NO_TARGET"
        return result
    if cand["pnu"] == row["pnu"]:
        result["status"] = "SAME"
        return result

    # 재건축 계보 면제는 같은 부지 근거(주소)로 찾은 후보에만 — 이름 후보에 주면 옛 단지
    # 실적이 같은 이름의 신축으로 옮겨진다(mapping_checks.check_mapping 참조).
    cand_signals = check_mapping(
        deal, _as_apt(cand, prefix=""), allow_predecessor=why.startswith("address")
    )
    result.update({"new_pnu": cand["pnu"], "new_nm": cand["bld_nm"], "matched_by": why})
    if not candidate_acceptable(cand_signals):
        result["status"] = "REJECTED"
        result["new_failures"] = [s.detail for s in cand_signals]
    else:
        result["status"] = "REMATCH"
    return result


def candidate_acceptable(signals) -> bool:
    """대체 후보로 옮겨도 되는지 — 기존 매핑 감사(mismatch_confirmed)보다 엄격하다.

    거래를 옮기는 결정이라 확정 위반이 아니어도 타임라인 신호가 있으면 받지 않는다. 2026-11-16
    리허설에서 `극동`(1997) 75건이 이름 포함 매칭으로 주안극동스타클래스더로얄(2025)에 옮겨졌다 —
    이름이 겹쳐 이름 신호가 없고 타임라인 하나뿐이라 확정되지 않았다.
    """
    return not mismatch_confirmed(signals) and not any(
        s.code == "timeline" for s in signals
    )


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


def require_removed_table(conn) -> None:
    """보존 테이블이 없으면 해제하지 않는다 — 원본을 잃는 해제는 하지 않는다.

    테이블은 백엔드 부팅 시 create_tables() 가 만든다(Railway 는 이 변경의 배포 후).
    """
    cur = conn.cursor()
    cur.execute("SELECT to_regclass(%s)", [REMOVED_TABLE])
    if cur.fetchone()[0] is None:
        raise SystemExit(
            f"{REMOVED_TABLE} 테이블이 없습니다 — 백엔드를 배포(create_tables)한 뒤 다시 실행하세요."
        )


def apply_unmap(conn, rows: list[dict]) -> tuple[int, int]:
    """NO_TARGET 건의 매핑을 해제한다. 원본 행은 보존 테이블에 먼저 옮긴다.

    리포트 이후 매핑이 바뀐 건은 건너뛴다(apply_rematch 와 같은 전제조건 검사).
    반환: (해제, 건너뜀)
    """
    require_removed_table(conn)
    check = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    unmapped = skipped = 0
    for r in rows:
        check.execute("SELECT pnu FROM trade_apt_mapping WHERE apt_seq = %s", [r["apt_seq"]])
        row = check.fetchone()
        if not row or row["pnu"] != r["current_pnu"]:
            skipped += 1
            continue
        cur.execute(
            f"INSERT INTO {REMOVED_TABLE} (apt_seq, pnu, apt_nm, sgg_cd, match_method, reason) "
            "SELECT apt_seq, pnu, apt_nm, sgg_cd, match_method, %s "
            "FROM trade_apt_mapping WHERE apt_seq = %s",
            [", ".join(r.get("failures") or []), r["apt_seq"]],
        )
        cur.execute("DELETE FROM trade_apt_mapping WHERE apt_seq = %s", [r["apt_seq"]])
        unmapped += cur.rowcount
    conn.commit()
    return unmapped, skipped


def load_reviewed(path: str, status: str) -> list[dict]:
    """리포트 JSON 에서 한 분류(REMATCH·NO_TARGET)의 건만 읽는다.

    --apply 단독은 전 대상을 재분석하므로 Kakao 응답 변화에 따라 검토 시점과
    다른 집합이 반영될 수 있다. 검토한 결과를 그대로 적용하려면 이 경로를 쓴다.
    """
    data = json.loads(Path(path).read_text())
    return [r for r in data if r.get("status") == status]


def apply_reviewed(conn, rematch: list[dict], no_target: list[dict], unmap: bool) -> None:
    """REMATCH 반영 + (unmap 이면) NO_TARGET 해제. 반영 결과를 출력한다."""
    if rematch:
        applied, skipped = apply_rematch(conn, rematch)
        print(f"\n재매핑 완료: {applied}건 (건너뜀 {skipped}건)")
    if unmap and no_target:
        unmapped, skipped = apply_unmap(conn, no_target)
        print(f"매핑 해제 완료: {unmapped}건 (건너뜀 {skipped}건, 원본은 {REMOVED_TABLE})")
    if rematch or (unmap and no_target):
        print("가격점수 재계산 필요 (12h 거래 배치가 recalc_price 수행)")


def run(target: str, apply: bool, limit: int, out: str, unmap: bool = False) -> int:
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

    mixed = frozenset(mixed_name_keys(cur, [r["apt_seq"] for r in rows]))
    results = []
    for i, row in enumerate(rows, 1):
        results.append(classify(row, headers, sgg_map, by_name, by_addr, mixed))
        if i % 500 == 0:
            print(f"  진행 {i}/{len(rows)}")

    counts = Counter(r["status"] for r in results)
    print("\n=== 분류 ===")
    for s in ("OK", "REMATCH", "SAME", "REJECTED", "NO_TARGET", "MIXED_KEY"):
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

    no_target = [r for r in results if r["status"] == "NO_TARGET"]
    if apply:
        apply_reviewed(conn, rematch, no_target, unmap)
    else:
        conn.rollback()
        print(f"\nREPORT 모드 — DB 변경 없음 (재매핑 대상 {len(rematch)}건, "
              f"해제 후보 NO_TARGET {len(no_target)}건)")

    conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=["local", "railway"], default="local")
    ap.add_argument("--apply", action="store_true", help="REMATCH 건 반영 (기본은 리포트)")
    ap.add_argument("--limit", type=int, default=0, help="검사 건수 제한 (0=전체)")
    ap.add_argument("--out", default="", help="결과 JSON 저장 경로")
    ap.add_argument("--from-report", default="",
                    help="리포트 JSON 의 REMATCH(·NO_TARGET) 건을 재분석 없이 그대로 반영 (--apply 필요)")
    ap.add_argument("--unmap-no-target", action="store_true",
                    help=f"NO_TARGET 매핑 해제 — 원본은 {REMOVED_TABLE} 에 보존 (--apply 필요, ADR-017)")
    args = ap.parse_args()

    if args.unmap_no_target and not args.apply:
        raise SystemExit("--unmap-no-target 는 --apply 와 함께 써야 합니다.")
    if args.from_report:
        if not args.apply:
            raise SystemExit("--from-report 는 --apply 와 함께 써야 합니다.")
        conn = _connect(args.target)
        rematch = load_reviewed(args.from_report, "REMATCH")
        no_target = load_reviewed(args.from_report, "NO_TARGET") if args.unmap_no_target else []
        print(f"[{args.target}] APPLY (검토본) — REMATCH {len(rematch)}건, "
              f"해제 NO_TARGET {len(no_target)}건")
        apply_reviewed(conn, rematch, no_target, args.unmap_no_target)
        conn.close()
        return 0

    return run(args.target, args.apply, args.limit, args.out, args.unmap_no_target)


if __name__ == "__main__":
    raise SystemExit(main())
