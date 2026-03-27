# 아파트 주변 시설 매핑 시스템 설계

## 개요

아파트 마스터 데이터를 기준으로 주변 시설 정보를 구축하는 파이프라인.
서울+경기 지역 아파트별 5km 이내 시설을 매핑하고, 행정구역 단위 통계를 생성한다.
총 12종 시설 데이터 활용 (기존 5종 + 신규 수집 7종).

## 대상 지역

서울특별시 + 경기도

## 파이프라인 단계

### 1단계: 아파트 좌표 확보

- **입력:** `apt_eda/data/processed_gemini/apt_integrated_master_v1.csv`
- **방법:** Vworld 지오코딩 API로 `newPlatPlc`(도로명주소) → 위경도 변환. 실패 시 `platPlc`(지번주소)로 fallback. 그래도 실패 시 Kakao 지오코딩 API로 재시도.
- **API 키:** `.env` 파일에서 로드 (`VWORLD_API_KEY`, `KAKAO_API_KEY`)
- **Rate Limiting:** 0.1초 간격 호출, Vworld 일일 한도(10,000건) 도달 시 Kakao로 전환
- **체크포인트:** 100건마다 중간 결과 저장. 재실행 시 이미 좌표가 있는 행은 건너뜀
- **출력:** `apt_eda/data/processed/fm_apt_master_with_coords.csv` (기존 마스터 + lat, lng 컬럼)

### 2단계: 추가 시설 데이터 수집 (7종)

기존 보유 데이터 5종은 3단계에서 직접 정규화. 신규 7종만 수집:

#### 기존 보유 (3단계에서 활용)
| 시설 | 파일 | 비고 |
|------|------|------|
| 병원 | `raw/hospital_info_seoul_gyeonggi.csv` | 좌표 WGS84 |
| 동물병원 | `raw/animal_hospital_seoul_gyeonggi.csv` | **좌표 EPSG:5186 → WGS84 변환 필요** |
| 학교 | `raw/school_location_seoul_gyeonggi.csv` | 좌표 WGS84 |
| 공원 | `raw/city_park_seoul_gyeonggi.csv` | 좌표 WGS84 |
| 반려동물 문화시설 | `pet_friendly_cultural_facilities.csv` (루트) | **전국 데이터 → 서울+경기 필터링 필요** |

#### 신규 수집
| # | 시설 유형 | 수집 소스 | 저장 위치 |
|---|----------|----------|----------|
| 1 | 지하철역 | 공공데이터포털 (전국 도시철도역사 정보) | `raw/subway_station_seoul_gyeonggi.csv` |
| 2 | 버스정류장 | 공공데이터포털 (전국 버스정류장 위치) | `raw/bus_stop_seoul_gyeonggi.csv` |
| 3 | 대형마트/백화점 | 공공데이터포털 (대규모점포 정보) | `raw/large_store_seoul_gyeonggi.csv` |
| 4 | 어린이집/유치원 | 공공데이터포털 (어린이집/유치원 정보) | `raw/childcare_seoul_gyeonggi.csv` |
| 5 | 경찰서/소방서 | 공공데이터포털 (경찰관서/소방서 위치) | `raw/safety_facility_seoul_gyeonggi.csv` |
| 6 | 도서관/문화센터 | 공공데이터포털 (전국 도서관/문화시설) | `raw/library_culture_seoul_gyeonggi.csv` |
| 7 | 편의점/은행/약국 | 공공데이터포털 (소상공인 상가업소 정보) | 아래 3개 파일로 분리 저장 |

편의점/은행/약국은 업종코드가 다르므로 별도 파일로 분리:
- `raw/convenience_store_seoul_gyeonggi.csv`
- `raw/bank_seoul_gyeonggi.csv`
- `raw/pharmacy_seoul_gyeonggi.csv`

### 3단계: 시설 좌표 정규화

모든 시설 데이터(12종)를 통일 스키마로 변환:

```
facility_id      : str   — 시설 고유 ID (유형코드_일련번호, 아래 코드 테이블 참조)
facility_type    : str   — 대분류
facility_subtype : str   — 소분류
name             : str   — 시설명
lat              : float — 위도 (WGS84)
lng              : float — 경도 (WGS84)
address          : str   — 주소
bjd_code         : str   — 법정동코드 (10자리)
sigungu_code     : str   — 시군구코드 (5자리)
```

#### facility_id 코드 체계

