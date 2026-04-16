"""Chat API router with SSE streaming support."""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.chat_engine import process_chat, process_chat_stream

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    conversation: list[dict] | None = None
    context: dict | None = None


class ChatResponse(BaseModel):
    content: str
    tool_calls: list[dict] = []
    map_actions: list[dict] = []


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    """Process a chat message and return AI response with optional tool results."""
    device_id = request.headers.get("x-device-id")
    result = await process_chat(
        message=req.message,
        conversation=req.conversation,
        context=req.context,
        device_id=device_id,
    )
    return ChatResponse(**result)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """SSE streaming chat endpoint.

    Events:
      - event: tool_start   data: {"name": "tool_name"}
      - event: tool_done    data: {"name": "tool_name", "result_preview": "..."}
      - event: map_action   data: {"type": "highlight", "pnus": [...]}
      - event: delta        data: {"content": "chunk of text"}
      - event: done         data: {"tool_calls": [...]}
    """
    device_id = request.headers.get("x-device-id")

    async def event_stream():
        try:
            async for event in process_chat_stream(
                message=req.message,
                conversation=req.conversation,
                context=req.context,
                device_id=device_id,
            ):
                event_type = event.get("event", "delta")
                data = json.dumps(event.get("data", {}), ensure_ascii=False)
                yield f"event: {event_type}\ndata: {data}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
