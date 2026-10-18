from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    ollama_base_url: str = "http://127.0.0.1:11434"
    ai_model: str = "qwen3.5:4b"
    api_access_token: str = ""
    request_timeout_seconds: float = 180.0
    max_message_chars: int = 6000


@lru_cache
def get_settings() -> Settings:
    return Settings()
