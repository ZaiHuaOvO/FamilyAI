import pytest

from family_ai_api.agent import planner
from family_ai_api.agent.planner import extract_date_expression, resolve_due_at
from family_ai_api.config import Settings
from family_ai_api.services import ollama_client


def settings(tmp_path) -> Settings:
    return Settings(
        api_access_token="test-token",
        ai_model="test-model",
        tasks_db_path=str(tmp_path / "tasks.db"),
        memory_db_path=str(tmp_path / "memory.db"),
        kb_db_path=str(tmp_path / "kb.db"),
    )


@pytest.mark.asyncio
async def test_plan_parses_tool_call(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = '```json\n{"tool": "get_briefing", "arguments": {}}\n```'

    async def fake_chat(messages, settings):
        return ollama_client.ChatResult(content, settings.ai_model)

    monkeypatch.setattr(planner.ollama_client, "chat", fake_chat)

    result = await planner.plan("今天有什么任务？", settings(tmp_path))

    assert result is not None
    assert result.tool.name == "get_briefing"
    assert result.arguments == {}


@pytest.mark.asyncio
async def test_plan_without_tool_returns_none(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_chat(messages, settings):
        return ollama_client.ChatResult(
            '{"tool": null, "arguments": {}}', settings.ai_model
        )

    monkeypatch.setattr(planner.ollama_client, "chat", fake_chat)

    assert await planner.plan("你好", settings(tmp_path)) is None


@pytest.mark.asyncio
async def test_plan_rejects_invalid_output(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    for content in [
        "没有 JSON",
        "{invalid}",
        '{"tool": "unknown_tool", "arguments": {}}',
        '{"tool": "search_knowledge", "arguments": {}}',
    ]:

        async def fake_chat(messages, settings, content=content):
            return ollama_client.ChatResult(content, settings.ai_model)

        monkeypatch.setattr(planner.ollama_client, "chat", fake_chat)
        assert await planner.plan("你好", settings(tmp_path)) is None


def test_extract_date_expression() -> None:
    from datetime import date, timedelta

    assert extract_date_expression("2026-10-20 交水电费") == "2026-10-20"
    assert extract_date_expression("10月20日交水电费") == f"{date.today().year}-10-20"
    assert extract_date_expression("明天买菜") == (
        date.today() + timedelta(days=1)
    ).isoformat()
    assert extract_date_expression("今天交费") == date.today().isoformat()
    assert extract_date_expression("买菜") is None


def test_resolve_due_at_ignores_model_hallucination() -> None:
    from datetime import date, timedelta

    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    assert resolve_due_at("明天买菜", "2025-07-14T00:00:00") == tomorrow
    assert resolve_due_at("买菜", "2025-07-14T00:00:00") is None
    assert (
        resolve_due_at("2026-10-20 交费", "2026-10-20T00:00:00")
        == "2026-10-20T00:00:00"
    )


@pytest.mark.asyncio
async def test_plan_overrides_hallucinated_date(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date, timedelta

    content = (
        '{"tool": "create_task", "arguments": '
        '{"title": "买菜", "due_at": "2025-07-14T00:00:00"}}'
    )

    async def fake_chat(messages, settings):
        return ollama_client.ChatResult(content, settings.ai_model)

    monkeypatch.setattr(planner.ollama_client, "chat", fake_chat)

    plan = await planner.plan("明天买菜", settings(tmp_path))

    assert plan is not None
    assert plan.arguments["due_at"] == (date.today() + timedelta(days=1)).isoformat()


@pytest.mark.asyncio
async def test_answer_with_tool_includes_result(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    async def fake_chat(messages, settings):
        captured["messages"] = messages
        return ollama_client.ChatResult("最终回答", settings.ai_model)

    monkeypatch.setattr(planner.ollama_client, "chat", fake_chat)

    answer = await planner.answer_with_tool(
        "问题", '{"entries": []}', settings(tmp_path)
    )

    assert answer == "最终回答"
    assert '{"entries": []}' in captured["messages"][1]["content"]


@pytest.mark.asyncio
async def test_answer_without_tool(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_chat(messages, settings):
        assert messages == [{"role": "user", "content": "你好"}]
        return ollama_client.ChatResult("你好呀", settings.ai_model)

    monkeypatch.setattr(planner.ollama_client, "chat", fake_chat)

    assert await planner.answer_without_tool("你好", settings(tmp_path)) == "你好呀"
