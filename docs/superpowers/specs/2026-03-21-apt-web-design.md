# 아파트 추천 웹사이트 설계

## 개요

사용자의 라이프스타일(넛지)에 맞는 아파트를 지도 기반으로 추천하는 웹 서비스.
서울+경기 약 7,900개 아파트를 대상으로 8가지 넛지(가성비, 반려동물, 출퇴근, 신혼·육아, 학군, 시니어, 투자, 자연친화)별 스코어링을 제공한다.

## 기술 스택

| 영역 | 기술 |
|------|------|
| 프론트엔드 | React + TypeScript, TailwindCSS, Recharts |
| 백엔드 | Python FastAPI |
| 데이터베이스 | SQLite (신규 `apt_web.db`) |
| 지도 | Kakao Maps JavaScript API |
| 배포 | 로컬 우선, 추후 클라우드 고려 |

## 프로젝트 구조

```
web/
  backend/
    main.py                 # FastAPI 앱 진입점
    database.py             # SQLite 연결 및 쿼리
    build_db.py             # CSV → SQLite 빌드 스크립트
    routers/
      apartments.py         # 아파트 목록/검색 API
      nudge.py              # 넛지 스코어링 API
      detail.py             # 아파트 상세 정보 API
    services/
      scoring.py            # 넛지별 스코어 계산 엔진
    apt_web.db              # SQLite DB (빌드 생성)
  frontend/
    package.json
    src/
      App.tsx
      components/
        Map.tsx             # Kakao Maps 지도
        NudgeBar.tsx        # 상단 넛지 태그 선택 바
        WeightDrawer.tsx    # 가중치 슬라이더 드로어
        ResultCards.tsx     # 하단 결과 카드 슬라이드
        DetailModal.tsx     # 상세 정보 모달
        charts/
          PriceTrend.tsx    # 매매가 추이 차트
          PriceByArea.tsx   # 평수별 가격 분포
          FacilityBar.tsx   # 주변 시설 바 차트
          RadarScore.tsx    # 넛지 스코어 레이더
      hooks/
        useApartments.ts    # 아파트 데이터 훅
        useNudge.ts         # 넛지 스코어링 훅
      types/
        apartment.ts        # 타입 정의
```

## 메인 페이지 레이아웃

전체 지도 + 상단 검색/넛지 바 + 하단 결과 카드 (직방/Zillow 스타일)

```
┌─────────────────────────────────────────────────┐
│ 🏠 아파트추천  [검색바]  [가성비][육아][출퇴근]... [⚙상세] │
├─────────────────────────────────────────────────┤
│                                                 │
│              Kakao Maps 전체화면                  │
│         (아파트 마커 + 클러스터링)                  │
│                                                 │
│    마커 클릭 → 인포윈도우 (단지명, 스코어, 가격)     │
│                                                 │
├─────────────────────────────────────────────────┤
│ [🏆1위 아파트][2위][3위][4위][5위]  ← 가로 스크롤    │
│  92점 / 강남  88점     85점                       │
└─────────────────────────────────────────────────┘
```

**디자인 톤:** 클린 & 모던 (라이트) — 밝은 배경, 깔끔한 카드 UI, 블루 계열 포인트 컬러

## 인터랙션 흐름

1. 페이지 로드 → 전체 아파트 마커 표시 (클러스터링)
2. 사용자가 넛지 태그 선택 (복수 가능) → API 호출 → Top 5 결과 카드 + 지도 하이라이트
3. "⚙ 상세" 클릭 → 가중치 슬라이더 드로어 열림 → 시설별 가중치 조정 → 실시간 재스코어링
4. 결과 카드 또는 마커 클릭 → 모달 팝업으로 상세 정보

## 넛지 스코어링 엔진

### 넛지 8종

