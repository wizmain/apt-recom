# ADR-003: LLM 프로바이더 추상화 (Factory 패턴)

- **상태**: Accepted
- **날짜**: 2026-03-25

## 맥락

AI 챗봇 구현 시 OpenAI, Claude, Gemini 등 여러 LLM을 지원해야 했다. 각 프로바이더마다 API 형식, Tool Calling 스키마, 스트리밍 방식이 다르다.

## 결정

`BaseLLMProvider` 추상 클래스를 정의하고, 각 프로바이더별 구현체를 Factory 패턴으로 생성한다. `LLM_PROVIDER` 환경변수로 런타임에 프로바이더를 전환한다.

## 근거

- **유연성**: 환경변수 하나로 LLM을 전환할 수 있어 비용/성능 비교가 용이하다.
- **Tool 스키마 통일**: 내부 통일 포맷으로 Tool을 정의하고, `tool_adapter.py`가 각 프로바이더 형식으로 자동 변환한다.
- **확장성**: 새 프로바이더 추가 시 구현체만 작성하면 된다.

## 구조

```
services/llm/
├── base.py              # BaseLLMProvider ABC, Tool 타입 정의
├── factory.py           # get_llm_provider() — LLM_PROVIDER 환경변수 기반
├── openai_provider.py   # OpenAI GPT (기본)
├── claude_provider.py   # Anthropic Claude
├── gemini_provider.py   # Google Gemini
└── tool_adapter.py      # Tool 스키마 변환
```

## 트레이드오프

- 프로바이더별 고유 기능(예: Claude의 thinking, Gemini의 grounding)을 추상화에서 표현하기 어렵다.
- 추상화 레이어로 인한 약간의 코드 복잡도 증가.

## 결과

- 챗봇은 7개 Tool(검색, 상세, 비교, 시세, 학군, 지식, 출퇴근)을 프로바이더 무관하게 사용한다.
- `.env`의 `LLM_PROVIDER=openai|claude|gemini`으로 전환한다.
