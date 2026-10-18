import pytest
from fastapi.testclient import TestClient

from family_ai_api.config import Settings, get_settings
from family_ai_api.main import app
from family_ai_api.memory.store import MemoryStore
from family_ai_api.services import ollama_client

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def memory_client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    settings = Settings(
        api_access_token="test-token",
        ai_model="test-model",
        memory_db_path=str(tmp_path / "memory.db"),
        auto_memory_enabled=False,
        memory_min_score=0.0,
        memory_top_k=5,
    )

    async def fake_embed_texts(
        texts: list[str], settings: Settings, batch_size: int = 16
    ) -> list[list[float]]:
        return [[1.0, 0.0] if "户外" in text else [0.0, 1.0] for text in texts]

    async def fake_embed_query(text: str, settings: Settings) -> list[float]:
        return [1.0, 0.0]

    monkeypatch.setattr(
        "family_ai_api.memory.service.embed_texts", fake_embed_texts
    )
    monkeypatch.setattr(
        "family_ai_api.memory.service.embed_query", fake_embed_query
    )

    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, settings
    app.dependency_overrides.clear()


def test_memory_endpoints_require_token(memory_client) -> None:
    client, _ = memory_client

    assert client.post("/api/v1/memory", json={"content": "x"}).status_code == 401
    assert client.get("/api/v1/memory").status_code == 401
    assert client.patch("/api/v1/memory/1", json={"content": "x"}).status_code == 401
    assert client.delete("/api/v1/memory/1").status_code == 401


def test_memory_crud(memory_client) -> None:
    client, _ = memory_client

    created = client.post(
        "/api/v1/memory",
        headers=AUTH,
        json={"content": "周末优先户外", "tags": ["家庭"]},
    )
    assert created.status_code == 201
    body = created.json()
    memory_id = body["id"]
    assert body["content"] == "周末优先户外"
    assert body["tags"] == ["家庭"]
    assert body["source"] == "explicit"

    listed = client.get("/api/v1/memory", headers=AUTH)
    assert listed.status_code == 200
    assert listed.json()["entries"][0]["content"] == "周末优先户外"

    searched = client.get("/api/v1/memory?query=户外", headers=AUTH)
    assert searched.status_code == 200
    entries = searched.json()["entries"]
    assert entries[0]["score"] == pytest.approx(1.0)

    updated = client.patch(
        f"/api/v1/memory/{memory_id}",
        headers=AUTH,
        json={"content": "周末优先户外活动", "tags": ["家庭", "周末"]},
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "周末优先户外活动"
    assert updated.json()["tags"] == ["家庭", "周末"]

    deleted = client.delete(f"/api/v1/memory/{memory_id}", headers=AUTH)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert client.get("/api/v1/memory", headers=AUTH).json()["entries"] == []

    missing = client.delete(f"/api/v1/memory/{memory_id}", headers=AUTH)
    assert missing.status_code == 404


def test_memory_rejects_duplicate_and_invalid_input(memory_client) -> None:
    client, _ = memory_client

    first = client.post(
        "/api/v1/memory", headers=AUTH, json={"content": "喜欢户外"}
    )
    assert first.status_code == 201

    duplicate = client.post(
        "/api/v1/memory", headers=AUTH, json={"content": "喜欢户外"}
    )
    assert duplicate.status_code == 409

    assert (
        client.post("/api/v1/memory", headers=AUTH, json={"content": "   "}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/memory",
            headers=AUTH,
            json={"content": "x", "tags": [f"t{i}" for i in range(6)]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/memory", headers=AUTH, json={"content": "a" * 501}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/memory/{first.json()['id']}", headers=AUTH, json={}
        ).status_code
        == 422
    )


def test_memory_page_is_public_html(memory_client) -> None:
    client, _ = memory_client

    response = client.get("/api/v1/memory/view")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Family AI" in response.text


def test_memory_content_not_in_logs(memory_client) -> None:
    client, _ = memory_client

    response = client.post(
        "/api/v1/memory", headers=AUTH, json={"content": "private-memory-content"}
    )
    assert response.status_code == 201

    logs = client.get("/api/v1/logs?limit=20", headers=AUTH)

    assert logs.status_code == 200
    assert "private-memory-content" not in logs.text
    assert "test-token" not in logs.text


def test_chat_uses_memory_when_opted_in(
    memory_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, settings = memory_client
    store = MemoryStore(settings.memory_db_path)
    try:
        store.add("周末优先户外", ["家庭"], "explicit", [1.0, 0.0])
    finally:
        store.close()

    captured: dict = {}

    async def fake_chat(messages: list[dict[str, str]], settings: Settings):
        captured["messages"] = messages
        return ollama_client.ChatResult("建议去户外。", settings.ai_model)

    monkeypatch.setattr(ollama_client, "chat", fake_chat)

    response = client.post(
        "/api/v1/chat",
        headers=AUTH,
        json={"message": "周末做什么？", "use_memory": True},
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert "周末优先户外" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "周末做什么？"}

    captured.clear()
    response = client.post(
        "/api/v1/chat",
        headers=AUTH,
        json={"message": "周末做什么？", "use_memory": False},
    )
    assert response.status_code == 200
    assert all(message["role"] != "system" for message in captured["messages"])
