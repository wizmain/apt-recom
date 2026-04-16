"""Chat engine — orchestrates LLM calls and tool execution."""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(_env_path)

from services.llm import get_provider, LLMResponse, Tool
from services.tools import TOOL_DEFINITIONS, TOOL_EXECUTORS
from services.activity_log import log_chat

logger = logging.getLogger(__name__)

# 복합 질의(예: "A에서 B까지 출근시간")에서 tool을 최대 몇 번 연쇄 호출할지 제한.
# 루프 폭주(동일 tool 반복 호출)는 중복 시그니처 탐지로 별도로 차단함.
MAX_TOOL_ITERATIONS = 5


def _build_map_action(tool_name: str, result: str) -> dict | None:
    """search_apartments 결과에서 지도 하이라이트 액션을 생성."""
    if tool_name != "search_apartments":
        return None
    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        return None
    results = parsed.get("results") or []
    if not results:
        return None
    return {
        "type": "highlight",
        "pnus": [r["pnu"] for r in results],
        "apartments": [
            {"pnu": r["pnu"], "bld_nm": r["bld_nm"],
             "lat": r["lat"], "lng": r["lng"], "score": r["score"]}
            for r in results
        ],
    }


def _tool_preview(tool_name: str, result: str) -> str:
    """Tool 결과의 간략 프리뷰(스트리밍 SSE에 노출)."""
    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        return ""
    if tool_name == "get_apartment_detail" and "basic" in parsed:
        return parsed["basic"].get("bld_nm") or parsed["basic"].get("name") or ""
    if tool_name == "search_apartments" and "results" in parsed:
        return f"{len(parsed['results'])}건 검색됨"
    if tool_name == "search_commute" and "routes" in parsed:
        return f"{len(parsed['routes'])}개 경로 조회"
    return ""

