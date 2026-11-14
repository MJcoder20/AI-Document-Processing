
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AI Document Processing Platform"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Storage
    document_storage_dir: str = "storage/documents"
    max_upload_size_mb: int = 10


    # Background processing
    processing_mode: Literal[
        "inline",
        "local_worker",
        "azure_service_bus",
    ] = "inline"
    service_bus_connection_string: SecretStr | None = None
    service_bus_queue_name: str = "document-processing"
    service_bus_max_delivery_count: int = 5


    # Database
    database_url: str = (
        "postgresql+psycopg://postgres:postgres"
        "@localhost:5432/document_processing"
    )

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
    ]

    # AI extraction
    ai_provider: Literal["mock", "openai", "ollama"] = "ollama"

    # OpenAI
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: int = 60

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout_seconds: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
