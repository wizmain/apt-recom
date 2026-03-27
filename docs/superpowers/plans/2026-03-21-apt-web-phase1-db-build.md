# Phase 1: DB 빌드 — CSV → SQLite 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 CSV 데이터를 웹 서비스용 SQLite DB(`web/backend/apt_web.db`)로 변환하는 빌드 스크립트를 구현한다.

**Architecture:** `build_db.py` 스크립트가 6개 테이블 + 1개 요약 테이블 + 1개 매핑 테이블을 생성하고, 기존 CSV 파일들을 적재한다. 45M행의 시설 매핑 데이터는 청크 로드 + 인덱스 후생성 전략으로 최적화한다.

**Tech Stack:** Python 3.12, pandas, sqlite3

**Spec:** `docs/superpowers/specs/2026-03-21-apt-web-design.md`

---

## Task 0: 프로젝트 구조 생성

**Files:**
- Create: `web/backend/build_db.py`
- Create: `web/backend/database.py`

- [ ] **Step 1: 디렉토리 구조 생성**

```bash
mkdir -p web/backend/routers web/backend/services
```

- [ ] **Step 2: database.py — DB 연결 유틸리티**

```python
"""SQLite 연결 및 테이블 생성"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "apt_web.db"


def get_connection(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def create_tables(conn):
    """모든 테이블 생성 (인덱스 제외)"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS apartments (
            pnu TEXT PRIMARY KEY,
            bld_nm TEXT,
            total_hhld_cnt INTEGER,
            dong_count INTEGER,
            max_floor INTEGER,
            use_apr_day TEXT,
            plat_plc TEXT,
            new_plat_plc TEXT,
            bjd_code TEXT,
            sigungu_code TEXT,
            lat REAL,
            lng REAL
        );

        CREATE TABLE IF NOT EXISTS facilities (
            facility_id TEXT PRIMARY KEY,
            facility_type TEXT,
            facility_subtype TEXT,
            name TEXT,
            lat REAL,
            lng REAL,
            address TEXT
        );

        CREATE TABLE IF NOT EXISTS apt_facility_mapping (
            pnu TEXT,
            facility_id TEXT,
            facility_type TEXT,
            facility_subtype TEXT,
            distance_m REAL,
            PRIMARY KEY (pnu, facility_id)
        ) WITHOUT ROWID;

        CREATE TABLE IF NOT EXISTS apt_facility_summary (
            pnu TEXT,
            facility_subtype TEXT,
            nearest_distance_m REAL,
            count_1km INTEGER,
            count_3km INTEGER,
            count_5km INTEGER,
            PRIMARY KEY (pnu, facility_subtype)
        );

        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apt_seq TEXT,
            sgg_cd TEXT,
            apt_nm TEXT,
            deal_amount INTEGER,
            exclu_use_ar REAL,
            floor INTEGER,
            deal_year INTEGER,
            deal_month INTEGER,
            deal_day INTEGER,
            build_year INTEGER
        );

        CREATE TABLE IF NOT EXISTS rent_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apt_seq TEXT,
            sgg_cd TEXT,
            apt_nm TEXT,
            deposit INTEGER,
            monthly_rent INTEGER,
            exclu_use_ar REAL,
            floor INTEGER,
            deal_year INTEGER,
            deal_month INTEGER,
            deal_day INTEGER
        );

        CREATE TABLE IF NOT EXISTS trade_apt_mapping (
            apt_seq TEXT PRIMARY KEY,
            pnu TEXT,
            apt_nm TEXT,
            sgg_cd TEXT,
            match_method TEXT
        );

        CREATE TABLE IF NOT EXISTS school_zones (
            pnu TEXT PRIMARY KEY,
            elementary_school_name TEXT,
            elementary_school_id TEXT,
            elementary_school_full_name TEXT,
            elementary_zone_id TEXT,
            middle_school_zone TEXT,
            middle_school_zone_id TEXT,
            high_school_zone TEXT,
            high_school_zone_id TEXT,
            high_school_zone_type TEXT,
            edu_office_name TEXT,
            edu_district TEXT
        );
    """)
    conn.commit()


def create_indexes(conn):
    """데이터 적재 완료 후 인덱스 생성"""
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_mapping_pnu ON apt_facility_mapping(pnu);
        CREATE INDEX IF NOT EXISTS idx_mapping_type ON apt_facility_mapping(facility_subtype);
        CREATE INDEX IF NOT EXISTS idx_summary_pnu ON apt_facility_summary(pnu);
        CREATE INDEX IF NOT EXISTS idx_trade_sgg ON trade_history(sgg_cd);
        CREATE INDEX IF NOT EXISTS idx_trade_seq ON trade_history(apt_seq);
        CREATE INDEX IF NOT EXISTS idx_trade_year ON trade_history(deal_year);
        CREATE INDEX IF NOT EXISTS idx_rent_sgg ON rent_history(sgg_cd);
        CREATE INDEX IF NOT EXISTS idx_rent_seq ON rent_history(apt_seq);
        CREATE INDEX IF NOT EXISTS idx_apt_sigungu ON apartments(sigungu_code);
        CREATE INDEX IF NOT EXISTS idx_trade_map_pnu ON trade_apt_mapping(pnu);
    """)
    conn.commit()
```

