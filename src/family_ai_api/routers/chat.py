import asyncio
import json
import logging
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from family_ai_api.config import Settings, get_settings
from family_ai_api.security import require_token
from family_ai_api.services import ollama_client
from family_ai_api.services.chat_guard import acquire_slot, enforce_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    message: str
    model: str
    duration_ms: int


def build_messages(payload: ChatRequest, settings: Settings) -> list[dict[str, str]]:
    message = payload.message.strip()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="message must not be empty",
        )
    if len(payload.message) > settings.max_message_chars:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="message is too long",
        )
    if len(payload.history) > settings.max_history_messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="history is too long",
        )

    messages: list[dict[str, str]] = []
    history_chars = 0
    for item in payload.history:
        content = item.content.strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="history content must not be empty",
            )
        history_chars += len(item.content)
        messages.append({"role": item.role, "content": content})

    if history_chars > settings.max_history_chars:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="history is too large",
        )

    messages.append({"role": "user", "content": message})
    return messages


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    token_key: Annotated[str, Depends(require_token)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatResponse:
    messages = build_messages(payload, settings)
    enforce_rate_limit(request, token_key)
    semaphore = await acquire_slot(request)

    try:
        started = time.perf_counter()
        result = await ollama_client.chat(messages, settings)
        duration_ms = int((time.perf_counter() - started) * 1000)
    except ollama_client.OllamaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        semaphore.release()

    return ChatResponse(message=result.content, model=result.model, duration_ms=duration_ms)


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    token_key: Annotated[str, Depends(require_token)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    messages = build_messages(payload, settings)
    enforce_rate_limit(request, token_key)
    semaphore: asyncio.Semaphore = request.app.state.chat_semaphore

    async def event_generator():
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
        except TimeoutError:
            yield sse_event(
                "error",
                {"detail": "too many concurrent requests", "status": 429},
            )
            return

        started = time.perf_counter()
        try:
            async for delta in ollama_client.chat_stream(messages, settings):
                yield sse_event("delta", {"delta": delta})
            duration_ms = int((time.perf_counter() - started) * 1000)
            yield sse_event("done", {"model": settings.ai_model, "duration_ms": duration_ms})
        except ollama_client.OllamaError as exc:
            yield sse_event("error", {"detail": exc.detail, "status": exc.status_code})
        except Exception:
            logger.warning("chat stream failed", exc_info=True)
            yield sse_event("error", {"detail": "model request failed", "status": 502})
        finally:
            semaphore.release()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
