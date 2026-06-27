# service-planner 에이전트 설계

작성일: 2026-06-27
상태: 승인 대기

## 목적

apt-recom(집토리) 서비스 **기획 보조** Claude Code 서브에이전트. 기능 아이디어를
**구현 인지형 PRD**로 변환해, 기존 구현 에이전트 fleet의 앞단(기획 → 구현)에 둔다.

- 사용자: 개발/기획 담당(프로젝트 소유자)
- 핵심 작업: 아이디어 → PRD/기획서
- 배치 위치: db-architect → api-developer → frontend-developer → test-writer 파이프라인의 **앞단**

## 생성 방식

기존 5개 에이전트와 동일하게 **`.claude/agents/service-planner.md`** 단일 정의 파일로
생성한다(frontmatter + 시스템 프롬프트). harness 메타 스킬이나 슬래시 커맨드가 아니라,
fleet과의 일관성을 위해 기존 에이전트 파일 패턴을 따른다.

## 역할 / 경계

- **담당**: 아이디어 → 구현 인지형 PRD 작성. 레포 탐색으로 실현가능성 분석,
  fleet 핸드오프 구조화. **읽기 + PRD 문서 작성만.**
- **비담당**: 실제 구현(스키마=db-architect / API=api-developer / UI=frontend-developer
  / 테스트=test-writer), 코드 수정·실행·배포.

## 도구 / 모델

- `tools: Read, Grep, Glob, Write` — 코드 수정/실행 없음(Edit·Bash 제외, 순수 기획자).
- `model: opus` — 설계 추론 깊이가 필요한 기획 역할.

## PRD 산출물 구조 (fleet 매핑)

1. 배경/문제 (왜 — 사용자/비즈니스 관점)
2. 목표/성공지표 (측정가능, YAGNI로 범위 압축)
3. 사용자 스토리/시나리오
4. 범위 (In/Out of scope)
5. 현재 구현 분석 — 레포 근거(관련 스키마·API·컴포넌트 실제 인용)
6. 변경 설계 (핸드오프별)
   - DB → db-architect: 테이블/컬럼/인덱스
   - API → api-developer: 엔드포인트/Pydantic 스키마
   - FE → frontend-developer: 컴포넌트/화면/데이터흐름
   - Test → test-writer: 핵심 검증 케이스
7. 데이터/외부의존 (공공데이터 등)
8. 리스크/오픈이슈
9. 작업 순서 + 추정 (db → api → fe → test)

## 레포 탐색 방식 (근거 기반)

- 스키마: `web/backend/database.py` (`create_tables()`, `create_indexes()`)
- API: `web/backend/routers/`, `web/backend/services/`
- FE: `web/frontend-next/src/` (컴포넌트·훅). 레거시 `web/frontend`는 참고만.
- 맥락: `docs/adr/`, `docs/`, `chat_feedback`(사용자 피드백 테이블 — 스키마/용도만 참조)
- 원칙: 추측 금지, 실제 파일·테이블을 인용해 실현가능성 판단.

## 산출물 위치

- PRD: **`docs/prd/YYYY-MM-DD-<feature>.md`** (신규 디렉토리, PRD 전용).
- ADR(`docs/adr/`)은 **중요한 아키텍처 결정·변동사항** 기록용으로 분리.
  PRD가 그런 결정을 동반하면 PRD 내에 **"ADR 작성 권고"**를 명시(에이전트가 ADR을
  직접 쓰진 않음 — 결정 주체는 사람/구현 단계).

## Output (호출 측 반환, db-architect 패턴)

```json
{
  "prd_path": "docs/prd/2026-06-27-<feature>.md",
  "scope": "한 줄 요약",
  "handoff": {"db": [...], "api": [...], "frontend": [...], "test": [...]},
  "adr_recommended": false,
  "open_questions": [...],
  "recommended_order": ["db-architect", "api-developer", "frontend-developer", "test-writer"]
}
```

## 비목표 (YAGNI)

- 코드/스키마/UI 직접 작성, 명령 실행, 배포 — 각 구현 에이전트의 몫.
- ADR 직접 작성 — 권고만.
- 로드맵·백로그·우선순위 산출 — 이번 범위 밖(주 용도는 아이디어 → PRD).

## 구현

단일 파일 `.claude/agents/service-planner.md` 생성. 기존 에이전트 파일과 동일한
frontmatter/본문 컨벤션(한국어, 담당/비담당/Workflow/Rules/Output) 사용.