---

## Task 1: 아파트 마스터 적재

**Files:**
- Modify: `web/backend/build_db.py`

- [ ] **Step 1: build_db.py 기본 구조 + apartments 적재**

```python
"""CSV → SQLite 빌드 스크립트"""

import pandas as pd
import sqlite3
import re
from pathlib import Path
from database import get_connection, create_tables, create_indexes

DATA_DIR = Path(__file__).parent.parent.parent / "apt_eda" / "data"


def load_apartments(conn):
    """아파트 마스터 적재"""
    print("=== apartments 적재 ===")
    df = pd.read_csv(
        DATA_DIR / "processed" / "fm_apt_master_with_coords.csv",
        dtype={"PNU": str, "bjdCode": str}
    )
    df = df.rename(columns={
        "PNU": "pnu", "bldNm": "bld_nm", "total_hhldCnt": "total_hhld_cnt",
        "dong_count": "dong_count", "max_floor": "max_floor",
        "representative_useAprDay": "use_apr_day", "platPlc": "plat_plc",
        "newPlatPlc": "new_plat_plc", "bjdCode": "bjd_code",
    })
    df["sigungu_code"] = df["bjd_code"].str[:5]
    cols = ["pnu", "bld_nm", "total_hhld_cnt", "dong_count", "max_floor",
            "use_apr_day", "plat_plc", "new_plat_plc", "bjd_code",
            "sigungu_code", "lat", "lng"]
    df[cols].to_sql("apartments", conn, if_exists="replace", index=False)
    print(f"  적재: {len(df):,}건")


def main():
    db_path = Path(__file__).parent / "apt_web.db"
    if db_path.exists():
        db_path.unlink()
        print(f"기존 DB 삭제: {db_path}")

    conn = get_connection(db_path)
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=WAL")

    create_tables(conn)

    load_apartments(conn)

    # 이후 Task에서 추가
    # load_facilities(conn)
    # load_facility_mapping(conn)
    # load_facility_summary(conn)
    # load_trade_history(conn)
    # load_rent_history(conn)
    # load_trade_apt_mapping(conn)
    # load_school_zones(conn)

    create_indexes(conn)
    conn.close()
    print(f"\n빌드 완료: {db_path} ({db_path.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행 및 검증**

```bash
cd web/backend
../../.venv/bin/python build_db.py
../../.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('apt_web.db')
print(conn.execute('SELECT COUNT(*) FROM apartments').fetchone()[0])
print(conn.execute('SELECT pnu, bld_nm, lat, lng FROM apartments LIMIT 3').fetchall())
"
```

Expected: 7,916건 (또는 7,917건), 좌표 포함

---

## Task 2: 시설 데이터 적재

**Files:**
- Modify: `web/backend/build_db.py`

- [ ] **Step 1: load_facilities 함수 추가**

```python
def load_facilities(conn):
    """시설 정규화 데이터 적재"""
    print("=== facilities 적재 ===")
    df = pd.read_csv(DATA_DIR / "processed" / "fm_all_facilities_normalized.csv")
    df = df.rename(columns={"name": "name"})
    cols = ["facility_id", "facility_type", "facility_subtype", "name",
            "lat", "lng", "address"]
    df[cols].to_sql("facilities", conn, if_exists="replace", index=False)
    print(f"  적재: {len(df):,}건")