| ID | 태그 | 핵심 시설 | 기본 가중치 |
|----|------|----------|-----------|
| N1 | 가성비 | ㎡단가(시군구 대비), 전세가율, 역세권, 세대수 | 가격30 교통15 편의10 단지10 |
| N2 | 반려동물 | 동물병원, 반려시설, 공원 | 반려25 동물병원25 공원20 |
| N3 | 출퇴근 | 지하철, 버스, (직장 직선거리) | 지하철30 버스15 편의10 |
| N4 | 신혼·육아 | 유치원, 학교, 병원, 공원 | 유치원20 학교20 병원15 공원15 |
| N5 | 학군 | 학교 수/거리, 도서관, 배정학교 | 학교25 도서관15 편의10 |
| N6 | 시니어 | 병원, 약국, 공원, 편의점 | 병원25 약국15 공원15 편의10 |
| N7 | 투자 | 전세가율, GAP, 역세권, 건축연도 | 가격25 전세20 교통15 연도10 |
| N8 | 자연친화 | 공원 수/거리/면적 | 공원30 공원수25 병원10 |

### 스코어링 공식

```python
# 1. 시설 유형별 최근접 거리 → 점수 변환 (가까울수록 높은 점수)
# apt_facility_summary 테이블의 pre-aggregated 값 사용
distance_score = max(0, 100 - (nearest_distance_m / max_distance * 100))
# max_distance: 시설 유형별 상한 (subway=2000m, hospital=3000m, park=2000m 등)

# 2. 넛지별 가중합 (가중치 합이 100이 되도록 정규화)
nudge_score = sum(facility_score * (weight / sum_of_weights)
                  for facility, weight in nudge_weights.items())
# 결과: 0~100 범위

# 3. 복수 넛지 선택 시: 선택된 넛지 점수의 단순 평균
final_score = mean(nudge_scores)  # len(selected_nudges)로 나눔
```

### 성능: Pre-aggregation 전략

45M행의 `apt_facility_mapping`을 매 요청마다 쿼리하면 성능 문제가 발생한다.
`build_db.py`에서 요약 테이블을 사전 생성:

```sql
-- 아파트별 시설 유형별 요약 (빌드 시 생성)
CREATE TABLE apt_facility_summary (
  pnu TEXT,
  facility_subtype TEXT,
  nearest_distance_m REAL,   -- 최근접 거리
  count_1km INTEGER,          -- 1km 이내 시설 수
  count_3km INTEGER,          -- 3km 이내 시설 수
  count_5km INTEGER,          -- 5km 이내 시설 수
  PRIMARY KEY (pnu, facility_subtype)
);
```

스코어링 API는 이 요약 테이블만 쿼리 (약 7,900 × 14 = ~110K행).
상세 모달의 개별 시설 목록은 `apt_facility_mapping`을 PNU 기준으로 쿼리.

### 가중치 슬라이더

넛지 선택 시 기본값 자동 세팅. 사용자가 "⚙ 상세" 버튼으로 시설별 가중치 미세 조정 가능.
슬라이더 변경 시 실시간 재스코어링 (debounce 300ms).

## 아파트 상세 모달

모달 팝업. 4개 탭 구성:

### 탭 1: 기본정보
- 단지 개요: 세대수, 동수, 최고층, 사용승인일, 주소
- 넛지 스코어 레이더 차트 (Recharts RadarChart) — 8개 넛지 항목별 점수
- 소형 Kakao Maps (단지 위치 + 주변 시설 마커)

### 탭 2: 가격분석
- 매매가 추이 선 그래프 (2023~2025, 월별, Recharts LineChart)
- 평수별 가격 분포 (전용 60㎡ 이하 / 60~85 / 85~135, Recharts BarChart)
- 전세가율 추이 선 그래프
- ㎡당 가격 vs 시군구 평균 비교 바 차트
- 최근 거래 내역 테이블 (날짜, 층, 면적, 가격)

### 탭 3: 주변시설
- 시설 유형별 가장 가까운 시설 목록 (거리순)
- 반경 1km/3km/5km 내 시설 개수 바 차트
- 주변 시설 지도 (시설 유형별 색상 마커)

