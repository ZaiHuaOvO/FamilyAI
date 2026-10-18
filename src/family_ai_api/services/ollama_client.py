import asyncio
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


async def chat(message: str, settings: Settings) -> ChatResult:
    payload = {
        "model": settings.ai_model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
        "think": False,
    }
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            trust_env=False,
        ) as client:
            response = await asyncio.wait_for(
                client.post(url, json=payload),
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
