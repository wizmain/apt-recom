# 아파트 주변 시설 매핑 시스템 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 서울+경기 아파트 마스터 데이터에 주변 시설(12종) 매핑 정보를 구축한다.

**Architecture:** 5단계 순차 파이프라인. 아파트 좌표 확보 → 시설 데이터 수집 → 정규화 → BallTree 거리 계산 → 행정구역 통계. 각 단계는 독립 스크립트로 실행되며 CSV 파일로 연결된다.

**Tech Stack:** Python 3.12, pandas, scikit-learn (BallTree), pyproj, python-dotenv, requests

**Spec:** `docs/superpowers/specs/2026-03-20-apt-facility-mapping-design.md`

---

## Task 0: 환경 설정

**Files:**
- Create: `.env`

- [ ] **Step 1: 필요 패키지 설치**

```bash
cd /Users/wizmain/Documents/workspace/fcicb6-proj3
uv pip install scikit-learn pyproj python-dotenv --python .venv/bin/python
```

- [ ] **Step 2: .env 파일 생성**

```
VWORLD_API_KEY=28A43834-F3C3-3F49-A1DC-09E7FA0AFB39
KAKAO_API_KEY=54037323bb0a830a9e5c3b4e1bbf9abc
DATA_GO_KR_API_KEY=fdbb3cb0fcb85cd1b453e387630631cbf0e7201ee9b3592a540fc752a23523ad
```

DATA_GO_KR_API_KEY는 기존 수집 스크립트(`collect_park.py`)에서 사용 중인 키를 그대로 사용.

- [ ] **Step 3: 설치 확인**

```bash
.venv/bin/python -c "import sklearn, pyproj, dotenv; print('OK')"
```
Expected: `OK`

---

## Task 1: 아파트 좌표 확보 (step1_geocode_apt.py)

**Files:**
- Create: `apt_eda/src/step1_geocode_apt.py`

**입력:** `apt_eda/data/processed_gemini/apt_integrated_master_v1.csv` (7,917건)
**출력:** `apt_eda/data/processed/fm_apt_master_with_coords.csv`

- [ ] **Step 1: 스크립트 작성**

