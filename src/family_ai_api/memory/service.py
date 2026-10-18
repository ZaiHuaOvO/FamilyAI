from family_ai_api.config import Settings
from family_ai_api.knowledge.embeddings import embed_query, embed_texts
from family_ai_api.memory.store import Memory, MemorySearchResult, MemoryStore

MAX_TAGS = 5
MAX_TAG_CHARS = 20


class MemoryValidationError(Exception):
    pass


class MemoryNotFoundError(Exception):
    pass


def normalize_content(content: str, settings: Settings) -> str:
    text = content.strip()
    if not text:
        raise MemoryValidationError("content must not be empty")
    if len(content) > settings.memory_max_chars:
        raise MemoryValidationError("content is too long")
    return text


def normalize_tags(tags: list[str]) -> list[str]:
    cleaned = [tag.strip() for tag in tags if tag.strip()]
    if len(cleaned) > MAX_TAGS:
        raise MemoryValidationError("too many tags")
    if any(len(tag) > MAX_TAG_CHARS for tag in cleaned):
        raise MemoryValidationError("tag is too long")
    return list(dict.fromkeys(cleaned))


async def add_memory(
    content: str,
    tags: list[str],
    settings: Settings,
    source: str = "explicit",
) -> Memory:
    text = normalize_content(content, settings)
    normalized_tags = normalize_tags(tags)
    embeddings = await embed_texts([text], settings)

    store = MemoryStore(settings.memory_db_path)
    try:
        return store.add(text, normalized_tags, source, embeddings[0])
    finally:
        store.close()


async def update_memory(
    memory_id: int,
    content: str | None,
    tags: list[str] | None,
    settings: Settings,
) -> Memory:
    if content is None and tags is None:
        raise MemoryValidationError("no fields to update")

    store = MemoryStore(settings.memory_db_path)
    try:
        existing = store.get(memory_id)
        if existing is None:
            raise MemoryNotFoundError

        new_content = normalize_content(content, settings) if content is not None else None
        new_tags = normalize_tags(tags) if tags is not None else None
        embedding = None
        if new_content is not None and new_content != existing.content:
            embedding = (await embed_texts([new_content], settings))[0]

        updated = store.update(memory_id, new_content, new_tags, embedding)
        if updated is None:
            raise MemoryNotFoundError
        return updated
    finally:
        store.close()


async def delete_memory(memory_id: int, settings: Settings) -> bool:
    store = MemoryStore(settings.memory_db_path)
    try:
        return store.delete(memory_id)
    finally:
        store.close()


async def list_memories(
    query: str | None,
    limit: int,
    settings: Settings,
) -> list[Memory] | list[MemorySearchResult]:
    if query is not None and query.strip():
        embedding = await embed_query(query.strip(), settings)
        store = MemoryStore(settings.memory_db_path)
        try:
            return store.search(embedding, limit, settings.memory_min_score)
        finally:
            store.close()

    store = MemoryStore(settings.memory_db_path)
    try:
        return store.recent(limit)
    finally:
        store.close()


async def build_context(question: str, settings: Settings) -> str | None:
    embedding = await embed_query(question, settings)

    store = MemoryStore(settings.memory_db_path)
    try:
        results = store.search(
            embedding,
            settings.memory_top_k,
            settings.memory_min_score,
        )
    finally:
        store.close()

    if not results:
        return None

    lines: list[str] = []
    used_chars = 0
    for result in results:
        line = f"- {result.memory.content}"
        if used_chars + len(line) + 1 > settings.memory_max_context_chars:
            break
        lines.append(line)
        used_chars += len(line) + 1

    if not lines:
        return None
    return "以下是用户长期保存的记忆，仅在相关时参考：\n" + "\n".join(lines)
