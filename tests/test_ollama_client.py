from typing import ClassVar, Self

import httpx
import pytest

from family_ai_api.config import Settings
from family_ai_api.services import ollama_client


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("invalid json")
        return self._payload


class FakeClient:
    captured_init: ClassVar[dict] = {}
    captured_post: ClassVar[dict] = {}

    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None):
        self.response = response
        self.error = error

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, json: dict) -> FakeResponse:
        FakeClient.captured_init = self.init_kwargs
        FakeClient.captured_post = {"url": url, "json": json}
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def install_client(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeResponse | None = None,
    error: Exception | None = None,
) -> None:
    def factory(**kwargs: object) -> FakeClient:
        client = FakeClient(response=response, error=error)
        client.init_kwargs = kwargs  # type: ignore[attr-defined]
        return client

    monkeypatch.setattr(ollama_client.httpx, "AsyncClient", factory)


def settings() -> Settings:
    return Settings(api_access_token="test-token", ai_model="test-model")


@pytest.mark.asyncio
async def test_chat_success_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, FakeResponse(200, {"message": {"content": "你好"}}))

    result = await ollama_client.chat("问题", settings())

    assert result.content == "你好"
    assert result.model == "test-model"
    assert FakeClient.captured_post["json"] == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "问题"}],
        "stream": False,
        "think": False,
    }
    assert FakeClient.captured_init["trust_env"] is False


@pytest.mark.asyncio
async def test_chat_maps_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, error=httpx.ConnectError("refused"))

    with pytest.raises(ollama_client.ModelServiceUnavailableError):
        await ollama_client.chat("你好", settings())


@pytest.mark.asyncio
async def test_chat_maps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, error=httpx.ReadTimeout("timeout"))

    with pytest.raises(ollama_client.ModelTimeoutError):
        await ollama_client.chat("你好", settings())


@pytest.mark.asyncio
async def test_chat_maps_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, FakeResponse(404))

    with pytest.raises(ollama_client.ModelNotFoundError):
        await ollama_client.chat("你好", settings())


@pytest.mark.asyncio
async def test_chat_maps_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, FakeResponse(500))

    with pytest.raises(ollama_client.OllamaError):
        await ollama_client.chat("你好", settings())


@pytest.mark.asyncio
async def test_chat_maps_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, FakeResponse(200))

    with pytest.raises(ollama_client.OllamaError):
        await ollama_client.chat("你好", settings())