```python
"""
아파트 마스터 데이터에 위경도 좌표를 추가한다.
- 1차: Vworld 지오코딩 API (도로명주소 → 위경도)
- 2차: Vworld 지번주소 fallback
- 3차: Kakao 지오코딩 API fallback
- 체크포인트: 100건마다 중간 저장, 재실행 시 좌표 있는 행 건너뜀
"""

import os
import time
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

VWORLD_API_KEY = os.getenv("VWORLD_API_KEY")
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")

INPUT_PATH = Path("apt_eda/data/processed_gemini/apt_integrated_master_v1.csv")
OUTPUT_PATH = Path("apt_eda/data/processed/fm_apt_master_with_coords.csv")


def geocode_vworld(address):
    """Vworld 지오코딩 API로 주소 → (lat, lng) 변환"""
    url = "https://api.vworld.kr/req/address"
    params = {
        "service": "address",
        "request": "getcoord",
        "version": "2.0",
        "crs": "epsg:4326",
        "address": address,
        "refine": "true",
        "simple": "false",
        "format": "json",
        "type": "road",
        "key": VWORLD_API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("response", {}).get("status") == "OK":
            point = data["response"]["result"]["point"]
            return float(point["y"]), float(point["x"])
    except Exception:
        pass
    return None, None


def geocode_vworld_jibun(address):
    """Vworld 지오코딩 API (지번주소)"""
    url = "https://api.vworld.kr/req/address"
    params = {
        "service": "address",
        "request": "getcoord",
        "version": "2.0",
        "crs": "epsg:4326",
        "address": address,
        "refine": "true",
        "simple": "false",
        "format": "json",
        "type": "parcel",
        "key": VWORLD_API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("response", {}).get("status") == "OK":
            point = data["response"]["result"]["point"]
            return float(point["y"]), float(point["x"])
    except Exception:
        pass
    return None, None


def geocode_kakao(address):
    """Kakao 지오코딩 API로 주소 → (lat, lng) 변환"""
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": address}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        data = r.json()
        if data.get("documents"):
            doc = data["documents"][0]
            return float(doc["y"]), float(doc["x"])
    except Exception:
        pass
    return None, None


def main():
    print("=" * 60)
    print("아파트 마스터 좌표 확보")
    print("=" * 60)

    df = pd.read_csv(INPUT_PATH, dtype={"PNU": str, "bjdCode": str})

    # 체크포인트: 기존 출력 파일이 있으면 이미 처리된 좌표 로드
    if OUTPUT_PATH.exists():
        existing = pd.read_csv(OUTPUT_PATH, dtype={"PNU": str, "bjdCode": str})
        coords_map = {}
        for _, row in existing.iterrows():
            if pd.notna(row.get("lat")) and pd.notna(row.get("lng")):
                coords_map[row["PNU"]] = (row["lat"], row["lng"])
        print(f"기존 좌표 로드: {len(coords_map)}건")
    else:
        coords_map = {}

    if "lat" not in df.columns:
        df["lat"] = None
        df["lng"] = None

    # 기존 좌표 적용
    for idx, row in df.iterrows():
        if row["PNU"] in coords_map:
            df.at[idx, "lat"] = coords_map[row["PNU"]][0]
            df.at[idx, "lng"] = coords_map[row["PNU"]][1]

    total = len(df)
    need_geocode = df[df["lat"].isna()].index.tolist()
    print(f"총 {total}건 중 좌표 필요: {len(need_geocode)}건")

    success = 0
    fail = 0

    for i, idx in enumerate(need_geocode):
        row = df.loc[idx]

        # 1차: Vworld 도로명주소
        addr = row.get("newPlatPlc", "")
        if pd.notna(addr) and str(addr).strip():
            # 괄호 안 동명 제거 (예: "서울시 종로구 자하문로33길 43 (청운동)" → "서울시 종로구 자하문로33길 43")
            clean_addr = str(addr).split("(")[0].strip()
            lat, lng = geocode_vworld(clean_addr)
            if lat:
                df.at[idx, "lat"] = lat
                df.at[idx, "lng"] = lng
                success += 1
                time.sleep(0.1)
                if (i + 1) % 100 == 0:
                    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
                    print(f"  [{i+1}/{len(need_geocode)}] 성공: {success}, 실패: {fail}")
                continue

        # 2차: Vworld 지번주소
        addr_jibun = row.get("platPlc", "")
        if pd.notna(addr_jibun) and str(addr_jibun).strip():
            clean_jibun = str(addr_jibun).replace("번지", "").strip()
            lat, lng = geocode_vworld_jibun(clean_jibun)
            if lat:
                df.at[idx, "lat"] = lat
                df.at[idx, "lng"] = lng
                success += 1
                time.sleep(0.1)
                if (i + 1) % 100 == 0:
                    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
                    print(f"  [{i+1}/{len(need_geocode)}] 성공: {success}, 실패: {fail}")
                continue

        # 3차: Kakao
        addr_for_kakao = str(addr).strip() if pd.notna(addr) and str(addr).strip() else str(addr_jibun).strip()
        if addr_for_kakao:
            lat, lng = geocode_kakao(addr_for_kakao)
            if lat:
                df.at[idx, "lat"] = lat
                df.at[idx, "lng"] = lng
                success += 1
                time.sleep(0.1)
                if (i + 1) % 100 == 0:
                    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
                    print(f"  [{i+1}/{len(need_geocode)}] 성공: {success}, 실패: {fail}")
                continue

        fail += 1
        time.sleep(0.1)

        if (i + 1) % 100 == 0:
            df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
            print(f"  [{i+1}/{len(need_geocode)}] 성공: {success}, 실패: {fail}")

    # 최종 저장
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    geocoded = df["lat"].notna().sum()
    print(f"\n=== 결과 ===")
    print(f"총: {total}건")
    print(f"좌표 확보: {geocoded}건 ({geocoded/total*100:.1f}%)")
    print(f"좌표 미확보: {total - geocoded}건")
    print(f"저장: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행**

```bash
cd /Users/wizmain/Documents/workspace/fcicb6-proj3
.venv/bin/python apt_eda/src/step1_geocode_apt.py
```

약 7,917건 × 0.1초 = 약 13분 소요 예상. 체크포인트가 있으므로 중단 시 재실행 가능.

- [ ] **Step 3: 결과 검증**

```bash
.venv/bin/python -c "
import pandas as pd
df = pd.read_csv('apt_eda/data/processed/fm_apt_master_with_coords.csv')
total = len(df)
has_coords = df['lat'].notna().sum()
print(f'총: {total}, 좌표있음: {has_coords} ({has_coords/total*100:.1f}%)')
print(f'위도 범위: {df[\"lat\"].min():.4f} ~ {df[\"lat\"].max():.4f}')
print(f'경도 범위: {df[\"lng\"].min():.4f} ~ {df[\"lng\"].max():.4f}')
"
```

Expected: 좌표 확보율 90% 이상, 위도 37~38, 경도 126~128 범위

---

## Task 2: 추가 시설 데이터 수집 (step2_collect_facilities.py)

**Files:**
- Create: `apt_eda/src/step2_collect_facilities.py`

**출력:** `apt_eda/data/raw/` 아래 9개 파일

기존 수집 패턴(`collect_park.py`, `collect_school_location.py`)을 따른다: 공공데이터포털 API → JSON 파싱 → 서울+경기 필터 → CSV 저장.

- [ ] **Step 1: 수집 대상 API 조사**

각 시설 유형별 공공데이터포털 API/파일 데이터 URL을 조사. 아래는 주요 데이터셋:

| 시설 | 공공데이터포털 API | 비고 |
|------|------------------|------|
| 지하철역 | `tn_pubr_public_subway_stn_info_api` | 전국도시철도역사정보표준데이터 |
| 버스정류장 | `tn_pubr_public_bus_stn_info_api` | 전국버스정류장위치정보표준데이터 |
| 대형마트/백화점 | `tn_pubr_public_lgscl_strsp_api` | 전국대규모점포표준데이터 |
| 어린이집 | `tn_pubr_public_day_care_cen_api` | 전국어린이집표준데이터 |
| 유치원 | `tn_pubr_public_kndrgrt_api` | 전국유치원표준데이터 |
| 경찰서 | `tn_pubr_public_police_sttus_api` | 전국경찰관서현황표준데이터 |
| 소방서 | `tn_pubr_public_fire_sttus_api` | 전국소방서현황표준데이터 |
| 도서관 | `tn_pubr_public_lbrry_api` | 전국도서관표준데이터 |
| 편의점/은행/약국 | 소상공인 상가업소 정보 (파일 데이터) | 업종코드 필터 |

실제 API URL이 존재하지 않을 수 있으므로, 각 API를 먼저 테스트하고 실패 시 파일 데이터로 대체.

- [ ] **Step 2: 스크립트 작성**

스크립트 내에 시설 유형별 수집 함수를 정의. 공통 패턴:

```python
"""
추가 시설 데이터 수집 (7종 → 9개 파일)
- 공공데이터포털 API 기반 수집
- 서울+경기 필터링
"""

import os
import time
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

RAW_DIR = Path("apt_eda/data/raw")
RAW_DIR.mkdir(exist_ok=True)

SERVICE_KEY = os.getenv("DATA_GO_KR_API_KEY")
BASE_API = "http://api.data.go.kr/openapi"
NUM_OF_ROWS = 1000


