"""경찰청 범죄발생지(KOSIS DT_132004_A030) → 전국 시군구 범죄 상세/안전점수 적재.

- 소스: KOSIS A030 (죄종별 × 지역별, 시군구 단위, 2024)
- 산출: 5대범죄(살인/강도/성폭력/절도/폭력) + 인구 10만명당 범죄율 + 안전점수
- 점수식: 전국 시군구 범죄율의 백분위(낮은 범죄율 → 높은 점수). 기존 데이터 역설계 최적합.
- 일반구(청주/천안/전주/포항/창원 등): A030는 시 단위만 제공 → 모(母) 시 값을 일반구 코드에 상속.
- 부천 등 옛 구 코드(API 통합코드 미지원): 아파트가 쓰는 코드를 시 코드(xxxx0)에서 상속.
- 세종: A030에서 '세종'(B020706)이 울산 하위로 편제됨 → 세종 시군구코드(36110)로 보정.

실행:
  .venv/bin/python -m batch.safety.build_crime_detail --dry-run   # 검증만
  .venv/bin/python -m batch.safety.build_crime_detail             # 실제 적재(트랜잭션)
"""

import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict

import requests
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DB_URL = os.getenv("DATABASE_URL", "postgresql://wizmain@localhost:5432/apt_recom")
API_KEY = os.getenv("KOSIS_API_KEY")
DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
TARGET_YEAR = 2024

# 5대범죄 ← A030 죄종(C1) 코드 매핑.
# 검증: 종로(11110) total_crime=2754 (기존 DB와 정확 일치)로 확인.
#   강력범죄(A02) = 살인기수+살인미수+강도+강간+유사강간+강제추행+기타+방화
#   → 5대범죄는 이 중 방화(A0208) 제외.
BUCKET_CODES = {
    "murder": ["A0201", "A0202"],  # 살인기수+살인미수등
    "robbery": ["A0203"],  # 강도
    "sexual_assault": [
        "A0204",
        "A0205",
        "A0206",
        "A0207",
    ],  # 강간+유사강간+강제추행+기타
    "theft": ["A03"],  # 절도범죄(소계)
    "violence": ["A04"],  # 폭력범죄(소계)
}
BUCKET_FIELDS = list(BUCKET_CODES.keys())


def norm_sido(name: str) -> str:
    """시도명 표준키. 구/신 명칭(전라북도↔전북특별자치도) 흡수."""
    if not name:
        return ""
    n = name.strip()
    for s in [
        "서울",
        "부산",
        "대구",
        "인천",
        "광주",
        "대전",
        "울산",
        "세종",
        "경기",
        "강원",
        "제주",
    ]:
        if n.startswith(s):
            return s
    if n.startswith(("전라", "전북", "전남")):
        return "전남" if "남" in n else "전북"
    if n.startswith(("경상", "경북", "경남")):
        return "경남" if "남" in n else "경북"
    if n.startswith(("충청", "충북", "충남")):
        return "충남" if "남" in n else "충북"
    return n[:2]


def parent_si_name(raw_name: str) -> str:
    """인구테이블 sigungu_name → 매칭용 시군구명.
    '청주시 상당구' → '청주시' (일반구는 모 시로). '가평군'/'종로구' → 그대로.
    """
    raw = raw_name.strip()
    if " " in raw:
        first = raw.split()[0]
        if first.endswith(("시", "군")):
            return first
    return raw


# ---------- 수집 ----------


def fetch_a030():
    """A030 전체(죄종×지역, 2024) 수집."""
    params = {
        "method": "getList",
        "apiKey": API_KEY,
        "format": "json",
        "jsonVD": "Y",
        "orgId": "132",
        "tblId": "DT_132004_A030",
        "objL1": "ALL",
        "objL2": "ALL",
        "itmId": "ALL",
        "startPrdDe": str(TARGET_YEAR),
        "endPrdDe": str(TARGET_YEAR),
        "prdSe": "Y",
    }
    data = requests.get(DATA_URL, params=params, timeout=180).json()
    if isinstance(data, dict):
        raise RuntimeError(f"KOSIS 에러: {data}")
    return data


