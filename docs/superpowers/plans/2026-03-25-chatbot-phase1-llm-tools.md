# Phase 1: LLM 추상화 + Tool 함수 + Chat API 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 멀티 LLM 추상화 레이어와 6개 Tool 함수를 구현하여 채팅 API 엔드포인트를 완성한다.

**Architecture:** LLMProvider ABC로 OpenAI/Claude/Gemini를 추상화하고, .env 설정으로 전환. 6개 Tool 함수가 기존 DB를 쿼리하며, chat_engine이 대화를 관리하고 SSE로 스트리밍 응답한다.

**Tech Stack:** Python 3.12, FastAPI, OpenAI SDK, Anthropic SDK, Google GenerativeAI, sse-starlette

**Spec:** `docs/superpowers/specs/2026-03-25-chatbot-design.md`

---

## Task 0: 패키지 설치 + 환경 설정

**Files:**
- Modify: `.env`

- [ ] **Step 1: 패키지 설치**

```bash
uv pip install openai anthropic google-generativeai sse-starlette --python .venv/bin/python
```

- [ ] **Step 2: .env에 LLM 설정 추가**

```
# LLM 설정
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-key-here
```

- [ ] **Step 3: 설치 확인**

```bash
.venv/bin/python -c "import openai, anthropic, google.generativeai, sse_starlette; print('OK')"
```

---

## Task 1: LLM 추상화 레이어

**Files:**
- Create: `web/backend/services/llm/__init__.py`
- Create: `web/backend/services/llm/base.py`
- Create: `web/backend/services/llm/tool_adapter.py`
- Create: `web/backend/services/llm/openai_provider.py`
- Create: `web/backend/services/llm/claude_provider.py`
- Create: `web/backend/services/llm/gemini_provider.py`
- Create: `web/backend/services/llm/factory.py`

- [ ] **Step 1: base.py — 타입 정의 + ABC**

```python
"""LLM Provider 추상 인터페이스 및 공통 타입."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Any


@dataclass
class Tool:
    """통일된 Tool 정의."""
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    """LLM이 요청한 Tool 호출."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """LLM 응답."""
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


class LLMProvider(ABC):
    """LLM 공급자 추상 클래스."""

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[Tool],
        system_prompt: str,
    ) -> LLMResponse:
        """Tool calling이 가능한 채팅 호출."""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> str:
        """단순 채팅 (tool 없음)."""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        """스트리밍 응답."""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """텍스트 임베딩."""
        ...
```

- [ ] **Step 2: tool_adapter.py — Tool 스키마 변환**

```python
"""통일 Tool 스키마를 각 LLM 형식으로 변환."""

from .base import Tool


def to_openai_tools(tools: list[Tool]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": {
                    "type": "object",
                    "properties": t.parameters,
                },
            },
        }
        for t in tools
    ]


def to_claude_tools(tools: list[Tool]) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": {
                "type": "object",
                "properties": t.parameters,
            },
        }
        for t in tools
    ]


def to_gemini_tools(tools: list[Tool]) -> list[dict]:
    return [
        {
            "function_declarations": [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        "properties": t.parameters,
                    },
                }
                for t in tools
            ]
        }
    ]
```

- [ ] **Step 3: openai_provider.py**

```python
"""OpenAI GPT Provider."""

import os
import json
from typing import AsyncIterator
from openai import AsyncOpenAI
from .base import LLMProvider, LLMResponse, Tool, ToolCall
from .tool_adapter import to_openai_tools


class OpenAIProvider(LLMProvider):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("LLM_MODEL", "gpt-4o")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    async def chat_with_tools(self, messages, tools, system_prompt):
        msgs = [{"role": "system", "content": system_prompt}] + messages
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=msgs,
            tools=to_openai_tools(tools) if tools else None,
        )
        choice = resp.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))
        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
        )

    async def chat(self, messages, system_prompt):
        msgs = [{"role": "system", "content": system_prompt}] + messages
        resp = await self.client.chat.completions.create(
            model=self.model, messages=msgs,
        )
        return resp.choices[0].message.content

    async def stream_chat(self, messages, system_prompt):
        msgs = [{"role": "system", "content": system_prompt}] + messages
        stream = await self.client.chat.completions.create(
            model=self.model, messages=msgs, stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def embed(self, text):
        resp = await self.client.embeddings.create(
            model=self.embedding_model, input=text,
        )
        return resp.data[0].embedding
```

- [ ] **Step 4: claude_provider.py**