```

main()에서 `load_facilities(conn)` 호출 추가.

- [ ] **Step 2: 실행 및 검증**

```bash
../../.venv/bin/python build_db.py
../../.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('apt_web.db')
print('facilities:', conn.execute('SELECT COUNT(*) FROM facilities').fetchone()[0])
print(conn.execute('SELECT facility_subtype, COUNT(*) FROM facilities GROUP BY facility_subtype').fetchall())
"
```

Expected: 175,479건, 14종 시설 유형

---

## Task 3: 시설 매핑 + 요약 테이블 적재

**Files:**
- Modify: `web/backend/build_db.py`

- [ ] **Step 1: load_facility_mapping 함수 (청크 로드)**

```python
def load_facility_mapping(conn):
    """아파트-시설 매핑 적재 (45M행, 청크 로드)"""
    print("=== apt_facility_mapping 적재 ===")
    csv_path = DATA_DIR / "processed" / "fm_apt_facility_mapping.csv"
    chunk_size = 500_000
    total = 0

    for i, chunk in enumerate(pd.read_csv(csv_path, dtype={"PNU": str}, chunksize=chunk_size)):
        chunk = chunk.rename(columns={"PNU": "pnu", "bldNm": "bld_nm"})
        cols = ["pnu", "facility_id", "facility_type", "facility_subtype", "distance_m"]
        chunk[cols].to_sql("apt_facility_mapping", conn, if_exists="append", index=False)
        total += len(chunk)
        if (i + 1) % 10 == 0:
            print(f"  진행: {total:,}건")

    print(f"  적재 완료: {total:,}건")
```

- [ ] **Step 2: load_facility_summary 함수 (집계 테이블)**

```python
def load_facility_summary(conn):
    """아파트별 시설 유형별 요약 집계"""
    print("=== apt_facility_summary 생성 ===")
    conn.execute("""
        INSERT INTO apt_facility_summary (pnu, facility_subtype, nearest_distance_m,
                                          count_1km, count_3km, count_5km)
        SELECT
            pnu,
            facility_subtype,
            MIN(distance_m) as nearest_distance_m,
            SUM(CASE WHEN distance_m <= 1000 THEN 1 ELSE 0 END) as count_1km,
            SUM(CASE WHEN distance_m <= 3000 THEN 1 ELSE 0 END) as count_3km,
            COUNT(*) as count_5km
        FROM apt_facility_mapping
        GROUP BY pnu, facility_subtype
    """)
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM apt_facility_summary").fetchone()[0]
    print(f"  생성: {count:,}건")
```

main()에서 순서대로 호출. **주의:** mapping 적재 후 summary 생성, 인덱스는 모두 마지막에.

- [ ] **Step 3: 실행** (10~20분 소요 예상)

```bash
../../.venv/bin/python build_db.py
```

- [ ] **Step 4: 검증**

```bash
../../.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('apt_web.db')
print('mapping:', conn.execute('SELECT COUNT(*) FROM apt_facility_mapping').fetchone()[0])
print('summary:', conn.execute('SELECT COUNT(*) FROM apt_facility_summary').fetchone()[0])
print(conn.execute('SELECT * FROM apt_facility_summary LIMIT 5').fetchall())
"
```

Expected: mapping ~45M, summary ~110K

---

## Task 4: 거래 데이터 적재

**Files:**
- Modify: `web/backend/build_db.py`

- [ ] **Step 1: load_trade_history + load_rent_history 함수**

```python
def load_trade_history(conn):
    """매매 실거래가 적재"""
    print("=== trade_history 적재 ===")
    df = pd.read_csv(DATA_DIR / "raw" / "apt_trade_total_2023_2026.csv", low_memory=False)
    # dealAmount: "169,000" → 169000
    df["dealAmount"] = df["dealAmount"].astype(str).str.replace(",", "").str.strip()
    df["dealAmount"] = pd.to_numeric(df["dealAmount"], errors="coerce")
    df = df.rename(columns={
        "aptSeq": "apt_seq", "sggCd": "sgg_cd", "aptNm": "apt_nm",
        "dealAmount": "deal_amount", "excluUseAr": "exclu_use_ar",
        "floor": "floor", "dealYear": "deal_year", "dealMonth": "deal_month",
        "dealDay": "deal_day", "buildYear": "build_year"
    })
    cols = ["apt_seq", "sgg_cd", "apt_nm", "deal_amount", "exclu_use_ar",
            "floor", "deal_year", "deal_month", "deal_day", "build_year"]
    df[cols].to_sql("trade_history", conn, if_exists="replace", index=False)
    print(f"  적재: {len(df):,}건")


