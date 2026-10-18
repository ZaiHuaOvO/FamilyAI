import asyncio
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from family_ai_api.config import Settings, get_settings
from family_ai_api.main import app
from family_ai_api.services import ollama_client
from family_ai_api.services.limits import SlidingWindowRateLimiter

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(
        api_access_token="test-token",
        ai_model="test-model",
        max_message_chars=20,
        max_history_messages=3,
        max_history_chars=50,
        auto_memory_enabled=False,
        memory_db_path=str(tmp_path / "memory.db"),
    )
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_models_requires_token(client: TestClient) -> None:
    response = client.get("/api/v1/models")

    assert response.status_code == 401


def test_models_rejects_wrong_token(client: TestClient) -> None:
    response = client.get("/api/v1/models", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401


def test_models_returns_configured_model(client: TestClient) -> None:
    response = client.get("/api/v1/models", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"default_model": "test-model", "models": ["test-model"]}


def test_chat_requires_token_and_does_not_call_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    async def fake_chat(
        messages: list[dict[str, str]], settings: Settings
    ) -> ollama_client.ChatResult:
        nonlocal called
        called = True
        return ollama_client.ChatResult("x", settings.ai_model)

    monkeypatch.setattr(ollama_client, "chat", fake_chat)

    response = client.post("/api/v1/chat", json={"message": "你好"})

    assert response.status_code == 401
    assert called is False


@pytest.mark.parametrize("message", ["", "   ", "\n\t"])
def test_chat_rejects_empty_message(client: TestClient, message: str) -> None:
    response = client.post("/api/v1/chat", headers=AUTH, json={"message": message})

    assert response.status_code == 422


def test_chat_rejects_long_message(client: TestClient) -> None:
    response = client.post("/api/v1/chat", headers=AUTH, json={"message": "a" * 21})

    assert response.status_code == 422


def test_chat_includes_history(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_chat(
        messages: list[dict[str, str]], settings: Settings
    ) -> ollama_client.ChatResult:
        captured["messages"] = messages
        return ollama_client.ChatResult("ok", settings.ai_model)

    monkeypatch.setattr(ollama_client, "chat", fake_chat)

    response = client.post(
        "/api/v1/chat",
        headers=AUTH,
        json={
            "message": "第二轮",
            "history": [
                {"role": "user", "content": "第一轮"},
                {"role": "assistant", "content": "第一轮回答"},
            ],
        },
    )

    assert response.status_code == 200
    assert captured["messages"] == [
        {"role": "user", "content": "第一轮"},
        {"role": "assistant", "content": "第一轮回答"},
        {"role": "user", "content": "第二轮"},
    ]


def test_chat_rejects_too_much_history(client: TestClient) -> None:
    history = [{"role": "user", "content": "x"} for _ in range(4)]

    response = client.post(
        "/api/v1/chat", headers=AUTH, json={"message": "hi", "history": history}
    )

    assert response.status_code == 422


def test_chat_rejects_too_large_history(client: TestClient) -> None:
    history = [
        {"role": "user", "content": "a" * 30},
        {"role": "assistant", "content": "b" * 30},
    ]

    response = client.post(
        "/api/v1/chat", headers=AUTH, json={"message": "hi", "history": history}
    )

    assert response.status_code == 422


def test_chat_rejects_empty_history_content(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        headers=AUTH,
        json={"message": "hi", "history": [{"role": "user", "content": "   "}]},
    )

    assert response.status_code == 422


def test_chat_rejects_invalid_history_role(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        headers=AUTH,
        json={"message": "hi", "history": [{"role": "system", "content": "x"}]},
    )

    assert response.status_code == 422


def test_chat_returns_model_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_chat(
        messages: list[dict[str, str]], settings: Settings
    ) -> ollama_client.ChatResult:
        assert messages == [{"role": "user", "content": "你好"}]
        return ollama_client.ChatResult("你好呀", settings.ai_model)

    monkeypatch.setattr(ollama_client, "chat", fake_chat)

    response = client.post("/api/v1/chat", headers=AUTH, json={"message": " 你好 "})

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "你好呀"
    assert body["model"] == "test-model"
    assert isinstance(body["duration_ms"], int)
    assert body["duration_ms"] >= 0


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (ollama_client.ModelServiceUnavailableError(), 503),
        (ollama_client.ModelTimeoutError(), 504),
        (ollama_client.ModelNotFoundError(), 502),
        (ollama_client.OllamaError(), 502),
    ],
)
def test_chat_maps_upstream_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: ollama_client.OllamaError,
    expected_status: int,
) -> None:
    async def fake_chat(
        messages: list[dict[str, str]], settings: Settings
    ) -> ollama_client.ChatResult:
        raise error

    monkeypatch.setattr(ollama_client, "chat", fake_chat)

    response = client.post("/api/v1/chat", headers=AUTH, json={"message": "你好"})

    assert response.status_code == expected_status


