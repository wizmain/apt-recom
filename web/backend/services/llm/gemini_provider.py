"""Google Gemini provider implementation."""

import os
from typing import Any, AsyncIterator

import google.generativeai as genai

from .base import LLMProvider, LLMResponse, Tool, ToolCall
from .tool_adapter import to_gemini_tools


class GeminiProvider(LLMProvider):
    """Google Gemini implementation."""

    def __init__(self):
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model_name = os.getenv("LLM_MODEL", "gemini-2.0-flash")
        self.embedding_model = "models/text-embedding-004"

    def _build_model(self, tools: list | None = None) -> genai.GenerativeModel:
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools
        return genai.GenerativeModel(self.model_name, **kwargs)

    def _messages_to_contents(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | None, list[dict]]:
        """Convert OpenAI-style messages to Gemini contents + system instruction."""
        system = None
        contents = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            elif m["role"] == "assistant":
                contents.append({"role": "model", "parts": [{"text": m["content"]}]})
            elif m["role"] == "tool":
                # Tool results: wrap as function response
                contents.append(
                    {
                        "role": "function",
                        "parts": [
                            {
                                "function_response": {
                                    "name": m.get("name", "tool"),
                                    "response": {"result": m["content"]},
                                }
                            }
                        ],
                    }
                )
            else:
                contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        return system, contents

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[Tool],
        temperature: float = 0.7,
    ) -> LLMResponse:
        gemini_tools = to_gemini_tools(tools)
        system, contents = self._messages_to_contents(messages)

        model = genai.GenerativeModel(
            self.model_name,
            tools=gemini_tools,
            system_instruction=system,
        )
        response = await model.generate_content_async(
            contents,
            generation_config=genai.GenerationConfig(temperature=temperature),
        )

        content = ""
        tool_calls = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    content += part.text
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls.append(
                        ToolCall(
                            id=f"gemini_{fc.name}",
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {},
                        )
                    )

        return LLMResponse(
            content=content or None,
            tool_calls=tool_calls,
            usage={},
            raw=response,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
    ) -> LLMResponse:
        system, contents = self._messages_to_contents(messages)
        model = genai.GenerativeModel(
            self.model_name, system_instruction=system
        )
        response = await model.generate_content_async(
            contents,
            generation_config=genai.GenerationConfig(temperature=temperature),
        )
        content = ""
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    content += part.text

        return LLMResponse(content=content or None, usage={}, raw=response)

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        system, contents = self._messages_to_contents(messages)
        model = genai.GenerativeModel(
            self.model_name, system_instruction=system
        )
        response = await model.generate_content_async(
            contents,
            generation_config=genai.GenerationConfig(temperature=temperature),
            stream=True,
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text

    async def embed(self, text: str) -> list[float]:
        result = genai.embed_content(
            model=self.embedding_model, content=text
        )
        return result["embedding"]