```python
"""Anthropic Claude Provider."""

import os
import json
from typing import AsyncIterator
from anthropic import AsyncAnthropic
from .base import LLMProvider, LLMResponse, Tool, ToolCall
from .tool_adapter import to_claude_tools


class ClaudeProvider(LLMProvider):
    def __init__(self):
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

    async def chat_with_tools(self, messages, tools, system_prompt):
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=to_claude_tools(tools) if tools else None,
        )
        content = ""
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id, name=block.name, arguments=block.input,
                ))
        return LLMResponse(
            content=content or None,
            tool_calls=tool_calls,
            finish_reason=resp.stop_reason,
        )

    async def chat(self, messages, system_prompt):
        resp = await self.client.messages.create(
            model=self.model, max_tokens=4096,
            system=system_prompt, messages=messages,
        )
        return resp.content[0].text

    async def stream_chat(self, messages, system_prompt):
        async with self.client.messages.stream(
            model=self.model, max_tokens=4096,
            system=system_prompt, messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def embed(self, text):
        # Claude는 자체 임베딩 없음 — OpenAI fallback
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = await client.embeddings.create(
            model="text-embedding-3-small", input=text,
        )
        return resp.data[0].embedding
```

- [ ] **Step 5: gemini_provider.py**

```python
"""Google Gemini Provider."""

import os
import json
from typing import AsyncIterator
import google.generativeai as genai
from .base import LLMProvider, LLMResponse, Tool, ToolCall
from .tool_adapter import to_gemini_tools


class GeminiProvider(LLMProvider):
    def __init__(self):
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model_name = os.getenv("LLM_MODEL", "gemini-2.0-flash")

    async def chat_with_tools(self, messages, tools, system_prompt):
        model = genai.GenerativeModel(
            self.model_name,
            system_instruction=system_prompt,
            tools=to_gemini_tools(tools) if tools else None,
        )
        # Gemini 메시지 형식 변환
        gemini_msgs = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            gemini_msgs.append({"role": role, "parts": [m["content"]]})

        resp = await model.generate_content_async(gemini_msgs)
        content = ""
        tool_calls = []
        for part in resp.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                content += part.text
            elif hasattr(part, "function_call"):
                fc = part.function_call
                tool_calls.append(ToolCall(
                    id=fc.name, name=fc.name,
                    arguments=dict(fc.args) if fc.args else {},
                ))
        return LLMResponse(content=content or None, tool_calls=tool_calls)

    async def chat(self, messages, system_prompt):
        model = genai.GenerativeModel(self.model_name, system_instruction=system_prompt)
        gemini_msgs = [{"role": "model" if m["role"] == "assistant" else "user",
                        "parts": [m["content"]]} for m in messages]
        resp = await model.generate_content_async(gemini_msgs)
        return resp.text

    async def stream_chat(self, messages, system_prompt):
        model = genai.GenerativeModel(self.model_name, system_instruction=system_prompt)
        gemini_msgs = [{"role": "model" if m["role"] == "assistant" else "user",
                        "parts": [m["content"]]} for m in messages]
        resp = await model.generate_content_async(gemini_msgs, stream=True)
        async for chunk in resp:
            if chunk.text:
                yield chunk.text

    async def embed(self, text):
        result = genai.embed_content(
            model="models/text-embedding-004", content=text,
        )
        return result["embedding"]
```

- [ ] **Step 6: factory.py**

```python
"""LLM Provider 팩토리."""

import os
from .base import LLMProvider


def get_provider() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    elif provider == "claude":
        from .claude_provider import ClaudeProvider
        return ClaudeProvider()
    elif provider == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
```

- [ ] **Step 7: __init__.py**

```python
from .base import LLMProvider, LLMResponse, Tool, ToolCall
from .factory import get_provider
```

---

## Task 2: Tool 함수 구현

**Files:**
- Create: `web/backend/services/tools.py`

- [ ] **Step 1: 6개 Tool 함수 구현**

