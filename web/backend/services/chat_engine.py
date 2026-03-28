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

logger = logging.getLogger(__name__)

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
1. 아파트 추천 시 반드시 search_apartments 도구를 사용하세요.
2. 추천 결과를 사용자에게 알기 쉽게 정리하여 설명하세요.
3. 점수, 주소, 주요 특징을 포함하여 답변하세요.
4. 추가 질문이나 비교가 필요한지 안내하세요.
5. 한국어로 답변하세요.
6. 출퇴근 시간 조회 시 search_commute 도구를 사용하세요. PNU가 컨텍스트에 있으면 그것을 사용하고, 없으면 먼저 get_apartment_detail로 PNU를 확인하세요.
7. 출퇴근 결과는 경로별 소요시간, 환승횟수, 요금을 표 형태로 정리하세요.

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
) -> dict:
    """Process a chat message through LLM with tool calling.

    Args:
        message: User's message
        conversation: Previous conversation history
        context: Additional context (e.g., selected nudges, map bounds)

    Returns:
        dict with keys: content, tool_calls, map_actions
    """
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

    # Step 1: Call LLM with tools
    try:
        response: LLMResponse = await provider.chat_with_tools(
            messages=messages,
            tools=TOOL_DEFINITIONS,
            temperature=0.7,
        )
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return {
            "content": f"AI 서비스 호출 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요. ({type(e).__name__})",
            "tool_calls": [],
            "map_actions": [],
        }

    tool_results = []
    map_actions = []
    executed_tools = []

    # Step 2: Execute tool calls if any
    if response.tool_calls:
        for tc in response.tool_calls:
            executor = TOOL_EXECUTORS.get(tc.name)
            if not executor:
                logger.warning(f"Unknown tool: {tc.name}")
                continue

            try:
                result = await executor(**tc.arguments)
                tool_results.append(
                    {
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "result": result,
                    }
                )
                executed_tools.append(
                    {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                )

                # Build map actions from search results
                if tc.name == "search_apartments":
                    try:
                        parsed = json.loads(result)
                        if parsed.get("results"):
                            pnus = [r["pnu"] for r in parsed["results"]]
                            map_actions.append(
                                {
                                    "type": "highlight",
                                    "pnus": pnus,
                                    "apartments": [
                                        {
                                            "pnu": r["pnu"],
                                            "bld_nm": r["bld_nm"],
                                            "lat": r["lat"],
                                            "lng": r["lng"],
                                            "score": r["score"],
                                        }
                                        for r in parsed["results"]
                                    ],
                                }
                            )
                    except json.JSONDecodeError:
                        pass

            except Exception as e:
                logger.error(f"Tool execution failed for {tc.name}: {e}")
                tool_results.append(
                    {
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "result": json.dumps(
                            {"error": f"도구 실행 중 오류: {str(e)}"},
                            ensure_ascii=False,
                        ),
                    }
                )

    # Step 3: If tools were called, send results back to LLM for final answer
    if tool_results:
        # Add assistant message with tool calls
        if response.content:
            messages.append({"role": "assistant", "content": response.content})
        else:
            # For OpenAI format, we need to indicate the assistant wanted to call tools
            messages.append(
                {
                    "role": "assistant",
                    "content": f"[도구 호출 완료: {', '.join(t['name'] for t in executed_tools)}]",
                }
            )

        # Add tool results as user context
        tool_context = "다음은 도구 실행 결과입니다. 이 결과를 바탕으로 사용자에게 답변해주세요:\n\n"
        for tr in tool_results:
            tool_context += f"### {tr['name']} 결과:\n{tr['result']}\n\n"

        messages.append({"role": "user", "content": tool_context})

        # Get final response
        try:
            final_response = await provider.chat(
                messages=messages,
                temperature=0.7,
            )
            final_content = final_response.content or "답변을 생성할 수 없습니다."
        except Exception as e:
            logger.error(f"Final LLM call failed: {e}")
            # Fallback: provide raw tool results
            final_content = "도구 실행 결과를 요약하는 중 오류가 발생했습니다. 원본 결과를 제공합니다:\n\n"
            for tr in tool_results:
                final_content += f"**{tr['name']}**:\n{tr['result']}\n\n"
    else:
        final_content = response.content or "답변을 생성할 수 없습니다."

    return {
        "content": final_content,
        "tool_calls": executed_tools,
        "map_actions": map_actions,
    }


async def process_chat_stream(
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

    # Step 1: LLM with tools (non-streaming — need to see tool calls)
    try:
        response: LLMResponse = await provider.chat_with_tools(
            messages=messages,
            tools=TOOL_DEFINITIONS,
            temperature=0.7,
        )
    except Exception as e:
        yield {"event": "delta", "data": {"content": f"AI 서비스 오류: {type(e).__name__}"}}
        yield {"event": "done", "data": {"tool_calls": []}}
        return

    tool_results = []
    map_actions = []
    executed_tools = []

    # Step 2: Execute tools
    if response.tool_calls:
        for tc in response.tool_calls:
            executor = TOOL_EXECUTORS.get(tc.name)
            if not executor:
                continue

            yield {"event": "tool_start", "data": {"name": tc.name}}

            try:
                result = await executor(**tc.arguments)
                tool_results.append({"tool_call_id": tc.id, "name": tc.name, "result": result})
                executed_tools.append({"name": tc.name, "arguments": tc.arguments})

                # Preview for client
                try:
                    parsed = json.loads(result)
                    preview = ""
                    if tc.name == "get_apartment_detail" and "basic" in parsed:
                        preview = parsed["basic"].get("name", "")
                    elif tc.name == "search_apartments" and "results" in parsed:
                        preview = f"{len(parsed['results'])}건 검색됨"
                    yield {"event": "tool_done", "data": {"name": tc.name, "result_preview": preview}}
                except Exception:
                    yield {"event": "tool_done", "data": {"name": tc.name, "result_preview": ""}}

                # Map actions
                if tc.name == "search_apartments":
                    try:
                        parsed = json.loads(result)
                        if parsed.get("results"):
                            ma = {
                                "type": "highlight",
                                "pnus": [r["pnu"] for r in parsed["results"]],
                                "apartments": [
                                    {"pnu": r["pnu"], "bld_nm": r["bld_nm"],
                                     "lat": r["lat"], "lng": r["lng"], "score": r["score"]}
                                    for r in parsed["results"]
                                ],
                            }
                            map_actions.append(ma)
                            yield {"event": "map_action", "data": ma}
                    except json.JSONDecodeError:
                        pass

            except Exception as e:
                logger.error(f"Tool error {tc.name}: {e}")
                tool_results.append({
                    "tool_call_id": tc.id, "name": tc.name,
                    "result": json.dumps({"error": str(e)}, ensure_ascii=False),
                })
                yield {"event": "tool_done", "data": {"name": tc.name, "result_preview": f"오류: {e}"}}

    # Step 3: Stream final response
    if tool_results:
        if response.content:
            messages.append({"role": "assistant", "content": response.content})
        else:
            messages.append({
                "role": "assistant",
                "content": f"[도구 호출 완료: {', '.join(t['name'] for t in executed_tools)}]",
            })

        tool_context = "다음은 도구 실행 결과입니다. 이 결과를 바탕으로 사용자에게 답변해주세요:\n\n"
        for tr in tool_results:
            tool_context += f"### {tr['name']} 결과:\n{tr['result']}\n\n"
        messages.append({"role": "user", "content": tool_context})

    # Stream the final response
    if tool_results:
        yield {"event": "generating", "data": {"message": "답변 생성 중..."}}
    try:
        async for chunk in provider.stream_chat(messages=messages, temperature=0.7):
            yield {"event": "delta", "data": {"content": chunk}}
    except Exception as e:
        logger.error(f"Stream chat failed: {e}")
        yield {"event": "delta", "data": {"content": f"\n\n(스트리밍 오류: {e})"}}

    yield {"event": "done", "data": {"tool_calls": executed_tools, "map_actions": map_actions}}