def fetch_all_pages(api_name, extra_params=None):
    """공공데이터포털 표준 API에서 전체 데이터를 수집한다."""
    url = f"{BASE_API}/{api_name}"
    all_items = []
    page = 1
    total_pages = 1  # 첫 페이지 응답 전 기본값

    while True:
        params = {
            "serviceKey": SERVICE_KEY,
            "pageNo": str(page),
            "numOfRows": str(NUM_OF_ROWS),
            "type": "json",
        }
        if extra_params:
            params.update(extra_params)

        items = []
        total = 0
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, timeout=30)
                r.raise_for_status()
                data = r.json()
                body = data.get("response", {}).get("body", {})
                items = body.get("items", [])
                total = int(body.get("totalCount", 0))

                if isinstance(items, dict):
                    items = [items]

                all_items.extend(items)

                if page == 1:
                    total_pages = (total + NUM_OF_ROWS - 1) // NUM_OF_ROWS
                    print(f"  총 {total:,}건, {total_pages}페이지")

                if page % 10 == 0:
                    print(f"  [{page}/{total_pages}] 누적: {len(all_items):,}건")

                break
            except Exception as e:
                print(f"  page {page} attempt {attempt+1} 실패: {e}")
                time.sleep(1.0 * (attempt + 1))

        if not items or len(all_items) >= total:
            break

        page += 1
        time.sleep(0.2)

    return pd.DataFrame(all_items)


def filter_seoul_gyeonggi(df, addr_cols=None):
    """서울/경기 데이터만 필터링한다."""
    if addr_cols is None:
        addr_cols = ["rdnmadr", "lnmadr"]

    def is_sg(row):
        for col in addr_cols:
            val = str(row.get(col, ""))
            if val.startswith("서울") or val.startswith("경기"):
                return True
        return False

    return df[df.apply(is_sg, axis=1)].copy()


def collect_subway():
    """지하철역"""
    print("\n[1/9] 지하철역 수집...")
    df = fetch_all_pages("tn_pubr_public_subway_stn_info_api")
    if df.empty:
        print("  수집 실패 — 파일 데이터로 대체 필요")
        return
    df_f = filter_seoul_gyeonggi(df)
    df_f.to_csv(RAW_DIR / "subway_station_seoul_gyeonggi.csv", index=False, encoding="utf-8-sig")
    print(f"  저장: {len(df_f):,}건")


def collect_bus_stop():
    """버스정류장"""
    print("\n[2/9] 버스정류장 수집...")
    df = fetch_all_pages("tn_pubr_public_bus_stn_info_api")
    if df.empty:
        print("  수집 실패 — 파일 데이터로 대체 필요")
        return
    df_f = filter_seoul_gyeonggi(df)
    df_f.to_csv(RAW_DIR / "bus_stop_seoul_gyeonggi.csv", index=False, encoding="utf-8-sig")
    print(f"  저장: {len(df_f):,}건")


def collect_large_store():
    """대형마트/백화점"""
    print("\n[3/9] 대형마트/백화점 수집...")
    df = fetch_all_pages("tn_pubr_public_lgscl_strsp_api")
    if df.empty:
        print("  수집 실패 — 파일 데이터로 대체 필요")
        return
    df_f = filter_seoul_gyeonggi(df)
    df_f.to_csv(RAW_DIR / "large_store_seoul_gyeonggi.csv", index=False, encoding="utf-8-sig")
    print(f"  저장: {len(df_f):,}건")


def collect_childcare():
    """어린이집"""
    print("\n[4/9] 어린이집 수집...")
    df = fetch_all_pages("tn_pubr_public_day_care_cen_api")
    if df.empty:
        print("  수집 실패 — 파일 데이터로 대체 필요")
        return
    df_f = filter_seoul_gyeonggi(df)
    df_f.to_csv(RAW_DIR / "childcare_seoul_gyeonggi.csv", index=False, encoding="utf-8-sig")
    print(f"  저장: {len(df_f):,}건")


def collect_kindergarten():
    """유치원"""
    print("\n[5/9] 유치원 수집...")
    df = fetch_all_pages("tn_pubr_public_kndrgrt_api")
    if df.empty:
        print("  수집 실패 — 파일 데이터로 대체 필요")
        return
    df_f = filter_seoul_gyeonggi(df)
    df_f.to_csv(RAW_DIR / "kindergarten_seoul_gyeonggi.csv", index=False, encoding="utf-8-sig")
    print(f"  저장: {len(df_f):,}건")


def collect_safety():
    """경찰서 + 소방서"""
    print("\n[6/9] 경찰서 수집...")
    df_police = fetch_all_pages("tn_pubr_public_police_sttus_api")
    print("\n[7/9] 소방서 수집...")
    df_fire = fetch_all_pages("tn_pubr_public_fire_sttus_api")

    frames = []
    if not df_police.empty:
        df_police["safety_type"] = "police"
        frames.append(df_police)
    if not df_fire.empty:
        df_fire["safety_type"] = "fire_station"
        frames.append(df_fire)

    if not frames:
        print("  수집 실패 — 파일 데이터로 대체 필요")
        return

    df = pd.concat(frames, ignore_index=True)
    df_f = filter_seoul_gyeonggi(df)
    df_f.to_csv(RAW_DIR / "safety_facility_seoul_gyeonggi.csv", index=False, encoding="utf-8-sig")
    print(f"  저장: {len(df_f):,}건")


def collect_library_culture():
    """도서관 + 문화시설"""
    print("\n[8/9] 도서관 수집...")
    df = fetch_all_pages("tn_pubr_public_lbrry_api")
    if df.empty:
        print("  수집 실패 — 파일 데이터로 대체 필요")
        return
    df_f = filter_seoul_gyeonggi(df)
    df_f.to_csv(RAW_DIR / "library_culture_seoul_gyeonggi.csv", index=False, encoding="utf-8-sig")
    print(f"  저장: {len(df_f):,}건")


