import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from family_ai_api.agent.actions import ActionStore
from family_ai_api.agent.audit import AuditStore
from family_ai_api.config import get_settings
from family_ai_api.routers import agent, chat, health, logs, memory, models, rag, tasks
from family_ai_api.services.limits import SlidingWindowRateLimiter
from family_ai_api.services.request_log import RequestLogEntry, RequestLogStore

access_logger = logging.getLogger("family_ai_api.access")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.chat_semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
    app.state.rate_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_minute)
    app.state.request_log = RequestLogStore(settings.request_log_size)
    app.state.memory_extraction_semaphore = asyncio.Semaphore(1)
    app.state.agent_actions = ActionStore(settings.agent_action_ttl_seconds)
    app.state.agent_audit = AuditStore(settings.agent_audit_size)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Family AI API",
        description="家庭局域网内使用的本地大模型 API",
        version="5.0.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def limit_request_body(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                return JSONResponse({"detail": "invalid content-length"}, status_code=400)
            if length > get_settings().max_request_bytes:
                return JSONResponse({"detail": "request body too large"}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        access_logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        store = getattr(request.app.state, "request_log", None)
        if store is not None:
            store.add(
                RequestLogEntry(
                    timestamp=RequestLogStore.now(),
                    method=request.method,
                    path=request.url.path,
                    status=response.status_code,
                    duration_ms=round(duration_ms, 1),
                    client=request.client.host if request.client else "unknown",
                )
            )
        return response

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(models.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(logs.router, prefix="/api/v1")
    app.include_router(rag.router, prefix="/api/v1")
    app.include_router(memory.router, prefix="/api/v1")
    app.include_router(tasks.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")
    return app


app = create_app()
