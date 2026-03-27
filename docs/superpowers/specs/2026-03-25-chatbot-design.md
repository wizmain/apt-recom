# 아파트 추천 챗봇 설계

## 개요

기존 아파트 추천 웹서비스에 AI 챗봇을 추가하여 자연어 대화로 아파트 추천, 정보 조회, 비교 분석, 시장 트렌드, 부동산 정책 안내를 제공한다. RAG + DSPy로 PDF 기반 지식 검색을 지원하며, LLM 엔진을 OpenAI/Claude/Gemini로 자유롭게 전환할 수 있다.

## 기술 스택

| 영역 | 기술 |
|------|------|
| LLM | OpenAI GPT-4o (기본), Claude, Gemini (전환 가능) |
| Tool Calling | OpenAI function calling / Claude tool use / Gemini function declarations |
| RAG | DSPy + ChromaDB + OpenAI Embeddings |
| PDF 파싱 | PyMuPDF (fitz) |
| 청킹 | LangChain TextSplitters |
| 벡터DB | ChromaDB (로컬 persist) |
| 백엔드 | FastAPI (기존 서버 확장) |
| 프론트엔드 | React + TypeScript (기존 앱에 모달 추가) |

## 아키텍처

```
사용자 입력 (채팅 모달)
     ↓
FastAPI (/api/chat) — 스트리밍 응답
     ↓
┌─────────────────────────────────────────────┐
│         LLM Provider (추상화 레이어)           │
│         .env로 전환: openai|claude|gemini     │
├─────────────────────────────────────────────┤
│  Tool 1: search_apartments(keyword, nudges,  │
│           top_n, budget_max)                 │ → 넛지 스코어링 API
│  Tool 2: get_apartment_detail(query)         │ → DB 쿼리
│  Tool 3: compare_apartments(queries[])       │ → 복수 조회 + 비교
│  Tool 4: get_market_trend(region, period)    │ → 거래 통계
│  Tool 5: get_school_info(query)              │ → 학군 DB
│  Tool 6: search_knowledge(query)             │ → RAG 파이프라인
└─────────────────────────────────────────────┘
         │                       │
    [기존 DB/API]          [RAG 파이프라인]
    apt_web.db             ChromaDB + DSPy
```

## LLM 추상화 레이어

### 인터페이스

```python
class LLMProvider(ABC):
    @abstractmethod
    async def chat_with_tools(self, messages, tools, system_prompt) -> LLMResponse

    @abstractmethod
    async def embed(self, text) -> list[float]

    @abstractmethod
    async def stream_chat(self, messages, system_prompt) -> AsyncIterator[str]
```

### 구현체

| Provider | 채팅 모델 | 임베딩 모델 | Tool Calling |
|----------|----------|-----------|-------------|
| OpenAIProvider | gpt-4o | text-embedding-3-small | function calling |
| ClaudeProvider | claude-sonnet-4-20250514 | voyage-3 | tool use |
| GeminiProvider | gemini-2.0-flash | text-embedding-004 | function declarations |

### 전환 방법

```env
LLM_PROVIDER=openai          # openai | claude | gemini
LLM_MODEL=gpt-4o             # 모델 오버라이드 (선택)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...  # Claude 사용 시
GOOGLE_API_KEY=AI...          # Gemini 사용 시
```

### Tool 스키마 통일

내부 통일 포맷으로 Tool을 정의하고, 각 Provider가 자신의 API 형식으로 자동 변환:
- OpenAI: `{"type":"function", "function":{...}}`
- Claude: `{"name":"...", "input_schema":{...}}`
- Gemini: `{"function_declarations":[{...}]}`

## RAG 파이프라인

### 데이터 흐름

```
PDF 업로드 (/api/knowledge/upload)
     ↓
PyMuPDF: PDF → 텍스트/테이블 추출
     ↓
LangChain TextSplitter: 500~1000토큰 청킹
     ↓
LLMProvider.embed(): 벡터 변환
     ↓
ChromaDB: 벡터 저장 (로컬 persist)
```

### DSPy 파이프라인

```python
class ApartmentRAG(dspy.Module):
    def __init__(self):
        self.retrieve = dspy.Retrieve(k=5)
        self.generate = dspy.ChainOfThought("context, question -> answer")

    def forward(self, question):
        context = self.retrieve(question).passages
        answer = self.generate(context=context, question=question)
        return answer
```