SYSTEM_PROMPT = """\
당신은 서울/수도권 아파트 추천 전문 컨설턴트입니다.

## 역할
- 사용자의 라이프스타일과 요구사항을 파악하여 최적의 아파트를 추천합니다.
- 격식체(~합니다, ~입니다)를 사용하여 전문적이고 신뢰감 있는 답변을 제공합니다.
- 아파트 추천, 비교, 시세 동향, 학군 정보 등을 제공합니다.

## 사용 가능한 라이프 항목
- cost: 가성비 (교통, 편의시설, 가격 종합)
- pet: 반려동물 (동물병원, 펫시설, 공원)
- commute: 출퇴근 (지하철, 버스)
- newlywed: 신혼부부 (안전, 교통, 육아시설)
- education: 교육 (학교, 도서관)
- senior: 시니어 (병원, 약국, 편의시설)
- investment: 투자 (가격, 교통, 인프라)
- nature: 자연친화 (공원, 도서관, 펫시설)
- safety: 안전 (CCTV, 경찰서, 소방서, 범죄율, 안전점수)

## 응답 가이드라인
1. 아파트 검색/추천 요청 시 반드시 search_apartments 도구를 먼저 호출하세요. 지역명이 실제 존재하는지 직접 판단하지 마세요. 검색 엔진이 시군구, 읍면동, 단지명을 자동 분류합니다.
   - 결과에 region_candidates가 있으면 동명이인 지역입니다. 후보 목록을 사용자에게 보여주고 어느 지역인지 확인하세요.
   - 사용자가 지역을 선택하면, region_candidates의 label에서 "시군구명 동이름" 형태로 keyword를 조합하여 재검색하세요. 예: 사용자가 "경기도"를 선택하면 → keyword="용인 중동" (label에서 시군구+동 추출)
2. 추천 결과를 사용자에게 알기 쉽게 정리하여 설명하세요.
3. 점수, 주소, 주요 특징을 포함하여 답변하세요.
4. 추가 질문이나 비교가 필요한지 안내하세요.
5. 한국어로 답변하세요.
6. 출퇴근 시간 조회 시 **반드시 순차적으로** 도구를 호출하세요:
   ① 컨텍스트에 PNU가 없으면 `get_apartment_detail`로 아파트 정보를 조회해 PNU를 얻으세요.
   ② PNU를 확보하면 **같은 응답 내에서 곧바로** `search_commute`를 `pnu`와 `destination`을 인자로 호출하세요.
   ③ "조회해보겠습니다" 같은 대기성 응답을 먼저 보내지 말고 도구 호출을 연쇄 실행하세요. 모든 도구 결과가 나온 뒤에 한 번에 답변하세요.
7. 출퇴근 결과는 경로별 소요시간, 환승횟수, 요금을 표 형태로 정리하세요.
8. 사용자가 면적, 가격, 층수, 준공연도 등 조건을 언급하면 search_apartments의 필터 파라미터를 사용하세요. 예: "60~85㎡" → min_area=60, max_area=85, "10억 이하" → max_price=100000, "신축" → built_after=2020

## 안전 점수 설명 가이드
안전 점수 관련 질문 시, get_apartment_detail 결과의 safety 필드에 다음 정보가 포함됩니다:
- **종합 안전 점수** (nudge_safety_score): CCTV안전(25%) + 범죄안전(25%) + 경찰서(15%) + CCTV근접(15%) + 소방서(10%) + 편의점/공원(10%)
- **CCTV 안전 점수** (safety_score): CCTV 밀도 기반 (가중치: 생활방범 1.0, 어린이보호 1.2 등)
- **범죄 안전 점수** (crime_safety_score): 2024년 경찰청 5대범죄 통계 기반, 유동인구 보정 적용
- **범죄 유형 분석** (crime_detail): 살인(murder), 강도(robbery), 강간·강제추행(sexual_assault), 절도(theft), 폭력(violence)
  - total_crime: 5대범죄 합계
  - resident_pop: 주민등록인구
  - effective_pop: 유동인구 보정 인구 (상업/관광 밀집지역은 주민인구의 2~4배)
  - float_pop_ratio: 유동인구 보정계수 (1.0=보정없음, 4.2=중구 최대)
  - crime_rate: 보정인구 10만명당 범죄율

안전 점수를 설명할 때 반드시:
1. 종합 점수와 함께 CCTV 안전/범죄 안전 점수를 구분하여 설명
2. 범죄 유형별 건수와 비율을 언급 (특히 절도와 폭력이 대부분)
3. 유동인구 보정이 적용된 경우 "유동인구가 많은 지역이므로 실제 거주자 체감 안전도는 수치보다 높을 수 있습니다" 설명
4. CCTV 개수, 경찰서/소방서 거리 등 구체적 수치 제공
5. 70점 이상=안전, 40~70점=보통, 40점 미만=주의 기준으로 평가
"""


