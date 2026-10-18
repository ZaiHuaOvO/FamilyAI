import time
from dataclasses import dataclass

from family_ai_api.config import Settings
from family_ai_api.knowledge.embeddings import embed_query
from family_ai_api.knowledge.store import KnowledgeStore
from family_ai_api.services import ollama_client


class EmptyKnowledgeBaseError(Exception):
    pass


@dataclass(frozen=True)
class RagSource:
    title: str
    path: str
    chunk_index: int
    score: float


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    model: str
    duration_ms: int
    sources: list[RagSource]


async def answer(
    question: str,
    settings: Settings,
    top_k: int | None = None,
) -> RagAnswer:
    query_embedding = await embed_query(question, settings)

    store = KnowledgeStore(settings.kb_db_path)
    try:
        results = store.search(
            query_embedding,
            top_k if top_k is not None else settings.kb_top_k,
        )
    finally:
        store.close()

    if not results:
        raise EmptyKnowledgeBaseError

    context_parts: list[str] = []
    sources: list[RagSource] = []
    used_chars = 0

    for result in results:
        block = (
            f"[来源: {result.title} | {result.source} | 片段 {result.chunk_index}]\n"
            f"{result.content}"
        )
        remaining = settings.kb_max_context_chars - used_chars
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining]
        context_parts.append(block)
        used_chars += len(block)
        sources.append(
            RagSource(
                title=result.title,
                path=result.source,
                chunk_index=result.chunk_index,
                score=round(result.score, 4),
            )
        )

    context = "\n\n".join(context_parts)
    messages = [
        {
            "role": "system",
            "content": (
                "你是家庭知识库助手。只根据提供的资料回答；"
                "如果资料不足，明确说明资料中没有相关信息，不要编造。回答使用中文。"
            ),
        },
        {
            "role": "user",
            "content": f"资料：\n{context}\n\n问题：{question}",
        },
    ]

    started = time.perf_counter()
    result = await ollama_client.chat(messages, settings)
    duration_ms = int((time.perf_counter() - started) * 1000)

    return RagAnswer(
        answer=result.content,
        model=result.model,
        duration_ms=duration_ms,
        sources=sources,
    )
