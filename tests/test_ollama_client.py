import json
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


class FakeStreamResponse:
    def __init__(self, status_code: int, lines: list[str]) -> None:
        self.status_code = status_code
        self._lines = lines

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeClient:
    captured_init: ClassVar[dict] = {}
    captured_post: ClassVar[dict] = {}
    captured_stream: ClassVar[dict] = {}

    def __init__(
        self,
        response: FakeResponse | None = None,
        error: Exception | None = None,
        stream_response: FakeStreamResponse | None = None,
        stream_error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.stream_response = stream_response
        self.stream_error = stream_error

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

    def stream(self, method: str, url: str, json: dict) -> FakeStreamResponse:
        FakeClient.captured_init = self.init_kwargs
        FakeClient.captured_stream = {"method": method, "url": url, "json": json}
        if self.stream_error is not None:
            raise self.stream_error
        assert self.stream_response is not None
        return self.stream_response


def install_client(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeResponse | None = None,
    error: Exception | None = None,
    stream_response: FakeStreamResponse | None = None,
    stream_error: Exception | None = None,
) -> None:
    def factory(**kwargs: object) -> FakeClient:
        client = FakeClient(
            response=response,
            error=error,
            stream_response=stream_response,
            stream_error=stream_error,
        )
        client.init_kwargs = kwargs  # type: ignore[attr-defined]
        return client

    monkeypatch.setattr(ollama_client.httpx, "AsyncClient", factory)


def settings() -> Settings:
    return Settings(api_access_token="test-token", ai_model="test-model")


MESSAGES = [{"role": "user", "content": "问题"}]


@pytest.mark.asyncio
async def test_chat_success_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, FakeResponse(200, {"message": {"content": "你好"}}))

    result = await ollama_client.chat(MESSAGES, settings())

    assert result.content == "你好"
    assert result.model == "test-model"
    assert FakeClient.captured_post["json"] == {
        "model": "test-model",
        "messages": MESSAGES,
        "stream": False,
        "think": False,
    }
    assert FakeClient.captured_init["trust_env"] is False


@pytest.mark.asyncio
async def test_chat_maps_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, error=httpx.ConnectError("refused"))

    with pytest.raises(ollama_client.ModelServiceUnavailableError):
        await ollama_client.chat(MESSAGES, settings())


@pytest.mark.asyncio
async def test_chat_maps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, error=httpx.ReadTimeout("timeout"))

    with pytest.raises(ollama_client.ModelTimeoutError):
        await ollama_client.chat(MESSAGES, settings())


@pytest.mark.asyncio
async def test_chat_maps_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, FakeResponse(404))

    with pytest.raises(ollama_client.ModelNotFoundError):
        await ollama_client.chat(MESSAGES, settings())


@pytest.mark.asyncio
async def test_chat_maps_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, FakeResponse(500))

    with pytest.raises(ollama_client.OllamaError):
        await ollama_client.chat(MESSAGES, settings())


@pytest.mark.asyncio
async def test_chat_maps_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, FakeResponse(200))

    with pytest.raises(ollama_client.OllamaError):
        await ollama_client.chat(MESSAGES, settings())


@pytest.mark.asyncio
async def test_chat_stream_yields_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = [
        json.dumps({"message": {"content": "你"}, "done": False}),
        json.dumps({"message": {"content": "好"}, "done": True}),
    ]
    install_client(monkeypatch, stream_response=FakeStreamResponse(200, lines))

    chunks = [chunk async for chunk in ollama_client.chat_stream(MESSAGES, settings())]

    assert chunks == ["你", "好"]
    assert FakeClient.captured_stream["json"]["stream"] is True
    assert FakeClient.captured_stream["json"]["think"] is False


@pytest.mark.asyncio
async def test_chat_stream_maps_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, stream_error=httpx.ConnectError("refused"))

    with pytest.raises(ollama_client.ModelServiceUnavailableError):
        async for _ in ollama_client.chat_stream(MESSAGES, settings()):
            pass


@pytest.mark.asyncio
async def test_chat_stream_maps_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, stream_response=FakeStreamResponse(404, []))

    with pytest.raises(ollama_client.ModelNotFoundError):
        async for _ in ollama_client.chat_stream(MESSAGES, settings()):
            pass


@pytest.mark.asyncio
async def test_chat_stream_maps_invalid_line(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, stream_response=FakeStreamResponse(200, ["not-json"]))

    with pytest.raises(ollama_client.OllamaError):
        async for _ in ollama_client.chat_stream(MESSAGES, settings()):
            pass
