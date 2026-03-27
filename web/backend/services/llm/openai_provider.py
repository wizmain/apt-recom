"""OpenAI GPT provider implementation."""

import json
import os
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse, Tool, ToolCall
from .tool_adapter import to_openai_tools


class OpenAIProvider(LLMProvider):
    """OpenAI GPT implementation."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("LLM_MODEL", "gpt-4o")
        self.embedding_model = "text-embedding-3-small"

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[Tool],
        temperature: float = 0.7,
    ) -> LLMResponse:
        openai_tools = to_openai_tools(tools)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=openai_tools,
            temperature=temperature,
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
            model=self.model,
            messages=messages,
            temperature=temperature,
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
            model=self.model,
            messages=messages,
            temperature=temperature,
            stream=True,
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
