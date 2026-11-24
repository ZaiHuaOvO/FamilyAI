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
