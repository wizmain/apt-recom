# 집토리 (apt-recom)

라이프스타일 기반 아파트 추천 웹서비스. 서울·경기·인천 + 비수도권 아파트 데이터를 수집·분석하여 사용자 선호에 맞는 단지를 추천한다.

## 주요 기능

- **넛지 스코어링** — 교통·교육·안전·편의·가격 등 가중치 기반 라이프스타일 점수
- **지도 기반 탐색** — 카카오 지도 뷰포트 내 실시간 필터·검색
- **아파트 상세** — 실거래가 추이, 시설 접근성, 학군, 안전점수
- **AI 챗봇** — 자연어 질의로 아파트 검색/비교/통근 분석 (OpenAI·Claude·Gemini 지원)
- **RAG 지식베이스** — ChromaDB 기반 부동산 지식 검색
- **MCP 서버** — Model Context Protocol로 Claude Desktop·Cursor·Claude Code 등에 직접 노출

## 기술 스택

| 영역 | 스택 |
|---|---|
| Backend | FastAPI (Python 3.12), psycopg2 (raw SQL), PostgreSQL |
| Frontend | React 19, TypeScript, Vite 8, Tailwind CSS 4 |
| Frontend (Next) | Next.js 16 (OpenNext Cloudflare Workers 배포) |
| LLM | OpenAI / Anthropic Claude / Google Gemini (factory 패턴) |
| Vector DB | ChromaDB |
| Map | Kakao Maps SDK |
| 배포 | Railway (backend+DB), Cloudflare Workers (frontend-next) |

## 디렉토리 구조

```
apt-recom/
├── .venv/                    # 루트 단일 가상환경 (uv 관리)
├── web/
│   ├── backend/              # FastAPI 백엔드 (Railway 배포 단위)
│   │   ├── main.py
│   │   ├── database.py       # DictConnection, 스키마 정의
│   │   ├── mcp_server.py     # MCP (Model Context Protocol) 서버
│   │   ├── routers/          # API 라우터
│   │   ├── services/         # 비즈니스 로직 + LLM
│   │   └── tests/test_core.py
│   ├── frontend/             # React + Vite (레거시)
│   └── frontend-next/        # Next.js 16 (신규)
├── batch/                    # 데이터 수집/동기화 배치
├── apt_eda/                  # EDA·전처리 모듈
├── docs/                     # ADR, ERD, 설계 문서
└── scripts/                  # 운영/검증 스크립트
```

## 빠른 시작

### 사전 요구사항

