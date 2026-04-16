"""LLM 모델별 파라미터 호환성 레지스트리.

새 모델을 추가하거나 기본값을 바꿀 때 이 파일을 반드시 갱신한다.
프로바이더는 이 레지스트리를 조회하여 API 호출 파라미터를 동적으로 구성한다.

검증:
- 프로바이더 초기화 시 `assert_registered(model)` 호출 → 미등록 모델이면 즉시 ValueError
- 신규 모델 추가 후 `scripts/llm_smoke_test.py` 로 실제 호출 검증

capability 키 의미:
- provider           : openai | claude | gemini (라우팅용 메타데이터)
- temperature        : "free"      = 0.0 ~ 2.0 자유 설정
                       "fixed_1"   = API가 1만 허용 (gpt-5 등) → 호출 시 파라미터 생략
                       "fixed_default" = 기본값만 허용 (전송 시 생략)
- token_param        : "max_tokens" | "max_completion_tokens"
                       (gpt-5 계열은 max_completion_tokens만 허용)
- supports_tools     : function/tool calling 지원 여부
- supports_streaming : SSE/stream 호출 지원 여부
- notes              : 사람용 메모 (deprecation, alias 등)
"""

from typing import Literal, TypedDict


class ModelCaps(TypedDict, total=False):
    provider: Literal["openai", "claude", "gemini"]
    temperature: Literal["free", "fixed_1", "fixed_default"]
    token_param: Literal["max_tokens", "max_completion_tokens"]
    supports_tools: bool
    supports_streaming: bool
    notes: str


MODEL_CAPABILITIES: dict[str, ModelCaps] = {
    # ── OpenAI ─────────────────────────────────────────────────────────
    "gpt-4o": {
        "provider": "openai",
        "temperature": "free",
        "token_param": "max_tokens",
        "supports_tools": True,
        "supports_streaming": True,
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "temperature": "free",
        "token_param": "max_tokens",
        "supports_tools": True,
        "supports_streaming": True,
    },
    "gpt-5": {
        "provider": "openai",
        "temperature": "fixed_1",
        "token_param": "max_completion_tokens",
        "supports_tools": True,
        "supports_streaming": True,
        "notes": "temperature=1 고정. max_tokens 대신 max_completion_tokens 사용.",
    },
    "gpt-5-mini": {
        "provider": "openai",
        "temperature": "fixed_1",
        "token_param": "max_completion_tokens",
        "supports_tools": True,
        "supports_streaming": True,
        "notes": "temperature=1 고정. max_tokens 대신 max_completion_tokens 사용.",
    },

    # ── Anthropic Claude ───────────────────────────────────────────────
    "claude-sonnet-4-20250514": {
        "provider": "claude",
        "temperature": "free",
        "token_param": "max_tokens",
        "supports_tools": True,
        "supports_streaming": True,
    },
    "claude-opus-4-20250514": {
        "provider": "claude",
        "temperature": "free",
        "token_param": "max_tokens",
        "supports_tools": True,
        "supports_streaming": True,
    },

    # ── Google Gemini ──────────────────────────────────────────────────
    "gemini-2.0-flash": {
        "provider": "gemini",
        "temperature": "free",
        "supports_tools": True,
        "supports_streaming": True,
    },
    "gemini-1.5-pro": {
        "provider": "gemini",
        "temperature": "free",
        "supports_tools": True,
        "supports_streaming": True,
    },
}


def get_caps(model: str) -> ModelCaps:
    """모델 capability 조회. 미등록 시 ValueError."""
    caps = MODEL_CAPABILITIES.get(model)
    if caps is None:
        raise ValueError(
            f"Unregistered LLM model: '{model}'. "
            f"Register it in web/backend/services/llm/model_registry.py "
            f"and verify with scripts/llm_smoke_test.py."
        )
    return caps


def supports_custom_temperature(model: str) -> bool:
    """temperature 파라미터를 자유롭게 설정할 수 있는지."""
    return get_caps(model).get("temperature") == "free"


def get_token_param_name(model: str) -> str:
    """API에 전달할 토큰 한도 파라미터 이름."""
    return get_caps(model).get("token_param", "max_tokens")
