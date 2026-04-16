# Backend Rules (FastAPI + psycopg2)

## 배포 환경 제약
- Railway 배포 시 `web/backend/` 디렉토리만 존재함
- **web/backend/ 코드에서 batch/, apt_eda/ 등 프로젝트 루트의 외부 모듈을 직접 import 금지**
- 모듈 간 공유 데이터는 DB 테이블로 관리 (예: sigungu_code 테이블)
- sys.path 조작으로 외부 모듈을 import하는 것도 금지 (배포 환경에서 동작하지 않음)

## 라우터 (web/backend/routers/)
- `apartments.py` — 아파트 목록/검색 (뷰포트 기반, 키워드 검색)
- `nudge.py` — 넛지 스코어링 (라이프스타일 기반 추천)
- `detail.py` — 아파트 상세 정보
- `chat.py` — AI 챗봇 (SSE 스트리밍)
- `knowledge.py` — 지식 베이스 관리 (PDF 업로드, RAG)
- `commute.py` — 출퇴근 시간 계산
- `feedback.py` — 사용자 피드백 수집

새 라우터 추가 시: `main.py`에 `app.include_router(xxx.router, prefix="/api")` 등록.

## 서비스 (web/backend/services/)
- `scoring.py` — NUDGE_WEIGHTS, distance_to_score(), calculate_nudge_score()
- `chat_engine.py` — ChatEngine 클래스 (LLM 오케스트레이션)
- `tools.py` — LLM tool 정의 (search_apartments, get_apartment_detail, search_commute, compare_apartments, get_market_trend, get_school_info)
- `rag.py` — ChromaDB 기반 RAG 검색
- `knowledge_manager.py` — PDF 처리, 지식 베이스 CRUD

## LLM 모델 변경 규칙 (필수)

`LLM_MODEL` 또는 프로바이더 기본 모델을 변경할 때는 반드시 다음 절차를 모두 거친다.

### 절차 (체크리스트)
- [ ] 1. 모델 공식 문서에서 파라미터 호환성 확인
  - `temperature` 자유 설정 가능 여부 (gpt-5 계열은 1만 허용)
  - 토큰 한도 파라미터명 (`max_tokens` vs `max_completion_tokens`)
  - tool/function calling 지원 여부
  - streaming 지원 여부
- [ ] 2. `web/backend/services/llm/model_registry.py` 의 `MODEL_CAPABILITIES` 에 새 모델 등록
  - provider, temperature 정책, token_param, supports_tools, supports_streaming, notes 모두 채울 것
- [ ] 3. 프로바이더 코드(`openai_provider.py` 등)는 레지스트리 함수(`get_caps`, `supports_custom_temperature`, `get_token_param_name`)를 사용해 호출 파라미터를 동적으로 구성. 모델명 하드코딩 금지.
- [ ] 4. `.venv/bin/python -m scripts.llm_smoke_test` 실행 → 4단계(레지스트리/chat/chat_with_tools/stream_chat) 모두 PASS 확인
- [ ] 5. 위 4단계 모두 통과하지 못하면 커밋·배포 금지

### 왜 이렇게 하는가
- gpt-5 계열은 OpenAI Chat Completions API에서 `temperature` 와 `max_tokens` 파라미터 동작이 다름 → 기존 코드 그대로 모델만 바꾸면 BadRequestError 발생
- 스트리밍 예외는 SSE 본문으로 흘러 HTTP 200으로 보이므로 액세스 로그만 보면 발견 어려움 → 사전 검증 필수
- 신규 모델은 model_registry 에 등록되지 않은 상태로 기동되면 즉시 ValueError 로 차단됨 (런타임 안전망)
- `llm/` — LLM 프로바이더 추상화
  - `base.py` — BaseLLMProvider, Tool 클래스
  - `factory.py` — get_llm_provider() (LLM_PROVIDER 환경변수)
  - `openai_provider.py`, `claude_provider.py`, `gemini_provider.py`

## DB 연결 패턴
```python
# 읽기 (autocommit=True)
conn = DictConnection()
rows = conn.execute("SELECT ... WHERE col = %s", [value]).fetchall()
conn.close()

# 트랜잭션이 필요한 경우
conn = get_connection()  # autocommit=False
try:
    cur = conn.cursor()
    cur.execute("INSERT INTO ...", [...])
    conn.commit()
finally:
    conn.close()
```

## 테이블 스키마 (11개)
| 테이블 | PK | 설명 |
|--------|-----|------|
| apartments | pnu | 건물 마스터 (좌표, 세대수, 준공일) |
| facilities | facility_id | 시설 마스터 (유형, 좌표) |
| apt_facility_summary | (pnu, facility_subtype) | 시설별 거리/개수 집계 |
| trade_history | id (SERIAL) | 매매 이력 |
| rent_history | id (SERIAL) | 전월세 이력 |
| trade_apt_mapping | apt_seq | 거래↔아파트 매핑 |
| school_zones | pnu | 학군 정보 |
| apt_price_score | pnu | 가격 점수/전세비율 |
| apt_safety_score | pnu | CCTV 기반 안전 점수 (cctv_count_500m, nearest_cctv_m 포함) |
| population_by_district | (sigungu_code, age_group) | 인구 통계 |

## SQL 규칙
- 파라미터 바인딩: `%s` 필수 (SQL injection 방지). 문자열 포매팅 절대 금지.
- LIKE 패턴: `LIKE %s` + `[f'%{keyword}%']` (파라미터로 전달)
- 연결은 반드시 close() 호출 또는 with 문 사용.
- DictConnection 결과는 `dict` — `row['column_name']`으로 접근.

## 테스트
- 위치: `web/backend/tests/test_core.py` (단일 파일)
- 실행: `.venv/bin/python web/backend/tests/test_core.py` (프로젝트 루트에서)
- 패턴: `@test("설명")` 데코레이터 사용
- 요구사항: 라이브 DB 연결 필요 (테스트 DB 아닌 실제 DB 사용)

```python
@test("필터: 준공연도 2011년 이후")
def test_filter_built_after():
    conn = DictConnection()
    rows = conn.execute("SELECT ... WHERE ... >= %s", [2011]).fetchall()
    conn.close()
    for r in rows:
        assert int(r['use_apr_day'][:4]) >= 2011
```

## 에러 처리
- FastAPI HTTPException 사용
- 상세 에러 메시지 한국어 가능