def collect_living_convenience():
    """편의점/은행/약국 — 소상공인 상가업소 정보 파일 데이터"""
    print("\n[9/9] 편의점/은행/약국 수집...")

    # 소상공인 상가업소 정보 CSV 파일 다운로드
    # data.go.kr/data/15083033 (소상공인시장진흥공단_상가(상권)정보)
    # 대용량 파일이므로 curl로 다운로드 후 업종코드로 필터링
    import subprocess

    csv_url = "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000002873498&fileDetailSn=1"
    temp_path = RAW_DIR / "temp_store_info.csv"

    if not temp_path.exists():
        print("  상가업소 파일 다운로드 중...")
        subprocess.run([
            "curl", "-L", "-o", str(temp_path), csv_url,
            "-H", "User-Agent: Mozilla/5.0",
            "-H", "Referer: https://www.data.go.kr/data/15083033/fileData.do",
            "--max-time", "120"
        ], check=True)

    print("  파일 로딩 및 필터링 중...")
    df = pd.read_csv(temp_path, low_memory=False)

    # 서울+경기 필터
    df = df[df["시도명"].isin(["서울특별시", "경기도"])].copy()

    # 업종별 필터링 및 저장
    filters = {
        "convenience_store": df["상권업종소분류명"].str.contains("편의점", na=False),
        "bank": df["상권업종소분류명"].str.contains("은행", na=False),
        "pharmacy": df["상권업종소분류명"].str.contains("약국", na=False),
    }

    for subtype, mask in filters.items():
        subset = df[mask].copy()
        out_path = RAW_DIR / f"{subtype}_seoul_gyeonggi.csv"
        subset.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"  {subtype}: {len(subset):,}건 → {out_path.name}")

    # 임시 파일 정리
    if temp_path.exists():
        temp_path.unlink()
        print("  임시 파일 삭제 완료")


def main():
    print("=" * 60)
    print("추가 시설 데이터 수집 (7종)")
    print("=" * 60)

    collect_subway()
    collect_bus_stop()
    collect_large_store()
    collect_childcare()
    collect_kindergarten()
    collect_safety()
    collect_library_culture()
    collect_living_convenience()

    print("\n=== 수집 완료 ===")
    for f in sorted(RAW_DIR.glob("*.csv")):
        if any(k in f.name for k in ["subway", "bus_stop", "large_store", "childcare",
                                       "kindergarten", "safety", "library", "convenience",
                                       "bank", "pharmacy"]):
            df = pd.read_csv(f)
            print(f"  {f.name}: {len(df):,}건")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 실행**

```bash
.venv/bin/python apt_eda/src/step2_collect_facilities.py
```

API 실패 시 각 시설 유형별로 공공데이터포털에서 파일 데이터를 직접 다운로드하여 `raw/` 아래 저장. 실패한 API는 로그로 확인 후 개별 대응.

- [ ] **Step 4: 편의점/은행/약국 별도 수집**

소상공인 상가업소 데이터는 대용량이므로 파일 데이터 다운로드 방식으로 별도 처리:
1. data.go.kr에서 소상공인 상가업소 정보 파일 다운로드
2. 업종코드로 편의점/은행/약국 필터링
3. 서울+경기 필터링
4. 3개 파일로 분리 저장

```bash
# 수집 결과 확인
ls -la apt_eda/data/raw/*seoul_gyeonggi*.csv
```

---

## Task 3: 시설 좌표 정규화 (step3_normalize_facilities.py)

**Files:**
- Create: `apt_eda/src/step3_normalize_facilities.py`

**입력:** `apt_eda/data/raw/` 아래 모든 시설 CSV (12종)
**출력:** `apt_eda/data/processed/fm_all_facilities_normalized.csv`

- [ ] **Step 1: 스크립트 작성**

