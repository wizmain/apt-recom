"""시군구 코드 별칭(sigungu_alias / sido_alias)을 실측으로 만들어 적재한다.

방식
  추측으로 신·구 대응을 만들지 않는다. 시군구마다 실제 단지의 지번 주소를
  Kakao 주소검색에 넣어, 응답 b_code 를 그 단지의 PNU 와 필지 단위로 대조한다.
    검증: b_code[5:10] == pnu[5:10] (법정동 보존)
          main/sub 지번 == pnu 본번/부번
  같은 필지가 확인됐을 때만 (구코드 → b_code 앞 5자리) 를 대응으로 인정한다.
  앞 5자리가 같으면 개편이 없는 지역이므로 별칭을 만들지 않는다.

  시군구당 표본 여러 곳(기본 3)을 조사해 법정동별로 신코드가 갈리는 재편
  (인천 중구+동구 → 제물포구+영종구 유형)을 감지한다. 표본들이 서로 다른
  신코드를 가리키면 5자리 별칭 대신 10자리(신시군구+법정동) 항목으로 남긴다
  — 이 경우 표본에 없는 법정동은 커버되지 않으므로 리포트에 명시한다.

  시도명 별칭은 응답의 region_1depth_name 이 우리 표기(common_code.extra)와
  다를 때 수집한다 (예: 전남광주통합특별시 → 광주).

사용
  .venv/bin/python scripts/seed_sigungu_aliases.py                    # 리포트만
  .venv/bin/python scripts/seed_sigungu_aliases.py --apply            # 로컬 적재
  .venv/bin/python scripts/seed_sigungu_aliases.py --target railway --apply

비용
  시군구 258개 × 표본 3 ≈ 800 Kakao 호출, rate 0.1s → 약 2분.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from batch.config import KAKAO_API_KEY, KAKAO_RATE  # noqa: E402
from batch.region_codes import SIGUNGU_ALIAS_GROUP  # noqa: E402

KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

# 시군구당 조사할 표본 필지 수. 1이면 재편(법정동별 분기)을 놓친다.
SAMPLES_PER_SIGUNGU = 3

# 표본은 서로 다른 법정동에서 뽑는다 — 같은 동만 보면 분기를 감지할 수 없다.
SAMPLE_SQL = """
SELECT DISTINCT ON (SUBSTRING(pnu, 6, 5))
       pnu, plat_plc
FROM apartments
WHERE pnu LIKE %(prefix)s AND LENGTH(pnu) = 19
  AND plat_plc IS NOT NULL AND plat_plc != ''