def load_rent_history(conn):
    """전월세 실거래가 적재"""
    print("=== rent_history 적재 ===")
    df = pd.read_csv(DATA_DIR / "raw" / "apt_rent_total_2023_2026.csv", low_memory=False)
    df["deposit"] = df["deposit"].astype(str).str.replace(",", "").str.strip()
    df["deposit"] = pd.to_numeric(df["deposit"], errors="coerce")
    df["monthlyRent"] = pd.to_numeric(df["monthlyRent"], errors="coerce")
    df = df.rename(columns={
        "aptSeq": "apt_seq", "sggCd": "sgg_cd", "aptNm": "apt_nm",
        "deposit": "deposit", "monthlyRent": "monthly_rent",
        "excluUseAr": "exclu_use_ar", "floor": "floor",
        "dealYear": "deal_year", "dealMonth": "deal_month", "dealDay": "deal_day"
    })
    cols = ["apt_seq", "sgg_cd", "apt_nm", "deposit", "monthly_rent",
            "exclu_use_ar", "floor", "deal_year", "deal_month", "deal_day"]
    df[cols].to_sql("rent_history", conn, if_exists="replace", index=False)
    print(f"  적재: {len(df):,}건")
```

- [ ] **Step 2: 실행 및 검증**

```bash
../../.venv/bin/python build_db.py
../../.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('apt_web.db')
print('trades:', conn.execute('SELECT COUNT(*) FROM trade_history').fetchone()[0])
print('rents:', conn.execute('SELECT COUNT(*) FROM rent_history').fetchone()[0])
print(conn.execute('SELECT deal_year, COUNT(*) FROM trade_history GROUP BY deal_year').fetchall())
"
```

---

## Task 5: 거래-아파트 매핑

**Files:**
- Modify: `web/backend/build_db.py`

- [ ] **Step 1: load_trade_apt_mapping 함수**

```python
def normalize_name(name):
    """단지명 정규화 (공백, 괄호, 특수문자 제거)"""
    if pd.isna(name):
        return ""
    s = str(name).strip()
    s = re.sub(r'\(.*?\)', '', s)  # 괄호 안 내용 제거
    s = re.sub(r'[^가-힣a-zA-Z0-9]', '', s)  # 특수문자 제거
    return s.upper()


def load_trade_apt_mapping(conn):
    """실거래 단지 ↔ 아파트 마스터 PNU 매핑"""
    print("=== trade_apt_mapping 생성 ===")

    # 고유 apt_seq 목록
    trade_apts = pd.read_sql("""
        SELECT DISTINCT apt_seq, sgg_cd, apt_nm
        FROM trade_history
        WHERE apt_seq IS NOT NULL AND apt_seq != ''
    """, conn)

    # 아파트 마스터
    apts = pd.read_sql("SELECT pnu, bld_nm, sigungu_code FROM apartments", conn)

    # 정규화 이름
    trade_apts["name_norm"] = trade_apts["apt_nm"].apply(normalize_name)
    apts["name_norm"] = apts["bld_nm"].apply(normalize_name)

    # 1차: sgg_cd + 정규화이름 정확 일치
    merged = trade_apts.merge(
        apts, left_on=["sgg_cd", "name_norm"],
        right_on=["sigungu_code", "name_norm"], how="left"
    )
    merged["match_method"] = None
    merged.loc[merged["pnu"].notna(), "match_method"] = "exact_name"

    # 매칭 결과 저장
    result = merged[["apt_seq", "pnu", "apt_nm", "sgg_cd", "match_method"]].copy()
    result = result.drop_duplicates(subset=["apt_seq"], keep="first")
    result.to_sql("trade_apt_mapping", conn, if_exists="replace", index=False)

    matched = result["pnu"].notna().sum()
    print(f"  매칭: {matched:,} / {len(result):,} ({matched/len(result)*100:.1f}%)")