def build_a030_buckets(data):
    """(sido_norm, 지역명) → {버킷필드: 합계}. 시군구(C2 길이7) + 세종(시도 길이5)."""
    # 지역코드 → 명칭, 시도명(길이5)
    code_name = {}
    for d in data:
        c2 = d.get("C2")
        if c2:
            code_name[c2] = d.get("C2_NM")
    sido_name_by_code5 = {c: n for c, n in code_name.items() if len(c) == 5}

    # 지역코드 → {죄종코드: 값}
    cells = defaultdict(dict)
    for d in data:
        c2 = d.get("C2")
        c1 = d.get("C1")
        if not c2 or not c1:
            continue
        try:
            v = int(float(d.get("DT")))
        except (TypeError, ValueError):
            continue
        cells[c2][c1] = v

    def buckets_of(c2):
        cc = cells.get(c2, {})
        b = {f: sum(cc.get(code, 0) for code in BUCKET_CODES[f]) for f in BUCKET_FIELDS}
        b["total_crime"] = sum(b[f] for f in BUCKET_FIELDS)
        return b

    result = {}
    # 시군구(길이7)
    for c2, nm in code_name.items():
        if len(c2) != 7:
            continue
        # 세종: A030에서 '세종'(B020706)이 울산(B0207) 하위로 잘못 편제됨 → 보정
        if nm == "세종":
            result[("세종", "세종특별자치시")] = buckets_of(c2)
            continue
        sido = norm_sido(sido_name_by_code5.get(c2[:5], ""))
        result[(sido, nm)] = buckets_of(c2)
    return result


def load_population():
    """population_by_district(계) → 코드별 인구 + 시도/시군구명."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT DISTINCT substr(sigungu_code,1,5) AS code, sido_name, sigungu_name,
               total_pop, daytime_pop
        FROM population_by_district
        WHERE age_group='계' AND sigungu_code IS NOT NULL AND sigungu_name IS NOT NULL
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def load_apartment_codes():
    """아파트가 실제 사용하는 시군구코드(5자리) 집합."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT substr(sigungu_code,1,5) FROM apartments "
        "WHERE sigungu_code IS NOT NULL"
    )
    codes = [r[0] for r in cur.fetchall() if r[0]]
    conn.close()
    return codes


# ---------- 산출 ----------


def compute(a030, pop_rows):
    """시(매칭키)별 집계 → 점수 산출 → 코드별 행 생성."""
    # 1) 시(매칭키)별 그룹: 멤버 코드 + 시 단위 인구 합산
    groups = defaultdict(
        lambda: {"members": [], "resident": 0, "daytime": 0, "daytime_ok": True}
    )
    for r in pop_rows:
        key = (norm_sido(r["sido_name"]), parent_si_name(r["sigungu_name"]))
        g = groups[key]
        g["members"].append(r["code"])
        g["resident"] += int(r["total_pop"] or 0)
        if r["daytime_pop"]:
            g["daytime"] += int(r["daytime_pop"])
        else:
            g["daytime_ok"] = False

    # 2) A030 매칭 + 시 단위 지표
    matched, unmatched = {}, []
    for key, g in groups.items():
        b = a030.get(key)
        if not b or g["resident"] <= 0:
            unmatched.append((key, g))
            continue
        resident = g["resident"]
        ratio = (
            round(g["daytime"] / resident, 2)
            if (g["daytime_ok"] and g["daytime"] > 0)
            else 1.0
        )
        effective = max(1, round(resident * ratio))
        rate = round(b["total_crime"] / effective * 100000, 1)
        matched[key] = {
            **b,
            "resident": resident,
            "effective": effective,
            "ratio": ratio,
            "rate": rate,
            "members": g["members"],
        }

    # 3) 전국 백분위 점수 (낮은 rate=높은 점수). 기존 데이터 역설계 최적합(avg_err≈1.9).
    import bisect

    sorted_rates = sorted(m["rate"] for m in matched.values())
    denom = (len(sorted_rates) - 1) or 1
    for m in matched.values():
        rank = bisect.bisect_left(sorted_rates, m["rate"])
        score = 100 * (1 - rank / denom)
        m["score"] = round(max(0.0, min(100.0, score)), 1)

    # 4) 코드별 행 펼치기 (일반구는 시 값 상속)
    def make_row(code, m):
        return {
            "sigungu_code": code,
            "murder": m["murder"],
            "robbery": m["robbery"],
            "sexual_assault": m["sexual_assault"],
            "theft": m["theft"],
            "violence": m["violence"],
            "total_crime": m["total_crime"],
            "resident_pop": m["resident"],
            "effective_pop": m["effective"],
            "crime_rate": m["rate"],
            "crime_safety_score": m["score"],
            "float_pop_ratio": m["ratio"],
            "updated_year": TARGET_YEAR,
        }

    out_rows = []
    for key, m in matched.items():
        for code in m["members"]:
            out_rows.append(make_row(code, m))

    # 5) 코드 보정 상속: 일반구/옛 구 코드(예: 부천 4159x, 진해구)는 시 단위만
    #    범죄데이터가 있으므로 '시 코드(xxxx0)' 또는 같은 first-4 매칭 행의 값을 상속.
    by_code = {r["sigungu_code"]: r for r in out_rows}

    def inherit(code):
        """code에 대해 시 단위 매칭 행을 찾아 복제 추가. 성공 시 True."""
        if code in by_code:
            return True
        rep = by_code.get(code[:4] + "0")
        if rep is None:
            rep = next((r for c, r in by_code.items() if c[:4] == code[:4]), None)
        if rep is None:
            return False
        row = {**rep, "sigungu_code": code}
        out_rows.append(row)
        by_code[code] = row
        return True

    # 5a) 이름 미매칭 일반구
    still_unmatched = []
    for key, g in unmatched:
        name = key[1]
        ok = name.endswith("구") and all(inherit(c) for c in g["members"])
        if not ok:
            still_unmatched.append((key, g))

    # 5b) 아파트가 실제 사용하는 시군구 코드 중 미커버분 보충
    #     (부천/화성 등 API 통합코드 미지원으로 옛 구 코드를 쓰는 케이스)
    for code in load_apartment_codes():
        inherit(code)

    return out_rows, matched, still_unmatched


