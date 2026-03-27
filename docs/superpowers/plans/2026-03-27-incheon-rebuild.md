# Incheon Apartment Data Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild all Incheon apartment data from scratch — fix bad geocoding for TRADE_ apartments, regenerate facility mappings, and recalculate all scores.

**Architecture:** Delete all Incheon rows from the DB, fix the geocoding script to validate coordinates fall within Incheon bounds (lat 37.3-37.6, lng 126.3-126.8), re-run the master collection with forced re-geocoding, then re-run integrate_incheon.py to repopulate all tables and scores.

**Tech Stack:** Python, SQLite, K-APT API, Vworld/Kakao geocoding APIs, scikit-learn BallTree, GeoPandas

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `apt_eda/src/collect_incheon_master.py` | Master apt collection + geocoding | Modify: add coordinate validation |
| `apt_eda/src/rebuild_incheon.py` | Orchestrator: purge DB → rebuild all | Create |
| `apt_eda/src/integrate_incheon.py` | Facilities, distances, school zones, DB update | No changes (re-run as-is) |
| `web/backend/apt_web.db` | Production SQLite database | Modified by rebuild |

---

### Task 1: Fix geocoding with coordinate validation

**Files:**
- Modify: `apt_eda/src/collect_incheon_master.py:365-420` (geocode_row function)
- Modify: `apt_eda/src/collect_incheon_master.py:427-466` (build_master function)

- [ ] **Step 1: Add Incheon bounds validation to `geocode_row`**

After each geocoding attempt, validate the returned coordinates are within Incheon's bounding box. If not, discard and try next method. This prevents Kakao name-search from returning coordinates of a same-named apartment in another city.

```python
# In collect_incheon_master.py, add this helper before geocode_row:

# 인천광역시 좌표 범위 (여유 포함)
INCHEON_BOUNDS = {
    "lat_min": 37.15,  # 옹진군 남단
    "lat_max": 37.62,  # 강화군 북단
    "lng_min": 125.50, # 옹진군 서단
    "lng_max": 126.85, # 내륙 동단
}


def _is_incheon(lat, lng) -> bool:
    """좌표가 인천광역시 범위 내인지 확인."""
    if lat is None or lng is None:
        return False
    return (INCHEON_BOUNDS["lat_min"] <= lat <= INCHEON_BOUNDS["lat_max"]
            and INCHEON_BOUNDS["lng_min"] <= lng <= INCHEON_BOUNDS["lng_max"])
```

- [ ] **Step 2: Update `geocode_row` to validate every result**

Replace the current `geocode_row` function. Each geocoding attempt now checks `_is_incheon()` before returning.

```python
def geocode_row(row) -> tuple:
    """한 행에 대해 지오코딩 수행 (좌표 검증 포함)."""
    # 1) 도로명 주소
    doro = str(row.get("doroJuso", "")).strip()
    if not doro:
        doro = str(row.get("roadNm_trade", "")).strip()

    road_addr = clean_road_address(doro)

    # 2) 지번 주소
    kapt_addr = str(row.get("kaptAddr", "")).strip()

    # 시도 제한 접두사 (Kakao 검색 시 인천 범위 강제)
    kapt_name = str(row.get("kaptName", "")).strip()
    umd = str(row.get("as4", row.get("umdNm_trade", ""))).strip()

    attempts = []

    # Vworld 도로명
    if road_addr:
        attempts.append(("vworld_road", lambda: geocode_vworld(road_addr, "road")))
    # Vworld 지번
    if kapt_addr:
        attempts.append(("vworld_parcel", lambda: geocode_vworld(kapt_addr, "parcel")))
    # Kakao 도로명
    if road_addr:
        attempts.append(("kakao_road", lambda: geocode_kakao(road_addr)))
    # Kakao 지번
    if kapt_addr:
        attempts.append(("kakao_parcel", lambda: geocode_kakao(kapt_addr)))
    # Kakao 이름+읍면동 (인천 명시)
    if kapt_name and umd:
        attempts.append(("kakao_name", lambda: geocode_kakao(f"인천광역시 {umd} {kapt_name}")))
    # Kakao 이름만 (인천 명시)
    if kapt_name:
        attempts.append(("kakao_name_only", lambda: geocode_kakao(f"인천광역시 {kapt_name}")))

    for source, fn in attempts:
        lat, lng = fn()
        if lat is not None and _is_incheon(lat, lng):
            return lat, lng, source
        time.sleep(SLEEP_SECONDS)

    return None, None, None
```