```python
"""챗봇 Tool 함수 — 기존 DB/API를 활용하여 데이터 조회."""

import sqlite3
import re
from pathlib import Path
from services.scoring import (
    NUDGE_WEIGHTS, distance_to_score,
    calculate_nudge_score, calculate_multi_nudge_score,
)
from services.llm.base import Tool

DB_PATH = Path(__file__).resolve().parent.parent / "apt_web.db"


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = _dict_factory
    return conn


# ---- Tool 정의 (LLM에 전달) ----

CHAT_TOOLS = [
    Tool(
        name="search_apartments",
        description="넛지 기반 아파트 검색 및 추천. 지역명, 라이프스타일, 예산 기반으로 최적 아파트를 찾습니다.",
        parameters={
            "keyword": {"type": "string", "description": "지역명 또는 단지명 (예: 자양동, 강남구)"},
            "nudges": {"type": "array", "items": {"type": "string"}, "description": "넛지 목록 (cost,pet,commute,newlywed,education,senior,investment,nature)"},
            "top_n": {"type": "integer", "description": "추천 개수 (기본 5)"},
        },
    ),
    Tool(
        name="get_apartment_detail",
        description="특정 아파트의 상세 정보 (기본정보, 가격, 시설, 학군, 안전점수)",
        parameters={
            "query": {"type": "string", "description": "아파트명 또는 PNU"},
        },
    ),
    Tool(
        name="compare_apartments",
        description="2~5개 아파트를 비교 분석합니다",
        parameters={
            "queries": {"type": "array", "items": {"type": "string"}, "description": "비교할 아파트명 목록"},
        },
    ),
    Tool(
        name="get_market_trend",
        description="지역별 매매/전세 시세 동향, 거래량 추이를 분석합니다",
        parameters={
            "region": {"type": "string", "description": "지역명 (예: 강남구, 자양동)"},
            "period": {"type": "string", "description": "기간 (1year, 3year, all)"},
        },
    ),
    Tool(
        name="get_school_info",
        description="학군 정보를 조회합니다 (배정 학교, 학교군, 교육지원청)",
        parameters={
            "query": {"type": "string", "description": "아파트명 또는 지역명"},
        },
    ),
    Tool(
        name="search_knowledge",
        description="부동산 정책, 세금, 투자 가이드 등 업로드된 PDF 문서에서 정보를 검색합니다",
        parameters={
            "query": {"type": "string", "description": "검색 질문 (예: 양도세 비과세 조건)"},
        },
    ),
]


# ---- Tool 실행 함수 ----

def _find_pnu_by_name(conn, name):
    """아파트명으로 PNU 검색."""
    row = conn.execute(
        "SELECT pnu, bld_nm FROM apartments WHERE bld_nm LIKE ? LIMIT 1",
        (f"%{name}%",)
    ).fetchone()
    return row["pnu"] if row else None


def search_apartments(keyword: str = "", nudges: list = None, top_n: int = 5, **kwargs) -> dict:
    conn = _get_conn()
    try:
        sql = "SELECT pnu, bld_nm, lat, lng, total_hhld_cnt, new_plat_plc, sigungu_code FROM apartments"
        params = []
        if keyword:
            sql += " WHERE (new_plat_plc LIKE ? OR plat_plc LIKE ? OR bld_nm LIKE ?)"
            params = [f"%{keyword}%"] * 3
        apts = conn.execute(sql, params).fetchall()

        if not nudges or not apts:
            return {"apartments": apts[:top_n], "total": len(apts)}

        # 스코어링
        pnu_list = [a["pnu"] for a in apts]
        apt_map = {a["pnu"]: a for a in apts}
        summaries = {}
        for i in range(0, len(pnu_list), 500):
            chunk = pnu_list[i:i+500]
            ph = ",".join(["?"] * len(chunk))
            rows = conn.execute(
                f"SELECT pnu, facility_subtype, nearest_distance_m FROM apt_facility_summary WHERE pnu IN ({ph})",
                chunk,
            ).fetchall()
            for r in rows:
                summaries.setdefault(r["pnu"], {})[r["facility_subtype"]] = r["nearest_distance_m"]

        results = []
        for pnu in pnu_list:
            dists = summaries.get(pnu, {})
            fscores = {ft: distance_to_score(d, ft) for ft, d in dists.items()}
            score = calculate_multi_nudge_score(fscores, nudges)
            apt = apt_map[pnu]
            results.append({**apt, "score": score})

        results.sort(key=lambda x: x["score"], reverse=True)
        return {"apartments": results[:top_n], "total": len(results)}
    finally:
        conn.close()


def get_apartment_detail(query: str, **kwargs) -> dict:
    conn = _get_conn()
    try:
        pnu = query if len(query) > 10 else _find_pnu_by_name(conn, query)
        if not pnu:
            return {"error": f"'{query}' 아파트를 찾을 수 없습니다."}

        basic = conn.execute("SELECT * FROM apartments WHERE pnu = ?", (pnu,)).fetchone()
        if not basic:
            return {"error": "아파트 정보가 없습니다."}

        school = conn.execute("SELECT * FROM school_zones WHERE pnu = ?", (pnu,)).fetchone()
        price = conn.execute("SELECT * FROM apt_price_score WHERE pnu = ?", (pnu,)).fetchone()
        safety = conn.execute("SELECT * FROM apt_safety_score WHERE pnu = ?", (pnu,)).fetchone()
        facilities = conn.execute(
            "SELECT facility_subtype, nearest_distance_m, count_1km FROM apt_facility_summary WHERE pnu = ?",
            (pnu,),
        ).fetchall()

        # 최근 거래
        mapping = conn.execute("SELECT apt_seq FROM trade_apt_mapping WHERE pnu = ?", (pnu,)).fetchone()
        trades = []
        if mapping:
            trades = conn.execute(
                "SELECT deal_year, deal_month, deal_amount, exclu_use_ar, floor FROM trade_history WHERE apt_seq = ? ORDER BY deal_year DESC, deal_month DESC LIMIT 5",
                (mapping["apt_seq"],),
            ).fetchall()

        return {
            "basic": basic, "school": school, "price": price,
            "safety": safety, "facilities": facilities, "recent_trades": trades,
        }
    finally:
        conn.close()


def compare_apartments(queries: list, **kwargs) -> dict:
    results = []
    for q in queries[:5]:
        detail = get_apartment_detail(q)
        if "error" not in detail:
            results.append(detail)
    return {"apartments": results, "count": len(results)}


def get_market_trend(region: str = "", period: str = "1year", **kwargs) -> dict:
    conn = _get_conn()
    try:
        # 시군구 코드 찾기
        sgg = conn.execute(
            "SELECT DISTINCT sigungu_code FROM apartments WHERE new_plat_plc LIKE ? LIMIT 1",
            (f"%{region}%",),
        ).fetchone()

        if not sgg:
            return {"error": f"'{region}' 지역을 찾을 수 없습니다."}

        sgg_cd = sgg["sigungu_code"]
        year_filter = "AND deal_year >= 2025" if period == "1year" else (
            "AND deal_year >= 2023" if period == "3year" else "")

        trends = conn.execute(f"""
            SELECT deal_year, deal_month, COUNT(*) as count,
                   AVG(deal_amount) as avg_price,
                   AVG(deal_amount * 10000.0 / exclu_use_ar) as avg_price_per_m2
            FROM trade_history
            WHERE sgg_cd = ? {year_filter} AND deal_amount > 0 AND exclu_use_ar > 0
            GROUP BY deal_year, deal_month
            ORDER BY deal_year, deal_month
        """, (sgg_cd,)).fetchall()

        return {"region": region, "sgg_cd": sgg_cd, "trends": trends}
    finally:
        conn.close()


def get_school_info(query: str, **kwargs) -> dict:
    conn = _get_conn()
    try:
        pnu = _find_pnu_by_name(conn, query) if len(query) < 15 else query
        if pnu:
            school = conn.execute("SELECT * FROM school_zones WHERE pnu = ?", (pnu,)).fetchone()
            if school:
                return school

        # 지역명으로 검색
        schools = conn.execute("""
            SELECT s.*, a.bld_nm, a.new_plat_plc
            FROM school_zones s JOIN apartments a ON s.pnu = a.pnu
            WHERE a.new_plat_plc LIKE ? LIMIT 10
        """, (f"%{query}%",)).fetchall()
        return {"results": schools}
    finally:
        conn.close()


def search_knowledge(query: str, **kwargs) -> dict:
    """RAG 검색 — Phase 2에서 구현. 현재는 플레이스홀더."""
    return {"answer": "Knowledge Base가 아직 구성되지 않았습니다. PDF를 업로드해주세요.", "sources": []}


# Tool 이름 → 실행 함수 매핑
TOOL_EXECUTORS = {
    "search_apartments": search_apartments,
    "get_apartment_detail": get_apartment_detail,
    "compare_apartments": compare_apartments,
    "get_market_trend": get_market_trend,
    "get_school_info": get_school_info,
    "search_knowledge": search_knowledge,
}
```

