# 집토리 MCP 서버

집토리는 [Model Context Protocol](https://modelcontextprotocol.io/) 표준을 구현해, Claude Desktop · Cursor · Codex · Claude Code 같은 MCP 클라이언트가 집토리의 아파트 데이터를 직접 조회할 수 있게 한다. AAO(Assistive Agent Optimization) 관점에서 **웹 크롤링을 거치지 않고 agent에게 직접 푸시**하는 채널이다.

## 엔드포인트

- **URL**: `https://api.apt-recom.kr/mcp/`
- **Transport**: Streamable HTTP (MCP 2025-11-25 spec)
- **Auth**: 없음(공개). 요청 단위 CORS 전역 허용.
- **Stateless**: 세션 저장 없이 요청-응답만. 대규모 동시 접속 대응.

## 제공 도구 (7종)

| 이름 | 설명 |
|---|---|
| `search_apartments` | 지역·단지명 키워드 + 라이프스타일 항목으로 NUDGE 스코어 순 추천 |
| `get_apartment_detail` | 단일 아파트 전체 프로필 (기본정보·점수·시설·학군·최근 거래) |
| `compare_apartments` | 2~5개 단지 매트릭스 비교 |
| `get_similar_apartments` | 위치/가격/라이프스타일/종합 기준 유사 단지 추천 |
| `get_market_trend` | 지역(시군구) 월별 거래량·평균가 추이 |
| `get_school_info` | 아파트의 초·중·고 학군 배정 정보 (학교명·학군·교육지원청) |
| `get_dashboard_info` | 시군구 거래 동향 대시보드 — 이번 달/전월 요약 + 월별 추이 |

전체 스키마는 MCP 클라이언트의 `list_tools` 응답에서 확인.

## 클라이언트 설정

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) 또는 `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "apt-recom": {
      "url": "https://api.apt-recom.kr/mcp/"
    }
  }
}
```

저장 후 Claude Desktop 재시작. 대화 중 "🔧" 아이콘에서 apt-recom의 도구 5개가 보이면 연결 완료.

### Cursor

`~/.cursor/mcp.json` 또는 프로젝트 루트의 `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "apt-recom": {
      "url": "https://api.apt-recom.kr/mcp/"
    }
  }
}
```

Cursor 재시작 후 Composer에서 사용 가능.

### Claude Code

```bash
claude mcp add --transport http apt-recom https://api.apt-recom.kr/mcp/
```

### Python SDK (프로그래매틱 접근)

```python
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

async with streamablehttp_client("https://api.apt-recom.kr/mcp/") as (r, w, _):
    async with ClientSession(r, w) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool(
            "search_apartments",
            arguments={"keyword": "자양동", "nudges": ["commute", "education"], "top_n": 5},
        )
```

## 로컬 개발

백엔드를 로컬에서 기동하면 `http://localhost:8000/mcp/` 에 MCP 엔드포인트가 노출된다. 클라이언트 설정에서 URL만 교체하면 된다.

```bash
cd web/backend
../../.venv/bin/uvicorn main:app --reload --port 8000
```

MCP Inspector 로 GUI 검증:

```bash
npx @modelcontextprotocol/inspector
# 접속 URL: http://localhost:8000/mcp/  (Transport: Streamable HTTP)
```

## 사용 예시 (agent 관점)

사용자: "강남구에서 출퇴근 좋은 아파트 3개 추천해줘."

agent 내부 동작:
1. `search_apartments(keyword="강남구", nudges=["commute"], top_n=3)` 호출
2. 반환된 JSON에서 상위 3개 단지 요약
3. 사용자에게 "쌍용플래티넘(94.4점), 미켈란107(93.5점), 논현프라임아파트(92.9점)…" 응답

사용자: "쌍용플래티넘 상세 알려줘."

agent:
1. `get_apartment_detail(query="쌍용플래티넘")` 호출
2. `basic`, `nudge_scores`, `facility_summary`, `school`, `recent_trades` 분석
3. 구조화된 요약 응답

## 서버 측 구현

- 파일: `web/backend/mcp_server.py`
- 의존성: `mcp==1.27.0` (공식 Python SDK)
- 마운트: `main.py` 에서 `app.mount("/mcp", mcp_asgi_app)`
- Lifespan: FastAPI 메인 lifespan 이 `_mcp.session_manager.run()` 을 감싸 관리
- Tool 실행: 기존 `services/tools.py` 의 async executor 를 얇게 래핑 (중복 코드 없음)

## 로드맵

- [ ] Rate limit / API key (관측 후 필요 시)
- [ ] 추가 tool: `search_commute` (ODSay API 의존 검토 후)
- [ ] MCP Resources: 자주 쓰는 지역 요약 문서 등
- [ ] MCP Prompts: 사용자 페르소나별 추천 템플릿
