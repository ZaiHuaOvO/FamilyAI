import pytest
from pydantic import ValidationError

from family_ai_api.config import Settings


def test_blank_weather_values_become_none() -> None:
    settings = Settings(weather_latitude="", weather_longitude="  ")

    assert settings.weather_latitude is None
    assert settings.weather_longitude is None


def test_blank_weather_from_env_file_becomes_none(tmp_path) -> None:
    env_file = tmp_path / "test.env"
    env_file.write_text("WEATHER_LATITUDE=\nWEATHER_LONGITUDE=\n", encoding="utf-8")

    settings = Settings(_env_file=str(env_file))

    assert settings.weather_latitude is None
    assert settings.weather_longitude is None


def test_weather_numbers_are_parsed() -> None:
    settings = Settings(weather_latitude="39.9", weather_longitude="116.4")

    assert settings.weather_latitude == 39.9
    assert settings.weather_longitude == 116.4


@pytest.mark.parametrize(
    "value",
    ["", " ", "*", "0.0.0.0", "192.168.1.10", "127.0.0.1,*"],
)
def test_forwarded_allow_ips_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(forwarded_allow_ips=value)


def test_forwarded_allow_ips_normalizes_loopback_list() -> None:
    settings = Settings(forwarded_allow_ips=" 127.0.0.1 , ::1 ")

    assert settings.forwarded_allow_ips == "127.0.0.1,::1"
    assert settings.forwarded_allow_ips_list == ["127.0.0.1", "::1"]


def test_forwarded_allow_ips_from_env_is_validated(monkeypatch) -> None:
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
