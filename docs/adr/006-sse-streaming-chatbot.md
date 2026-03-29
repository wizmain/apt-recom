# ADR-006: 챗봇 SSE 스트리밍 응답

- **상태**: Accepted
- **날짜**: 2026-03-25

## 맥락

AI 챗봇 응답은 LLM 생성 특성상 수 초가 걸린다. 전체 응답을 기다린 후 한 번에 표시하면 UX가 나빠진다.

## 결정

Server-Sent Events (SSE)를 사용하여 LLM 응답을 토큰 단위로 실시간 스트리밍한다.

## 근거

- **UX**: 사용자가 답변이 생성되는 과정을 실시간으로 볼 수 있다.
- **단순성**: WebSocket 대비 SSE는 단방향이라 구현이 간단하다. 챗봇은 요청-응답 패턴이므로 양방향이 불필요하다.
- **호환성**: FastAPI의 `StreamingResponse` + 프론트엔드 `EventSource`로 구현이 용이하다.

## 메시지 타입

```
data: {"type": "text", "content": "..."}           # 텍스트 토큰
data: {"type": "tool_call", "name": "...", ...}    # Tool 호출 알림
data: {"type": "apartment_card", "data": [...]}    # 아파트 카드 데이터
data: {"type": "map_action", "action": "..."}      # 지도 연동 액션
data: {"type": "done"}                             # 스트림 종료
```

## 트레이드오프

- SSE는 단방향이므로 클라이언트에서 스트림 중간에 취소하려면 별도 메커니즘이 필요하다.
- 네트워크 끊김 시 재연결 로직이 필요하다.

## 결과

- 엔드포인트: `POST /api/chat/stream`
- 프론트엔드: `useChat` 훅에서 `EventSource`로 SSE 수신 및 상태 관리.
- Tool 실행 결과(아파트 카드, 비교 테이블 등)도 SSE 이벤트로 전달.
