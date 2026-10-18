from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from family_ai_api.config import Settings, get_settings
from family_ai_api.knowledge import service as rag_service
from family_ai_api.knowledge.embeddings import EmbeddingError
from family_ai_api.knowledge.store import KnowledgeStore
from family_ai_api.security import require_token
from family_ai_api.services import ollama_client
from family_ai_api.services.chat_guard import acquire_slot, enforce_rate_limit

router = APIRouter(tags=["knowledge"])


class RagQueryRequest(BaseModel):
    message: str
    top_k: int | None = Field(default=None, ge=1, le=10)


class RagSourceModel(BaseModel):
    title: str
    path: str
    chunk_index: int
    score: float


class RagQueryResponse(BaseModel):
    answer: str
    model: str
    duration_ms: int
    sources: list[RagSourceModel]


@router.post("/rag/query", response_model=RagQueryResponse)
async def rag_query(
    payload: RagQueryRequest,
    request: Request,
    token_key: Annotated[str, Depends(require_token)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RagQueryResponse:
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
            result = await rag_service.answer(message, settings, payload.top_k)
        except EmbeddingError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="embedding service unavailable",
            ) from exc
        except rag_service.EmptyKnowledgeBaseError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="knowledge base is empty",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="knowledge base index is incompatible; re-index required",
            ) from exc
        except ollama_client.OllamaError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        semaphore.release()

    return RagQueryResponse(
        answer=result.answer,
        model=result.model,
        duration_ms=result.duration_ms,
        sources=[
            RagSourceModel(
                title=source.title,
                path=source.path,
                chunk_index=source.chunk_index,
                score=source.score,
            )
            for source in result.sources
        ],
    )


@router.get("/kb/stats", dependencies=[Depends(require_token)])
async def kb_stats(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    store = KnowledgeStore(settings.kb_db_path)
    try:
        stats = store.stats()
    finally:
        store.close()
    return {**stats, "embedding_model": settings.embedding_model}