- [ ] **Step 3: Update `build_master` to filter invalid coordinates**

In the `build_master` function, add a final validation step that NULLs out any coordinates outside Incheon bounds.

```python
# At the end of build_master(), before return:
    # 최종 좌표 검증 — 인천 범위 외 좌표 제거
    for i, row in master.iterrows():
        lat = row.get("lat")
        lng = row.get("lng")
        try:
            lat_f = float(lat) if lat is not None and str(lat).strip() not in ("", "nan", "None") else None
            lng_f = float(lng) if lng is not None and str(lng).strip() not in ("", "nan", "None") else None
        except (ValueError, TypeError):
            lat_f, lng_f = None, None
        if lat_f is not None and not _is_incheon(lat_f, lng_f):
            master.at[i, "lat"] = None
            master.at[i, "lng"] = None
            master.at[i, "geocode_source"] = ""
```

- [ ] **Step 4: Delete cached files to force re-collection**

```bash
rm -f apt_eda/data/processed/fm_apt_master_incheon.csv
rm -f apt_eda/data/processed/_incheon_master_checkpoint.csv
# Keep kapt_incheon_raw.csv — K-APT API data is correct, no need to re-fetch
```

- [ ] **Step 5: Run collect_incheon_master.py**

```bash
cd /Users/wizmain/Documents/workspace/apt-recom
.venv/bin/python apt_eda/src/collect_incheon_master.py
```

Expected: ~2,900 apartments, geocode rate should be similar but with NO coordinates outside Incheon bounds. Check the report at the end — zero coordinates with `lng > 127.0`.

- [ ] **Step 6: Verify output has no bad coordinates**

```bash
.venv/bin/python -c "
import pandas as pd
df = pd.read_csv('apt_eda/data/processed/fm_apt_master_incheon.csv')
df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
df['lng'] = pd.to_numeric(df['lng'], errors='coerce')
has_coords = df['lat'].notna().sum()
bad = df[(df['lng'] > 126.85) | (df['lng'] < 125.5) | (df['lat'] > 37.62) | (df['lat'] < 37.15)]
bad = bad[bad['lat'].notna()]
print(f'Total: {len(df)}, Has coords: {has_coords}, Bad coords: {len(bad)}')
assert len(bad) == 0, f'Found {len(bad)} apartments with coordinates outside Incheon!'
print('✅ All coordinates within Incheon bounds')
"
```

---

### Task 2: Purge Incheon data from DB

**Files:**
- Create: `apt_eda/src/rebuild_incheon.py`

- [ ] **Step 1: Create the rebuild orchestrator script**

This script purges all Incheon data from the DB then calls the existing integration pipeline.

