import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from family_ai_api.config import Settings


class OllamaError(Exception):
    status_code = 502
    detail = "model request failed"


class ModelServiceUnavailableError(OllamaError):
    status_code = 503
    detail = "model service unavailable"


class ModelNotFoundError(OllamaError):
    status_code = 502
    detail = "configured model is not available"


class ModelTimeoutError(OllamaError):
    status_code = 504
    detail = "model request timed out"


@dataclass(frozen=True)
class ChatResult:
    content: str
    model: str


def _base_payload(messages: list[dict[str, str]], settings: Settings, stream: bool) -> dict:
    return {
        "model": settings.ai_model,
        "messages": messages,
        "stream": stream,
        "think": False,
    }


def _chat_url(settings: Settings) -> str:
    return f"{settings.ollama_base_url.rstrip('/')}/api/chat"


def _client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout_seconds),
        trust_env=False,
    )


async def chat(messages: list[dict[str, str]], settings: Settings) -> ChatResult:
    try:
        async with _client(settings) as client:
            response = await asyncio.wait_for(
                client.post(_chat_url(settings), json=_base_payload(messages, settings, False)),
                timeout=settings.request_timeout_seconds,
            )
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise ModelTimeoutError from exc
    except httpx.HTTPError as exc:
        raise ModelServiceUnavailableError from exc

    if response.status_code == 404:
        raise ModelNotFoundError
    if response.status_code >= 400:
        raise OllamaError

    try:
        content = response.json()["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise OllamaError from exc
    if not isinstance(content, str):
        raise OllamaError

    return ChatResult(content=content, model=settings.ai_model)


async def chat_stream(messages: list[dict[str, str]], settings: Settings) -> AsyncIterator[str]:
    try:
        async with _client(settings) as client, client.stream(
            "POST",
            _chat_url(settings),
            json=_base_payload(messages, settings, True),
        ) as response:
            if response.status_code == 404:
                raise ModelNotFoundError
            if response.status_code >= 400:
                raise OllamaError

            async with asyncio.timeout(settings.request_timeout_seconds):
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except ValueError as exc:
                        raise OllamaError from exc
                    message = data.get("message") or {}
                    content = message.get("content") or ""
                    if content:
                        yield content
                    if data.get("done"):
                        break
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise ModelTimeoutError from exc
    except httpx.HTTPError as exc:
        raise ModelServiceUnavailableError from exc
