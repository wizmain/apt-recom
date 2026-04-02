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
