# 배치 작업 및 데이터 동기화 가이드

## 개요

집토리 서비스의 데이터를 최신 상태로 유지하기 위한 배치 수집/갱신 파이프라인과 Railway↔로컬 DB 동기화 워크플로우.

---

## 1. 배치 수집 파이프라인

### 구조

```
batch/
├── run.py                    # CLI 진입점 (--type weekly|quarterly|annual)
├── config.py                 # DB URL, API 키, rate limit
├── db.py                     # DB 연결 헬퍼
├── logger.py                 # 로깅 + BatchResult
├── verify.py                 # 배치 후 검증 쿼리
├── sync_from_railway.py      # Railway → 로컬 동기화
├── initial_collect.py        # 비수도권 초기 수집 (체크포인트 분할)
├── nationwide_codes.py       # 전국 시군구 코드 목록
├── weekly/                   # 거래 데이터 (12시간 간격)
│   ├── collect_trades.py     # API 수집 (RTMSDataSvc)
│   ├── load_trades.py        # 중복 제거 후 DB 적재
│   └── recalc_price.py       # apt_price_score 재계산
├── quarterly/                # 시설 데이터 (분기별)
│   ├── collect_facilities.py # 시설 6종 API 수집
│   ├── update_facilities.py  # facilities 테이블 UPSERT
│   └── recalc_summary.py     # BallTree 집계 + 안전점수
└── annual/                   # 인구/범죄 (연 1회)
    ├── collect_stats.py      # KOSIS 인구 + 경찰청 범죄
    └── update_stats.py       # population/crime 테이블 갱신
```

### 스케줄

| 배치 | 주기 | GitHub Actions | 대상 DB |
|------|------|---------------|---------|
| Weekly (거래) | 12시간 | `batch-weekly.yml` (`0 3,15 * * *`) | Railway |
| Quarterly (시설) | 분기 첫째날 | `batch-quarterly.yml` (`0 18 1 1,4,7,10 *`) | Railway |
| Annual (인구/범죄) | 1월 15일 | `batch-annual.yml` (`0 19 15 1 *`) | Railway |
| 초기 수집 (비수도권) | 매일 | `batch-initial-collect.yml` (`0 15 * * *`) | Railway |

### CLI 실행 방법

```bash
# Weekly: 거래 데이터 증분 수집 → 적재 → 가격 점수 재계산
.venv/bin/python -m batch.run --type weekly

# Quarterly: 시설 수집 → DB 갱신 → BallTree 집계
.venv/bin/python -m batch.run --type quarterly

# Annual: 인구/범죄 수집 → DB 갱신
.venv/bin/python -m batch.run --type annual

# Dry-run (수집만, DB 적재 안 함)
.venv/bin/python -m batch.run --type weekly --dry-run

# 비수도권 초기 수집 (일 900콜 제한)
.venv/bin/python -m batch.initial_collect --max-calls 900
```

### 로컬에서 Railway DB에 직접 실행

```bash
DATABASE_URL=$RAILWAY_DATABASE_URL .venv/bin/python -m batch.run --type weekly
```

---

## 2. 데이터 수집 범위

### 거래 데이터 (trade_history / rent_history)

| 구분 | 시군구 수 | 기간 | 건수 |
|------|----------|------|------|
| 수도권 (서울/경기/인천) | 74개 | 2016~2026 (10년) | 매매 236만 + 전월세 553만 |
| 비수도권 (부산~제주) | 165개 | 2023~2026 (3년) | 수집 진행 중 |
| **전국 합계** | **239개** | | **830만+** |

### 비수도권 초기 수집 진행 상황

- **전체**: 6,600쌍 (165개 시군구 × 40개월)
- **일일 한도**: API 1,000콜 → 450쌍/일
- **완료까지**: 약 14일
- **체크포인트**: `common_code` 테이블 (`group_id='initial_collect_checkpoint'`)에 저장
- GitHub Actions가 매일 자동 실행하여 Railway DB에 적재

### API 정보

| API | 용도 | Rate Limit |
|-----|------|-----------|
| RTMSDataSvcAptTradeDev | 매매 실거래가 | 0.15초/건, 일 1,000콜 |
| RTMSDataSvcAptRent | 전월세 실거래가 | 0.15초/건, 일 1,000콜 |
| data.go.kr (시설) | 병원, CCTV, 편의점 등 | 0.2초/건 |
| KOSIS | 인구/범죄 통계 | 2초/건, 일 120콜 |

---

## 3. Railway ↔ 로컬 동기화

### 동기화 방향

```
GitHub Actions → Railway DB (프로덕션, 마스터)
                     ↓ 동기화
               로컬 DB (개발/테스트)
```

Railway가 마스터 DB. 배치는 Railway에 직접 적재하고, 로컬은 필요 시 동기화.

### 동기화 모드

| 모드 | 명령 | 소요 시간 | 용도 |
|------|------|----------|------|
| **증분** (기본) | `.venv/bin/python -m batch.sync_from_railway` | **수 초** | 배치 후 신규 건만 동기화 |
| **전체** | `.venv/bin/python -m batch.sync_from_railway --mode full` | **~9분** | 스키마 변경, 전체 재동기화 |