```python
"""
모든 시설 데이터(12종)를 통일된 스키마로 정규화한다.
- 좌표계 통일 (EPSG:5186 → WGS84 변환)
- 좌표 없는 시설 지오코딩
- 서울+경기 필터링
- facility_id 부여
"""

import os
import time
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from pyproj import Transformer

load_dotenv()

VWORLD_API_KEY = os.getenv("VWORLD_API_KEY")
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")

RAW_DIR = Path("apt_eda/data/raw")
OUTPUT_PATH = Path("apt_eda/data/processed/fm_all_facilities_normalized.csv")

# EPSG:5186 (Korean TM) → EPSG:4326 (WGS84) 변환기
transformer = Transformer.from_crs("EPSG:5186", "EPSG:4326", always_xy=True)

# 서울+경기 위경도 범위 (대략적 유효성 검증용)
LAT_MIN, LAT_MAX = 36.8, 38.3
LNG_MIN, LNG_MAX = 126.0, 128.0


def geocode_kakao(address):
    """Kakao 지오코딩"""
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    try:
        r = requests.get(url, headers=headers, params={"query": address}, timeout=10)
        docs = r.json().get("documents", [])
        if docs:
            return float(docs[0]["y"]), float(docs[0]["x"])
    except Exception:
        pass
    return None, None


def convert_epsg5186_to_wgs84(x, y):
    """EPSG:5186 좌표를 WGS84 (lat, lng)로 변환"""
    try:
        lng, lat = transformer.transform(float(x), float(y))
        return lat, lng
    except Exception:
        return None, None


def extract_sigungu_code(bjd_code):
    """법정동코드에서 시군구코드 추출"""
    if pd.notna(bjd_code) and len(str(bjd_code)) >= 5:
        return str(bjd_code)[:5]
    return None


def normalize_hospital():
    """병원 정규화"""
    path = RAW_DIR / "hospital_info_seoul_gyeonggi.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    records = []
    for i, row in df.iterrows():
        lat = pd.to_numeric(row.get("YPos"), errors="coerce")
        lng = pd.to_numeric(row.get("XPos"), errors="coerce")
        addr = str(row.get("addr", ""))
        sggu = str(row.get("sgguCd", ""))[:5] if pd.notna(row.get("sgguCd")) else None
        records.append({
            "facility_type": "medical",
            "facility_subtype": "hospital",
            "name": row.get("yadmNm", ""),
            "lat": lat if pd.notna(lat) else None,
            "lng": lng if pd.notna(lng) else None,
            "address": addr,
            "sigungu_code": sggu,
        })
    return pd.DataFrame(records)


def normalize_animal_hospital():
    """동물병원 정규화 (EPSG:5186 → WGS84 변환)"""
    path = RAW_DIR / "animal_hospital_seoul_gyeonggi.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    records = []
    for i, row in df.iterrows():
        x = row.get("CRD_INFO_X")
        y = row.get("CRD_INFO_Y")
        lat, lng = None, None
        if pd.notna(x) and pd.notna(y) and float(x) > 100:
            lat, lng = convert_epsg5186_to_wgs84(x, y)
        addr = str(row.get("ROAD_NM_ADDR") or row.get("LOTNO_ADDR") or "")
        records.append({
            "facility_type": "medical",
            "facility_subtype": "animal_hospital",
            "name": row.get("BPLC_NM", ""),
            "lat": lat,
            "lng": lng,
            "address": addr,
            "sigungu_code": None,
        })
    return pd.DataFrame(records)


def normalize_school():
    """학교 정규화"""
    path = RAW_DIR / "school_location_seoul_gyeonggi.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    records = []
    for i, row in df.iterrows():
        records.append({
            "facility_type": "education",
            "facility_subtype": "school",
            "name": row.get("schoolNm", ""),
            "lat": pd.to_numeric(row.get("latitude"), errors="coerce"),
            "lng": pd.to_numeric(row.get("longitude"), errors="coerce"),
            "address": str(row.get("rdnmadr") or row.get("lnmadr") or ""),
            "sigungu_code": None,
        })
    return pd.DataFrame(records)


def normalize_park():
    """공원 정규화"""
    path = RAW_DIR / "city_park_seoul_gyeonggi.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    records = []
    for i, row in df.iterrows():
        records.append({
            "facility_type": "culture",
            "facility_subtype": "park",
            "name": row.get("parkNm", ""),
            "lat": pd.to_numeric(row.get("latitude"), errors="coerce"),
            "lng": pd.to_numeric(row.get("longitude"), errors="coerce"),
            "address": str(row.get("rdnmadr") or row.get("lnmadr") or ""),
            "sigungu_code": None,
        })
    return pd.DataFrame(records)


def normalize_pet_facility():
    """반려동물 문화시설 정규화 (전국 → 서울+경기 필터)"""
    # 프로젝트 루트의 파일 참조 (스크립트 위치 기준 상대 경로)
    path = Path(__file__).parent.parent.parent / "pet_friendly_cultural_facilities.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    # 서울+경기 필터링
    df = df[df["시도 명칭"].isin(["서울특별시", "경기도"])].copy()
    records = []
    for i, row in df.iterrows():
        records.append({
            "facility_type": "pet",
            "facility_subtype": "pet_facility",
            "name": row.get("시설명", ""),
            "lat": pd.to_numeric(row.get("위도"), errors="coerce"),
            "lng": pd.to_numeric(row.get("경도"), errors="coerce"),
            "address": str(row.get("도로명주소") or row.get("지번주소") or ""),
            "sigungu_code": None,
        })
    return pd.DataFrame(records)


def normalize_generic(filename, facility_type, facility_subtype,
                      name_col, lat_col="latitude", lng_col="longitude",
                      addr_cols=None):
    """신규 수집 시설 범용 정규화"""
    path = RAW_DIR / filename
    if not path.exists():
        print(f"  파일 없음: {filename}")
        return pd.DataFrame()
    df = pd.read_csv(path)
    if addr_cols is None:
        addr_cols = ["rdnmadr", "lnmadr"]
    records = []
    for i, row in df.iterrows():
        addr = ""
        for col in addr_cols:
            v = row.get(col, "")
            if pd.notna(v) and str(v).strip():
                addr = str(v)
                break
        records.append({
            "facility_type": facility_type,
            "facility_subtype": facility_subtype,
            "name": row.get(name_col, ""),
            "lat": pd.to_numeric(row.get(lat_col), errors="coerce"),
            "lng": pd.to_numeric(row.get(lng_col), errors="coerce"),
            "address": addr,
            "sigungu_code": None,
        })
    return pd.DataFrame(records)


def geocode_missing(df):
    """좌표 없는 시설을 Kakao API로 지오코딩 (100건마다 체크포인트 저장)"""
    missing = df[df["lat"].isna() & df["address"].notna() & (df["address"] != "")].index
    print(f"좌표 미확보 시설 지오코딩: {len(missing)}건")

    success = 0
    for i, idx in enumerate(missing):
        addr = df.at[idx, "address"]
        lat, lng = geocode_kakao(str(addr))
        if lat:
            df.at[idx, "lat"] = lat
            df.at[idx, "lng"] = lng
            success += 1
        time.sleep(0.1)
        if (i + 1) % 100 == 0:
            # 체크포인트: 중간 저장
            df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
            print(f"  [{i+1}/{len(missing)}] 성공: {success} (체크포인트 저장)")

    print(f"  지오코딩 완료: {success}/{len(missing)}")
    return df


def main():
    print("=" * 60)
    print("시설 좌표 정규화")
    print("=" * 60)

    frames = []

    # 기존 보유 5종
    print("\n--- 기존 데이터 정규화 ---")

    print("병원...")
    frames.append(normalize_hospital())

    print("동물병원 (CRS 변환)...")
    frames.append(normalize_animal_hospital())

    print("학교...")
    frames.append(normalize_school())

    print("공원...")
    frames.append(normalize_park())

    print("반려동물 문화시설 (서울+경기 필터)...")
    frames.append(normalize_pet_facility())

    # 신규 수집 7종 (API 컬럼명은 실제 수집 결과에 따라 조정 필요)
    print("\n--- 신규 데이터 정규화 ---")

    new_sources = [
        ("subway_station_seoul_gyeonggi.csv", "transport", "subway", "stnNm"),
        ("bus_stop_seoul_gyeonggi.csv", "transport", "bus", "busStnNm"),
        ("large_store_seoul_gyeonggi.csv", "commerce", "mart", "bizplcNm"),
        ("childcare_seoul_gyeonggi.csv", "education", "childcare", "creName"),
        ("kindergarten_seoul_gyeonggi.csv", "education", "kindergarten", "kindNm"),
        ("library_culture_seoul_gyeonggi.csv", "culture", "library", "lbrryNm"),
    ]

    for filename, ftype, fsubtype, name_col in new_sources:
        print(f"{fsubtype}...")
        frames.append(normalize_generic(filename, ftype, fsubtype, name_col))

    # 안전시설 (경찰서+소방서 합본)
    safety_path = RAW_DIR / "safety_facility_seoul_gyeonggi.csv"
    if safety_path.exists():
        print("경찰서/소방서...")
        sf = pd.read_csv(safety_path)
        records = []
        for i, row in sf.iterrows():
            subtype = row.get("safety_type", "police")
            name_col_cand = ["plcNm", "fireNm", "instNm", "rdnmadr"]
            name = ""
            for nc in name_col_cand:
                if nc in row and pd.notna(row[nc]):
                    name = row[nc]
                    break
            addr = str(row.get("rdnmadr") or row.get("lnmadr") or "")
            records.append({
                "facility_type": "safety",
                "facility_subtype": subtype,
                "name": name,
                "lat": pd.to_numeric(row.get("latitude"), errors="coerce"),
                "lng": pd.to_numeric(row.get("longitude"), errors="coerce"),
                "address": addr,
                "sigungu_code": None,
            })
        frames.append(pd.DataFrame(records))

    # 편의점/은행/약국
    for filename, subtype in [
        ("convenience_store_seoul_gyeonggi.csv", "convenience_store"),
        ("bank_seoul_gyeonggi.csv", "bank"),
        ("pharmacy_seoul_gyeonggi.csv", "pharmacy"),
    ]:
        path = RAW_DIR / filename
        if path.exists():
            print(f"{subtype}...")
            frames.append(normalize_generic(filename, "living", subtype, "bizesNm"))

    # 합치기
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    print(f"\n합계: {len(df):,}건")

    # 위경도 범위 검증 (서울+경기 외 제거)
    valid_mask = (
        (df["lat"] >= LAT_MIN) & (df["lat"] <= LAT_MAX) &
        (df["lng"] >= LNG_MIN) & (df["lng"] <= LNG_MAX)
    ) | df["lat"].isna()
    removed = (~valid_mask).sum()
    if removed > 0:
        print(f"좌표 범위 외 제거: {removed}건")
        df = df[valid_mask].copy()

    # 좌표 없는 시설 지오코딩
    df = geocode_missing(df)

    # facility_id 부여
    code_map = {
        ("transport", "subway"): "SUB",
        ("transport", "bus"): "BUS",
        ("commerce", "mart"): "MRT",
        ("commerce", "department_store"): "DPT",
        ("education", "school"): "SCH",
        ("education", "kindergarten"): "KDG",
        ("education", "childcare"): "CDC",
        ("safety", "police"): "POL",
        ("safety", "fire_station"): "FIR",
        ("culture", "library"): "LIB",
        ("culture", "culture_center"): "CUL",
        ("culture", "park"): "PRK",
        ("living", "convenience_store"): "CVS",
        ("living", "bank"): "BNK",
        ("living", "pharmacy"): "PHR",
        ("medical", "hospital"): "HSP",
        ("medical", "animal_hospital"): "AHP",
        ("pet", "pet_facility"): "PET",
    }

    facility_ids = []
    counters = {}
    for _, row in df.iterrows():
        key = (row["facility_type"], row["facility_subtype"])
        code = code_map.get(key, "UNK")
        counters[code] = counters.get(code, 0) + 1
        facility_ids.append(f"{code}_{counters[code]:06d}")
    df.insert(0, "facility_id", facility_ids)

    # bjd_code는 현재 비어있으므로 빈값으로 유지
    if "bjd_code" not in df.columns:
        df["bjd_code"] = None

    # 컬럼 순서 정리
    cols = ["facility_id", "facility_type", "facility_subtype", "name",
            "lat", "lng", "address", "bjd_code", "sigungu_code"]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]

    # 좌표 없는 행 제거 (거리 계산 불가)
    before = len(df)
    df = df.dropna(subset=["lat", "lng"])
    print(f"좌표 없는 행 제거: {before - len(df)}건")

    # 저장
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n=== 결과 ===")
    print(f"총 시설: {len(df):,}건")
    print(f"\n유형별 분포:")
    print(df.groupby(["facility_type", "facility_subtype"]).size().to_string())
    print(f"\n저장: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행**

```bash
.venv/bin/python apt_eda/src/step3_normalize_facilities.py
```

- [ ] **Step 3: 결과 검증**

```bash
.venv/bin/python -c "
import pandas as pd
df = pd.read_csv('apt_eda/data/processed/fm_all_facilities_normalized.csv')
print(f'총: {len(df):,}건')
print(df.groupby(['facility_type','facility_subtype']).size())
print(f'위도 범위: {df[\"lat\"].min():.4f} ~ {df[\"lat\"].max():.4f}')
print(f'경도 범위: {df[\"lng\"].min():.4f} ~ {df[\"lng\"].max():.4f}')
"
```

---

## Task 4: 거리 계산 & 매핑 (step4_calc_distance.py)

**Files:**
- Create: `apt_eda/src/step4_calc_distance.py`

**입력:**
- `apt_eda/data/processed/fm_apt_master_with_coords.csv`
- `apt_eda/data/processed/fm_all_facilities_normalized.csv`

**출력:** `apt_eda/data/processed/fm_apt_facility_mapping.csv`

- [ ] **Step 1: 스크립트 작성**

```python
"""
아파트별 5km 이내 시설을 BallTree로 검색하고 거리를 계산한다.
- scikit-learn BallTree (haversine metric)
- 지구 반경 6371km 기준
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.neighbors import BallTree

APT_PATH = Path("apt_eda/data/processed/fm_apt_master_with_coords.csv")
FAC_PATH = Path("apt_eda/data/processed/fm_all_facilities_normalized.csv")
OUTPUT_PATH = Path("apt_eda/data/processed/fm_apt_facility_mapping.csv")

RADIUS_KM = 5.0
EARTH_RADIUS_KM = 6371.0


def main():
    print("=" * 60)
    print("거리 계산 & 매핑")
    print("=" * 60)

    # 데이터 로드
    apt_df = pd.read_csv(APT_PATH, dtype={"PNU": str, "bjdCode": str})
    fac_df = pd.read_csv(FAC_PATH)

    # 좌표 있는 아파트만
    apt_df = apt_df.dropna(subset=["lat", "lng"]).reset_index(drop=True)
    print(f"아파트: {len(apt_df):,}건 (좌표 있는 것만)")
    print(f"시설: {len(fac_df):,}건")

    # BallTree 구축 (시설 좌표, radian 변환)
    fac_coords = np.radians(fac_df[["lat", "lng"]].values)
    tree = BallTree(fac_coords, metric="haversine")

    # 아파트별 5km 이내 시설 검색
    apt_coords = np.radians(apt_df[["lat", "lng"]].values)
    radius_rad = RADIUS_KM / EARTH_RADIUS_KM

    print(f"BallTree 쿼리 시작 (반경 {RADIUS_KM}km)...")

    all_rows = []
    batch_size = 500

    for start in range(0, len(apt_df), batch_size):
        end = min(start + batch_size, len(apt_df))
        batch_coords = apt_coords[start:end]

        indices, distances = tree.query_radius(
            batch_coords, r=radius_rad, return_distance=True
        )

        for i, (idx_list, dist_list) in enumerate(zip(indices, distances)):
            apt_idx = start + i
            apt_row = apt_df.iloc[apt_idx]

            for fac_idx, dist_rad in zip(idx_list, dist_list):
                fac_row = fac_df.iloc[fac_idx]
                distance_m = dist_rad * EARTH_RADIUS_KM * 1000

                all_rows.append({
                    "PNU": apt_row["PNU"],
                    "bldNm": apt_row["bldNm"],
                    "facility_id": fac_row["facility_id"],
                    "facility_type": fac_row["facility_type"],
                    "facility_subtype": fac_row["facility_subtype"],
                    "facility_name": fac_row["name"],
                    "facility_lat": fac_row["lat"],
                    "facility_lng": fac_row["lng"],
                    "distance_m": round(distance_m, 1),
                })

        if (end) % 1000 == 0 or end == len(apt_df):
            print(f"  [{end}/{len(apt_df)}] 매핑 건수: {len(all_rows):,}")

    # 결과 저장
    result_df = pd.DataFrame(all_rows)
    result_df = result_df.sort_values(["PNU", "facility_type", "distance_m"])
    result_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"\n=== 결과 ===")
    print(f"총 매핑: {len(result_df):,}건")
    print(f"아파트 수: {result_df['PNU'].nunique():,}")
    print(f"\n유형별 매핑 수:")
    print(result_df.groupby("facility_type").size().to_string())
    print(f"\n저장: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행**

```bash
.venv/bin/python apt_eda/src/step4_calc_distance.py
```

대량 데이터이므로 메모리 사용량 주의. 약 7,000 아파트 × 수만 시설 → 수백만~수천만 매핑 예상.

- [ ] **Step 3: 결과 검증**

```bash
.venv/bin/python -c "
import pandas as pd
df = pd.read_csv('apt_eda/data/processed/fm_apt_facility_mapping.csv', nrows=100000)
print(f'샘플 100K rows')
print(f'거리 범위: {df[\"distance_m\"].min():.0f}m ~ {df[\"distance_m\"].max():.0f}m')
print(f'아파트 수: {df[\"PNU\"].nunique()}')
print(df.groupby('facility_type').size())
"
```

---

## Task 5: 행정구역 통계 (step5_calc_stats.py)

**Files:**
- Create: `apt_eda/src/step5_calc_stats.py`

**입력:**
- `apt_eda/data/processed/fm_apt_facility_mapping.csv`
- `apt_eda/data/processed/fm_apt_master_with_coords.csv`
- `apt_eda/data/processed/fm_all_facilities_normalized.csv`
- `apt_eda/data/raw/census_population_2025.csv`

**출력:**
- `apt_eda/data/processed/fm_stats_by_bjd.csv`
- `apt_eda/data/processed/fm_stats_by_sigungu.csv`

- [ ] **Step 1: 스크립트 작성**

```python
"""
행정구역 단위(법정동, 시군구) 시설 통계를 생성한다.
- 시설 유형별 개수
- 인구 1,000명당 시설 수
- 아파트 기준 최근접 거리 통계 (평균, 최솟값, 최댓값)
"""

import pandas as pd
import numpy as np
from pathlib import Path

MAPPING_PATH = Path("apt_eda/data/processed/fm_apt_facility_mapping.csv")
APT_PATH = Path("apt_eda/data/processed/fm_apt_master_with_coords.csv")
FAC_PATH = Path("apt_eda/data/processed/fm_all_facilities_normalized.csv")
CENSUS_PATH = Path("apt_eda/data/raw/census_population_2025.csv")

OUT_BJD = Path("apt_eda/data/processed/fm_stats_by_bjd.csv")
OUT_SIGUNGU = Path("apt_eda/data/processed/fm_stats_by_sigungu.csv")


def load_population():
    """인구 데이터 로드 — 시도 단위 (현재 census 데이터에 시군구 단위 없음)

    census_population_2025.csv의 분류값ID1은 시도 코드(2자리)만 존재:
    - '11' = 서울특별시, '41' = 경기도
    bjdCode의 처음 2자리가 시도 코드에 해당.
    """
    df = pd.read_csv(CENSUS_PATH)
    # 총인구수만 (항목ID == 'T2'), 계(분류값ID2 == '0')
    pop = df[(df["항목ID"] == "T2") & (df["분류값ID2"] == "0")].copy()
    pop["sido_code"] = pop["분류값ID1"].astype(str)
    pop["population"] = pd.to_numeric(pop["수치값"], errors="coerce")
    # 서울(11), 경기(41)만
    pop_sido = pop[pop["sido_code"].isin(["11", "41"])][["sido_code", "population"]].copy()
    return pop_sido


def calc_nearest_distance(mapping_df, group_col):
    """아파트별 시설 유형별 최근접 거리를 구한 뒤 행정구역으로 집계"""
    # 아파트별 시설 유형별 최근접 거리
    nearest = mapping_df.groupby(["PNU", "facility_subtype"])["distance_m"].min().reset_index()
    nearest.rename(columns={"distance_m": "nearest_distance_m"}, inplace=True)

    # 아파트의 행정구역 코드 매핑
    # bjdCode(10자리): 시도(2) + 시군구(3) + 읍면동(3) + 리(2)
    # sigungu_code = bjdCode[:5] (시도2 + 시군구3)
    apt_df = pd.read_csv(APT_PATH, dtype={"PNU": str, "bjdCode": str})
    apt_df["sigungu_code"] = apt_df["bjdCode"].str[:5]
    apt_df["bjd_code"] = apt_df["bjdCode"].str[:10]

    nearest = nearest.merge(
        apt_df[["PNU", "bjd_code", "sigungu_code"]],
        on="PNU", how="left"
    )

    # 행정구역별 집계
    stats = nearest.groupby([group_col, "facility_subtype"]).agg(
        avg_nearest_distance_m=("nearest_distance_m", "mean"),
        min_nearest_distance_m=("nearest_distance_m", "min"),
        max_nearest_distance_m=("nearest_distance_m", "max"),
    ).reset_index()

    return stats


def calc_facility_count(fac_df, group_col):
    """행정구역별 시설 수 집계 — 정규화 시설 파일에서 직접 집계"""
    # 정규화된 시설 데이터에서 sigungu_code가 있으면 사용
    # 없으면 주소의 시도 정보로 sido_code 생성
    fac = fac_df.copy()

    # sigungu_code가 없는 행은 주소에서 추정
    if "sigungu_code" not in fac.columns or fac["sigungu_code"].isna().all():
        # 매핑 파일에서 시설별 가장 가까운 아파트의 행정구역 사용
        apt_df = pd.read_csv(APT_PATH, dtype={"PNU": str, "bjdCode": str})
        mapping_df = pd.read_csv(MAPPING_PATH, dtype={"PNU": str})

        fac_nearest_apt = mapping_df.sort_values("distance_m").drop_duplicates("facility_id")
        fac_nearest_apt = fac_nearest_apt.merge(
            apt_df[["PNU", "bjdCode"]], on="PNU", how="left"
        )
        fac_nearest_apt["sigungu_code"] = fac_nearest_apt["bjdCode"].str[:5]
        fac_nearest_apt["bjd_code"] = fac_nearest_apt["bjdCode"].str[:10]
        fac_nearest_apt["sido_code"] = fac_nearest_apt["bjdCode"].str[:2]

        fac = fac.merge(
            fac_nearest_apt[["facility_id", "sigungu_code", "bjd_code", "sido_code"]],
            on="facility_id", how="left"
        )

    counts = fac.dropna(subset=[group_col]).groupby(
        [group_col, "facility_subtype"]
    ).size().reset_index(name="facility_count")
    return counts


def main():
    print("=" * 60)
    print("행정구역 통계 생성")
    print("=" * 60)

    mapping_df = pd.read_csv(MAPPING_PATH, dtype={"PNU": str})
    fac_df = pd.read_csv(FAC_PATH)

    pop_sido = load_population()

    for group_col, out_path in [
        ("bjd_code", OUT_BJD),
        ("sigungu_code", OUT_SIGUNGU),
    ]:
        print(f"\n--- {group_col} 단위 통계 ---")

        # 시설 수
        counts = calc_facility_count(fac_df, group_col)

        # 거리 통계
        dist_stats = calc_nearest_distance(mapping_df, group_col)

        # 병합
        stats = counts.merge(dist_stats, on=[group_col, "facility_subtype"], how="outer")

        # 인구 대비 — sido_code(2자리) 기준으로 조인
        # bjdCode[:2] = sido_code (11=서울, 41=경기)
        stats["sido_code"] = stats[group_col].astype(str).str[:2]
        stats = stats.merge(pop_sido, on="sido_code", how="left")
        stats["facility_per_1000"] = (
            stats["facility_count"] / stats["population"] * 1000
        ).round(2)
        stats.drop(columns=["sido_code"], inplace=True)

        # 반올림
        for col in ["avg_nearest_distance_m", "min_nearest_distance_m", "max_nearest_distance_m"]:
            if col in stats.columns:
                stats[col] = stats[col].round(1)

        stats.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"저장: {out_path} ({len(stats):,}건)")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행**

```bash
.venv/bin/python apt_eda/src/step5_calc_stats.py
```

- [ ] **Step 3: 결과 검증**

```bash
.venv/bin/python -c "
import pandas as pd
for f in ['fm_stats_by_bjd.csv', 'fm_stats_by_sigungu.csv']:
    df = pd.read_csv(f'apt_eda/data/processed/{f}')
    print(f'\n{f}: {len(df)}건')
    print(df.head(10).to_string())
"
```

---

## 실행 순서 요약

```
Task 0: 환경 설정 (.env, 패키지 설치)
  ↓
Task 1: step1_geocode_apt.py (아파트 좌표 확보, ~13분)
  ↓
Task 2: step2_collect_facilities.py (시설 데이터 수집)
  ↓
Task 3: step3_normalize_facilities.py (정규화 + CRS 변환)
  ↓
Task 4: step4_calc_distance.py (BallTree 거리 계산)
  ↓
Task 5: step5_calc_stats.py (행정구역 통계)
```

각 Task는 순차 의존성이 있으므로 순서대로 실행해야 한다.
