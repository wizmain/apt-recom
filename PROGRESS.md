# 아파트 추천 서비스 프로젝트 진행 현황

> 최종 업데이트: 2026-03-26

---

## 프로젝트 개요

서울+경기+인천 아파트 데이터를 수집·분석하여 넛지(Nudge) 기반 아파트 추천 웹서비스를 구축하는 프로젝트.

---

## Phase 1: 데이터 수집 (2026-03-20 ~ 03-22)

### 1.1 아파트 마스터 구축
- [x] 건축물대장 API → 아파트 마스터 생성 (서울+경기 7,916건)
- [x] Vworld/Kakao 지오코딩 → 좌표 확보 (99.8%)
- [x] K-APT 데이터 매칭 → 세대수/동수/층수 보완
- [x] 인천 아파트 마스터 구축 (거래 데이터 기반 2,291건 + K-APT 보완)
- [x] 아파트명 없는 건물 복원 (K-APT 144건 + juso.go.kr 161건)
- [x] 마스터 통합: `fm_apt_master_all.csv` (10,093건)

### 1.2 시설 데이터 수집 (15종)
- [x] 병원 (41,683건) — 건강보험심사평가원 API
- [x] 학교 (4,398건) — data.go.kr 표준데이터
- [x] 공원 (7,326건) — data.go.kr 표준데이터
- [x] 지하철역 (777건) — KRIC 데이터
- [x] 버스정류장 (64,339건) — data.go.kr 파일
- [x] 도서관 (1,251건) — data.go.kr API
- [x] 경찰서/소방서 (460건) — data.go.kr 파일
- [x] CCTV (38,856건) — data.go.kr API
- [x] 편의점 (27,377건) — 소상공인 상가업소
- [x] 약국 (11,983건) — 소상공인 상가업소
- [x] 대형마트 (2,673건) — localdata.go.kr
- [x] 유치원 (2,724건) — 학교알리미/Kakao API
- [x] 동물병원 (331건) — 동물병원 인허가 데이터
- [x] 반려동물시설 (11,387건) — 반려동물 동반 가능 문화시설 (동물약국 제외)
- [x] 시설 통합: `fm_facilities_all.csv` (182,902건)

### 1.3 거래 데이터 수집
- [x] 매매 실거래가 2016~2026 서울+경기 (2,014,557건)
- [x] 전월세 실거래가 2016~2026 서울+경기 (4,935,673건)
- [x] 매매 실거래가 2016~2026 인천 (344,782건)
- [x] 전월세 실거래가 2016~2026 인천 (579,399건)
- [x] **총 거래: 7,874,411건 (10년치)**

### 1.4 학군 데이터 수집
- [x] 초등학교 통학구역 Shapefile → Spatial Join (99.8% 매칭)
- [x] 중학교 학교군 Shapefile → Spatial Join (99.9%)
- [x] 고등학교 학교군 Shapefile (평준화+비평준화) → Spatial Join (99.9%)
- [x] 교육행정구역 Shapefile → Spatial Join (100%)
- [x] 학교학구도연계정보 CSV → 학교ID 연결
- [x] 인천 학군 매핑 (초/중/고 통합, 88~90% 매칭)

### 1.5 연령대별 거래 통계
- [x] R-ONE 한국부동산원 연령대별 매매 통계 수집 (2019~2025, 시군구별)
- [x] KOSIS 조사 결과: 연령대+거래금액 결합 공개 데이터 없음 확인

### 1.6 인구 데이터
- [x] 행정안전부 주민등록인구통계 시군구별 연령대별 (2,068행, 94개 시군구)

---

## Phase 2: 데이터 가공 & 매핑 (2026-03-20 ~ 03-24)

### 2.1 시설 정규화
- [x] 15종 시설 통일 스키마 (facility_id, type, subtype, name, lat, lng, address)
- [x] 동물병원 CRS 변환 (EPSG:5186 → WGS84)
- [x] 안전시설 지오코딩 (Kakao API)
- [x] 시설 sub_category 추가 (반려동물시설 세부 분류)
- [x] 시군구코드 주소 파싱 보완 (55,075건)