ORDER BY SUBSTRING(pnu, 6, 5), pnu
LIMIT %(n)s
"""


def _connect(target: str):
    key = "DATABASE_URL" if target == "local" else "RAILWAY_DATABASE_URL"
    url = os.environ.get(key)
    if not url:
        raise SystemExit(f"{key} 환경변수가 없습니다.")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def _geocode(headers: dict, addr: str) -> dict | None:
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
    return docs[0].get("address") if docs else None


def _same_parcel(pnu: str, addr: dict) -> bool:
    """응답 필지가 표본 PNU 와 같은 땅인지 — 법정동·본번·부번 대조."""
    b_code = addr.get("b_code") or ""
    if len(b_code) < 10 or b_code[5:10] != pnu[5:10]:
        return False
    bun = str(addr.get("main_address_no") or "0").zfill(4)
    ji = str(addr.get("sub_address_no") or "0").zfill(4)
    return bun == pnu[11:15] and ji == pnu[15:19]


def probe(conn, headers: dict) -> dict:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT code, name, extra FROM common_code WHERE group_id='sigungu' ORDER BY code")
    registry = [dict(r) for r in cur.fetchall()]

    results = {"unchanged": 0, "no_sample": [], "unverified": [],
               "renamed": {}, "split": {}, "sido": {}}

    for i, row in enumerate(registry, 1):
        old = row["code"]
        cur.execute(SAMPLE_SQL, {"prefix": old + "%", "n": SAMPLES_PER_SIGUNGU})
        samples = cur.fetchall()
        if not samples:
            results["no_sample"].append(old)
            continue

        seen_new: dict[str, list[str]] = defaultdict(list)  # 신코드 → [법정동...]
        verified = 0
        for s in samples:
            addr = _geocode(headers, s["plat_plc"])
            if not addr or not _same_parcel(s["pnu"], addr):
                continue
            verified += 1
            new = (addr.get("b_code") or "")[:5]
            seen_new[new].append(s["pnu"][5:10])
            sido_new = (addr.get("region_1depth_name") or "").strip()
            if sido_new and row["extra"] and not sido_new.startswith(row["extra"]):
                results["sido"][sido_new] = row["extra"]

        if verified == 0:
            results["unverified"].append(old)
        elif set(seen_new) == {old}:
            results["unchanged"] += 1
        elif len(seen_new) == 1:
            new = next(iter(seen_new))
            results["renamed"][old] = new
        else:
            # 법정동별로 신코드가 갈리는 재편 — 10자리 항목으로 남긴다
            for new, bjds in seen_new.items():
                if new == old:
                    continue
                for bjd in bjds:
                    results["split"][new + bjd] = old
        if i % 50 == 0:
            print(f"  진행 {i}/{len(registry)}")

    return results


def apply_aliases(conn, results: dict) -> tuple[int, int]:
    cur = conn.cursor()
    n_sgg = 0
    # 5자리 개명: 신코드 → 구코드. 10자리 분기: 신시군구+법정동 → 구코드
    entries = {new: old for old, new in results["renamed"].items()}
    entries.update(results["split"])
    for new, old in entries.items():
        cur.execute(
            """INSERT INTO common_code (group_id, code, name, extra, sort_order)
               VALUES (%s, %s, %s, %s, 0)
               ON CONFLICT (group_id, code) DO UPDATE SET name = EXCLUDED.name""",
            [SIGUNGU_ALIAS_GROUP, new, old, "2026-08 실측(필지 대조)"],
        )
        n_sgg += cur.rowcount
    # 시도명 별칭은 자동 적재하지 않는다. common_code sigungu 의 extra 는
    # 시도명이 아니라 도시명("청주", "창원", "경기 화성시")인 행이 섞여 있어
    # region_1depth_name 과의 비교가 "경남 → 창원" 같은 오류 쌍을 만든다
    # (2026-08 프로브에서 7건 중 6건이 오류). 시도명 정규화는 별도의 시도
    # 레지스트리를 갖춘 뒤 진행한다. 수집 결과는 리포트로만 남긴다.
    conn.commit()
    return n_sgg, 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", choices=["local", "railway"], default="local")
    ap.add_argument("--apply", action="store_true", help="common_code 에 적재 (기본은 리포트)")
    ap.add_argument("--out", default="", help="결과 JSON 저장 경로")
    ap.add_argument("--from-report", default="",
                    help="프로브 결과 JSON 을 재조사 없이 적재 (--apply 필요)")
    args = ap.parse_args()

    if args.from_report:
        if not args.apply:
            raise SystemExit("--from-report 는 --apply 와 함께 써야 합니다.")
        conn = _connect(args.target)
        results = json.loads(Path(args.from_report).read_text())
        n_sgg, _ = apply_aliases(conn, results)
        print(f"[{args.target}] APPLY (검토본) — sigungu_alias {n_sgg}건 적재")
        conn.close()
        return 0

    if not KAKAO_API_KEY:
        raise SystemExit("KAKAO_API_KEY 환경변수가 없습니다.")
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    conn = _connect(args.target)
    print(f"[{args.target}] {'APPLY' if args.apply else 'REPORT'} — 필지 대조 시작\n")
    results = probe(conn, headers)

    print("\n=== 결과 ===")
    print(f"  변화 없음        : {results['unchanged']}")
    print(f"  개명(5자리 별칭)  : {len(results['renamed'])}")
    print(f"  재편(10자리 별칭) : {len(results['split'])}")
    print(f"  시도명 별칭       : {len(results['sido'])}")
    print(f"  표본 없음         : {len(results['no_sample'])}  검증 실패: {len(results['unverified'])}")

    if results["renamed"]:
        print("\n  [개명] 구코드 → 신코드")
        for old, new in sorted(results["renamed"].items()):
            print(f"    {old} → {new}")
    if results["split"]:
        print("\n  [재편] 신시군구+법정동 → 구코드 (표본에 없는 법정동은 미커버)")
        for k, v in sorted(results["split"].items()):
            print(f"    {k} → {v}")
    if results["sido"]:
        print("\n  [시도명] 신명칭 → 표준")
        for k, v in sorted(results["sido"].items()):
            print(f"    {k} → {v}")
    if results["unverified"]:
        print(f"\n  [검증 실패] {results['unverified'][:10]}{'...' if len(results['unverified'])>10 else ''}")

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"\n결과 JSON: {args.out}")

    if args.apply:
        n_sgg, _ = apply_aliases(conn, results)
        print(f"\n적재 — sigungu_alias {n_sgg}건 (시도명은 리포트 전용 — apply_aliases 주석 참조)")
    else:
        conn.rollback()
        print("\nREPORT 모드 — DB 변경 없음")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
