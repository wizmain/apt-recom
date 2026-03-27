"""Abstract base class and data types for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class Tool:
    """Tool definition for LLM function calling."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for parameters


@dataclass
class ToolCall:
    """A tool call returned by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[Tool],
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send a chat request with tool definitions."""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send a simple chat request without tools."""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Stream a chat response token by token."""
        ...

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text."""
        raise NotImplementedError("Embedding not supported by this provider")
