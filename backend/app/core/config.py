import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except Exception:
    BaseSettings = BaseModel  # type: ignore[assignment,misc]
    SettingsConfigDict = None  # type: ignore[assignment]


class Settings(BaseSettings):  # type: ignore[misc,valid-type]
    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Research Paper Replicator"
    environment: str = "development"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    generated_root: Path = Path("generated")
    max_iterations: int = 3
    database_url: str = "postgresql+psycopg://replicator:replicator@postgres:5432/replicator"
    redis_url: str = "redis://redis:6379/0"

    # LLM — ChatOllama (LangChain) with Ollama backend
    llm_model: str = "ollama/qwen3:8b"
    ollama_base_url: str = "http://localhost:11434"
    llm_timeout: int = 120  # seconds — Qwen3 thinking is slow
    llm_retries: int = 3



@lru_cache
def get_settings() -> Settings:
    if SettingsConfigDict is not None:
        return Settings()

    values = {
        "app_name": os.getenv("APP_NAME"),
        "environment": os.getenv("ENVIRONMENT"),
        "cors_origins": _json_list(os.getenv("CORS_ORIGINS")),
        "generated_root": Path(os.getenv("GENERATED_ROOT", "generated")),
        "max_iterations": _int("MAX_ITERATIONS", 3),
        "database_url": os.getenv("DATABASE_URL"),
        "redis_url": os.getenv("REDIS_URL"),
        "llm_model": os.getenv("LLM_MODEL", "ollama/qwen3:8b"),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "llm_timeout": _int("LLM_TIMEOUT", 120),
        "llm_retries": _int("LLM_RETRIES", 3),
    }
    return Settings(**{key: value for key, value in values.items() if value not in (None, [])})


def _json_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        return [part.strip() for part in value.split(",") if part.strip()]
    return None


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (ValueError, TypeError):
        return default


settings = get_settings()
