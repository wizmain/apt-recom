# Project: 집토리 — 아파트 추천 서비스

## Tech Stack
- Backend: FastAPI (Python 3.12), psycopg2 (raw SQL), PostgreSQL
- Frontend: React 19, TypeScript, Vite 8, Tailwind CSS 4, axios
- LLM: OpenAI / Anthropic Claude / Google Gemini (factory 패턴)
- Vector DB: ChromaDB (RAG용)
- Map: Kakao Maps SDK
- Charts: Recharts

## 가상환경 규칙 (uv + 단일 .venv)
- 가상환경은 워크스페이스 루트의 `.venv`만 사용합니다.
- `.venv`가 존재하면 절대로 새로 생성하지 않습니다.
- 프로젝트 내부에 `.venv`를 만들지 않습니다.
- uv 실행 및 패키지 관리는 항상 루트 기준으로 수행합니다.
- 실행 전 반드시 루트 `.venv` 사용 여부를 확인합니다.

## 디렉토리 구조
```
apt-recom/                          # 워크스페이스 루트, .venv 여기에 위치
├── web/backend/                    # FastAPI 백엔드
│   ├── main.py                     # FastAPI app 진입점
│   ├── database.py                 # DB 연결 (psycopg2 raw SQL)
│   ├── routers/                    # API 라우터 (7개)
│   ├── services/                   # 비즈니스 로직 + LLM
│   └── tests/test_core.py          # 통합 테스트
├── web/frontend/                   # React + Vite 프론트엔드
│   └── src/
│       ├── components/             # 컴포넌트 (11개, flat 구조)
│       ├── hooks/                  # 커스텀 훅 (3개)
│       └── types/                  # TypeScript 타입
├── apt_eda/                        # 데이터 수집/분석 모듈
└── .env                            # 환경변수 (gitignore)
```

## 실행 정책

| 항목 | 명령 |
|------|------|
| **cwd** | 항상 프로젝트 루트 (`apt-recom/`) |
| **백엔드 서버** | `cd web/backend && ../../.venv/bin/uvicorn main:app --reload --port 8000` |
| **프론트엔드** | `cd web/frontend && npm run dev` |
| **백엔드 테스트** | `.venv/bin/python web/backend/tests/test_core.py` |
| **타입 체크** | `cd web/frontend && npm run check` |
| **린트** | `cd web/frontend && npm run lint` |
| **프론트 빌드** | `cd web/frontend && npm run build` |
| **의존성 추가 (Python)** | `uv pip install {패키지}` + `requirements.txt` 수동 업데이트 |
| **의존성 추가 (JS)** | `cd web/frontend && npm install {패키지}` |
| **Python 포맷** | `ruff format {파일}` / `ruff check --fix {파일}` |
| **Railway→로컬 동기화 (증분)** | `.venv/bin/python -m batch.sync_from_railway` |
| **Railway→로컬 동기화 (전체)** | `.venv/bin/python -m batch.sync_from_railway --mode full` |
| **비수도권 초기 수집** | `.venv/bin/python -m batch.initial_collect --max-calls 900` |
| **배치 실행 (weekly)** | `.venv/bin/python -m batch.run --type weekly` |
| **배치 실행 (quarterly)** | `.venv/bin/python -m batch.run --type quarterly` |
| **배치 실행 (annual)** | `.venv/bin/python -m batch.run --type annual` |

## 데이터베이스 규칙
- **ORM 없음**: raw SQL + psycopg2. SQLAlchemy, Alembic 사용하지 않음.
- **연결**: `DictConnection()` — autocommit=True, RealDictCursor 반환.
- **파라미터**: `%s` placeholder 사용 (psycopg2 형식). `?` 사용 금지.
- **스키마**: `web/backend/database.py`의 `create_tables()` 함수에 정의.
- **마이그레이션**: 별도 프레임워크 없음. 스키마 변경 시 `create_tables()` 수정 + ALTER TABLE SQL 작성.
- **주요 테이블**: apartments, facilities, apt_facility_summary, trade_history, rent_history, trade_apt_mapping, school_zones, apt_price_score, apt_safety_score, population_by_district, chat_feedback

## 데이터베이스 설계 원칙

### 정규화 & 무결성
- 제3정규형(3NF) 이상 유지 — 동일 데이터가 2곳 이상에 존재하면 정규화 검토
- 모든 테이블에 명확한 PK 정의 — 자연키 우선, 불가능 시 대리키(SERIAL)
- 대리키(SERIAL) 사용 시 비즈니스 키에 UNIQUE 제약조건 필수
  — 예: trade_history는 id(PK) + (sgg_cd, apt_nm, area, floor, year, month, day, amount)(UNIQUE)
- 외래키 관계가 존재하면 FK 제약조건 또는 최소한 인덱스로 참조 무결성 보장
- ENUM성 값은 common_code 테이블로 관리 — 코드에 하드코딩 금지

### 컬럼 설계
- 컬럼명은 snake_case, 의미를 명확히 드러내는 접두어 사용 (score_, count_, avg_)
- 금액은 정수(만원 단위), 면적은 DOUBLE PRECISION(㎡), 좌표는 DOUBLE PRECISION
- 날짜/시간: 이력성 데이터는 created_at TIMESTAMPTZ DEFAULT NOW() 필수
- NULL 허용 컬럼은 보충 전략을 함께 설계 (어떤 프로세스가 채우는지 명시)