### 탭 4: 학군
- 배정 초등학교 (학교명 + 학교ID)
- 중학교 학교군
- 고등학교 학교군 (평준화/비평준화)
- 교육지원청 정보
- 반경 내 학교 목록 (거리순)

## API 설계

### GET /api/apartments
아파트 목록 조회 (지도 마커용)
```json
Response: [{
  "pnu": "1111010100000560045",
  "bld_nm": "청운현대(아)102동",
  "lat": 37.584, "lng": 126.969,
  "total_hhld_cnt": 20,
  "sigungu_code": "11110"
}]
```

### POST /api/nudge/score
넛지 스코어링 → Top N 추천
```json
Request: {
  "nudges": ["pet", "nature"],
  "weights": {"animal_hospital": 80, "park": 100, "pet_facility": 90},
  "top_n": 5,
  "bounds": {"sw_lat": 37.4, "sw_lng": 126.8, "ne_lat": 37.7, "ne_lng": 127.2}
}
Response: [{
  "pnu": "...", "bld_nm": "...", "score": 92.3,
  "score_breakdown": {"animal_hospital": 95, "park": 88, "pet_facility": 94},
  "lat": 37.5, "lng": 127.0
}]
```

### GET /api/apartment/{pnu}
아파트 상세 정보
```json
Response: {
  "basic": { "pnu", "bld_nm", "total_hhld_cnt", "dong_count", ... },
  "scores": { "cost": 72, "pet": 95, "commute": 60, ... },
  "facilities": [{ "type", "subtype", "name", "distance_m" }],
  "school": { "elementary", "middle", "high", "edu_district" }
}
```

### GET /api/apartment/{pnu}/trades
매매/전세 거래 내역
```json
Response: {
  "trades": [{ "deal_year", "deal_month", "deal_amount", "exclu_use_ar", "floor" }],
  "rents": [{ "deal_year", "deal_month", "deposit", "monthly_rent", "exclu_use_ar" }]
}
```

## SQLite DB 스키마

DB 파일: `web/backend/apt_web.db`

```sql
-- 아파트 마스터
CREATE TABLE apartments (
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

-- 시설 정규화
CREATE TABLE facilities (
  facility_id TEXT PRIMARY KEY,
  facility_type TEXT,
  facility_subtype TEXT,
  name TEXT,
  lat REAL,
  lng REAL,
  address TEXT
);

-- 아파트-시설 매핑 (5km 이내)
CREATE TABLE apt_facility_mapping (
  pnu TEXT,
  facility_id TEXT,
  facility_type TEXT,
  facility_subtype TEXT,
  distance_m REAL,
  PRIMARY KEY (pnu, facility_id)
);

-- 매매 실거래가
CREATE TABLE trade_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  apt_seq TEXT,             -- 실거래 API 단지키 (예: 11110-2445)
  sgg_cd TEXT,
  apt_nm TEXT,
  deal_amount INTEGER,      -- 만원 단위
  exclu_use_ar REAL,        -- 전용면적 ㎡
  floor INTEGER,
  deal_year INTEGER,
  deal_month INTEGER,
  deal_day INTEGER,
  build_year INTEGER
);

-- 전월세 실거래가
CREATE TABLE rent_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  apt_seq TEXT,             -- 실거래 API 단지키
  sgg_cd TEXT,
  apt_nm TEXT,
  deposit INTEGER,          -- 보증금 만원
  monthly_rent INTEGER,     -- 월세 만원
  exclu_use_ar REAL,
  floor INTEGER,
  deal_year INTEGER,
  deal_month INTEGER,
  deal_day INTEGER
);

-- 실거래 단지 ↔ 아파트 마스터 매핑
-- aptSeq → PNU 매핑 (빌드 시 sgg_cd + apt_nm 기반 매칭)
CREATE TABLE trade_apt_mapping (
  apt_seq TEXT PRIMARY KEY,
  pnu TEXT,
  apt_nm TEXT,
  sgg_cd TEXT,
  match_method TEXT         -- exact_name, fuzzy_name 등
);

-- 학군 매핑
CREATE TABLE school_zones (
  pnu TEXT PRIMARY KEY,
  elementary_school_name TEXT,
  elementary_school_id TEXT,
  elementary_school_full_name TEXT,
  elementary_zone_id TEXT,
  middle_school_zone TEXT,
  middle_school_zone_id TEXT,
  high_school_zone TEXT,
  high_school_zone_id TEXT,
  high_school_zone_type TEXT,   -- 평준화/비평준화
  edu_office_name TEXT,
  edu_district TEXT
);

-- 인덱스
CREATE INDEX idx_mapping_pnu ON apt_facility_mapping(pnu);
CREATE INDEX idx_mapping_type ON apt_facility_mapping(facility_type);
CREATE INDEX idx_trade_sgg ON trade_history(sgg_cd);
CREATE INDEX idx_trade_year ON trade_history(deal_year);
CREATE INDEX idx_rent_sgg ON rent_history(sgg_cd);
CREATE INDEX idx_apt_sigungu ON apartments(sigungu_code);
```