### Knowledge Base 관리 API

```
POST   /api/knowledge/upload       — PDF 업로드 → 벡터DB 저장
GET    /api/knowledge/list         — 업로드된 문서 목록
DELETE /api/knowledge/{doc_id}     — 문서 삭제
```

## Tool 함수 정의

### Tool 1: search_apartments

```json
{
    "name": "search_apartments",
    "description": "넛지 기반 아파트 검색 및 추천. 지역, 라이프스타일, 예산 기반으로 최적 아파트를 찾습니다.",
    "parameters": {
        "keyword": "지역명 또는 단지명 (예: 자양동, 강남구)",
        "nudges": ["cost", "pet", "commute", "newlywed", "education", "senior", "investment", "nature"],
        "top_n": 5,
        "budget_max": null
    }
}
```
→ 기존 POST /api/nudge/score 호출

### Tool 2: get_apartment_detail

```json
{
    "name": "get_apartment_detail",
    "description": "특정 아파트의 상세 정보 (기본정보, 가격, 시설, 학군, 안전점수)",
    "parameters": {
        "query": "아파트명 또는 PNU"
    }
}
```
→ 아파트명으로 DB 검색 후 GET /api/apartment/{pnu} 호출

### Tool 3: compare_apartments

```json
{
    "name": "compare_apartments",
    "description": "2~5개 아파트를 비교 분석합니다",
    "parameters": {
        "queries": ["역삼2차아이파크", "청량리역 롯데캐슬"]
    }
}
```
→ 각 아파트 상세 조회 후 비교 테이블 생성

### Tool 4: get_market_trend

```json
{
    "name": "get_market_trend",
    "description": "지역별 시세 동향, 거래량 추이를 분석합니다",
    "parameters": {
        "region": "강남구",
        "period": "1year"
    }
}
```
→ trade_history에서 집계 쿼리

### Tool 5: get_school_info

```json
{
    "name": "get_school_info",
    "description": "학군 정보를 조회합니다 (배정 학교, 학교군, 교육지원청)",
    "parameters": {
        "query": "아파트명 또는 지역명"
    }
}
```
→ school_zones 테이블 쿼리

### Tool 6: search_knowledge

```json
{
    "name": "search_knowledge",
    "description": "부동산 정책, 세금, 투자 가이드 등 업로드된 PDF 문서에서 정보를 검색합니다",
    "parameters": {
        "query": "양도세 비과세 조건"
    }
}
```
→ DSPy RAG 파이프라인 호출

## 프론트엔드 채팅 모달

### 배치
지도 위 모달 팝업 (기존 DetailModal과 유사). 우측 하단 채팅 버튼으로 토글.

### 레이아웃

```
┌──────────────────────────────────────┐
│ 🏠 아파트 컨설턴트          ─  □  ✕ │
├──────────────────────────────────────┤
│  메시지 영역 (스크롤)                  │
│  - 텍스트 메시지                      │
│  - 아파트 추천 카드 (클릭→지도)        │
│  - 비교 테이블                        │
│  - Knowledge 답변 (출처 표시)         │
├──────────────────────────────────────┤
│ [📎] 메시지를 입력하세요...     [전송] │
└──────────────────────────────────────┘
```

### 메시지 타입

| 타입 | 렌더링 |
|------|--------|
| text | 일반 텍스트 (마크다운 지원) |
| apartment_card | 아파트 카드 (이름, 점수, 가격, 시설 요약, 클릭→지도) |
| comparison_table | 비교 테이블 (항목별 나란히) |
| knowledge | RAG 답변 + 출처 PDF 명시 |
| loading | 스트리밍 중 타이핑 인디케이터 |

### 지도 양방향 연동

**챗봇 → 지도:**
- search_apartments 결과 → 지도에 빨간 마커 + 자동 이동
- "강남구 보여줘" → 지도 해당 영역으로 panTo

**지도 → 챗봇:**
- 아파트 마커 클릭 시 인포윈도우에 "💬 챗봇 분석" 버튼
- 클릭 시 챗봇에 "OO아파트 분석해줘" 자동 전송

## 시스템 프롬프트