### 2.2 아파트-시설 거리 계산
- [x] BallTree (haversine) 5km 반경 매핑
- [x] 서울+경기: ~56M행
- [x] 인천: ~12M행
- [x] apt_facility_summary 요약 테이블 생성

### 2.3 거래-아파트 매핑
- [x] 1차: 정확 이름 매칭 (39.8%)
- [x] 2차: 퍼지 매칭 (84.8%)
- [x] 3차: 주소 기반 매칭 (88.1%)
- [x] 4차: Dev API aptSeq 복원 + 브릿지 + 지번 기반 (99.6%)
- [x] **최종 매핑률: 매매 99.6%, 전월세 94.6%**

### 2.4 가격 점수 계산
- [x] 시군구 평균 대비 ㎡당 가격 점수 (0~100)
- [x] 전세가율 계산
- [x] apt_price_score 테이블 (15,859건)

### 2.5 안전 점수 계산
- [x] CCTV 목적별 가중치 적용 (생활방범 1.0, 어린이보호 1.2, 교통단속 0.2 등)
- [x] 안전점수 = CCTV 40% + 경찰서 30% + 소방서 30%
- [x] apt_safety_score 테이블 (10,077건)

---

## Phase 3: 분석 & EDA (2026-03-20 ~ 03-25)

### 3.1 연령대별 분석
- [x] 연령대별 시설 상관관계 히트맵 (상관계수 분석)
- [x] 연령대별 가격 패턴 분석 (시군구 평균가격 × 구매비중)
- [x] 리포트: `age_facility_correlation_report.md`, `age_price_pattern_report.md`

### 3.2 종합 EDA
- [x] processed 폴더 종합 EDA v2 (19개 차트)
- [x] 서울 상세 EDA (23개 차트, 6개 관점)
- [x] 경기 상세 EDA (24개 차트, 6개 관점)
- [x] 학군 × 아파트 EDA (21개 차트)
- [x] 5개 테이블 통합 EDA (14개 차트, Plotly HTML)
- [x] 서울 아파트 마스터 EDA (11개 차트, Plotly HTML)

### 3.3 raw 데이터 EDA (7종)
- [x] 전월세 시장 심층 분석 (17개 차트)
- [x] CCTV × 안전 분석 (14개 차트)
- [x] 건축물대장 심층 분석 (13개 차트)
- [x] 병원 인프라 분석 (13개 차트)
- [x] K-APT 단지 상세 분석 (12개 차트)
- [x] 교통 인프라 분석 (12개 차트)
- [x] 인구 × 시설 분석 (10개 차트)

### 3.4 EDA 산출물
- [x] 마크다운 리포트 16개
- [x] PDF 리포트 16개 (`apt_eda/docs/pdf/`)
- [x] HTML 리포트 2개 (Plotly 인터랙티브)
- [x] **총 차트: 200개+**

---

## Phase 4: 웹 서비스 구축 (2026-03-21 ~ 03-25)

### 4.1 SQLite DB 빌드
- [x] `web/backend/apt_web.db` (8.3GB)
- [x] 11개 테이블 + 인구 테이블 = 12개 테이블
- [x] apartments: 16,755건
- [x] facilities: 182,902건
- [x] apt_facility_mapping: ~56M행
- [x] trade_history: 2,359,339건
- [x] rent_history: 5,515,072건
- [x] school_zones: 10,077건
- [x] population_by_district: 2,068행