```

- [ ] **Step 2: 실행 및 검증**

```bash
../../.venv/bin/python build_db.py
../../.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('apt_web.db')
r = conn.execute('SELECT COUNT(*) as total, SUM(CASE WHEN pnu IS NOT NULL THEN 1 ELSE 0 END) as matched FROM trade_apt_mapping').fetchone()
print(f'total: {r[0]}, matched: {r[1]} ({r[1]/r[0]*100:.1f}%)')
"
```

---

## Task 6: 학군 데이터 적재

**Files:**
- Modify: `web/backend/build_db.py`

- [ ] **Step 1: load_school_zones 함수**

```python
def load_school_zones(conn):
    """학군 매핑 적재 (4개 CSV 병합)"""
    print("=== school_zones 적재 ===")
    proc = DATA_DIR / "processed"

    # 초등학교
    elem = pd.read_csv(proc / "fm_apt_school_zone_enriched.csv", dtype={"PNU": str, "bjdCode": str})
    elem = elem.rename(columns={
        "PNU": "pnu", "school_name": "elementary_school_name",
        "school_id": "elementary_school_id",
        "school_full_name": "elementary_school_full_name",
        "school_zone_id": "elementary_zone_id"
    })

    # 중학교
    mid = pd.read_csv(proc / "fm_apt_middle_school_zone.csv", dtype={"PNU": str})
    mid = mid.rename(columns={
        "PNU": "pnu", "middle_school_zone_name": "middle_school_zone",
        "middle_school_zone_id": "middle_school_zone_id"
    })

    # 고등학교
    high = pd.read_csv(proc / "fm_apt_high_school_zone.csv", dtype={"PNU": str})
    high = high.rename(columns={
        "PNU": "pnu", "high_school_zone_name": "high_school_zone",
        "high_school_zone_id": "high_school_zone_id",
        "high_school_zone_type": "high_school_zone_type"
    })

    # 교육행정구역
    edu = pd.read_csv(proc / "fm_apt_edu_district.csv", dtype={"PNU": str})
    edu = edu.rename(columns={
        "PNU": "pnu", "edu_office_name": "edu_office_name",
        "edu_district_name": "edu_district"
    })

    # 병합
    result = elem[["pnu", "elementary_school_name", "elementary_school_id",
                    "elementary_school_full_name", "elementary_zone_id"]].copy()
    result = result.merge(mid[["pnu", "middle_school_zone", "middle_school_zone_id"]],
                          on="pnu", how="left")
    result = result.merge(high[["pnu", "high_school_zone", "high_school_zone_id",
                                "high_school_zone_type"]], on="pnu", how="left")
    result = result.merge(edu[["pnu", "edu_office_name", "edu_district"]],
                          on="pnu", how="left")
    result = result.drop_duplicates(subset=["pnu"], keep="first")

    result.to_sql("school_zones", conn, if_exists="replace", index=False)
    print(f"  적재: {len(result):,}건")
```

- [ ] **Step 2: 실행 및 검증**

```bash
../../.venv/bin/python build_db.py
../../.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('apt_web.db')
print('school_zones:', conn.execute('SELECT COUNT(*) FROM school_zones').fetchone()[0])
print(conn.execute('SELECT pnu, elementary_school_name, middle_school_zone, high_school_zone, edu_district FROM school_zones LIMIT 3').fetchall())
"
```

---

## Task 7: 전체 빌드 실행 및 최종 검증

- [ ] **Step 1: main()에 모든 함수 호출 추가 후 전체 빌드**

```bash
cd web/backend
../../.venv/bin/python build_db.py
```

- [ ] **Step 2: 최종 검증**

```bash
../../.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('apt_web.db')
tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
for t in tables:
    name = t[0]
    count = conn.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
    print(f'{name}: {count:,}')
"
```

Expected:
```
apartments: ~7,916
facilities: ~175,479
apt_facility_mapping: ~45,000,000
apt_facility_summary: ~110,000
trade_history: (매매 거래 건수)
rent_history: (전월세 거래 건수)
trade_apt_mapping: (고유 단지 수)
school_zones: ~7,914
```

- [ ] **Step 3: DB 파일 크기 확인**

```bash
ls -lh apt_web.db
```

---

## 실행 순서 요약

```
Task 0: 프로젝트 구조 + database.py
  ↓
Task 1: apartments 적재
  ↓
Task 2: facilities 적재
  ↓
Task 3: apt_facility_mapping + summary (10~20분)
  ↓
Task 4: trade_history + rent_history
  ↓
Task 5: trade_apt_mapping
  ↓
Task 6: school_zones
  ↓
Task 7: 전체 빌드 + 최종 검증
```