# ---------- 적재 ----------

UPSERT = """
INSERT INTO sigungu_crime_detail
  (sigungu_code, murder, robbery, sexual_assault, theft, violence, total_crime,
   resident_pop, effective_pop, crime_rate, crime_safety_score, float_pop_ratio, updated_year)
VALUES (%(sigungu_code)s,%(murder)s,%(robbery)s,%(sexual_assault)s,%(theft)s,%(violence)s,
        %(total_crime)s,%(resident_pop)s,%(effective_pop)s,%(crime_rate)s,
        %(crime_safety_score)s,%(float_pop_ratio)s,%(updated_year)s)
ON CONFLICT (sigungu_code) DO UPDATE SET
  murder=EXCLUDED.murder, robbery=EXCLUDED.robbery, sexual_assault=EXCLUDED.sexual_assault,
  theft=EXCLUDED.theft, violence=EXCLUDED.violence, total_crime=EXCLUDED.total_crime,
  resident_pop=EXCLUDED.resident_pop, effective_pop=EXCLUDED.effective_pop,
  crime_rate=EXCLUDED.crime_rate, crime_safety_score=EXCLUDED.crime_safety_score,
  float_pop_ratio=EXCLUDED.float_pop_ratio, updated_year=EXCLUDED.updated_year
"""


def persist(out_rows):
    conn = psycopg2.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sigungu_crime_detail (
                sigungu_code TEXT PRIMARY KEY,
                murder INTEGER, robbery INTEGER, sexual_assault INTEGER,
                theft INTEGER, violence INTEGER, total_crime INTEGER,
                resident_pop INTEGER, effective_pop INTEGER,
                crime_rate DOUBLE PRECISION, crime_safety_score DOUBLE PRECISION,
                float_pop_ratio DOUBLE PRECISION, updated_year INTEGER
            )
        """)
        # 전국 재계산이므로 좀비/사장 코드 제거를 위해 전체 삭제 후 적재 (원자적)
        cur.execute("DELETE FROM sigungu_crime_detail")
        psycopg2.extras.execute_batch(cur, UPSERT, out_rows, page_size=200)
        conn.commit()
    finally:
        conn.close()


def write_report(path, out_rows, matched, unmatched):
    lines = []
    by_sido = defaultdict(int)
    for r in out_rows:
        by_sido[r["sigungu_code"][:2]] += 1
    lines.append(f"적재 대상 행(코드) 수: {len(out_rows)}")
    lines.append(f"매칭 시군구(시 단위) 수: {len(matched)}")
    lines.append(f"미매칭 그룹 수: {len(unmatched)}")
    # 종로 검증
    jongno = next((r for r in out_rows if r["sigungu_code"] == "11110"), None)
    if jongno:
        lines.append(
            f"[검증] 종로(11110) total_crime={jongno['total_crime']} "
            f"(기대 2875), score={jongno['crime_safety_score']}"
        )
    scores = [r["crime_safety_score"] for r in out_rows]
    lines.append(f"점수 범위: {min(scores)} ~ {max(scores)}")
    lines.append(
        "시도prefix별 행수: " + ", ".join(f"{k}:{by_sido[k]}" for k in sorted(by_sido))
    )
    lines.append("\n[미매칭 그룹 (최대 40)]")
    for key, g in sorted(unmatched)[:40]:
        lines.append(f"  {key}  members={len(g['members'])} resident={g['resident']}")
    Path(path).write_text("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", default="batch/logs/crime_detail_report.txt")
    args = ap.parse_args()

    if not API_KEY:
        print("KOSIS_API_KEY 없음", file=sys.stderr)
        sys.exit(1)

    data = fetch_a030()
    a030 = build_a030_buckets(data)
    pop_rows = load_population()
    out_rows, matched, unmatched = compute(a030, pop_rows)
    write_report(args.report, out_rows, matched, unmatched)

    if args.dry_run:
        print(f"[DRY-RUN] {len(out_rows)}행 산출, 리포트: {args.report}")
        return

    persist(out_rows)
    print(f"[적재완료] {len(out_rows)}행 UPSERT, 리포트: {args.report}")


if __name__ == "__main__":
    main()
