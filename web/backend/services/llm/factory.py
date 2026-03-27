"""Provider factory — instantiates the LLM provider based on env config."""

import os

from .base import LLMProvider


def get_provider() -> LLMProvider:
    """Read LLM_PROVIDER from env and return the corresponding provider instance."""
    provider_name = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider_name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    elif provider_name == "claude":
        from .claude_provider import ClaudeProvider
        return ClaudeProvider()
    elif provider_name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider_name}. Use openai|claude|gemini.")
