"""Anthropic Claude provider implementation."""

import os
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from .base import LLMProvider, LLMResponse, Tool, ToolCall
from .tool_adapter import to_claude_tools


class ClaudeProvider(LLMProvider):
    """Anthropic Claude implementation."""

    def __init__(self):
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

    def _extract_system(self, messages: list[dict[str, Any]]) -> tuple[str, list[dict]]:
        """Separate system message from conversation messages."""
        system = ""
        conversation = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                conversation.append(m)
        return system, conversation

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[Tool],
        temperature: float = 0.7,
    ) -> LLMResponse:
        system, conversation = self._extract_system(messages)
        claude_tools = to_claude_tools(tools)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": conversation,
            "tools": claude_tools,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = await self.client.messages.create(**kwargs)

        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=block.input)
                )

        return LLMResponse(
            content=content or None,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
            raw=response,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
    ) -> LLMResponse:
        system, conversation = self._extract_system(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": conversation,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = await self.client.messages.create(**kwargs)

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content or None,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
            raw=response,
        )

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        system, conversation = self._extract_system(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": conversation,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def embed(self, text: str) -> list[float]:
        """Claude has no embedding API; fall back to OpenAI if available."""
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise NotImplementedError(
                "Claude does not support embeddings. Set OPENAI_API_KEY for fallback."
            )
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=openai_key)
        response = await client.embeddings.create(
            model="text-embedding-3-small", input=text
        )
        return response.data[0].embedding