---

## Task 3: Chat Engine + API 엔드포인트

**Files:**
- Create: `web/backend/services/chat_engine.py`
- Create: `web/backend/routers/chat.py`
- Modify: `web/backend/main.py`

- [ ] **Step 1: chat_engine.py — 대화 관리 + Tool 실행**

```python
"""채팅 엔진 — LLM 호출, Tool 실행, 응답 조합."""

import json
from services.llm import get_provider, Tool
from services.tools import CHAT_TOOLS, TOOL_EXECUTORS

SYSTEM_PROMPT = """당신은 수도권(서울/경기/인천) 아파트 전문 컨설턴트입니다.

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
- 답변에 추천 아파트가 있으면 PNU를 포함해주세요."""


async def process_chat(message: str, conversation: list[dict] = None) -> dict:
    """채팅 메시지를 처리하고 응답을 반환한다."""
    provider = get_provider()
    messages = (conversation or []) + [{"role": "user", "content": message}]

    # 1차: Tool calling 요청
    response = await provider.chat_with_tools(messages, CHAT_TOOLS, SYSTEM_PROMPT)

    # Tool 호출이 있으면 실행
    if response.tool_calls:
        tool_results = []
        map_actions = []

        for tc in response.tool_calls:
            executor = TOOL_EXECUTORS.get(tc.name)
            if executor:
                result = executor(**tc.arguments)
                tool_results.append({
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "result": result,
                })

                # 지도 액션 생성
                if tc.name == "search_apartments" and "apartments" in result:
                    pnus = [a["pnu"] for a in result["apartments"] if "pnu" in a]
                    if pnus:
                        map_actions.append({"action": "highlight", "pnus": pnus})
                elif tc.name == "get_apartment_detail" and "basic" in result:
                    pnu = result["basic"].get("pnu")
                    if pnu:
                        map_actions.append({"action": "focus", "pnus": [pnu]})

        # 2차: Tool 결과를 포함하여 최종 답변 생성
        messages.append({"role": "assistant", "content": response.content or "",
                         "tool_calls_data": [{"name": tr["name"], "result": tr["result"]} for tr in tool_results]})

        tool_context = "\n\n".join([
            f"[{tr['name']}] 결과:\n{json.dumps(tr['result'], ensure_ascii=False, default=str)[:3000]}"
            for tr in tool_results
        ])
        messages.append({"role": "user", "content": f"위 Tool 결과를 바탕으로 사용자에게 전문 컨설턴트 격식체로 답변해주세요.\n\nTool 결과:\n{tool_context}"})

        final_response = await provider.chat(messages, SYSTEM_PROMPT)

        return {
            "content": final_response,
            "tool_calls": [{"name": tr["name"], "result": tr["result"]} for tr in tool_results],
            "map_actions": map_actions,
        }

    # Tool 호출 없이 직접 답변
    return {
        "content": response.content,
        "tool_calls": [],
        "map_actions": [],
    }
```

