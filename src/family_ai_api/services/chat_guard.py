import asyncio

from fastapi import HTTPException, Request, status


def enforce_rate_limit(request: Request, token_key: str) -> None:
    if not request.app.state.rate_limiter.allow(token_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
        )


async def acquire_slot(request: Request) -> asyncio.Semaphore:
    semaphore: asyncio.Semaphore = request.app.state.chat_semaphore
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many concurrent requests",
        ) from None
    return semaphore
