# 집토리 관리자 페이지 설계 스펙

## 1. 개요

집토리 서비스의 운영 상태를 모니터링하고, 데이터/배치/피드백/스코어링/지식베이스/공통코드를 관리하는 관리자 전용 페이지.

## 2. 결정 사항

| 항목 | 결정 |
|------|------|
| 레이아웃 | 접이식 사이드바(아이콘) + 카드 그리드 |
| 분리 방식 | 별도 프론트엔드 앱 (`web/admin/`) |
| 기술 스택 | React 19 + TypeScript + Vite 8 + Tailwind CSS 4 + Recharts |
| 백엔드 | 기존 FastAPI 앱에 `/api/admin/` 라우터 추가 |
| 인증 | Phase 1부터 ADMIN_TOKEN Bearer 인증 적용 (미설정 시 503) |

## 3. 메뉴 구성 (7개 섹션)

### 3.1 운영 대시보드 (홈)
- KPI 카드 4개: 총 아파트 수, 오늘 거래 건수, 챗봇 만족도, 주소 커버리지
- 배치 실행 현황: trade/quarterly/annual/mgmt_cost별 최근 실행 상태, 건수, 소요시간
- 최근 피드백: 좋아요/싫어요 실시간 피드 (최근 10건)
- 데이터 품질: 테이블별 커버리지 프로그레스 바
- 거래 추이: 최근 12개월 막대 차트 (recharts)

### 3.2 데이터 관리
- 주요 테이블별 레코드 수, NULL 비율, 최근 갱신 시각
- 테이블 선택 시 데이터 검색/조회 (페이지네이션)
- 대상 테이블: apartments, facilities, trade_history, rent_history, school_zones, apt_price_score, apt_safety_score, apt_vectors
- 데이터 품질 리포트: NULL 컬럼 분포, 이상치 감지

### 3.3 배치 모니터링
- 배치 타입별 실행 이력 (최근 30일)
- step별 상태: 성공/경고/실패, 처리 건수, 소요 시간
- 로그 상세 보기 (batch/logs/ 파일 내용)
- 수동 실행 트리거 (dry-run 옵션 포함)

### 3.4 사용자 피드백
- 피드백 목록: 좋아요/싫어요 필터, 태그 필터, 기간 필터
- 만족도 추이 차트 (일/주/월)
- 불만 태그 분포 도넛 차트
- 개별 피드백 상세: 사용자 메시지, 어시스턴트 응답, 태그, 코멘트

### 3.5 스코어링/가중치 관리
- 넛지별 가중치 조회/수정 (common_code nudge_weight 그룹)
- 시설 거리 기준값 관리 (common_code facility_distance 그룹)
- 넛지별 점수 분포 히스토그램
- 가중치 변경 이력 (변경 전/후 비교)

### 3.6 지식베이스 관리
- 업로드된 PDF 문서 목록 (기존 /api/knowledge/list 활용)
- PDF 업로드 (기존 /api/knowledge/upload 활용)
- 문서 삭제 (기존 /api/knowledge/{doc_id} 활용)
- ChromaDB 청크 현황 (문서별 청크 수)

### 3.7 공통코드 관리
- 코드 그룹 목록 (기존 /api/codes 활용)
- 그룹 선택 시 코드 목록 조회
- 코드 추가/수정/삭제 (CRUD)
- 주요 그룹: sigungu, feedback_tag, nudge_weight, facility_distance, facility_max_distance

## 4. 프론트엔드 구조

```
web/admin/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── main.tsx                  # 진입점
│   ├── App.tsx                   # 라우터 + 사이드바 레이아웃
│   ├── config.ts                 # API_BASE 설정
│   ├── components/
│   │   ├── Sidebar.tsx           # 접이식 아이콘 사이드바
│   │   ├── KpiCard.tsx           # KPI 카드 (재사용)
│   │   ├── DataTable.tsx         # 범용 데이터 테이블 (페이지네이션, 정렬)
│   │   ├── ProgressBar.tsx       # 프로그레스 바 (데이터 품질)
│   │   ├── StatusBadge.tsx       # 상태 배지 (성공/경고/실패)
│   │   └── ConfirmDialog.tsx     # 확인 다이얼로그 (삭제 등)
│   ├── pages/
│   │   ├── Dashboard.tsx         # 운영 대시보드
│   │   ├── DataManagement.tsx    # 데이터 관리
│   │   ├── BatchMonitor.tsx      # 배치 모니터링
│   │   ├── Feedback.tsx          # 사용자 피드백
│   │   ├── Scoring.tsx           # 스코어링/가중치
│   │   ├── Knowledge.tsx         # 지식베이스
│   │   └── CommonCode.tsx        # 공통코드
│   ├── hooks/
│   │   ├── useAdminApi.ts        # 관리자 API 호출 훅
│   │   └── usePagination.ts      # 페이지네이션 훅
│   └── types/
│       └── admin.ts              # 관리자 전용 타입
```

## 5. 백엔드 API 추가

### 새 라우터: `web/backend/routers/admin.py`

```
GET  /api/admin/dashboard/summary     # KPI 카드 데이터
GET  /api/admin/dashboard/quality     # 테이블별 데이터 품질
GET  /api/admin/data/{table}          # 테이블 데이터 조회 (페이지네이션)
GET  /api/admin/data/stats            # 테이블별 레코드 수/NULL 비율
GET  /api/admin/batch/history         # 배치 실행 이력
GET  /api/admin/batch/logs/{filename} # 배치 로그 상세
POST /api/admin/batch/trigger         # 수동 배치 실행
GET  /api/admin/feedback/list         # 피드백 목록 (필터/페이지네이션)
GET  /api/admin/feedback/trend        # 만족도 추이
GET  /api/admin/scoring/weights       # 가중치 조회
PUT  /api/admin/scoring/weights       # 가중치 수정
GET  /api/admin/scoring/distribution  # 점수 분포
POST /api/admin/codes/{group}         # 코드 추가
PUT  /api/admin/codes/{group}/{code}  # 코드 수정
DELETE /api/admin/codes/{group}/{code} # 코드 삭제
```

기존 API 재사용:
- `/api/dashboard/*` → 거래 추이 차트
- `/api/chat/feedback/stats` → 피드백 통계
- `/api/knowledge/*` → 지식베이스 CRUD
- `/api/codes/*` → 코드 조회
- `/api/nudge/weights` → 넛지 가중치 조회

## 6. 디자인 시스템

| 요소 | 값 |
|------|-----|
| 사이드바 배경 | #0f172a (slate-900) |
| 브랜드 색상 | #fbbf24 (amber-400) |
| 주색상 | #2563eb (blue-600) |
| 성공 | #16a34a (green-600) |
| 경고 | #f59e0b (amber-500) |
| 실패 | #dc2626 (red-600) |
| 콘텐츠 배경 | #f1f5f9 (slate-100) |
| 카드 배경 | #ffffff |
| 카드 라운드 | 10px |
| 카드 그림자 | 0 1px 3px rgba(0,0,0,0.06) |
| 사이드바 너비 | 접힘: 56px, 펼침: 200px |

## 7. 범위 외 (추후)

- 역할 기반 접근 제어 (RBAC, 다중 관리자)
- 실시간 알림 (WebSocket 기반 배치 실패 알림)
- API 성능 모니터링 (응답 시간, 에러율)
- 다크 모드
- 배치 스케줄 편집 (GitHub Actions cron 수정)
