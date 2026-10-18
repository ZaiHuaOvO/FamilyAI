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
    max_concurrent_requests: int = 2
    rate_limit_per_minute: int = 30
    max_request_bytes: int = 16384
    max_history_messages: int = 20
    max_history_chars: int = 12000
    request_log_size: int = 200
    embedding_model: str = "qwen3-embedding:0.6b"
    kb_db_path: str = "data/knowledge.db"
    kb_top_k: int = 4
    kb_max_context_chars: int = 6000
    kb_chunk_chars: int = 500
    kb_chunk_overlap: int = 80
    memory_db_path: str = "data/memory.db"
    memory_top_k: int = 5
    memory_min_score: float = 0.3
    memory_max_context_chars: int = 2000
    memory_max_chars: int = 500
    auto_memory_enabled: bool = True
    auto_memory_min_chars: int = 4
    auto_memory_max_items: int = 3
    tasks_db_path: str = "data/tasks.db"
    weather_latitude: float | None = None
    weather_longitude: float | None = None
    weather_location_name: str = ""
    weather_timeout_seconds: float = 10.0
    agent_enabled: bool = True
    agent_write_tools_enabled: bool = True
    agent_max_tool_result_chars: int = 6000
    agent_action_ttl_seconds: int = 300
    agent_audit_size: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
