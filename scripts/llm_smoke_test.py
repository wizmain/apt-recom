"""LLM 프로바이더 호환성 smoke test.

사용:
    .venv/bin/python -m scripts.llm_smoke_test

수행:
    1) .env 의 LLM_PROVIDER + LLM_MODEL 로드
    2) 모델이 model_registry 에 등록돼 있는지 검증
    3) 다음 3개 메서드가 실제로 동작하는지 호출:
       - chat()                     : 단순 응답
       - chat_with_tools()          : function/tool calling
       - stream_chat()              : SSE 스트리밍
    4) 각 단계 PASS/FAIL 출력. 하나라도 실패하면 exit 1

LLM 모델/프로바이더를 변경한 경우 커밋 전 반드시 1회 실행.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# 프로젝트 루트 보정 + .env 로드
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web" / "backend"))

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT / ".env")
except ImportError:
    # python-dotenv 미설치 시 환경변수가 외부에서 주입돼 있다고 가정
    pass

from services.llm.factory import get_provider  # noqa: E402
from services.llm.base import Tool  # noqa: E402
from services.llm.model_registry import get_caps  # noqa: E402


# 가벼운 테스트용 도구 — 항상 같은 결과 반환
SAMPLE_TOOL = Tool(
    name="get_current_temperature",
    description="현재 서울의 기온을 섭씨로 반환",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "도시명"},
        },
        "required": ["city"],
    },
)


def _print_header() -> None:
    provider = os.getenv("LLM_PROVIDER", "(unset)")
    model = os.getenv("LLM_MODEL", "(default)")
    print("=" * 60)
    print(f"LLM Smoke Test  |  provider={provider}  model={model}")
    print("=" * 60)


def _ok(label: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"  ✅ {label}{suffix}")


def _fail(label: str, err: Exception) -> None:
    print(f"  ❌ {label} — {type(err).__name__}: {err}")


async def _test_registry(provider) -> bool:
    print("[1/4] Registry check")
    try:
        model = getattr(provider, "model", None) or getattr(provider, "model_name", None)
        caps = get_caps(model)
        _ok(f"등록된 모델: {model}", str(caps))
        return True
    except Exception as e:
        _fail("registry lookup", e)
        return False


async def _test_chat(provider) -> bool:
    print("[2/4] chat()")
    try:
        r = await provider.chat(
            messages=[{"role": "user", "content": "한 단어로만 인사"}],
            temperature=0.7,
        )
        _ok("응답 수신", (r.content or "").strip()[:60])
        return True
    except Exception as e:
        _fail("chat", e)
        return False


async def _test_chat_with_tools(provider) -> bool:
    print("[3/4] chat_with_tools()")
    try:
        r = await provider.chat_with_tools(
            messages=[{"role": "user", "content": "서울 기온 알려줘"}],
            tools=[SAMPLE_TOOL],
            temperature=0.7,
        )
        n_tools = len(r.tool_calls or [])
        _ok("호출 성공", f"tool_calls={n_tools}, content={(r.content or '')[:40]!r}")
        return True
    except Exception as e:
        _fail("chat_with_tools", e)
        return False


async def _test_stream_chat(provider) -> bool:
    print("[4/4] stream_chat()")
    try:
        chunks: list[str] = []
        async for chunk in provider.stream_chat(
            messages=[{"role": "user", "content": "1부터 3까지 세어줘"}],
            temperature=0.7,
        ):
            chunks.append(chunk)
        text = "".join(chunks).strip()
        _ok("스트리밍 수신", f"{len(chunks)} chunks, body={text[:60]!r}")
        return True
    except Exception as e:
        _fail("stream_chat", e)
        return False


async def main() -> int:
    _print_header()
    try:
        provider = get_provider()
    except Exception as e:
        print(f"❌ get_provider() 실패: {type(e).__name__}: {e}")
        return 1

    results = [
        await _test_registry(provider),
        await _test_chat(provider),
        await _test_chat_with_tools(provider),
        await _test_stream_chat(provider),
    ]
    passed = sum(results)
    total = len(results)
    print("=" * 60)
    print(f"결과: {passed}/{total} PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
