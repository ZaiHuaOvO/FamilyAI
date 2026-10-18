import pytest
from fastapi.testclient import TestClient

from family_ai_api.agent import registry
from family_ai_api.agent.planner import Plan
from family_ai_api.config import Settings, get_settings
from family_ai_api.main import app

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def agent_client(tmp_path):
    settings = Settings(
        api_access_token="test-token",
        ai_model="test-model",
        tasks_db_path=str(tmp_path / "tasks.db"),
        memory_db_path=str(tmp_path / "memory.db"),
        kb_db_path=str(tmp_path / "kb.db"),
        auto_memory_enabled=False,
        agent_action_ttl_seconds=300,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, settings
    app.dependency_overrides.clear()


def test_agent_endpoints_require_token(agent_client) -> None:
    client, _ = agent_client

    assert client.post("/api/v1/agent/chat", json={"message": "hi"}).status_code == 401
    assert client.get("/api/v1/agent/tools").status_code == 401
    assert client.get("/api/v1/agent/audit").status_code == 401
    assert client.post("/api/v1/agent/actions/x/confirm").status_code == 401
    assert client.post("/api/v1/agent/actions/x/cancel").status_code == 401


def test_agent_without_tool(agent_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = agent_client

    async def no_plan(message, settings):
        return None

    async def answer(message, settings):
        return "直接回答"

    monkeypatch.setattr("family_ai_api.agent.planner.plan", no_plan)
    monkeypatch.setattr(
        "family_ai_api.agent.planner.answer_without_tool", answer
    )

    response = client.post(
        "/api/v1/agent/chat", headers=AUTH, json={"message": "你好"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "直接回答",
        "tool": None,
        "pending_action": None,
    }


def test_agent_lists_tools(agent_client) -> None:
    client, _ = agent_client

    response = client.get("/api/v1/agent/tools", headers=AUTH)

    assert response.status_code == 200
    tools = {tool["name"]: tool for tool in response.json()["tools"]}
    assert set(tools) == {
        "get_briefing",
        "list_tasks",
        "search_knowledge",
        "list_memories",
        "create_task",
        "complete_task",
        "add_memory",
    }
    assert tools["create_task"]["write"] is True
    assert tools["get_briefing"]["write"] is False


def test_agent_read_tool(agent_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = agent_client

    async def read_plan(message, settings):
        return Plan(tool=registry.TOOLS["get_briefing"], arguments={})

    async def execute(name, arguments, settings):
        return {"counts": {"today": 0, "overdue": 0, "open": 0}}

    async def answer(message, tool_result, settings):
        assert "counts" in tool_result
        return "今天没有任务。"

    monkeypatch.setattr("family_ai_api.agent.planner.plan", read_plan)
    monkeypatch.setattr("family_ai_api.agent.registry.execute_tool", execute)
    monkeypatch.setattr("family_ai_api.agent.planner.answer_with_tool", answer)

    response = client.post(
        "/api/v1/agent/chat", headers=AUTH, json={"message": "今天有什么任务？"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "今天没有任务。"
    assert body["tool"] == {"name": "get_briefing", "status": "ok"}

    audit = client.get("/api/v1/agent/audit", headers=AUTH)
    assert audit.status_code == 200
    entries = audit.json()["entries"]
    assert entries[0]["tool"] == "get_briefing"
    assert entries[0]["write"] is False


def test_agent_write_tool_requires_confirmation(
    agent_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = agent_client

    async def write_plan(message, settings):
        return Plan(
            tool=registry.TOOLS["create_task"],
            arguments={"title": "买菜", "notes": "", "due_at": None},
        )

    monkeypatch.setattr("family_ai_api.agent.planner.plan", write_plan)

    response = client.post(
        "/api/v1/agent/chat", headers=AUTH, json={"message": "帮我创建一个买菜任务"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pending_action"]["tool"] == "create_task"
    assert body["pending_action"]["arguments"]["title"] == "买菜"
    action_id = body["pending_action"]["id"]

    assert client.get("/api/v1/tasks", headers=AUTH).json()["entries"] == []

    confirmed = client.post(
        f"/api/v1/agent/actions/{action_id}/confirm", headers=AUTH
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["executed"] is True
    assert confirmed.json()["tool"] == "create_task"
    assert confirmed.json()["result"]["title"] == "买菜"

    tasks = client.get("/api/v1/tasks", headers=AUTH).json()["entries"]
    assert [task["title"] for task in tasks] == ["买菜"]

    again = client.post(
        f"/api/v1/agent/actions/{action_id}/confirm", headers=AUTH
    )
    assert again.status_code == 404

    audit = client.get("/api/v1/agent/audit", headers=AUTH).json()["entries"]
    assert audit[0]["tool"] == "create_task"
    assert audit[0]["write"] is True
    assert audit[0]["action_id"] == action_id


def test_agent_cancel_action(agent_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = agent_client

    async def write_plan(message, settings):
        return Plan(
            tool=registry.TOOLS["create_task"],
            arguments={"title": "买菜", "notes": "", "due_at": None},
        )

    monkeypatch.setattr("family_ai_api.agent.planner.plan", write_plan)

    response = client.post(
        "/api/v1/agent/chat", headers=AUTH, json={"message": "创建一个任务"}
    )
    action_id = response.json()["pending_action"]["id"]

    cancelled = client.post(
        f"/api/v1/agent/actions/{action_id}/cancel", headers=AUTH
    )
    assert cancelled.status_code == 200
    assert cancelled.json() == {"cancelled": True}

    confirmed = client.post(
        f"/api/v1/agent/actions/{action_id}/confirm", headers=AUTH
    )
    assert confirmed.status_code == 404


def test_agent_action_is_bound_to_token(
    agent_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = agent_client

    async def write_plan(message, settings):
        return Plan(
            tool=registry.TOOLS["create_task"],
            arguments={"title": "买菜", "notes": "", "due_at": None},
        )

    monkeypatch.setattr("family_ai_api.agent.planner.plan", write_plan)

    response = client.post(
        "/api/v1/agent/chat", headers=AUTH, json={"message": "创建一个任务"}
    )
    action_id = response.json()["pending_action"]["id"]

    other = app.state.agent_actions.create(
        "create_task", {"title": "别人创建的任务"}, "other-token"
    )
    assert client.post(
        f"/api/v1/agent/actions/{other.id}/confirm", headers=AUTH
    ).status_code == 404

    assert client.post(
        f"/api/v1/agent/actions/{action_id}/confirm", headers=AUTH
    ).status_code == 200


def test_agent_can_be_disabled(
    agent_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, settings = agent_client
    settings.agent_enabled = False

    response = client.post(
        "/api/v1/agent/chat", headers=AUTH, json={"message": "你好"}
    )

    assert response.status_code == 503


def test_agent_write_tools_can_be_disabled(
    agent_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, settings = agent_client
    settings.agent_write_tools_enabled = False

    async def write_plan(message, settings):
        return Plan(
            tool=registry.TOOLS["create_task"],
            arguments={"title": "买菜", "notes": "", "due_at": None},
        )

    monkeypatch.setattr("family_ai_api.agent.planner.plan", write_plan)

    response = client.post(
        "/api/v1/agent/chat", headers=AUTH, json={"message": "创建一个任务"}
    )

    assert response.status_code == 403
