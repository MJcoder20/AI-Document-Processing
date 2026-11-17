
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
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

    # Authentication
    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Storage
    storage_provider: Literal["local"] = "local"
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

    local_worker_lease_seconds: int = 300


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

    # Security
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]

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

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.app_env.lower() == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production.")

            if self.jwt_algorithm != "HS256":
                raise ValueError(
                    "Production JWT_ALGORITHM must be HS256."
                )

            if self.jwt_secret_key is None:
                raise ValueError("JWT_SECRET_KEY is required in production.")

            if len(self.jwt_secret_key.get_secret_value()) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must contain at least 32 characters."
                )

            if not self.cors_origins:
                raise ValueError("CORS_ORIGINS must be configured in production.")

            if any("localhost" in origin or "127.0.0.1" in origin
                   for origin in self.cors_origins):
                raise ValueError(
                    "Production CORS origins cannot contain localhost."
                )

            if any(
                not origin.startswith("https://")
                for origin in self.cors_origins
            ):
                raise ValueError(
                    "Production CORS origins must use HTTPS."
                )

            if not self.allowed_hosts:
                raise ValueError("ALLOWED_HOSTS must be configured in production.")

            if any(
                host in {"localhost", "127.0.0.1", "testserver"}
                for host in self.allowed_hosts
            ):
                raise ValueError(
                    "Production ALLOWED_HOSTS cannot contain local development hosts."
                )

        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