### 인덱스 설계
- 조회 패턴(WHERE, JOIN, ORDER BY)에 맞는 인덱스를 테이블 생성과 동시에 설계
- 복합 인덱스는 카디널리티 높은 컬럼을 앞에 배치
- UNIQUE 인덱스는 데이터 정합성 보호 수단 — 중복 방지가 필요한 곳에 반드시 적용

### 외부 데이터 연동
- 외부 API 코드는 실제 API 응답 기준으로 등록 (행정코드 ≠ API코드 주의)
- 데이터 수집과 보충을 분리 — 부분 데이터라도 먼저 적재 가능하게 설계
- 외부 수집 데이터는 원본 키를 보존하여 재수집/검증 가능하게 유지

### 테이블 생성 체크리스트
- [ ] PK 정의 + 비즈니스 키 UNIQUE 제약조건
- [ ] 증분 동기화용 created_at 컬럼
- [ ] NULL 허용 컬럼의 보충 전략
- [ ] 조회 패턴 기반 인덱스
- [ ] 관련 테이블과의 참조 관계 정리

## Architecture
아키텍처 변경 결정은 `docs/adr/`에 ADR로 기록한다.
새로운 구조 변경 시 기존 ADR을 참고하고, 새 ADR을 작성할 것.

## Backend Architecture
```
routers/ → services/ → database.py (raw SQL)
```
- **router**: HTTP 엔드포인트 정의. DictConnection으로 직접 쿼리하거나 service 호출.
- **services**: 비즈니스 로직 (scoring, chat_engine, rag, tools, knowledge_manager).
- **services/llm/**: LLM 프로바이더 추상화 (factory → base → openai/claude/gemini).
- 새 라우터 추가 시 `main.py`에 `app.include_router()` 등록 필수.

## Frontend Architecture
- **Flat component 구조**: 모든 컴포넌트는 `src/components/`에 위치.
- **Custom hooks**: `src/hooks/` (useApartments, useChat, useNudge).
- **API 호출**: axios + `API_BASE` from `src/config.ts`.
- **스타일**: Tailwind CSS utility classes.

## Subagent 실행 순서 (복합 작업 시)
1. db-architect → 스키마/테이블 변경 (전제조건)
2. api-developer → API 구현 (스키마 의존)
3. frontend-developer → UI 구현 (API 의존)
4. test-writer → 테스트 작성 (구현 완료 후)
5. code-reviewer → 리뷰 (Read-only, 최후)
단일 영역 작업은 해당 에이전트만 직접 호출.

## Code Standards
- Python: ruff (format + check), snake_case
- TypeScript: ESLint, camelCase (변수/함수), PascalCase (컴포넌트)
- 커밋: Conventional Commits (feat:, fix:, refactor:, docs:, test:)
- 한국어 주석 허용, 변수/함수명은 영어

## 변수/키 명명 규칙
- 모든 변수명, dict 키, DB 컬럼명, API 필드명은 알파벳 소문자로 시작해야 한다
- underscore(_) prefix는 Python 내부 전용(private) 변수에만 사용하고, API 응답/DB 데이터/프론트엔드에 노출되는 값에는 사용 금지
- 외부로 전달되는 모든 이름은 snake_case를 따르며, 의미를 명확히 드러내는 접두어를 사용한다 (예: score_, count_, avg_)

## 코딩 원칙
- 코드 작성 전 반드시 영향 범위와 컴포넌트 구조를 먼저 설명하고 승인 후 진행
- 하나의 함수/컴포넌트가 여러 역할을 하면 분리 (단일 책임 원칙)
- 동일한 데이터/로직이 2곳 이상에서 사용되면 공통 모듈로 추출
- 조건부 렌더링은 분기 로직과 UI를 분리하여 가독성 확보
- 새 기능 추가 시 기존 코드에 끼워넣지 말고 독립 컴포넌트/함수로 작성

## 작업 프로세스
- 3개 이상 파일을 수정하는 작업은 반드시 구조 설계를 먼저 제시하고 승인 후 코딩
- 구조 설계에 포함할 내용: 컴포넌트/함수 분리 방안, 데이터 흐름, 재사용 계획
- 기존 코드에 조건문(if viewMode === ...)을 추가하는 대신 컴포넌트 분리를 우선 검토

## Git Workflow
- main 브랜치 직접 push 금지
- 브랜치명: feature/, bugfix/, hotfix/ 접두어

## 금지 사항
- .env 파일 git 커밋 (.env.example만 추적)
- rm -rf, DROP DATABASE, DROP TABLE 등 파괴적 명령
- pip install / pip3 install (uv pip install 사용)
- 하위 디렉토리에 별도 .venv 생성
- production DB 직접 접속 (Railway)
- any 타입 사용 (TypeScript)
- useEffect 내 직접 API 호출 (hooks 패턴 사용)
- 문서/코드에 "Generated with Claude Code" 문구 삽입 금지
- Git 커밋 메시지에 Co-Authored-By: Claude 등 AI 작업자 표기 금지
