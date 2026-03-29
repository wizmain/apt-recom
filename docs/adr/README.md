# Architecture Decision Records (ADR)

프로젝트의 주요 아키텍처 결정을 기록합니다.

## 형식

각 ADR은 다음 형식을 따릅니다:
- **상태**: 제안(Proposed) / 승인(Accepted) / 폐기(Deprecated) / 대체(Superseded)
- **날짜**: 결정이 내려진 날짜
- **맥락**: 결정이 필요했던 배경
- **결정**: 선택한 방안
- **근거**: 선택 이유와 트레이드오프
- **결과**: 결정으로 인한 영향

## 목록

| # | 제목 | 상태 | 날짜 |
|---|------|------|------|
| [001](001-raw-sql-over-orm.md) | ORM 대신 Raw SQL (psycopg2) 사용 | Accepted | 2026-03-21 |
| [002](002-sqlite-to-postgresql.md) | SQLite에서 PostgreSQL로 마이그레이션 | Accepted | 2026-03-21 |
| [003](003-llm-provider-abstraction.md) | LLM 프로바이더 추상화 (Factory 패턴) | Accepted | 2026-03-25 |
| [004](004-pre-aggregation-scoring.md) | 시설 스코어링 Pre-aggregation 전략 | Accepted | 2026-03-20 |
| [005](005-balltree-spatial-index.md) | BallTree 공간 인덱스로 거리 계산 | Accepted | 2026-03-20 |
| [006](006-sse-streaming-chatbot.md) | 챗봇 SSE 스트리밍 응답 | Accepted | 2026-03-25 |
| [007](007-flat-component-structure.md) | 프론트엔드 Flat 컴포넌트 구조 | Accepted | 2026-03-21 |
| [008](008-rag-chromadb-knowledge.md) | ChromaDB 기반 RAG 지식 베이스 | Accepted | 2026-03-25 |
| [009](009-viewport-based-loading.md) | 뷰포트 기반 마커 로딩 | Accepted | 2026-03-21 |
| [010](010-railway-cloudflare-deploy.md) | Railway + Cloudflare Pages 배포 | Accepted | 2026-03-21 |
| [011](011-group-pnu-dedup.md) | 동일 단지 중복 PNU 통합 (group_pnu) | Accepted | 2026-03-29 |
