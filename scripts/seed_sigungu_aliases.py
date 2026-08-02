"""시군구 코드 별칭(sigungu_alias / sido_alias)을 실측으로 만들어 적재한다.

방식
  추측으로 신·구 대응을 만들지 않는다. 시군구마다 실제 단지의 지번 주소를
  Kakao 주소검색에 넣어, 응답 b_code 를 그 단지의 PNU 와 필지 단위로 대조한다.
    검증: b_code[5:10] == pnu[5:10] (법정동 보존)
          main/sub 지번 == pnu 본번/부번
  같은 필지가 확인됐을 때만 (구코드 → b_code 앞 5자리) 를 대응으로 인정한다.
  앞 5자리가 같으면 개편이 없는 지역이므로 별칭을 만들지 않는다.

  시군구당 표본 여러 곳(기본 3)을 조사한다. 판정 규칙:
    - 표본 전부가 필지 완전일치(법정동 보존)이고 신코드가 하나로 모이며
      검증 표본이 MIN_VERIFIED 이상이면 → 5자리 개명 별칭
    - 법정동이 바뀌었는데 본번·부번과 동명(emd 레지스트리 대조)이 일치하면
      법정동 재부여형 재편(인천 유형) → 10자리→10자리 별칭. 이 유형에서
      5자리 치환은 엉뚱한 동의 PNU 를 만들므로 절대 5자리 별칭을 만들지
      않는다. 표본에 없는 법정동은 커버되지 않는다(미커버 유입은 정규화
      되지 않고 SGG 가드 → 거래 기반 재조합 경로로 안전하게 빠진다).
    - 부번 포함 지번이 검색되지 않으면 본번만으로 재시도한다(신안 유형).
      이때는 부번 대조가 불가능하므로 동명 일치를 필수로 요구한다.

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
import re
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


_JIBUN_TAIL = re.compile(r"(\d+)-\d+$")


def _geocode_with_fallback(headers: dict, addr: str) -> tuple[dict | None, bool]:
    """(응답, 부번대조가능). 부번 포함 지번이 안 잡히면 본번만으로 재시도한다.

    신안 지도읍 읍내리 168-50 은 검색 불가, 168 은 성공(2026-08 실측).
    본번 검색이면 응답 부번을 원 지번과 대조할 수 없어 False 를 함께 준다.
    """
    got = _geocode(headers, addr)
    if got:
        return got, True
    stripped = _JIBUN_TAIL.sub(r"\1", addr)
    if stripped != addr:
        return _geocode(headers, stripped), False
    return None, True


# 개명(5자리) 판정에 필요한 최소 검증 표본. 1건으로 판정하면 인천 서구처럼
# 재부여형 재편의 보존 동 하나가 우연히 통과해 오판한다(2026-08 실제 사례).
MIN_VERIFIED = 2


def _judge_sample(pnu: str, addr: dict, emd_names: dict,
                  ji_checked: bool) -> tuple[str, str] | None:
    """표본 하나를 판정한다. (신코드, 유형) 반환 — 유형은 exact | reassigned.

    exact      법정동 보존 + 본번·부번 일치
    reassigned 법정동 재부여 — 본번(·부번) 일치 + 동명이 emd 레지스트리와 일치
    """
    b_code = addr.get("b_code") or ""
    if len(b_code) < 10:
        return None
    bun = str(addr.get("main_address_no") or "0").zfill(4)
    ji = str(addr.get("sub_address_no") or "0").zfill(4)
    if bun != pnu[11:15]:
        return None
    if ji_checked and ji != pnu[15:19]:
        return None

    if b_code[5:10] == pnu[5:10]:
        if ji_checked:
            return b_code[:5], "exact"
        # 부번 미대조면 완전일치로 보지 않고 동명까지 요구한다
    old_name = emd_names.get(pnu[:10], "")
    new_name = (addr.get("region_3depth_name") or "").strip()
    if old_name and new_name and old_name == new_name:
        kind = "exact" if b_code[5:10] == pnu[5:10] else "reassigned"
        return (b_code[:5] if kind == "exact" else b_code[:10]), kind
    return None


def probe(conn, headers: dict) -> dict:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT code, name, extra FROM common_code WHERE group_id='sigungu' ORDER BY code")
    registry = [dict(r) for r in cur.fetchall()]

    # emd 레지스트리 — 재부여 판정의 동명 대조 재료
    cur.execute("SELECT code, name FROM common_code WHERE group_id = 'emd'")
    emd_names = {r["code"]: r["name"] for r in cur.fetchall()}

    # 알려진 시도 표기 — 여기 없는 region_1depth_name 만 신명칭 후보로 남긴다
    cur.execute("SELECT code, name, extra FROM common_code WHERE group_id IN ('sido', 'sido_alias')")
    known_sido: set[str] = set()
    for r in cur.fetchall():
        known_sido.add(r["code"])
        if r["name"]:
            known_sido.add(r["name"])
        if r["extra"] and r["extra"] != "매칭 전용 canonical 토큰":
            known_sido.add(r["extra"])

    results = {"unchanged": 0, "no_sample": [], "unverified": [],
               "renamed": {}, "reassigned": {}, "sido": {}}

    for i, row in enumerate(registry, 1):
        old = row["code"]
        cur.execute(SAMPLE_SQL, {"prefix": old + "%", "n": SAMPLES_PER_SIGUNGU})
        samples = cur.fetchall()
        if not samples:
            results["no_sample"].append(old)
            continue

        exact_new: dict[str, int] = defaultdict(int)      # 신5자리 → 표본 수
        reassigned: dict[str, str] = {}                    # 신10자리 → 구10자리
        reassigned_backup: dict[str, str] = {}             # exact 의 10자리 대응
        for s in samples:
            addr, ji_checked = _geocode_with_fallback(headers, s["plat_plc"])
            if not addr:
                continue
            judged = _judge_sample(s["pnu"], addr, emd_names, ji_checked)
            if not judged:
                continue
            new_code, kind = judged
            if kind == "exact":
                exact_new[new_code] += 1
                # 재부여형으로 판명될 경우를 대비해 10자리 대응도 함께 기록.
                # 보존 동은 신법정동 == 구법정동이다.
                reassigned_backup[new_code + s["pnu"][5:10]] = s["pnu"][:10]
            else:
                reassigned[new_code] = s["pnu"][:10]
            sido_new = (addr.get("region_1depth_name") or "").strip()
            if sido_new and sido_new not in known_sido:
                # sido/sido_alias 어디에도 없는 표기 — 새 개편의 시도명 후보.
                # extra 비교는 도시명 혼용("청주")으로 오류 쌍을 만들어 폐기했다.
                results["sido"][sido_new] = "미등록 표기"

        verified = sum(exact_new.values()) + len(reassigned)
        if verified == 0:
            results["unverified"].append(old)
        elif reassigned:
            # 법정동 재부여형 — 검증된 표본 전부(보존 동 포함)를 10자리로 남기고
            # 5자리 별칭은 절대 만들지 않는다. 서구 백석동처럼 보존 동이 섞여도
            # 10자리 항목이면 안전하다.
            results["reassigned"].update(reassigned)
            results["reassigned"].update(reassigned_backup)
        elif set(exact_new) == {old}:
            results["unchanged"] += 1
        elif len(exact_new) == 1 and verified >= MIN_VERIFIED:
            results["renamed"][old] = next(iter(exact_new))
        else:
            # 신코드가 갈리거나 표본이 부족 — 판정 보류
            results["unverified"].append(old)
        if i % 50 == 0:
            print(f"  진행 {i}/{len(registry)}")

    # 병합 교차검증 — 서로 다른 구코드가 같은 신코드로 합쳐지는 재편에서는
    # 구코드별 독립 판정이 한쪽을 "개명"으로 오판한다. 인천 동구(법정동 보존)가
    # 28125 로 개명 판정되지만, 28125 는 구 중구 유래의 재부여 법정동도 담는다.
    # 5자리 별칭이 있으면 미커버 법정동이 "동구+엉뚱한 법정동"으로 오변환되므로,
    # 재부여 매핑에 등장하는 신코드의 개명 판정은 10자리로 강등한다.
    reassigned_sggs = {k[:5] for k in results["reassigned"]}
    for old_code, new_code in list(results["renamed"].items()):
        if new_code in reassigned_sggs:
            del results["renamed"][old_code]
            results["demoted_to_reassigned"] = results.get("demoted_to_reassigned", [])
            results["demoted_to_reassigned"].append(f"{old_code}→{new_code}")

    return results


def apply_aliases(conn, results: dict) -> tuple[int, int]:
    cur = conn.cursor()
    n_sgg = 0
    # 5자리 개명: 신코드 → 구코드. 10자리 재부여: 신10자리 → 구10자리
    entries = {new: old for old, new in results["renamed"].items()}
    entries.update(results.get("reassigned", {}))
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
    print(f"  재부여(10자리)    : {len(results['reassigned'])}")
    print(f"  시도명 별칭       : {len(results['sido'])}")
    print(f"  표본 없음         : {len(results['no_sample'])}  검증 실패: {len(results['unverified'])}")

    if results["renamed"]:
        print("\n  [개명] 구코드 → 신코드")
        for old, new in sorted(results["renamed"].items()):
            print(f"    {old} → {new}")
    if results["reassigned"]:
        print("\n  [재부여] 신10자리 → 구10자리 (표본에 없는 법정동은 미커버)")
        for k, v in sorted(results["reassigned"].items()):
            print(f"    {k} → {v}")
    if results["sido"]:
        print("\n  [시도명 후보] 미등록 표기 — seed_sido_registry.py 목록에 추가 검토")
        for k in sorted(results["sido"]):
            print(f"    {k}")
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