```python
"""인천 데이터 전체 재구축 — DB에서 인천 데이터 삭제 후 재적재."""

import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "web" / "backend" / "apt_web.db"


def purge_incheon(conn):
    """인천 관련 모든 데이터를 DB에서 삭제."""
    cur = conn.cursor()

    # 인천 PNU 패턴: 28xxxxx..., TRADE_28xxx..., ICN_xxx..., A28xxx...
    incheon_pnu_conditions = (
        "pnu LIKE '28%' OR pnu LIKE 'TRADE_28%' OR pnu LIKE 'ICN_%' OR pnu LIKE 'A28%'"
    )
    incheon_sgg_conditions = "sgg_cd LIKE '28%'"
    incheon_fac_conditions = "facility_id LIKE 'ICN_%'"

    tables_pnu = [
        ("apt_safety_score", incheon_pnu_conditions),
        ("apt_price_score", incheon_pnu_conditions),
        ("school_zones", incheon_pnu_conditions),
        ("trade_apt_mapping", incheon_sgg_conditions.replace("sgg_cd", "sgg_cd")),
        ("apt_facility_summary", incheon_pnu_conditions),
        ("apt_facility_mapping", incheon_pnu_conditions),
        ("apartments", incheon_pnu_conditions),
    ]

    print("=" * 60)
    print("Purging Incheon data from DB")
    print("=" * 60)

    for table, condition in tables_pnu:
        before = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        cur.execute(f"DELETE FROM {table} WHERE {condition}")
        after = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        deleted = before - after
        print(f"  {table}: deleted {deleted:,} rows ({before:,} → {after:,})")

    # Trade/rent history — delete by sgg_cd
    for table in ["trade_history", "rent_history"]:
        before = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        cur.execute(f"DELETE FROM {table} WHERE {incheon_sgg_conditions}")
        after = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        deleted = before - after
        print(f"  {table}: deleted {deleted:,} rows ({before:,} → {after:,})")

    # Facilities — delete ICN_ prefixed
    before = cur.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
    cur.execute(f"DELETE FROM facilities WHERE {incheon_fac_conditions}")
    after = cur.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
    print(f"  facilities: deleted {before - after:,} rows ({before:,} → {after:,})")

    conn.commit()
    print("\n✅ Purge complete")


def main():
    t0 = time.time()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=WAL")

    purge_incheon(conn)
    conn.close()

    elapsed = time.time() - t0
    print(f"\nPurge finished in {elapsed:.0f}s")
    print("\nNext steps:")
    print("  1. python apt_eda/src/integrate_incheon.py")
    print("  2. python apt_eda/src/improve_trade_mapping.py  (optional, for better trade matching)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the purge**

```bash
.venv/bin/python apt_eda/src/rebuild_incheon.py
```

Expected output: ~2,000-2,200 apartments deleted, ~12M facility mappings deleted, ~30K facility summaries deleted, ~344K trade history, ~579K rent history.

- [ ] **Step 3: Verify purge was clean**

```bash
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('web/backend/apt_web.db')
for t in ['apartments', 'facilities', 'apt_facility_mapping', 'apt_facility_summary', 'trade_history', 'rent_history', 'trade_apt_mapping', 'school_zones', 'apt_price_score', 'apt_safety_score']:
    try:
        cnt = conn.execute(f\"SELECT COUNT(*) FROM {t} WHERE pnu LIKE 'TRADE_28%' OR pnu LIKE '28%' OR pnu LIKE 'ICN_%'\").fetchone()[0]
    except:
        cnt = conn.execute(f\"SELECT COUNT(*) FROM {t} WHERE sgg_cd LIKE '28%'\").fetchone()[0]
    assert cnt == 0, f'{t} still has {cnt} Incheon rows!'
    print(f'  {t}: 0 Incheon rows ✅')
print('All clean')
"
```

---

### Task 3: Re-run integrate_incheon.py

**Files:**
- Run: `apt_eda/src/integrate_incheon.py` (no modifications needed)

This script has 4 steps:
1. Normalize facilities → `fm_incheon_facilities_normalized.csv`
2. Calculate distances (BallTree) → `fm_incheon_apt_facility_mapping.csv` + `fm_incheon_apt_facility_summary.csv`
3. School zones (GeoPandas spatial join) → `fm_incheon_school_zones.csv`
4. Update SQLite DB (apartments, facilities, mappings, summaries, trade/rent, school zones, price scores, safety scores)

- [ ] **Step 1: Delete stale intermediate files to force regeneration**

```bash
rm -f apt_eda/data/processed/fm_incheon_apt_facility_mapping.csv
rm -f apt_eda/data/processed/fm_incheon_apt_facility_summary.csv
rm -f apt_eda/data/processed/fm_incheon_school_zones.csv
# Keep fm_incheon_facilities_normalized.csv — facility data hasn't changed
```

- [ ] **Step 2: Ensure required packages are installed**

```bash
uv pip install scikit-learn geopandas shapely
```

- [ ] **Step 3: Run integrate_incheon.py**

```bash
.venv/bin/python apt_eda/src/integrate_incheon.py
```

Expected: ~30-60 minutes. Step 2 (BallTree distances) is the longest — ~12M rows for ~2,900 apartments × facilities within 5km. Step 4 updates the DB with all Incheon data.

- [ ] **Step 4: Verify DB was repopulated**

```bash
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('web/backend/apt_web.db')
print('Post-rebuild counts:')
for t in ['apartments', 'facilities', 'apt_facility_mapping', 'apt_facility_summary', 'trade_history', 'rent_history', 'trade_apt_mapping', 'school_zones']:
    total = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'  {t}: {total:,}')

# Verify no bad coordinates in DB
bad = conn.execute('''
    SELECT COUNT(*) FROM apartments
    WHERE sigungu_code LIKE '28%'
    AND lat IS NOT NULL
    AND (lng > 126.85 OR lng < 125.5 OR lat > 37.62 OR lat < 37.15)
''').fetchone()[0]
print(f'\nBad coordinates (Incheon apts outside bounds): {bad}')
assert bad == 0, f'{bad} apartments still have bad coordinates!'
print('✅ All Incheon coordinates valid')
"
```

---

### Task 4: Recalculate price and safety scores

**Files:**
- Run: portions of `apt_eda/src/integrate_incheon.py` step4 (already handles apt_price_score and apt_safety_score)

If `integrate_incheon.py` step4 already handles price/safety score calculation (check output), this task is already done. Otherwise:

- [ ] **Step 1: Verify price and safety scores exist for Incheon**

```bash
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('web/backend/apt_web.db')
price_cnt = conn.execute(\"SELECT COUNT(*) FROM apt_price_score WHERE pnu LIKE '28%' OR pnu LIKE 'TRADE_28%'\").fetchone()[0]
safety_cnt = conn.execute(\"SELECT COUNT(*) FROM apt_safety_score WHERE pnu LIKE '28%' OR pnu LIKE 'TRADE_28%'\").fetchone()[0]
apt_cnt = conn.execute(\"SELECT COUNT(*) FROM apartments WHERE sigungu_code LIKE '28%'\").fetchone()[0]
print(f'Incheon apartments: {apt_cnt}')
print(f'Price scores: {price_cnt}')
print(f'Safety scores: {safety_cnt}')
"
```

If counts are 0 or much lower than apartment count, run `improve_trade_mapping.py` which includes price score recalculation.

- [ ] **Step 2: Run improve_trade_mapping.py if needed**

```bash
.venv/bin/python apt_eda/src/improve_trade_mapping.py
```

This recalculates `apt_price_score` for all mapped apartments.

---

### Task 5: End-to-end verification

- [ ] **Step 1: Test chatbot analysis for a known Incheon apartment**

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "부평신일해피트리더루츠 분석해줘"}' | python3 -m json.tool | head -20
```

Verify: address field is populated (or at least shows "인천 부평구"), tool_calls includes `get_apartment_detail`, and response contains meaningful nudge scores.

- [ ] **Step 2: Verify coordinate accuracy for previously-bad apartments**

```bash
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('web/backend/apt_web.db')
# Check apartments that had bad coords before
test_apts = ['부평신일해피트리더루츠', '삼익', '부성', '송현주공솔빛마을(154)']
for name in test_apts:
    row = conn.execute('SELECT bld_nm, lat, lng, sigungu_code FROM apartments WHERE bld_nm LIKE ?', [f'%{name}%']).fetchone()
    if row:
        lat, lng = row[1], row[2]
        status = '✅' if (lat is None or (126.3 < lng < 126.85)) else '❌ BAD'
        print(f'  {row[0]:35s} ({lat}, {lng}) {status}')
    else:
        print(f'  {name}: not found')
"
```

- [ ] **Step 3: Summary statistics**

```bash
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('web/backend/apt_web.db')
total = conn.execute(\"SELECT COUNT(*) FROM apartments WHERE sigungu_code LIKE '28%'\").fetchone()[0]
has_coords = conn.execute(\"SELECT COUNT(*) FROM apartments WHERE sigungu_code LIKE '28%' AND lat IS NOT NULL\").fetchone()[0]
has_addr = conn.execute(\"SELECT COUNT(*) FROM apartments WHERE sigungu_code LIKE '28%' AND new_plat_plc IS NOT NULL\").fetchone()[0]
has_scores = conn.execute(\"SELECT COUNT(*) FROM apt_price_score WHERE pnu IN (SELECT pnu FROM apartments WHERE sigungu_code LIKE '28%')\").fetchone()[0]
print(f'인천 아파트 총: {total}')
print(f'  좌표 있음: {has_coords} ({has_coords/total*100:.1f}%)')
print(f'  주소 있음: {has_addr} ({has_addr/total*100:.1f}%)')
print(f'  가격점수: {has_scores} ({has_scores/total*100:.1f}%)')
"
```
