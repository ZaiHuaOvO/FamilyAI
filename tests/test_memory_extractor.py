import asyncio

import pytest

from family_ai_api.config import Settings
from family_ai_api.memory.extractor import Candidate, parse_candidates, run_auto_extraction
from family_ai_api.memory.store import MemoryStore


def settings(tmp_path, **overrides) -> Settings:
    values = {
        "api_access_token": "test-token",
        "ai_model": "test-model",
        "memory_db_path": str(tmp_path / "memory.db"),
        "auto_memory_enabled": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_parse_candidates_deduplicates_and_parses_code_fence(tmp_path) -> None:
    text = (
        '```json\n{"memories":['
        '{"content":"喜欢户外","tags":["家庭"]},'
        '{"content":"喜欢户外","tags":["重复"]},'
        '{"content":"  "}'
        "]}\n```"
    )

    candidates = parse_candidates(text, settings(tmp_path))

    assert candidates == [Candidate(content="喜欢户外", tags=["家庭"])]


def test_parse_candidates_rejects_invalid_output(tmp_path) -> None:
    assert parse_candidates("没有 JSON", settings(tmp_path)) == []
    assert parse_candidates("{invalid}", settings(tmp_path)) == []
    assert parse_candidates('{"memories": "x"}', settings(tmp_path)) == []


def test_parse_candidates_respects_max_items(tmp_path) -> None:
    text = (
        '{"memories":['
        '{"content":"一"},{"content":"二"},{"content":"三"},{"content":"四"}'
        "]}"
    )

    candidates = parse_candidates(
        text, settings(tmp_path, auto_memory_max_items=3)
    )

    assert [candidate.content for candidate in candidates] == ["一", "二", "三"]


@pytest.mark.asyncio
async def test_run_auto_extraction_saves_and_deduplicates(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = settings(tmp_path)

    async def fake_extract(message: str, settings: Settings):
        return [Candidate("喜欢户外", ["家庭"])]

    async def fake_embed(texts: list[str], settings: Settings, batch_size: int = 16):
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(
        "family_ai_api.memory.extractor.extract_candidates", fake_extract
    )
    monkeypatch.setattr("family_ai_api.memory.extractor.embed_texts", fake_embed)

    semaphore = asyncio.Semaphore(1)
    await run_auto_extraction("请记住我喜欢户外", config, semaphore)
    await run_auto_extraction("请记住我喜欢户外", config, semaphore)

    store = MemoryStore(config.memory_db_path)
    try:
        memories = store.recent()
        assert len(memories) == 1
        assert memories[0].content == "喜欢户外"
        assert memories[0].source == "auto"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_run_auto_extraction_disabled_and_no_semaphore(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = settings(tmp_path, auto_memory_enabled=False)
    called = False

    async def fake_extract(message: str, settings: Settings):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        "family_ai_api.memory.extractor.extract_candidates", fake_extract
    )

    await run_auto_extraction("请记住我喜欢户外", config, asyncio.Semaphore(1))
    await run_auto_extraction("请记住我喜欢户外", settings(tmp_path), None)

    assert called is False
    store = MemoryStore(config.memory_db_path)
    try:
        assert store.count() == 0
    finally:
        store.close()