빌드 스크립트(`build_db.py`)가 기존 CSV 파일들을 읽어 위 테이블에 적재.
`apt_facility_mapping`은 5.2GB(45M행)이므로 청크로 읽어 INSERT.

## 데이터 소스 매핑

| 테이블 | 소스 CSV |
|--------|---------|
| apartments | `fm_apt_master_with_coords.csv` |
| facilities | `fm_all_facilities_normalized.csv` |
| apt_facility_mapping | `fm_apt_facility_mapping.csv` |
| trade_history | `apt_trade_total_2023_2026.csv` |
| rent_history | `apt_rent_total_2023_2026.csv` |
| school_zones | `fm_apt_school_zone_enriched.csv` + `fm_apt_middle_school_zone.csv` + `fm_apt_high_school_zone.csv` + `fm_apt_edu_district.csv` |
| apt_facility_summary | `fm_apt_facility_mapping.csv`에서 집계하여 생성 |
| trade_apt_mapping | `apt_trade_total_2023_2026.csv`의 aptSeq + sggCd + aptNm으로 apartments.pnu 매칭 |

## 환경 변수

```
# backend/.env
DATABASE_PATH=apt_web.db

# frontend/.env
VITE_API_BASE_URL=http://localhost:8000
VITE_KAKAO_MAP_KEY=54037323bb0a830a9e5c3b4e1bbf9abc
```

Kakao Maps JavaScript API는 `VITE_KAKAO_MAP_KEY`로 주입. 개발용 `localhost` 도메인을 Kakao 개발자 콘솔에 등록 필요.

## CORS 설정

FastAPI `main.py`에 CORSMiddleware 설정:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React dev server
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## DB 빌드 전략

### 벌크 로드 순서
1. 테이블 생성 (인덱스 없이)
2. apartments, facilities, school_zones 적재
3. trade_history, rent_history 적재 + trade_apt_mapping 생성
4. apt_facility_mapping 청크 로드 (100만 행씩, 단일 트랜잭션)
5. apt_facility_summary 집계 테이블 생성
6. 인덱스 생성 (적재 완료 후)

### apt_facility_mapping 최적화
- `WITHOUT ROWID` 사용하여 저장 공간 절약
- 인덱스는 모든 데이터 INSERT 후 생성
- `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=OFF` 적용 (빌드 시)
- 예상 빌드 시간: 약 10~20분

### trade_apt_mapping 매칭 전략
1. `sgg_cd`(5자리) + `apt_nm` 정확 일치 → apartments의 `sigungu_code` + `bld_nm`
2. 정확 일치 실패 시 정규화 이름(공백/괄호 제거) 매칭
3. 매칭률은 기존 프로젝트의 `05_kapt_trade_mapping_v2.csv` 결과 참조 가능