async def process_chat(
    message: str,
    conversation: list[dict] | None = None,
    context: dict | None = None,
    device_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Process a chat message through LLM with tool calling.

    Args:
        message: User's message
        conversation: Previous conversation history
        context: Additional context (e.g., selected nudges, map bounds)
        device_id: 익명 사용자 식별자(프론트 localStorage UUID). 있으면 chat_log 저장.
        session_id: 선택적 세션 ID.

    Returns:
        dict with keys: content, tool_calls, map_actions
    """
    result = await _process_chat_core(message, conversation, context)
    # 완성된 대화 로깅 (device_id 없으면 no-op, 실패는 흡수)
    log_chat(
        device_id=device_id,
        session_id=session_id,
        user_message=message,
        assistant_message=result.get("content", ""),
        tool_calls=result.get("tool_calls", []),
        context=context,
        terminated_early=False,
    )
    return result


async def _process_chat_core(
    message: str,
    conversation: list[dict] | None = None,
    context: dict | None = None,
) -> dict:
    """process_chat 본 로직 — 로깅은 상위 wrapper가 담당."""
    # Check if API key is configured
    provider_name = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider_name == "openai" and not os.getenv("OPENAI_API_KEY"):
        return {
            "content": "API 키가 설정되지 않았습니다. .env 파일에 OPENAI_API_KEY를 설정해주세요.",
            "tool_calls": [],
            "map_actions": [],
        }
    if provider_name == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
        return {
            "content": "API 키가 설정되지 않았습니다. .env 파일에 ANTHROPIC_API_KEY를 설정해주세요.",
            "tool_calls": [],
            "map_actions": [],
        }
    if provider_name == "gemini" and not os.getenv("GOOGLE_API_KEY"):
        return {
            "content": "API 키가 설정되지 않았습니다. .env 파일에 GOOGLE_API_KEY를 설정해주세요.",
            "tool_calls": [],
            "map_actions": [],
        }

    try:
        provider = get_provider()
    except Exception as e:
        logger.error(f"Failed to initialize LLM provider: {e}")
        return {
            "content": f"LLM 프로바이더 초기화에 실패했습니다: {str(e)}",
            "tool_calls": [],
            "map_actions": [],
        }

    # Build messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history
    if conversation:
        for msg in conversation:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})

    # Add context hint if provided
    if context:
        context_hint = ""
        if context.get("apartment_pnu"):
            context_hint += (
                f"사용자가 지도에서 선택한 아파트: "
                f"PNU={context['apartment_pnu']}, "
                f"이름={context.get('apartment_name', '')}. "
                f"get_apartment_detail 도구를 호출할 때 반드시 이 PNU를 query 인자로 사용하세요. "
            )
        if context.get("nudges"):
            context_hint += f"사용자가 선택한 라이프 항목: {', '.join(context['nudges'])}. "
        if context.get("bounds"):
            context_hint += "사용자가 지도에서 특정 영역을 보고 있습니다. "
        if context_hint:
            messages.append(
                {"role": "system", "content": f"[현재 맥락] {context_hint}"}
            )

    messages.append({"role": "user", "content": message})

    executed_tools: list[dict] = []
    map_actions: list[dict] = []
    seen_calls: set[tuple[str, str]] = set()
    final_content: str | None = None

    # Multi-turn tool loop: 같은 응답 내에서 여러 tool을 연쇄 호출할 수 있도록 반복
    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response: LLMResponse = await provider.chat_with_tools(
                messages=messages,
                tools=TOOL_DEFINITIONS,
                temperature=0.7,
            )
        except Exception as e:
            logger.error(f"LLM call failed (iteration {iteration}): {e}")
            return {
                "content": f"AI 서비스 호출 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요. ({type(e).__name__})",
                "tool_calls": executed_tools,
                "map_actions": map_actions,
            }

        if not response.tool_calls:
            final_content = response.content or "답변을 생성할 수 없습니다."
            break

        # 이번 턴에 실행할 tool 결과 수집
        tool_results_turn: list[dict] = []
        for tc in response.tool_calls:
            sig = (tc.name, json.dumps(tc.arguments, sort_keys=True, ensure_ascii=False))
            if sig in seen_calls:
                logger.warning(f"중복 tool 호출 감지 — skip: {sig}")
                continue
            seen_calls.add(sig)

            executor = TOOL_EXECUTORS.get(tc.name)
            if not executor:
                logger.warning(f"Unknown tool: {tc.name}")
                continue

            try:
                result = await executor(**tc.arguments)
            except Exception as e:
                logger.error(f"Tool execution failed for {tc.name}: {e}")
                result = json.dumps({"error": f"도구 실행 중 오류: {e}"}, ensure_ascii=False)

            tool_results_turn.append({"name": tc.name, "result": result})
            executed_tools.append({"name": tc.name, "arguments": tc.arguments})
            ma = _build_map_action(tc.name, result)
            if ma:
                map_actions.append(ma)

        if not tool_results_turn:
            # 모든 호출이 중복·미지원이라 실행된 게 없으면 루프 종료
            final_content = response.content or "도구 호출이 반복되어 추가 진행을 중단했습니다."
            break

        # 다음 iteration을 위해 message 히스토리에 추가
        assistant_note = response.content or f"[도구 호출: {', '.join(t['name'] for t in tool_results_turn)}]"
        messages.append({"role": "assistant", "content": assistant_note})
        tool_context = "다음은 도구 실행 결과입니다. 추가 도구 호출이 필요하면 호출하고, 충분하면 사용자에게 답변하세요.\n\n"
        for tr in tool_results_turn:
            tool_context += f"### {tr['name']} 결과:\n{tr['result']}\n\n"
        messages.append({"role": "user", "content": tool_context})

    # 루프가 MAX_ITERATIONS에 도달한 경우: 마지막 tool 결과 기반으로 한 번 더 요약 요청
    if final_content is None:
        try:
            final_response = await provider.chat(messages=messages, temperature=0.7)
            final_content = final_response.content or "도구 호출이 반복되어 답변을 완성하지 못했습니다."
        except Exception as e:
            logger.error(f"Final summary call failed: {e}")
            final_content = "도구 실행은 완료됐으나 요약 생성에 실패했습니다."

    return {
        "content": final_content,
        "tool_calls": executed_tools,
        "map_actions": map_actions,
    }


async def process_chat_stream(
    message: str,
    conversation: list[dict] | None = None,
    context: dict | None = None,
    device_id: str | None = None,
    session_id: str | None = None,
):
    """Streaming version of process_chat — yields SSE events.

    SSE 스트리밍은 클라이언트 abort / early return / 예외 모두에서 대화가
    어딘가에서 '완성 직전에 끊길' 수 있다. try/finally 로 감싸 모든 종료
    경로에서 chat_log 1회 저장을 보장한다. terminated_early 플래그로
    정상 종료 여부를 구분한다.
    """
    collected_content: list[str] = []
    collected_tool_calls: list[dict] = []
    completed_normally = False
    try:
        async for event in _process_chat_stream_core(message, conversation, context):
            data = event.get("data") or {}
            if event.get("event") == "delta":
                content = data.get("content") or ""
                if content:
                    collected_content.append(content)
            elif event.get("event") == "done":
                completed_normally = True
                # done 이벤트의 tool_calls 가 최종 누적본 — core 가 관리하는 값 사용
                final_tools = data.get("tool_calls") or []
                if final_tools:
                    collected_tool_calls = final_tools
            yield event
    finally:
        log_chat(
            device_id=device_id,
            session_id=session_id,
            user_message=message,
            assistant_message="".join(collected_content),
            tool_calls=collected_tool_calls,
            context=context,
            terminated_early=not completed_normally,
        )


async def _process_chat_stream_core(
    message: str,
    conversation: list[dict] | None = None,
    context: dict | None = None,
):
    """Streaming version of process_chat — yields SSE events."""
    # Check API key
    provider_name = os.getenv("LLM_PROVIDER", "openai").lower()
    key_map = {
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",
    }
    if provider_name in key_map and not os.getenv(key_map[provider_name]):
        yield {"event": "delta", "data": {"content": f"API 키가 설정되지 않았습니다."}}
        yield {"event": "done", "data": {"tool_calls": []}}
        return

    try:
        provider = get_provider()
    except Exception as e:
        yield {"event": "delta", "data": {"content": f"LLM 초기화 실패: {e}"}}
        yield {"event": "done", "data": {"tool_calls": []}}
        return

    # Build messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation:
        for msg in conversation:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})

    if context:
        context_hint = ""
        if context.get("apartment_pnu"):
            context_hint += (
                f"사용자가 지도에서 선택한 아파트: "
                f"PNU={context['apartment_pnu']}, "
                f"이름={context.get('apartment_name', '')}. "
                f"get_apartment_detail 도구를 호출할 때 반드시 이 PNU를 query 인자로 사용하세요. "
            )
        if context.get("nudges"):
            context_hint += f"사용자가 선택한 라이프 항목: {', '.join(context['nudges'])}. "
        if context_hint:
            messages.append({"role": "system", "content": f"[현재 맥락] {context_hint}"})

    messages.append({"role": "user", "content": message})

    executed_tools: list[dict] = []
    map_actions: list[dict] = []
    seen_calls: set[tuple[str, str]] = set()
    any_tool_called = False

    # Multi-turn tool loop: 같은 응답 내에서 여러 tool 연쇄 호출 허용
    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response: LLMResponse = await provider.chat_with_tools(
                messages=messages,
                tools=TOOL_DEFINITIONS,
                temperature=0.7,
            )
        except Exception as e:
            logger.exception(f"LLM stream call failed (iteration {iteration}): {e}")
            yield {"event": "delta", "data": {"content": f"AI 서비스 오류: {type(e).__name__}"}}
            yield {"event": "done", "data": {"tool_calls": executed_tools, "map_actions": map_actions}}
            return

        if not response.tool_calls:
            # 최종 답변: 이미 받은 content를 단일 delta로 전송
            if response.content:
                yield {"event": "delta", "data": {"content": response.content}}
            yield {"event": "done", "data": {"tool_calls": executed_tools, "map_actions": map_actions}}
            return

        # 이번 턴에 실행될 tool 처리
        tool_results_turn: list[dict] = []
        for tc in response.tool_calls:
            sig = (tc.name, json.dumps(tc.arguments, sort_keys=True, ensure_ascii=False))
            if sig in seen_calls:
                logger.warning(f"중복 tool 호출 감지 — skip: {sig}")
                continue
            seen_calls.add(sig)

            executor = TOOL_EXECUTORS.get(tc.name)
            if not executor:
                continue

            yield {"event": "tool_start", "data": {"name": tc.name}}
            try:
                result = await executor(**tc.arguments)
            except Exception as e:
                logger.error(f"Tool error {tc.name}: {e}")
                result = json.dumps({"error": str(e)}, ensure_ascii=False)
                yield {"event": "tool_done", "data": {"name": tc.name, "result_preview": f"오류: {e}"}}
            else:
                preview = _tool_preview(tc.name, result)
                yield {"event": "tool_done", "data": {"name": tc.name, "result_preview": preview}}

            tool_results_turn.append({"name": tc.name, "result": result})
            executed_tools.append({"name": tc.name, "arguments": tc.arguments})
            any_tool_called = True

            ma = _build_map_action(tc.name, result)
            if ma:
                map_actions.append(ma)
                yield {"event": "map_action", "data": ma}

        if not tool_results_turn:
            # 실행된 게 없음(중복/미지원) — 루프 종료
            if response.content:
                yield {"event": "delta", "data": {"content": response.content}}
            yield {"event": "done", "data": {"tool_calls": executed_tools, "map_actions": map_actions}}
            return

        # 다음 iteration을 위한 히스토리 추가
        assistant_note = response.content or f"[도구 호출: {', '.join(t['name'] for t in tool_results_turn)}]"
        messages.append({"role": "assistant", "content": assistant_note})
        tool_context = "다음은 도구 실행 결과입니다. 추가 도구 호출이 필요하면 호출하고, 충분하면 사용자에게 답변하세요.\n\n"
        for tr in tool_results_turn:
            tool_context += f"### {tr['name']} 결과:\n{tr['result']}\n\n"
        messages.append({"role": "user", "content": tool_context})

    # MAX_TOOL_ITERATIONS 도달 — 최종 스트리밍 요약
    if any_tool_called:
        yield {"event": "generating", "data": {"message": "답변 생성 중..."}}
    try:
        async for chunk in provider.stream_chat(messages=messages, temperature=0.7):
            yield {"event": "delta", "data": {"content": chunk}}
    except Exception as e:
        logger.error(f"Stream chat failed: {e}")
        yield {"event": "delta", "data": {"content": f"\n\n(스트리밍 오류: {e})"}}

    yield {"event": "done", "data": {"tool_calls": executed_tools, "map_actions": map_actions}}