### 4.2 FastAPI 백엔드
- [x] 아파트 목록 API (GET /api/apartments)
- [x] 아파트 검색 API (GET /api/apartments/search)
- [x] 넛지 스코어링 API (POST /api/nudge/score)
- [x] 넛지 가중치 API (GET /api/nudge/weights)
- [x] 아파트 상세 API (GET /api/apartment/{pnu})
- [x] 거래 내역 API (GET /api/apartment/{pnu}/trades)
- [x] 채팅 API (POST /api/chat)
- [x] Knowledge 관리 API (POST/GET/DELETE /api/knowledge/*)

### 4.3 React 프론트엔드
- [x] Kakao Maps 지도 (클러스터링, 마커, 인포윈도우)
- [x] 넛지 태그 바 (8개 넛지 선택)
- [x] 지역명/단지명 검색 + 지도 자동 이동/줌인
- [x] 가중치 슬라이더 드로어 (한글 라벨)
- [x] 하단 결과 카드 (Top 5 추천)
- [x] 상세 모달 (5탭: 기본정보, 가격분석, 주변시설, 학군, 인구)
  - 넛지 스코어 레이더 차트
  - 월별 매매가 추이 (면적별 멀티 라인)
  - 면적별 평균가 바 차트
  - 전세가율 추이
  - 최근 거래 내역 테이블
  - 시설 요약 카드 + 바 차트
  - 학군 정보 (초/중/고 + 교육지원청)
  - 인구 피라미드 (구별 연령대/성별)

### 4.4 넛지 스코어링 엔진
- [x] 8개 넛지: 가성비, 반려동물, 출퇴근, 신혼육아, 학군, 시니어, 투자, 자연친화
- [x] 가격 점수 반영 (_price, _jeonse)
- [x] 안전 점수 반영 (_safety)
- [x] 사용자 가중치 커스터마이징

---

## Phase 5: AI 챗봇 (2026-03-25)

### 5.1 LLM 추상화 레이어
- [x] LLMProvider ABC (chat_with_tools, chat, stream_chat, embed)
- [x] OpenAI Provider (GPT-4o)
- [x] Claude Provider (Claude Sonnet)
- [x] Gemini Provider (Gemini 2.0 Flash)
- [x] .env 기반 전환 (LLM_PROVIDER=openai|claude|gemini)
- [x] Tool 스키마 자동 변환 (OpenAI/Claude/Gemini 형식)

### 5.2 Tool 함수 (6개)
- [x] search_apartments — 넛지 기반 아파트 검색
- [x] get_apartment_detail — 상세 정보 조회
- [x] compare_apartments — 아파트 비교
- [x] get_market_trend — 시세 동향
- [x] get_school_info — 학군 정보
- [x] search_knowledge — RAG 기반 PDF 검색

### 5.3 RAG 파이프라인
- [x] PDF 업로드 → PyMuPDF 텍스트 추출
- [x] LangChain TextSplitter 청킹 (800토큰)
- [x] OpenAI 임베딩 → ChromaDB 벡터 저장
- [x] Knowledge 검색 API

### 5.4 채팅 프론트엔드
- [x] 우측 하단 채팅 버튼
- [x] 채팅 모달 (메시지 + 아파트 카드 + 로딩)
- [x] 지도 양방향 연동 (챗봇→지도 하이라이트, 지도→챗봇 분석)

---

## Phase 6: 문서화 (2026-03-24 ~ 03-26)

### 6.1 ERD
- [x] processed CSV 파일 ERD (`apt_eda/docs/data_erd.md`)
- [x] apt_web.db ERD (`apt_eda/docs/db_erd.md`)

### 6.2 컬럼 매핑
- [x] 전체 CSV 영문-한글 매핑 (`apt_eda/docs/column_mapping.md`)

### 6.3 설계 문서
- [x] 가성비 아파트 데이터 수집 전략 (`가성비_아파트_데이터_수집_전략.md`)
- [x] 아파트 추천 넛지 전략 (`아파트_추천_넛지_전략.md`)
- [x] 시설 매핑 설계 (`2026-03-20-apt-facility-mapping-design.md`)
- [x] 웹 서비스 설계 (`2026-03-21-apt-web-design.md`)
- [x] 챗봇 설계 (`2026-03-25-chatbot-design.md`)

---

## 데이터 규모 요약

| 항목 | 규모 |
|------|------|
| 대상 지역 | 서울(25구) + 경기(40시군구) + 인천(10구군) |
| 아파트 | 16,755개 (마스터 10,093 + 거래 기반 6,662) |
| 시설 | 182,902개 (15종) |
| 시설 매핑 | ~56M행 |
| 매매 거래 | 2,359,339건 (2016~2026) |
| 전월세 거래 | 5,515,072건 (2016~2026) |
| 학군 매핑 | 10,077건 |
| 인구 데이터 | 94개 시군구 × 22개 연령대 |
| EDA 차트 | 200개+ |
| PDF 리포트 | 16개 |
| DB 크기 | 8.3GB |

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 백엔드 | Python 3.12, FastAPI, SQLite, uvicorn |
| 프론트엔드 | React, TypeScript, Vite, TailwindCSS, Recharts |
| 지도 | Kakao Maps JavaScript API |
| AI/LLM | OpenAI GPT-4o (기본), Claude, Gemini (전환 가능) |
| RAG | ChromaDB, PyMuPDF, LangChain TextSplitters |
| 데이터 | pandas, scikit-learn (BallTree), geopandas, pyproj |
| 시각화 | matplotlib, koreanize_matplotlib, Plotly, seaborn |

---

## 프로젝트 구조

```
fcicb6-proj3/
├── .env                          # API 키 설정
├── CLAUDE.md                     # 프로젝트 규칙
├── PROGRESS.md                   # 이 파일
├── pet_friendly_cultural_facilities.csv  # 반려동물 원본 (전국)
│
├── apt_eda/
│   ├── data/
│   │   ├── raw/                  # 원본 수집 데이터 (47개 CSV)
│   │   ├── processed/            # 가공 데이터 (32개 CSV)
│   │   ├── polished/             # 핵심 데이터 복사본 (18개)
│   │   └── hakguzi/              # 학군 Shapefile
│   ├── docs/                     # EDA 리포트 (MD + PDF + HTML)
│   ├── images/                   # 분석 차트 이미지
│   ├── scripts/                  # EDA 스크립트
│   └── src/                      # 데이터 수집/가공 스크립트
│
├── web/
│   ├── backend/
│   │   ├── main.py               # FastAPI 앱
│   │   ├── database.py           # DB 연결
│   │   ├── build_db.py           # CSV→SQLite 빌드
│   │   ├── apt_web.db            # SQLite DB (8.3GB)
│   │   ├── routers/              # API 엔드포인트
│   │   │   ├── apartments.py
│   │   │   ├── nudge.py
│   │   │   ├── detail.py
│   │   │   ├── chat.py
│   │   │   └── knowledge.py
│   │   ├── services/             # 비즈니스 로직
│   │   │   ├── scoring.py        # 넛지 스코어링
│   │   │   ├── chat_engine.py    # 챗봇 엔진
│   │   │   ├── tools.py          # 6개 Tool 함수
│   │   │   ├── rag.py            # RAG 파이프라인
│   │   │   ├── knowledge_manager.py
│   │   │   └── llm/              # LLM 추상화
│   │   │       ├── base.py
│   │   │       ├── openai_provider.py
│   │   │       ├── claude_provider.py
│   │   │       ├── gemini_provider.py
│   │   │       ├── factory.py
│   │   │       └── tool_adapter.py
│   │   ├── knowledge_db/         # ChromaDB
│   │   └── uploaded_pdfs/        # PDF 저장소
│   │
│   └── frontend/
│       ├── src/
│       │   ├── App.tsx
│       │   ├── components/
│       │   │   ├── Map.tsx
│       │   │   ├── NudgeBar.tsx
│       │   │   ├── WeightDrawer.tsx
│       │   │   ├── ResultCards.tsx
│       │   │   ├── DetailModal.tsx
│       │   │   ├── ChatButton.tsx
│       │   │   ├── ChatModal.tsx
│       │   │   ├── ChatMessage.tsx
│       │   │   └── ChatInput.tsx
│       │   ├── hooks/
│       │   │   ├── useApartments.ts
│       │   │   ├── useNudge.ts
│       │   │   └── useChat.ts
│       │   └── types/
│       │       └── apartment.ts
│       └── .env
│
└── docs/superpowers/
    ├── specs/                    # 설계 문서
    └── plans/                    # 구현 계획
```

---

## 향후 계획

### 미완료 / 개선 가능
- [ ] ML 모델: 가격 예측 (XGBoost), 유사 아파트 추천 (KNN), 가격 변동 예측
- [ ] 2016~2026 거래 데이터로 DB 완전 교체 (현재 일부 반영)
- [ ] 인천 지하철역 107개 반영 (현재 6개만)
- [ ] 이름 없는 아파트 63건 처리
- [ ] 클라우드 배포 (Vercel/AWS)
- [ ] 사용자 인증 + 관심 아파트 저장
- [ ] 챗봇 대화 이력 저장
- [ ] 모바일 반응형 UI
