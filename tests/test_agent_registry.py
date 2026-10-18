import pytest

from family_ai_api.agent import registry
from family_ai_api.config import Settings
from family_ai_api.knowledge.store import KnowledgeStore
from family_ai_api.tasks.store import TaskStore


def settings(tmp_path, **overrides) -> Settings:
    values = {
        "api_access_token": "test-token",
        "ai_model": "test-model",
        "tasks_db_path": str(tmp_path / "tasks.db"),
        "memory_db_path": str(tmp_path / "memory.db"),
        "kb_db_path": str(tmp_path / "kb.db"),
    }
    values.update(overrides)
    return Settings(**values)


def test_validate_arguments() -> None:
    config = Settings(api_access_token="x", ai_model="m")

    assert registry.validate_arguments("get_briefing", {}, config) == {}
    assert registry.validate_arguments("list_tasks", {}, config) == {
        "status": "all",
        "due": "all",
    }
    assert registry.validate_arguments(
        "search_knowledge", {"query": " 模型 ", "top_k": 3}, config
    ) == {"query": "模型", "top_k": 3}
    assert registry.validate_arguments("list_memories", {}, config) == {
        "query": None,
        "limit": 20,
    }
    assert registry.validate_arguments(
        "create_task", {"title": " 买菜 "}, config
    )["title"] == "买菜"
    assert registry.validate_arguments(
        "complete_task", {"task_id": 3}, config
    ) == {"task_id": 3}
    assert registry.validate_arguments(
        "add_memory", {"content": "喜欢户外", "tags": ["家庭"]}, config
    ) == {"content": "喜欢户外", "tags": ["家庭"]}


def test_validate_arguments_rejects_bad_input() -> None:
    config = Settings(api_access_token="x", ai_model="m")

    with pytest.raises(registry.UnknownToolError):
        registry.validate_arguments("delete_everything", {}, config)
    with pytest.raises(registry.ToolValidationError):
        registry.validate_arguments("get_briefing", {"x": 1}, config)
    with pytest.raises(registry.ToolValidationError):
        registry.validate_arguments("list_tasks", {"status": "bad"}, config)
    with pytest.raises(registry.ToolValidationError):
        registry.validate_arguments("search_knowledge", {}, config)
    with pytest.raises(registry.ToolValidationError):
        registry.validate_arguments(
            "search_knowledge", {"query": "x", "top_k": 20}, config
        )
    with pytest.raises(registry.ToolValidationError):
        registry.validate_arguments(
            "create_task", {"title": "x", "due_at": "bad"}, config
        )
    with pytest.raises(registry.ToolValidationError):
        registry.validate_arguments(
            "add_memory", {"content": "x", "tags": [f"t{i}" for i in range(6)]}, config
        )


@pytest.mark.asyncio
async def test_read_and_write_task_tools(tmp_path) -> None:
    config = settings(tmp_path)

    created = await registry.execute_tool(
        "create_task",
        {"title": "测试任务", "notes": "", "due_at": None},
        config,
    )
    assert created["title"] == "测试任务"
    task_id = created["id"]

    listed = await registry.execute_tool(
        "list_tasks", {"status": "open", "due": "all"}, config
    )
    assert [task["id"] for task in listed["entries"]] == [task_id]

    completed = await registry.execute_tool(
        "complete_task", {"task_id": task_id}, config
    )
    assert completed["done"] is True

    briefing = await registry.execute_tool("get_briefing", {}, config)
    assert briefing["counts"]["open"] == 0

    store = TaskStore(config.tasks_db_path)
    try:
        assert store.get(task_id).done is True
    finally:
        store.close()


@pytest.mark.asyncio
async def test_memory_tools(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = settings(tmp_path)

    async def fake_embed_texts(texts, settings, batch_size=16):
        return [[1.0, 0.0] for _ in texts]

    async def fake_embed_query(text, settings):
        return [1.0, 0.0]

    monkeypatch.setattr(
        "family_ai_api.memory.service.embed_texts", fake_embed_texts
    )
    monkeypatch.setattr(
        "family_ai_api.memory.service.embed_query", fake_embed_query
    )

    created = await registry.execute_tool(
        "add_memory", {"content": "喜欢户外", "tags": ["家庭"]}, config
    )
    assert created["content"] == "喜欢户外"
    assert created["source"] == "agent"

    listed = await registry.execute_tool(
        "list_memories", {"query": "户外", "limit": 5}, config
    )
    assert listed["entries"][0]["content"] == "喜欢户外"
    assert listed["entries"][0]["score"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_search_knowledge_tool(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = settings(tmp_path)
    store = KnowledgeStore(config.kb_db_path)
    try:
        store.upsert_document(
            "doc.md", "文档", "hash", ["知识库内容"], [[1.0, 0.0]]
        )
    finally:
        store.close()

    async def fake_embed_query(text, settings):
        return [1.0, 0.0]

    monkeypatch.setattr("family_ai_api.agent.registry.embed_query", fake_embed_query)

    result = await registry.execute_tool(
        "search_knowledge", {"query": "内容", "top_k": 3}, config
    )

    assert result["results"][0]["source"] == "doc.md"
    assert result["results"][0]["content"] == "知识库内容"


def test_tool_result_text_truncates() -> None:
    text = registry.tool_result_text({"entries": ["x" * 100]}, max_chars=30)

    assert len(text) < 60
    assert "结果已截断" in text
