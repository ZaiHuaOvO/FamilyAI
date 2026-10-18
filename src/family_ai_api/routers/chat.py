import asyncio
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from family_ai_api.config import Settings, get_settings
from family_ai_api.security import require_token
from family_ai_api.services import ollama_client

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    message: str
    model: str
    duration_ms: int


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    token_key: Annotated[str, Depends(require_token)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatResponse:
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

    if not request.app.state.rate_limiter.allow(token_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
        )

    semaphore: asyncio.Semaphore = request.app.state.chat_semaphore
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many concurrent requests",
        ) from None

    try:
        started = time.perf_counter()
        result = await ollama_client.chat(message, settings)
        duration_ms = int((time.perf_counter() - started) * 1000)
    except ollama_client.OllamaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        semaphore.release()

    return ChatResponse(message=result.content, model=result.model, duration_ms=duration_ms)
