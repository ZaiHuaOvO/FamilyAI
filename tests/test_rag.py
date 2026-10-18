import pytest
from fastapi.testclient import TestClient

from family_ai_api.config import Settings, get_settings
from family_ai_api.knowledge import service as rag_service
from family_ai_api.knowledge.embeddings import EmbeddingError
from family_ai_api.knowledge.store import KnowledgeStore
from family_ai_api.main import app
from family_ai_api.services import ollama_client

AUTH = {"Authorization": "Bearer test-token"}
CHUNK = "默认模型是 qwen3.5:4b，Embedding 是 qwen3-embedding:0.6b。"


@pytest.fixture
def rag_client(tmp_path):
    settings = Settings(
        api_access_token="test-token",
        ai_model="test-model",
        kb_db_path=str(tmp_path / "kb.db"),
        kb_top_k=1,
        kb_max_context_chars=1000,
        auto_memory_enabled=False,
        memory_db_path=str(tmp_path / "memory.db"),
    )
    store = KnowledgeStore(settings.kb_db_path)
    store.upsert_document(
        source="overview.md",
        title="项目概览",
        content_hash="hash",
        chunks=[CHUNK],
        embeddings=[[1.0, 0.0]],
    )
    store.close()

    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, settings
    app.dependency_overrides.clear()


def test_rag_query_requires_token(rag_client) -> None:
    client, _ = rag_client

    response = client.post("/api/v1/rag/query", json={"message": "默认模型是什么？"})

    assert response.status_code == 401


def test_kb_stats_requires_token(rag_client) -> None:
    client, _ = rag_client

    response = client.get("/api/v1/kb/stats")

    assert response.status_code == 401


def test_kb_stats_returns_counts(rag_client) -> None:
    client, _ = rag_client

    response = client.get("/api/v1/kb/stats", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == 1
    assert body["chunks"] == 1
    assert body["embedding_model"] == "qwen3-embedding:0.6b"


def test_rag_query_returns_answer_and_sources(
    rag_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = rag_client
    captured: dict = {}

    async def fake_embed(text: str, settings: Settings) -> list[float]:
        return [1.0, 0.0]

    async def fake_chat(messages: list[dict[str, str]], settings: Settings):
        captured["messages"] = messages
        return ollama_client.ChatResult("默认模型是 qwen3.5:4b。", settings.ai_model)

    monkeypatch.setattr(rag_service, "embed_query", fake_embed)
    monkeypatch.setattr(ollama_client, "chat", fake_chat)

    response = client.post(
        "/api/v1/rag/query",
        headers=AUTH,
        json={"message": "默认模型是什么？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "默认模型是 qwen3.5:4b。"
    assert body["model"] == "test-model"
    assert body["sources"] == [
        {"title": "项目概览", "path": "overview.md", "chunk_index": 0, "score": 1.0}
    ]
    assert CHUNK in captured["messages"][1]["content"]
    assert "系统" not in captured["messages"][0]["content"]


def test_rag_query_empty_knowledge_base(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        api_access_token="test-token",
        ai_model="test-model",
        kb_db_path=str(tmp_path / "empty.db"),
    )
    app.dependency_overrides[get_settings] = lambda: settings

    async def fake_embed(text: str, settings: Settings) -> list[float]:
        return [1.0, 0.0]

    monkeypatch.setattr(rag_service, "embed_query", fake_embed)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/query", headers=AUTH, json={"message": "问题"}
        )

    app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "knowledge base is empty"


def test_rag_query_maps_embedding_error(
    rag_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = rag_client

    async def failing_embed(text: str, settings: Settings) -> list[float]:
        raise EmbeddingError("down")

    monkeypatch.setattr(rag_service, "embed_query", failing_embed)

    response = client.post("/api/v1/rag/query", headers=AUTH, json={"message": "问题"})

    assert response.status_code == 503


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "   "},
        {"message": "问题", "top_k": 0},
        {"message": "问题", "top_k": 11},
    ],
)
def test_rag_query_validates_input(rag_client, payload: dict) -> None:
    client, _ = rag_client

    response = client.post("/api/v1/rag/query", headers=AUTH, json=payload)

    assert response.status_code == 422


def test_rag_query_does_not_leak_content_to_logs(
    rag_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = rag_client

    async def fake_embed(text: str, settings: Settings) -> list[float]:
        return [1.0, 0.0]

    async def fake_chat(messages: list[dict[str, str]], settings: Settings):
        return ollama_client.ChatResult("secret answer", settings.ai_model)

    monkeypatch.setattr(rag_service, "embed_query", fake_embed)
    monkeypatch.setattr(ollama_client, "chat", fake_chat)

    response = client.post(
        "/api/v1/rag/query",
        headers=AUTH,
        json={"message": "private question about qwen3.5"},
    )
    assert response.status_code == 200

    logs = client.get("/api/v1/logs?limit=20", headers=AUTH)
    assert logs.status_code == 200
    assert "private question" not in logs.text
    assert "qwen3.5" not in logs.text
    assert CHUNK not in logs.text
    assert "secret answer" not in logs.text
