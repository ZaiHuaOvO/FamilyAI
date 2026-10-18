from typing import ClassVar, Self

import httpx
import pytest

from family_ai_api.config import Settings
from family_ai_api.tasks import weather as weather_module
from family_ai_api.tasks.weather import Weather, describe_weather, get_weather


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("GET", "http://test"), response=None
            )

    def json(self) -> dict:
        return self.payload


class FakeClient:
    captured: ClassVar[dict] = {}
    payload: ClassVar[dict] = {}
    error: ClassVar[Exception | None] = None

    def __init__(self, **kwargs: object) -> None:
        FakeClient.captured = kwargs

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, params: dict) -> FakeResponse:
        FakeClient.captured["url"] = url
        FakeClient.captured["params"] = params
        if FakeClient.error is not None:
            raise FakeClient.error
        return FakeResponse(FakeClient.payload)


def settings(**overrides) -> Settings:
    values = {"api_access_token": "test-token", "ai_model": "test-model"}
    values.update(overrides)
    return Settings(**values)


def test_describe_weather() -> None:
    assert describe_weather(0) == "晴"
    assert describe_weather(2) == "多云"
    assert describe_weather(45) == "雾"
    assert describe_weather(61) == "雨"
    assert describe_weather(71) == "雪"
    assert describe_weather(95) == "雷暴"
    assert describe_weather(None) == "未知"


@pytest.mark.asyncio
async def test_weather_disabled_without_coordinates() -> None:
    assert await get_weather(settings()) is None


@pytest.mark.asyncio
async def test_weather_success(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.payload = {
        "current": {"temperature_2m": 10.9, "weather_code": 0},
        "daily": {
            "temperature_2m_max": [18.2],
            "temperature_2m_min": [6.1],
            "precipitation_probability_max": [10],
        },
    }
    FakeClient.error = None
    monkeypatch.setattr(weather_module.httpx, "AsyncClient", FakeClient)

    result = await get_weather(
        settings(
            weather_latitude=39.9,
            weather_longitude=116.4,
            weather_location_name="测试城市",
        )
    )

    assert result == Weather(
        location="测试城市",
        temperature_c=10.9,
        description="晴",
        high_c=18.2,
        low_c=6.1,
        precipitation_probability=10.0,
    )
    assert FakeClient.captured["params"]["latitude"] == 39.9


@pytest.mark.asyncio
async def test_weather_failure_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.payload = {}
    FakeClient.error = httpx.ConnectError("down")
    monkeypatch.setattr(weather_module.httpx, "AsyncClient", FakeClient)

    result = await get_weather(
        settings(weather_latitude=39.9, weather_longitude=116.4)
    )

    assert result is None
