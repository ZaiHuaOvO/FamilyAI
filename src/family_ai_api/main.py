import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi

from family_ai_api.agent.actions import ActionStore
from family_ai_api.agent.audit import AuditStore
from family_ai_api.config import get_settings
from family_ai_api.members.store import MemberStore
from family_ai_api.routers import agent, chat, health, logs, me, memory, models, rag, tasks
from family_ai_api.services.limits import SlidingWindowRateLimiter
from family_ai_api.services.request_log import RequestLogEntry, RequestLogStore

access_logger = logging.getLogger("family_ai_api.access")


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def _reject(self, send, status_code: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                await self._reject(send, 400, "invalid content-length")
                return
            if length > self.max_bytes:
                await self._reject(send, 413, "request body too large")
                return

        received = 0
        too_large = False
        sent_413 = False

        async def limited_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    return {
                        "type": "http.request",
                        "body": b"",
                        "more_body": False,
                    }
            return message

        async def tracked_send(message):
            nonlocal sent_413
            if too_large:
                if message["type"] == "http.response.start" and not sent_413:
                    sent_413 = True
                    await self._reject(send, 413, "request body too large")
                return
            await send(message)

        await self.app(scope, limited_receive, tracked_send)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    member_store = MemberStore(settings.members_db_path)
    try:
        member_store.ensure_bootstrap(settings.api_access_token)
    finally:
        member_store.close()
    app.state.chat_semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
    app.state.rate_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_minute)
    app.state.request_log = RequestLogStore(settings.request_log_size)
    app.state.memory_extraction_semaphore = asyncio.Semaphore(1)
    app.state.agent_actions = ActionStore(settings.agent_action_ttl_seconds)
    app.state.agent_audit = AuditStore(settings.agent_audit_size)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Family AI API",
        description="家庭局域网内使用的本地大模型 API",
        version="6.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)

    @app.middleware("http")
    async def memory_no_store(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/memory"):
            response.headers["Cache-Control"] = "no-store"
        return response

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
                    member_id=getattr(request.state, "member_id", None),
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
    app.include_router(me.router, prefix="/api/v1")

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        public_paths = {
            "/api/v1/health",
            "/api/v1/logs/view",
            "/api/v1/memory/view",
            "/api/v1/tasks/view",
        }
        for path, item in schema.get("paths", {}).items():
            for method, operation in item.items():
                if method.lower() not in {"get", "post", "patch", "delete", "put"}:
                    continue
                responses = operation.setdefault("responses", {})
                if path == "/api/v1/chat/stream":
                    content = responses.get("200", {}).get("content", {})
                    content.pop("application/json", None)
                if path.startswith("/api/v1/") and path not in public_paths:
                    responses.setdefault("401", {"description": "unauthorized"})
                    responses.setdefault("503", {"description": "service unavailable"})
                if path in {
                    "/api/v1/chat",
                    "/api/v1/chat/stream",
                    "/api/v1/agent/chat",
                }:
                    responses.setdefault(
                        "429", {"description": "rate limit or concurrency exceeded"}
                    )
                    responses.setdefault("502", {"description": "upstream model error"})
                    responses.setdefault("504", {"description": "upstream timeout"})
                if path.startswith("/api/v1/agent/"):
                    responses.setdefault("403", {"description": "forbidden"})
                if method.lower() in {"post", "patch"}:
                    responses.setdefault(
                        "413", {"description": "request body too large"}
                    )
                if "{" in path:
                    responses.setdefault("404", {"description": "resource not found"})
                if path.startswith(("/api/v1/memory", "/api/v1/agent/actions")):
                    responses.setdefault("409", {"description": "conflict"})
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi

    return app


app = create_app()
