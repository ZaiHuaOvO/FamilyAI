import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from family_ai_api.agent import planner, registry
from family_ai_api.config import Settings, get_settings
from family_ai_api.knowledge.embeddings import EmbeddingError
from family_ai_api.security import require_token
from family_ai_api.services import ollama_client
from family_ai_api.services.chat_guard import acquire_slot, enforce_rate_limit

router = APIRouter(tags=["agent"])


class AgentChatRequest(BaseModel):
    message: str


class ToolCallInfo(BaseModel):
    name: str
    status: str


class PendingActionInfo(BaseModel):
    id: str
    tool: str
    arguments: dict
    expires_at: str


class AgentChatResponse(BaseModel):
    answer: str
    tool: ToolCallInfo | None = None
    pending_action: PendingActionInfo | None = None


class ToolInfo(BaseModel):
    name: str
    description: str
    parameters: dict
    write: bool


class ToolListResponse(BaseModel):
    tools: list[ToolInfo]


class AuditEntryModel(BaseModel):
    timestamp: str
    tool: str
    write: bool
    status: str
    duration_ms: float
    action_id: str | None


class AuditResponse(BaseModel):
    entries: list[AuditEntryModel]


class ConfirmResponse(BaseModel):
    executed: bool
    tool: str
    result: Any


def _agent_state(request: Request):
    actions = getattr(request.app.state, "agent_actions", None)
    audit = getattr(request.app.state, "agent_audit", None)
    return actions, audit


def _audit(
    request: Request,
    tool: str,
    write: bool,
    status: str,
    started: float,
    action_id: str | None = None,
) -> None:
    _, audit = _agent_state(request)
    if audit is not None:
        audit.add(tool, write, status, (time.perf_counter() - started) * 1000, action_id)


def _ollama_http_error(exc: ollama_client.OllamaError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/agent/chat", response_model=AgentChatResponse)
async def agent_chat(
    payload: AgentChatRequest,
    request: Request,
    token_key: Annotated[str, Depends(require_token)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentChatResponse:
    if not settings.agent_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="agent is disabled",
        )

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

    enforce_rate_limit(request, token_key)
    semaphore = await acquire_slot(request)
    try:
        try:
            plan = await planner.plan(message, settings)
        except ollama_client.OllamaError as exc:
            raise _ollama_http_error(exc) from exc

        if plan is None:
            try:
                answer = await planner.answer_without_tool(message, settings)
            except ollama_client.OllamaError as exc:
                raise _ollama_http_error(exc) from exc
            return AgentChatResponse(answer=answer)

        if plan.tool.write:
            if not settings.agent_write_tools_enabled:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="write tools are disabled",
                )
            actions, _ = _agent_state(request)
            if actions is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="agent actions are not initialized",
                )
            action = actions.create(plan.tool.name, plan.arguments, token_key)
            return AgentChatResponse(
                answer=planner.confirmation_text(plan),
                pending_action=PendingActionInfo(
                    id=action.id,
                    tool=action.tool,
                    arguments=action.arguments,
                    expires_at=action.expires_at,
                ),
            )

        started = time.perf_counter()
        try:
            result = await registry.execute_tool(
                plan.tool.name, plan.arguments, settings
            )
        except (registry.ToolExecutionError, registry.ToolValidationError) as exc:
            _audit(request, plan.tool.name, False, "error", started)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
            ) from exc
        except EmbeddingError as exc:
            _audit(request, plan.tool.name, False, "error", started)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="embedding service unavailable",
            ) from exc
        _audit(request, plan.tool.name, False, "ok", started)

        result_text = registry.tool_result_text(
            result, settings.agent_max_tool_result_chars
        )
        try:
            answer = await planner.answer_with_tool(message, result_text, settings)
        except ollama_client.OllamaError as exc:
            raise _ollama_http_error(exc) from exc

        return AgentChatResponse(
            answer=answer,
            tool=ToolCallInfo(name=plan.tool.name, status="ok"),
        )
    finally:
        semaphore.release()


@router.get(
    "/agent/tools",
    response_model=ToolListResponse,
    dependencies=[Depends(require_token)],
)
async def list_tools() -> ToolListResponse:
    return ToolListResponse(tools=[ToolInfo(**spec) for spec in registry.tool_specs()])


@router.get(
    "/agent/audit",
    response_model=AuditResponse,
    dependencies=[Depends(require_token)],
)
async def list_audit(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditResponse:
    _, audit = _agent_state(request)
    entries = audit.recent(limit) if audit is not None else []
    return AuditResponse(
        entries=[AuditEntryModel(**entry.as_dict()) for entry in entries]
    )


@router.post(
    "/agent/actions/{action_id}/confirm",
    response_model=ConfirmResponse,
)
async def confirm_action(
    action_id: str,
    request: Request,
    token_key: Annotated[str, Depends(require_token)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConfirmResponse:
    if not settings.agent_enabled or not settings.agent_write_tools_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="write tools are disabled",
        )

    actions, _ = _agent_state(request)
    if actions is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="agent actions are not initialized",
        )

    action = actions.get(action_id, token_key)
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="action not found or expired",
        )

    try:
        normalized = registry.validate_arguments(
            action.tool, action.arguments, settings
        )
    except registry.ToolError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    action = actions.pop(action_id, token_key)
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="action not found or expired",
        )

    started = time.perf_counter()
    try:
        result = await registry.execute_tool(action.tool, normalized, settings)
    except (registry.ToolExecutionError, registry.ToolValidationError) as exc:
        _audit(request, action.tool, True, "error", started, action.id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except EmbeddingError as exc:
        _audit(request, action.tool, True, "error", started, action.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="embedding service unavailable",
        ) from exc

    _audit(request, action.tool, True, "ok", started, action.id)
    return ConfirmResponse(
        executed=True,
        tool=action.tool,
        result=registry.to_jsonable(result),
    )


@router.post(
    "/agent/actions/{action_id}/cancel",
)
async def cancel_action(
    action_id: str,
    request: Request,
    token_key: Annotated[str, Depends(require_token)],
) -> dict[str, bool]:
    actions, _ = _agent_state(request)
    if actions is None or not actions.cancel(action_id, token_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="action not found or expired",
        )
    return {"cancelled": True}