- [ ] **Step 2: routers/chat.py — Chat API 엔드포인트**

```python
"""채팅 API."""

from fastapi import APIRouter
from pydantic import BaseModel
from services.chat_engine import process_chat

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation: list[dict] | None = None
    context: dict | None = None  # 지도 상태 등


class ChatResponse(BaseModel):
    content: str
    tool_calls: list[dict] = []
    map_actions: list[dict] = []


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """채팅 메시지 처리."""
    result = await process_chat(
        message=req.message,
        conversation=req.conversation,
    )
    return ChatResponse(**result)
```

- [ ] **Step 3: main.py에 chat 라우터 추가**

```python
# 기존 import에 추가
from routers import apartments, nudge, detail, chat

# 기존 include_router 아래에 추가
app.include_router(chat.router, prefix="/api")
```

---

## Task 4: 테스트 및 검증

- [ ] **Step 1: 서버 재시작**

```bash
pkill -f "uvicorn main:app" 2>/dev/null; sleep 1
cd web/backend && ../../.venv/bin/python -m uvicorn main:app --port 8000 &
sleep 3
```

- [ ] **Step 2: 채팅 API 테스트**

```bash
# 기본 대화
curl -s -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "안녕하세요"}' | python -m json.tool

# 아파트 추천
curl -s -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "자양동 30대 전세 추천해줘"}' | python -m json.tool

# 아파트 상세
curl -s -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "역삼2차아이파크 정보 알려줘"}' | python -m json.tool

# 비교
curl -s -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "경희궁자이와 래미안 비교해줘"}' | python -m json.tool

# 시장 동향
curl -s -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "강남구 최근 1년 시세 동향 알려줘"}' | python -m json.tool

# 학군
curl -s -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "신안네트빌 학군 정보 알려줘"}' | python -m json.tool
```

Expected: 각 요청에 대해 Tool이 호출되고 전문 컨설턴트 톤의 답변이 반환됨.

---

## 실행 순서

```
Task 0: 패키지 설치 + .env 설정
  ↓
Task 1: LLM 추상화 레이어 (7개 파일)
  ↓
Task 2: Tool 함수 (6개 함수)
  ↓
Task 3: Chat Engine + API 엔드포인트
  ↓
Task 4: 테스트 및 검증
```