```
당신은 수도권(서울/경기/인천) 아파트 전문 컨설턴트입니다.

역할:
- 데이터 기반 아파트 추천 및 분석을 제공합니다.
- 학군, 교통, 안전, 가격 등 종합 정보를 제공합니다.
- 부동산 정책 및 세금 관련 안내를 Knowledge Base 기반으로 제공합니다.

톤:
- 전문 컨설턴트 격식체를 사용합니다.
- 구체적 수치와 데이터 근거를 제시합니다.
- 장단점을 균형있게 설명합니다.

제약:
- 투자 수익을 보장하는 발언을 하지 않습니다.
- 데이터에 없는 정보는 "확인이 필요합니다"로 안내합니다.
- 개인정보를 요청하지 않습니다.
- Knowledge Base 답변 시 출처 PDF를 명시합니다.
```

## API 설계

### POST /api/chat

```json
Request:
{
    "message": "자양동 30대 전세 추천해줘",
    "conversation_id": "uuid",
    "context": {
        "selected_pnu": null,
        "map_bounds": {"sw_lat":37.5, ...}
    }
}

Response (SSE 스트리밍):
data: {"type": "text", "content": "자양동 인근 30대 맞춤 전세 매물을"}
data: {"type": "text", "content": " 분석해드리겠습니다.\n\n"}
data: {"type": "tool_call", "name": "search_apartments", "args": {...}}
data: {"type": "apartment_card", "data": [{"pnu":"...", "bld_nm":"...", "score":92}]}
data: {"type": "map_action", "action": "highlight", "pnus": ["...", "..."]}
data: {"type": "text", "content": "상기 3개 단지를 추천드립니다."}
data: {"type": "done"}
```

### POST /api/knowledge/upload

```json
Request: multipart/form-data
  file: PDF 파일
  category: "정책" | "세금" | "투자" | "기타"

Response:
{
    "doc_id": "uuid",
    "filename": "2026_부동산_세금_가이드.pdf",
    "chunks": 45,
    "status": "indexed"
}
```

## 파일 구조

```
web/backend/
  routers/
    chat.py                    # POST /api/chat (SSE 스트리밍)
    knowledge.py               # PDF 업로드/관리 API
  services/
    llm/
      __init__.py
      base.py                  # LLMProvider ABC, LLMResponse, Tool 타입
      openai_provider.py       # OpenAI GPT 구현
      claude_provider.py       # Anthropic Claude 구현
      gemini_provider.py       # Google Gemini 구현
      factory.py               # get_provider() 팩토리
      tool_adapter.py          # 통일 Tool → 각 LLM 형식 변환
    chat_engine.py             # 대화 관리, Tool 실행, 응답 조합
    tools.py                   # 6개 Tool 함수 구현
    rag.py                     # DSPy RAG 파이프라인
    knowledge_manager.py       # PDF 파싱 + 청킹 + 임베딩 + ChromaDB
  knowledge_db/                # ChromaDB 데이터 (persist)
  uploaded_pdfs/               # 업로드된 PDF 원본

web/frontend/
  src/components/
    ChatButton.tsx             # 우측 하단 채팅 열기 버튼
    ChatModal.tsx              # 채팅 모달 (헤더, 메시지 영역, 입력바)
    ChatMessage.tsx            # 메시지 렌더링 (타입별 분기)
    ApartmentCard.tsx          # 추천 아파트 카드 (클릭→지도 연동)
    ComparisonTable.tsx        # 아파트 비교 테이블
    ChatInput.tsx              # 입력바 + PDF 첨부 + 전송
  hooks/
    useChat.ts                 # SSE 스트리밍 + 대화 상태 관리
```

## 의존 패키지

### 백엔드 추가
```
openai>=1.0
anthropic>=0.30        # Claude 사용 시
google-generativeai>=0.5  # Gemini 사용 시
chromadb>=0.4
dspy-ai>=2.0
PyMuPDF>=1.23
langchain-text-splitters>=0.0.1
sse-starlette>=1.0     # SSE 스트리밍
```

### 프론트엔드 추가
```
없음 (기존 React + axios 활용, SSE는 EventSource 네이티브)
```

## 환경 변수 추가

```env
# LLM 설정
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...

# Claude 사용 시 (선택)
# ANTHROPIC_API_KEY=sk-ant-...

# Gemini 사용 시 (선택)
# GOOGLE_API_KEY=AI...

# RAG 설정
CHROMA_PERSIST_DIR=knowledge_db
EMBEDDING_MODEL=text-embedding-3-small
```
