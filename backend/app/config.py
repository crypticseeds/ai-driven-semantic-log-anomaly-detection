"""Application configuration with Doppler integration.

This module loads configuration from environment variables, which are automatically
injected by the Doppler CLI when running with `doppler run --`.

For local development:
    doppler run -- uvicorn app.main:app

For Docker Compose:
    doppler run -- docker-compose up

For CI/CD with token:
    doppler run --token=$DOPPLER_TOKEN -- docker-compose up
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    When run with `doppler run --`, secrets are automatically injected as
    environment variables by the Doppler CLI. The application reads these
    environment variables directly.

    Falls back to:
    - Direct environment variables
    - .env file (if present)
    - Default values
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql://ailog:changeme@localhost:5432/ailog",
        description="PostgreSQL database URL",
    )

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        description="Kafka bootstrap servers",
    )

    # OpenAI
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key for embeddings",
    )
    openai_budget: float | None = Field(
        default=None,
        description="Daily budget limit for OpenAI embeddings in USD (None = no limit)",
    )

    # Qdrant
    qdrant_url: str | None = Field(
        default=None,
        description="Qdrant Cloud URL",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Qdrant Cloud API key",
    )
    qdrant_collection: str = Field(
        default="log_embeddings",
        description="Qdrant collection name for log embeddings",
    )

    # Langfuse
    langfuse_secret_key: str | None = Field(
        default=None,
        description="Langfuse secret key",
    )
    langfuse_public_key: str | None = Field(
        default=None,
        description="Langfuse public key",
    )
    langfuse_host: str = Field(
        default="http://langfuse:3000",
        description="Langfuse host URL",
    )

    # OpenTelemetry
    otel_service_name: str = Field(
        default="ai-log-backend",
        description="OpenTelemetry service name",
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="http://tempo:4317",
        description="OTLP gRPC endpoint",
    )

    # Sentry
    sentry_dsn: str | None = Field(
        default=None,
        description="Sentry DSN for error monitoring",
    )

    # Application
    app_name: str = Field(
        default="AI Log Analytics",
        description="Application name",
    )
    app_version: str = Field(
        default="0.1.0",
        description="Application version",
    )
    debug: bool = Field(
        default=False,
        description="Debug mode",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Loads settings from environment variables, which are automatically
    injected by Doppler CLI when running with `doppler run --`.

    Falls back to:
    - Direct environment variables
    - .env file (if present)
    - Default values
    """
    return Settings()