| facility_type | facility_subtype | 코드 | 예시 |
|---------------|-----------------|------|------|
| transport | subway | SUB | SUB_000001 |
| transport | bus | BUS | BUS_000001 |
| commerce | mart | MRT | MRT_000001 |
| commerce | department_store | DPT | DPT_000001 |
| education | school | SCH | SCH_000001 |
| education | kindergarten | KDG | KDG_000001 |
| education | childcare | CDC | CDC_000001 |
| safety | police | POL | POL_000001 |
| safety | fire_station | FIR | FIR_000001 |
| culture | library | LIB | LIB_000001 |
| culture | culture_center | CUL | CUL_000001 |
| culture | park | PRK | PRK_000001 |
| living | convenience_store | CVS | CVS_000001 |
| living | bank | BNK | BNK_000001 |
| living | pharmacy | PHR | PHR_000001 |
| medical | hospital | HSP | HSP_000001 |
| medical | animal_hospital | AHP | AHP_000001 |
| pet | pet_facility | PET | PET_000001 |

#### 좌표 변환 규칙
- **EPSG:5186 → WGS84 변환:** 동물병원 데이터 (`CRD_INFO_X`, `CRD_INFO_Y` → lat, lng). pyproj 사용.
- **좌표 없는 시설:** Vworld/Kakao 지오코딩으로 보완 (1단계와 동일한 rate limiting/체크포인트 적용)
- **서울+경기 필터링:** 전국 데이터인 반려동물 문화시설은 시도 컬럼(`시도 명칭`)으로 필터링

#### 재실행 정책
각 단계는 출력 파일을 처음부터 새로 생성한다 (덮어쓰기). 중간 체크포인트는 지오코딩(1단계, 3단계)에만 적용.

- **출력:** `apt_eda/data/processed/fm_all_facilities_normalized.csv`

### 4단계: 거리 계산 & 매핑

- **방법:** scikit-learn `BallTree` (haversine metric)로 아파트별 5km 이내 시설 검색 + 거리(m) 계산
- **출력 스키마:**

```
PNU              : str   — 아파트 PNU
bldNm            : str   — 아파트 단지명
facility_id      : str   — 시설 ID
facility_type    : str   — 대분류
facility_subtype : str   — 소분류
facility_name    : str   — 시설명
facility_lat     : float — 시설 위도
facility_lng     : float — 시설 경도
distance_m       : float — 거리 (미터)
```

- **출력:** `apt_eda/data/processed/fm_apt_facility_mapping.csv`

### 5단계: 행정구역 통계

**집계 단위:** 법정동 + 시군구

**인구 데이터 조인:**
- `census_population_2025.csv`의 행정구역 코드를 `sigungu_code`(5자리)로 매핑
- 법정동 단위 인구가 없는 경우 시군구 인구를 법정동 수로 균등 분배

**지표:**

| 지표 | 설명 |
|------|------|
| facility_count | 시설 유형별 개수 |
| facility_per_1000 | 인구 1,000명당 시설 수 |
| avg_nearest_distance_m | 구역 내 아파트들의 평균 최근접 거리 |
| min_nearest_distance_m | 최근접 거리 최솟값 |
| max_nearest_distance_m | 최근접 거리 최댓값 |

**출력:**
- `apt_eda/data/processed/fm_stats_by_bjd.csv` (법정동 단위)
- `apt_eda/data/processed/fm_stats_by_sigungu.csv` (시군구 단위)

## 기술 스택

- Python 3.12 (루트 `.venv`)
- pandas, scikit-learn (BallTree), requests, pyproj
- python-dotenv (API 키 관리)
- Vworld 지오코딩 API, Kakao 지오코딩 API (fallback)
- 공공데이터포털 API/파일 다운로드

## 파일 구조

출력 파일은 기존 `processed/` 파일과 구분하기 위해 `fm_` 접두사 사용:

```
apt_eda/
  src/
    step1_geocode_apt.py          # 아파트 좌표 확보
    step2_collect_facilities.py   # 추가 시설 데이터 수집
    step3_normalize_facilities.py # 시설 좌표 정규화 + CRS 변환
    step4_calc_distance.py        # 거리 계산 & 매핑
    step5_calc_stats.py           # 행정구역 통계
  data/
    raw/                          # 원본 데이터
    processed/                    # 가공 데이터 (fm_ 접두사 파일이 본 파이프라인 산출물)
    processed_gemini/             # 기존 가공 데이터
.env                              # API 키 (VWORLD_API_KEY, KAKAO_API_KEY)
```
