import logging
from dataclasses import dataclass

import httpx

from family_ai_api.config import Settings

logger = logging.getLogger(__name__)

WEATHER_API = "https://api.open-meteo.com/v1/forecast"


@dataclass(frozen=True)
class Weather:
    location: str
    temperature_c: float | None
    description: str
    high_c: float | None
    low_c: float | None
    precipitation_probability: float | None


def describe_weather(code: int | None) -> str:
    if code is None:
        return "未知"
    if code == 0:
        return "晴"
    if code in {1, 2, 3}:
        return "多云"
    if code in {45, 48}:
        return "雾"
    if 51 <= code <= 57:
        return "毛毛雨"
    if 61 <= code <= 67:
        return "雨"
    if 71 <= code <= 77:
        return "雪"
    if 80 <= code <= 82:
        return "阵雨"
    if 85 <= code <= 86:
        return "阵雪"
    if 95 <= code <= 99:
        return "雷暴"
    return "未知"


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def get_weather(settings: Settings) -> Weather | None:
    if settings.weather_latitude is None or settings.weather_longitude is None:
        return None

    params = {
        "latitude": settings.weather_latitude,
        "longitude": settings.weather_longitude,
        "current": "temperature_2m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": 1,
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.weather_timeout_seconds)
        ) as client:
            response = await client.get(WEATHER_API, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("weather request failed: %s", type(exc).__name__)
        return None

    current = data.get("current") or {}
    daily = data.get("daily") or {}
    high_values = daily.get("temperature_2m_max") or [None]
    low_values = daily.get("temperature_2m_min") or [None]
    precipitation_values = daily.get("precipitation_probability_max") or [None]

    return Weather(
        location=settings.weather_location_name or "当前位置",
        temperature_c=_number(current.get("temperature_2m")),
        description=describe_weather(current.get("weather_code")),
        high_c=_number(high_values[0]),
        low_c=_number(low_values[0]),
        precipitation_probability=_number(precipitation_values[0]),
    )
