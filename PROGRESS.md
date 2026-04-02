# 아파트 추천 서비스 프로젝트 진행 현황

> 최종 업데이트: 2026-04-02

---

## 프로젝트 개요

서울+경기+인천+전국 아파트 데이터를 수집·분석하여 라이프스타일 기반 아파트 추천 웹서비스 **"집토리"**를 구축하는 프로젝트.

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
- [x] 병원 (21,658건) — 건강보험심사평가원 API
- [x] 학교 (4,182건) — data.go.kr 표준데이터
- [x] 공원 (7,213건) — data.go.kr 표준데이터
- [x] 지하철역 (756건) — KRIC 데이터
- [x] 버스정류장 (64,339건) — data.go.kr 파일
- [x] 도서관 (1,231건) — data.go.kr API
- [x] 경찰서/소방서 (459건) — data.go.kr 파일
- [x] CCTV (32,494건) — data.go.kr API
- [x] 편의점 (21,480건) — 소상공인 상가업소
- [x] 약국 (9,943건) — 소상공인 상가업소
- [x] 대형마트 (1,326건) — localdata.go.kr
- [x] 유치원 (2,617건) — 학교알리미/Kakao API
- [x] 동물병원 (135건) — 동물병원 인허가 데이터
- [x] 반려동물시설 (6,195건) — 반려동물 동반 가능 문화시설
- [x] 시설 통합: 174,028건 (중복 제거 완료, UNIQUE 인덱스 적용)

### 1.3 거래 데이터 수집
- [x] 매매 실거래가 2016~2026 서울+경기+인천 (2,508,556건)
- [x] 전월세 실거래가 2016~2026 서울+경기+인천 (5,520,938건)
- [x] 부천시(원미/소사/오정), 화성시(동부/서부) 누락분 수집 (2026-04-01)
- [x] 중복 제거 + UNIQUE 인덱스 적용 (2026-04-02)
- [x] **총 거래: 8,029,494건 (중복 제거 후)**

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
- [x] BallTree (haversine) 기반 apt_facility_summary 생성
- [x] 17,086개 아파트 × 15종 시설 = 256,290건
- [x] apt_facility_mapping 폐기 (4,900만건, 7.3GB → 좌표 기반 실시간 조회로 대체, 2026-04-02)

### 2.3 거래-아파트 매핑
- [x] 1차: 정확 이름 매칭 (39.8%)
- [x] 2차: 퍼지 매칭 (84.8%)
- [x] 3차: 주소 기반 매칭 (88.1%)
- [x] 4차: Dev API aptSeq 복원 + 브릿지 + 지번 기반 (99.6%)
- [x] **최종 매핑률: 매매 99.6%, 전월세 94.6%**

### 2.4 가격 점수 계산
- [x] 시군구 평균 대비 ㎡당 가격 점수 (0~100)
- [x] 전세가율 계산
- [x] apt_price_score 테이블 (16,745건)

### 2.5 안전 점수 계산
- [x] 안전점수 = CCTV 40% + 경찰서 30% + 소방서 30%
- [x] apt_safety_score 테이블 (17,086건)

### 2.6 아파트 좌표 복원 (2026-03-27)
- [x] 3단계 좌표 복원: Vworld 도로명 → Kakao 지번 → PNU 지번 → 아파트명 검색
- [x] 좌표 커버리지: 86.2% → 97.3%
- [x] 통계적 이상치 탐지 (3σ per 시군구) → 492건 잘못된 좌표 정리

### 2.7 주소 데이터 보충 (2026-04-01)
- [x] Phase 1: Kakao 역지오코딩 (TRADE PNU + 좌표) → 2,050건
- [x] Phase 2: 건축물대장 API (정상 PNU) → ~5,371건
- [x] Phase 3: Kakao 키워드 검색 (fallback) → 311건
- [x] 주소 커버리지: **47.1% → 98.1%** (잔여 316건)
- [x] GitHub Actions 배치(batch-fill-addresses.yml)로 잔여분 주기적 재시도

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