- Python 3.12, [uv](https://github.com/astral-sh/uv)
- Node.js 20+
- PostgreSQL 접근 권한 (로컬 또는 Railway)
- `.env` 파일 (`.env.example` 참고)

### 설치

```bash
# 가상환경은 루트 .venv 하나만 사용 (하위 디렉토리 생성 금지)
uv venv
uv pip install -r requirements.txt

# 프론트엔드 (React)
cd web/frontend && npm install
# 프론트엔드 (Next.js)
cd web/frontend-next && npm install
```

### 실행

| 항목 | 명령 |
|---|---|
| 백엔드 | `cd web/backend && ../../.venv/bin/uvicorn main:app --reload --port 8000` |
| 프론트엔드 (React) | `cd web/frontend && npm run dev` |
| 프론트엔드 (Next) | `cd web/frontend-next && npm run dev` |
| 백엔드 테스트 | `.venv/bin/python web/backend/tests/test_core.py` |
| 타입 체크 | `cd web/frontend && npm run check` |
| 린트 | `cd web/frontend && npm run lint` |

### 데이터 동기화

```bash
# Railway → 로컬 증분 동기화
.venv/bin/python -m batch.sync_from_railway

# 전체 재동기화
.venv/bin/python -m batch.sync_from_railway --mode full

# 거래 데이터 배치
.venv/bin/python -m batch.run --type trade
```

## 아키텍처

### 백엔드 레이어

```
routers/ → services/ → database.py (raw SQL)
```

- **routers**: HTTP 엔드포인트 (apartments, nudge, detail, chat, knowledge, commute, feedback, dashboard, codes, similar, admin, log, sitemap)
- **services**: 비즈니스 로직 (scoring, chat_engine, rag, tools, knowledge_manager)
- **services/llm**: 프로바이더 추상화 (factory → base → openai/claude/gemini)
- **database**: `DictConnection` (autocommit + RealDictCursor), `%s` 파라미터 바인딩

ORM을 사용하지 않는다. 마이그레이션은 `database.py::create_tables()`의 `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`로 관리한다.

### 주요 테이블

| 테이블 | PK | 설명 |
|---|---|---|
| apartments | pnu | 건물 마스터 (좌표, 세대수) |
| facilities | facility_id | 시설 마스터 (15종) |
| apt_facility_summary | (pnu, subtype) | 시설별 거리/개수 집계 |
| trade_history / rent_history | id | 실거래 이력 |
| trade_apt_mapping | apt_seq | 거래 ↔ 아파트 매핑 |
| school_zones | pnu | 학군 정보 |
| apt_price_score | pnu | 가격 점수 / 전세가율 |
| apt_safety_score | pnu | CCTV 기반 안전 점수 |

## MCP 서버 (Model Context Protocol)

집토리는 [MCP](https://modelcontextprotocol.io/) 표준을 구현해 Claude Desktop·Cursor·Claude Code 등 MCP 클라이언트가 웹 크롤링 없이 아파트 데이터를 직접 조회할 수 있도록 한다.

- **엔드포인트**: `https://api.apt-recom.kr/mcp/`
- **Transport**: Streamable HTTP (MCP 2025-11-25 spec)
- **Auth**: 없음 (공개, stateless)
- **구현**: `web/backend/mcp_server.py` (공식 Python SDK `mcp==1.27.0`), `main.py` 에서 `app.mount("/mcp", mcp_asgi_app)`

### 제공 도구 (7종)

| 이름 | 설명 |
|---|---|
| `search_apartments` | 지역·단지명 키워드 + 라이프스타일 항목으로 NUDGE 스코어 순 추천 |
| `get_apartment_detail` | 단일 아파트 전체 프로필 (기본정보·점수·시설·학군·최근 거래) |
| `compare_apartments` | 2~5개 단지 매트릭스 비교 |
| `get_similar_apartments` | 위치/가격/라이프스타일/종합 기준 유사 단지 추천 |
| `get_market_trend` | 시군구 월별 거래량·평균가 추이 |
| `get_school_info` | 초·중·고 학군 배정 정보 |
| `get_dashboard_info` | 시군구 거래 동향 대시보드 |

### 클라이언트 연결

Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`) 또는 Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "apt-recom": {
      "url": "https://api.apt-recom.kr/mcp/"
    }
  }
}
```

Claude Code:

```bash
claude mcp add --transport http apt-recom https://api.apt-recom.kr/mcp/
```

### 로컬 개발

백엔드 기동 시 `http://localhost:8000/mcp/` 에서 동일 엔드포인트가 노출된다. MCP Inspector 로 검증:

```bash
npx @modelcontextprotocol/inspector
# 접속 URL: http://localhost:8000/mcp/  (Transport: Streamable HTTP)
```

상세 내용은 [`docs/mcp-server.md`](docs/mcp-server.md) 참고.

## 코드 규약

- **Python**: ruff (format + check), snake_case
- **TypeScript**: ESLint, `any` 금지, API 타입은 `src/types/`에 정의
- **커밋**: Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`)
- **네이밍**: 외부 노출 변수·DB 컬럼·API 필드는 소문자 시작 snake_case, `_` 접두어 금지
- **함수/컴포넌트**: 단일 책임 원칙, 조건 분기 누적 대신 분리

## 배포

- **Backend**: Railway (main 브랜치 자동 배포). `web/backend/` 디렉토리만 번들되므로 외부 모듈 import 금지.
- **Frontend (Next.js)**: Cloudflare Workers (OpenNext). PR 머지 시 자동 배포.
- **배치**: GitHub Actions 스케줄 (거래 수집, 주소 보충 등)

## 문서

- `docs/adr/` — 아키텍처 결정 기록 (ADR)
- `docs/erd.md` — 데이터베이스 ERD
- `docs/service-development-guide.md` — 개발 가이드
- `docs/nudge-scoring-system.md` — 넛지 스코어링 상세
- `docs/safety-score-v2.md` — 안전점수 v2 설계
- `docs/mcp-server.md` — MCP 서버 스펙 및 클라이언트 연동 가이드
- `PROGRESS.md` — Phase별 진행 현황

## 금지 사항

- `.env` 파일 커밋 (`.env.example`만 추적)
- `pip install` 직접 사용 — `uv pip install` 사용
- 하위 디렉토리에 별도 `.venv` 생성
- Production DB 직접 접속
- `any` 타입 (TypeScript)
- `useEffect` 내 직접 API 호출 (hooks 패턴 사용)
- `main` 브랜치 직접 push
