"""Convert Tool definitions to provider-specific formats."""

from .base import Tool


def to_openai_tools(tools: list[Tool]) -> list[dict]:
    """Convert Tool list to OpenAI function calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def to_claude_tools(tools: list[Tool]) -> list[dict]:
    """Convert Tool list to Anthropic tool use format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


def to_gemini_tools(tools: list[Tool]) -> list[dict]:
    """Convert Tool list to Google Gemini function declarations format."""

    def _clean_schema(schema: dict) -> dict:
        """Remove unsupported keys for Gemini (e.g. additionalProperties)."""
        cleaned = {}
        for k, v in schema.items():
            if k in ("additionalProperties",):
                continue
            if isinstance(v, dict):
                cleaned[k] = _clean_schema(v)
            elif isinstance(v, list):
                cleaned[k] = [_clean_schema(i) if isinstance(i, dict) else i for i in v]
            else:
                cleaned[k] = v
        return cleaned

    declarations = []
    for t in tools:
        declarations.append(
            {
                "name": t.name,
                "description": t.description,
                "parameters": _clean_schema(t.parameters),
            }
        )
    return [{"function_declarations": declarations}]
