import asyncio
import json
import logging
from dataclasses import dataclass

from family_ai_api.config import Settings
from family_ai_api.knowledge.embeddings import EmbeddingError, embed_texts
from family_ai_api.memory.service import MemoryValidationError, normalize_content, normalize_tags
from family_ai_api.memory.store import DuplicateMemoryError, MemoryStore
from family_ai_api.services import ollama_client

logger = logging.getLogger(__name__)

AUTO_MEMORY_MAX_CHARS = 200

EXTRACTION_PROMPT = """你是记忆提取器。只从用户消息中提取用户明确陈述的、长期稳定的个人事实、偏好或约定。

规则：
1. 只提取用户自己说出的内容，不推断。
2. 不提取临时信息（例如“今天”“这次”“当前”）。
3. 不提取密码、证件号、健康、财务等敏感信息。
4. 最多提取 3 条，每条不超过 100 字。
5. 如果没有可长期记住的内容，返回 {"memories": []}。

只输出 JSON，不要解释。格式：
{"memories":[{"content":"...","tags":["..."]}]}"""


@dataclass(frozen=True)
class Candidate:
    content: str
    tags: list[str]


def parse_candidates(text: str, settings: Settings) -> list[Candidate]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return []

    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return []

    items = data.get("memories")
    if not isinstance(items, list):
        return []

    candidates: list[Candidate] = []
    seen: set[str] = set()
    for item in items[: settings.auto_memory_max_items]:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, str):
            continue
        try:
            content = normalize_content(content, settings)
        except MemoryValidationError:
            continue
        if len(content) > AUTO_MEMORY_MAX_CHARS or content in seen:
            continue

        raw_tags = item.get("tags") or []
        if not isinstance(raw_tags, list):
            raw_tags = []
        try:
            tags = normalize_tags([str(tag) for tag in raw_tags])
        except MemoryValidationError:
            tags = []

        seen.add(content)
        candidates.append(Candidate(content=content, tags=tags))

    return candidates


async def extract_candidates(message: str, settings: Settings) -> list[Candidate]:
    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": f"用户消息：\n{message}"},
    ]
    result = await ollama_client.chat(messages, settings)
    return parse_candidates(result.content, settings)


async def run_auto_extraction(
    message: str,
    settings: Settings,
    semaphore: asyncio.Semaphore | None,
) -> None:
    if semaphore is None or not settings.auto_memory_enabled:
        return
    text = message.strip()
    if len(text) < settings.auto_memory_min_chars:
        return

    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
    except TimeoutError:
        return

    try:
        candidates = await extract_candidates(text, settings)
        if not candidates:
            return

        embeddings = await embed_texts([candidate.content for candidate in candidates], settings)
        store = MemoryStore(settings.memory_db_path)
        try:
            for candidate, embedding in zip(candidates, embeddings, strict=True):
                try:
                    store.add(candidate.content, candidate.tags, "auto", embedding)
                except DuplicateMemoryError:
                    continue
        finally:
            store.close()
    except (ollama_client.OllamaError, EmbeddingError) as exc:
        logger.warning("auto memory extraction skipped: %s", type(exc).__name__)
    finally:
        semaphore.release()