### 증분 동기화 원리

1. `common_code` 테이블에서 마지막 동기화 시각 조회 (`group_id='sync_checkpoint'`)
2. Railway에서 `created_at > 마지막 시각`인 행만 SELECT
3. 로컬에 INSERT
4. 동기화 시각 갱신

### 전체 동기화 원리

1. `pg_dump`로 Railway DB 백업 (455MB custom format)
2. `pg_restore`로 로컬 DB에 복원 (--clean --if-exists)
3. 정합성 검증 (테이블별 건수 비교)

### 주의사항

- 전체 동기화 시 로컬 데이터가 Railway 데이터로 **완전 교체**됨
- `pg_dump` 버전이 Railway PostgreSQL 버전(18.x) 이상이어야 함
  - macOS: `brew install postgresql@18`
  - 경로: `/opt/homebrew/opt/postgresql@18/bin/pg_dump`
- 증분 동기화는 `trade_history`, `rent_history`만 대상 (created_at 컬럼 필요)
- `apartments`, `common_code` 등 다른 테이블 변경은 `--mode full` 필요

---

## 4. GitHub Actions 설정

### 필수 Secrets

Repository Settings > Secrets and variables > Actions:

| Secret | 설명 |
|--------|------|
| `RAILWAY_DATABASE_URL` | Railway PostgreSQL 연결 문자열 |
| `DATA_GO_KR_API_KEY` | 공공데이터포털 API 인증키 |
| `KAKAO_API_KEY` | 카카오 API 키 (시설 지오코딩용) |

### Secrets 설정 방법

```bash
# .env에서 직접 설정
grep RAILWAY_DATABASE_URL .env | cut -d= -f2- | gh secret set RAILWAY_DATABASE_URL
grep DATA_GO_KR_API_KEY .env | cut -d= -f2- | gh secret set DATA_GO_KR_API_KEY
grep KAKAO_API_KEY .env | cut -d= -f2- | gh secret set KAKAO_API_KEY
```

### 수동 실행

```bash
# 특정 워크플로우 수동 트리거
gh workflow run batch-initial-collect.yml
gh workflow run batch-weekly.yml

# 실행 상태 확인
gh run list --workflow=batch-initial-collect.yml --limit 3

# 실행 로그 확인
gh run view <run_id> --log
```

### 초기 수집 완료 후

`batch-initial-collect.yml`의 schedule을 주석 처리하거나 삭제하여 비활성화:

```yaml
on:
  # schedule:
  #   - cron: '0 15 * * *'
  workflow_dispatch:  # 수동 실행은 유지
```

---

## 5. 데이터 흐름 전체 다이어그램

```
┌─────────────────────────────────────────────────────────────┐
│                    데이터 소스 (API)                          │
│  data.go.kr (거래/시설)  │  KOSIS (인구/범죄)  │  Kakao (지오코딩)  │
└───────────┬─────────────┴──────────────┬───────────────────┘
            │                            │
            ▼                            ▼
┌─────────────────────────────────────────────────────────────┐
│              GitHub Actions (배치 실행)                       │
│  batch-weekly (12h) │ batch-quarterly │ batch-initial-collect │
└───────────┬─────────┴────────────────┴──────────────────────┘
            │
            ▼
┌─────────────────────────┐     sync_from_railway      ┌──────────────┐
│    Railway DB (마스터)    │ ─────────────────────────▶ │   로컬 DB     │
│  PostgreSQL 18.x        │     증분(수초)/전체(9분)     │  PostgreSQL   │
│  trade_history 253만    │                             │              │
│  rent_history 586만     │                             │              │
└───────────┬─────────────┘                             └──────────────┘
            │
            ▼
┌─────────────────────────┐
│    서비스 (Railway)       │
│  FastAPI + Cloudflare    │
│  지도/대시보드/챗봇       │
└─────────────────────────┘
```

---

## 6. 트러블슈팅

### 배치 실패 시

```bash
# GitHub Actions 로그 확인
gh run list --workflow=batch-initial-collect.yml --limit 3
gh run view <run_id> --log-failed

# 체크포인트 확인
.venv/bin/python -c "
from batch.db import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute(\"SELECT extra FROM common_code WHERE group_id = 'initial_collect_checkpoint'\")
print(cur.fetchone())
conn.close()
"
```

### 동기화 불일치 시

```bash
# 건수 비교
.venv/bin/python << 'EOF'
import os, psycopg2
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(".env"))
for label, key in [("로컬", "DATABASE_URL"), ("Railway", "RAILWAY_DATABASE_URL")]:
    conn = psycopg2.connect(os.getenv(key))
    cur = conn.cursor()
    for t in ["trade_history", "rent_history"]:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"{label} {t}: {cur.fetchone()[0]:,}")
    conn.close()
EOF

# 전체 재동기화
.venv/bin/python -m batch.sync_from_railway --mode full
```

### pg_dump 버전 불일치

```bash
# Railway PostgreSQL 버전 확인 후 맞는 클라이언트 설치
brew install postgresql@18
# 스크립트가 자동으로 /opt/homebrew/opt/postgresql@18/bin/pg_dump 사용
```