def test_chat_rejects_oversized_body(client: TestClient) -> None:
    payload = b'{"message":"' + b"a" * 20000 + b'"}'

    response = client.post(
        "/api/v1/chat",
        content=payload,
        headers={**AUTH, "Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_rate_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    app.state.rate_limiter = SlidingWindowRateLimiter(1)

    async def fake_chat(
        messages: list[dict[str, str]], settings: Settings
    ) -> ollama_client.ChatResult:
        return ollama_client.ChatResult("ok", settings.ai_model)

    monkeypatch.setattr(ollama_client, "chat", fake_chat)

    first = client.post("/api/v1/chat", headers=AUTH, json={"message": "你好"})
    second = client.post("/api/v1/chat", headers=AUTH, json={"message": "你好"})

    assert first.status_code == 200
    assert second.status_code == 429


def test_access_log_does_not_contain_token_or_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def fake_chat(
        messages: list[dict[str, str]], settings: Settings
    ) -> ollama_client.ChatResult:
        return ollama_client.ChatResult("secret-answer", settings.ai_model)

    monkeypatch.setattr(ollama_client, "chat", fake_chat)

    with caplog.at_level(logging.INFO, logger="family_ai_api.access"):
        response = client.post(
            "/api/v1/chat", headers=AUTH, json={"message": "private-question"}
        )

    assert response.status_code == 200
    assert "test-token" not in caplog.text
    assert "private-question" not in caplog.text
    assert "secret-answer" not in caplog.text


def test_chat_stream_requires_token(client: TestClient) -> None:
    response = client.post("/api/v1/chat/stream", json={"message": "你好"})

    assert response.status_code == 401


def test_chat_stream_returns_sse(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_stream(messages: list[dict[str, str]], settings: Settings):
        yield "你"
        yield "好"

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)

    response = client.post(
        "/api/v1/chat/stream", headers=AUTH, json={"message": "你好"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert "event: delta" in text
    assert '"delta": "你"' in text
    assert '"delta": "好"' in text
    assert "event: done" in text
    assert '"model": "test-model"' in text


def test_chat_stream_emits_error_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_stream(messages: list[dict[str, str]], settings: Settings):
        if False:
            yield ""
        raise ollama_client.ModelServiceUnavailableError

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)

    response = client.post(
        "/api/v1/chat/stream", headers=AUTH, json={"message": "你好"}
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert '"status": 503' in response.text


def test_logs_requires_token(client: TestClient) -> None:
    response = client.get("/api/v1/logs")

    assert response.status_code == 401


def test_logs_returns_metadata_without_content(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_chat(
        messages: list[dict[str, str]], settings: Settings
    ) -> ollama_client.ChatResult:
        return ollama_client.ChatResult("secret-answer", settings.ai_model)

    monkeypatch.setattr(ollama_client, "chat", fake_chat)

    chat_response = client.post(
        "/api/v1/chat", headers=AUTH, json={"message": "private-question"}
    )
    assert chat_response.status_code == 200

    response = client.get("/api/v1/logs?limit=50", headers=AUTH)

    assert response.status_code == 200
    entries = response.json()["entries"]
    assert entries
    assert all(
        {"timestamp", "method", "path", "status", "duration_ms", "client"}
        <= set(entry)
        for entry in entries
    )
    assert any(entry["path"] == "/api/v1/chat" for entry in entries)
    assert "private-question" not in response.text
    assert "secret-answer" not in response.text
    assert "test-token" not in response.text


def test_logs_page_is_public_html(client: TestClient) -> None:
    response = client.get("/api/v1/logs/view")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Family AI" in response.text


@pytest.mark.asyncio
async def test_concurrency_limit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        api_access_token="test-token",
        ai_model="test-model",
        auto_memory_enabled=False,
        memory_db_path=str(tmp_path / "memory.db"),
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.chat_semaphore = asyncio.Semaphore(1)
    app.state.rate_limiter = SlidingWindowRateLimiter(100)
    app.state.memory_extraction_semaphore = asyncio.Semaphore(1)

    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_chat(
        messages: list[dict[str, str]], settings: Settings
    ) -> ollama_client.ChatResult:
        started.set()
        await release.wait()
        return ollama_client.ChatResult("ok", settings.ai_model)

    monkeypatch.setattr(ollama_client, "chat", slow_chat)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = asyncio.create_task(
            client.post("/api/v1/chat", headers=AUTH, json={"message": "你好"})
        )
        await started.wait()
        second = await client.post("/api/v1/chat", headers=AUTH, json={"message": "你好"})
        release.set()
        first_response = await first

    app.dependency_overrides.clear()

    assert first_response.status_code == 200
    assert second.status_code == 429
