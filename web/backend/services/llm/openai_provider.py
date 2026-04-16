"""OpenAI GPT provider implementation."""

import json
import os
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse, Tool, ToolCall
from .model_registry import get_caps, supports_custom_temperature
from .tool_adapter import to_openai_tools


class OpenAIProvider(LLMProvider):
    """OpenAI GPT implementation."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("LLM_MODEL", "gpt-4o")
        # 기동 시 모델 등록 여부 검증 — 미등록이면 ValueError 즉시 발생
        get_caps(self.model)
        self.embedding_model = "text-embedding-3-small"

    def _build_kwargs(self, temperature: float, **extra: Any) -> dict[str, Any]:
        """모델 capability 레지스트리에 따라 호출 파라미터 동적 구성."""
        kwargs: dict[str, Any] = {"model": self.model, **extra}
        if supports_custom_temperature(self.model):
            kwargs["temperature"] = temperature
        return kwargs

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[Tool],
        temperature: float = 0.7,
    ) -> LLMResponse:
        openai_tools = to_openai_tools(tools)
        response = await self.client.chat.completions.create(
            messages=messages,
            tools=openai_tools,
            **self._build_kwargs(temperature),
        )
        choice = response.choices[0]
        msg = choice.message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=args)
                )

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            raw=response,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
    ) -> LLMResponse:
        response = await self.client.chat.completions.create(
            messages=messages,
            **self._build_kwargs(temperature),
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            raw=response,
        )

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            messages=messages,
            stream=True,
            **self._build_kwargs(temperature),
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def embed(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            model=self.embedding_model,
            input=text,
        )
        return response.data[0].embedding