### 4.1 DB 구축
- [x] SQLite → PostgreSQL 마이그레이션 완료 (2026-03-27)
- [x] 테이블 구조 정비 + UNIQUE 인덱스 적용 (2026-04-02)
- [x] apartments: 16,870건
- [x] facilities: 174,028건 (중복 제거 후)
- [x] apt_facility_summary: 256,290건
- [x] trade_history: 2,508,556건 (UNIQUE 인덱스)
- [x] rent_history: 5,520,938건 (UNIQUE 인덱스)
- [x] school_zones: 10,077건
- [x] population_by_district: 2,068행

### 4.2 FastAPI 백엔드
- [x] 아파트 목록 API (GET /api/apartments)
- [x] 아파트 검색 API (GET /api/apartments/search) — sigungu_code 매칭 추가
- [x] 넛지 스코어링 API (POST /api/nudge/score) — 비선형 거리함수 + 밀도 블렌딩
- [x] 넛지 가중치 API (GET /api/nudge/weights)
- [x] 아파트 상세 API (GET /api/apartment/{pnu})
- [x] 거래 내역 API (GET /api/apartment/{pnu}/trades)
- [x] 채팅 API (POST /api/chat) + SSE 스트리밍 (POST /api/chat/stream)
- [x] 출퇴근 시간 조회 API (POST /api/commute) — ODSay 대중교통
- [x] 챗봇 피드백 API (POST /api/chat/feedback, GET /api/chat/feedback/stats)
- [x] Knowledge 관리 API (POST/GET/DELETE /api/knowledge/*)
- [x] 대시보드 API (GET /api/dashboard/*) — 요약/추이/랭킹/최근거래/지역/거래상세
- [x] 공통코드 API (GET /api/codes/{group})
- [x] 유사 아파트 API (GET /api/apartment/{pnu}/similar) — 코사인 유사도

### 4.3 React 프론트엔드
- [x] Kakao Maps 지도 (클러스터링, 마커, 인포윈도우)
- [x] 넛지 태그 바 (9개 항목) — NudgeBar 구조 분리 (ViewTabs + MapControls + NudgeChips)
- [x] 다중 키워드 검색 — Enter로 태그 추가, 개별/전체 삭제
- [x] 가중치 설정 드롭다운 패널
- [x] 하단 결과 카드 (Top 5 추천)
- [x] 순위별 색상 마커 (1위 빨강, 2위 주황, 3~5위 로즈)
- [x] 상세 모달 (6탭: 기본정보, 가격분석, 주변시설, 학군, 안전, 인구)
- [x] 아파트 비교 모달
- [x] 모바일 반응형 전환 (전 컴포넌트)
- [x] 대시보드 (요약카드, 차트 4종, 최근거래, 지역검색, 거래이력 팝업)

### 4.4 넛지 스코어링 엔진
- [x] 9개 항목: 가성비, 반려동물, 출퇴근, 신혼육아, 학군, 시니어, 투자, 자연친화, 안전
- [x] ML 기반 넛지 가중치 재조정 (60% 수동 + 40% ML, 2026-04-01)
- [x] 로그감쇠 비선형 distance_to_score (시설별 decay 파라미터, 2026-04-01)
- [x] 시설 밀도(count_1km) 30% 블렌딩 (2026-04-01)
- [x] common_code 테이블로 가중치/최대거리 관리 (하드코딩 제거)

---

## Phase 5: AI 챗봇 (2026-03-25)

### 5.1 LLM 추상화 레이어
- [x] LLMProvider ABC (chat_with_tools, chat, stream_chat, embed)
- [x] OpenAI / Claude / Gemini Provider
- [x] .env 기반 전환 (LLM_PROVIDER=openai|claude|gemini)

### 5.2 Tool 함수 (9개)
- [x] search_apartments — 넛지 점수 기반 아파트 검색
- [x] get_apartment_detail — 상세 정보 조회
- [x] compare_apartments — 아파트 비교
- [x] get_market_trend — 시세 동향
- [x] get_school_info — 학군 정보
- [x] search_knowledge — RAG 기반 PDF 검색
- [x] search_commute — ODSay 대중교통 출퇴근 시간 조회
- [x] get_dashboard_info — 대시보드 요약 정보
- [x] get_similar_apartments — 유사 아파트 추천

### 5.3 RAG 파이프라인
- [x] PDF 업로드 → PyMuPDF 텍스트 추출 → ChromaDB 벡터 저장

### 5.4 채팅 프론트엔드
- [x] SSE 스트리밍 응답 (실시간 글자 단위 출력)
- [x] 마크다운 렌더링 + 인포그래픽 UI
- [x] 지도 양방향 연동 (챗봇↔지도 하이라이트)
- [x] 피드백 UI (👍👎 + 태그 6종 + 자유 코멘트)

---

## Phase 6: 데이터 품질 개선 (2026-03-27 ~ 04-02)

### 6.1 인천 아파트 데이터 재구축 (2026-03-27)
- [x] 지오코딩 좌표 검증 — 인천 범위 밖 좌표 153건 수정
- [x] DB 전체 퍼지 → integrate_incheon.py 재실행

### 6.2 SQLite → PostgreSQL 마이그레이션 (2026-03-27)
- [x] psycopg2 기반 database.py 전면 재작성
- [x] 12개 테이블 데이터 마이그레이션

### 6.3 공통코드 테이블 도입 (2026-03-31)
- [x] common_code 통합 테이블 생성
- [x] 시군구코드, 넛지가중치, 최대거리, 시설라벨 등 하드코딩 → DB 전환
- [x] 프론트엔드 useCodes() 훅으로 동적 로드

### 6.4 데이터 중복 제거 + UNIQUE 인덱스 (2026-04-02)
- [x] trade_history: 84,738건 중복 삭제 + UNIQUE 인덱스
- [x] rent_history: 528,351건 중복 삭제 + UNIQUE 인덱스
- [x] facilities: 34,890건 중복 삭제 + UNIQUE 인덱스
- [x] CSV 원본 파일 중복 제거 (facilities, trade, rent)
- [x] apt_facility_mapping 폐기 (4,900만건, 7.3GB) → 좌표 기반 실시간 조회

### 6.5 부천시/화성시 수집 누락 해결 (2026-04-01)
- [x] 원인: 국토교통부 API가 통합코드(41190, 41590) 미지원
- [x] nationwide_codes.py 구 단위 코드로 교체 (41192/41194/41196, 41591/41593)
- [x] 거래 데이터 수집: 매매 26,844건, 전월세 90,364건
- [x] 아파트 963건 생성 + Kakao 지오코딩 + 시설/가격/안전 점수 계산

### 6.6 주소 데이터 보충 (2026-04-01)
- [x] Kakao 역지오코딩 + 건축물대장 API + Kakao 키워드 검색
- [x] 주소 커버리지: 47.1% → 98.1%
- [x] 검색 API에 sigungu_code 기반 매칭 추가

---

## Phase 7: ML 기능 (2026-03-31 ~ 04-01)

### 7.1 유사 아파트 추천
- [x] 39차원 특성 벡터 생성 (기본4 + 가격3 + 시설거리15 + 시설밀도15 + 안전2)
- [x] StandardScaler 정규화 + 코사인 유사도 검색
- [x] API: GET /api/apartment/{pnu}/similar?top_n=5
- [x] 챗봇 tool 연동: get_similar_apartments

### 7.2 넛지 스코어링 모델 학습
- [x] XGBoost 회귀 모델 (R²=0.59, MAE=187만원/㎡)
- [x] Feature Importance → 시설별 가격 기여도 분석
- [x] PDP 기반 비선형 거리→점수 곡선 추출

### 7.3 스코어링 고도화 적용 (2026-04-01)
- [x] 넛지 가중치 49건 ML 기반 재조정 (batch/ml/update_weights.py)
- [x] distance_to_score 로그감쇠 비선형화 (시설별 FACILITY_DECAY)
- [x] 시설 밀도 30% 블렌딩 (facility_score = 거리 70% + 밀도 30%)
- [x] docs/scoring-ml-enhancement.md 작업 기록

---

## Phase 8: 배치 파이프라인 (2026-03-30 ~ 04-01)

### 8.1 GitHub Actions 배치
- [x] 거래 데이터 12시간 수집 (batch-weekly.yml)
- [x] 비수도권 초기 수집 (batch-initial-collect.yml) — 진행 중 (~14%)
- [x] 시설 데이터 분기 갱신 (batch-quarterly.yml)
- [x] 인구/범죄 데이터 연간 갱신 (batch-annual.yml)
- [x] 주소 보충 일배치 (batch-fill-addresses.yml)

### 8.2 Railway↔로컬 동기화
- [x] 증분 동기화: created_at 기반 (batch/sync_from_railway.py)
- [x] 전체 동기화: pg_dump/pg_restore

---

## Phase 9: 호스팅 & DevOps (2026-03-27 ~ 03-28)

### 9.1 Railway 배포 (백엔드)
- [x] FastAPI + PostgreSQL Railway 배포
- [x] GitHub 연동 자동 배포

### 9.2 Cloudflare Pages 배포 (프론트엔드)
- [x] Vite 빌드 + Cloudflare Pages 배포

### 9.3 CI/CD 품질 관리
- [x] Git pre-commit hook — TypeScript 체크
- [x] 통합 테스트 29개 (`web/backend/tests/test_core.py`)
- [x] DB 설계 원칙 + 테이블 생성 체크리스트 (CLAUDE.md)

---

## Phase 10: 문서화 (2026-03-24 ~ 04-01)

- [x] ERD, 컬럼 매핑, 설계 문서 16종
- [x] ADR (Architecture Decision Records) 11개
- [x] 배치 작업 가이드 (docs/batch-operations.md)
- [x] ML 기능 가이드 (docs/ml-features.md)
- [x] 스코어링 보완 기록 (docs/scoring-ml-enhancement.md)

---

## 데이터 규모 요약

| 항목 | 규모 |
|------|------|
| 대상 지역 | 서울(25) + 경기(41) + 인천(10) + 비수도권 수집 중 |
| 아파트 | 16,870건, 좌표 98.1%, 주소 98.1% |
| 시설 | 174,028건 (15종, 중복 제거 + UNIQUE) |
| 시설 요약 | 256,290건 (BallTree 기반) |
| 매매 거래 | 2,508,556건 (UNIQUE 인덱스) |
| 전월세 거래 | 5,520,938건 (UNIQUE 인덱스) |
| 학군 매핑 | 10,077건 |
| 인구 데이터 | 94개 시군구 × 22개 연령대 |
| EDA 차트 | 200개+ |
| ML 모델 | XGBoost (R²=0.59), 39차원 벡터 |

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 백엔드 | Python 3.12, FastAPI, PostgreSQL, psycopg2, uvicorn |
| 프론트엔드 | React 19, TypeScript, Vite 8, TailwindCSS 4, Recharts |
| 지도 | Kakao Maps JavaScript API |
| AI/LLM | OpenAI GPT-4o (기본), Claude, Gemini (전환 가능), SSE 스트리밍 |
| ML | XGBoost, scikit-learn (BallTree, StandardScaler), numpy |
| 외부 API | ODSay, Kakao, Vworld, KOSIS, 국토교통부, 건축물대장 |
| RAG | ChromaDB, PyMuPDF, LangChain TextSplitters |
| 호스팅 | Railway (백엔드+DB), Cloudflare Pages (프론트엔드) |
| CI/CD | GitHub Actions (배치 5종), pre-commit hook |

---

## 향후 계획

### 미완료 / 개선 가능
- [ ] 비수도권 초기 수집 완료 (현재 ~14%)
- [ ] React Native 모바일 앱 완성
- [ ] ML 가격 예측 모델 (XGBoost → "예상 시세: 5억2천")
- [ ] 사용자 피드백 기반 개인화 가중치 학습
- [ ] 아파트 클러스터링 (K-Means → "이 아파트는 학군형입니다")
- [ ] 사용자 인증 + 관심 아파트 저장
- [ ] A/B 프롬프트 테스트
