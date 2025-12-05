"""Application configuration with Doppler integration."""

from functools import lru_cache

try:
    import doppler_sdk
except ImportError:
    doppler_sdk = None

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and Doppler."""

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

    # Qdrant
    qdrant_url: str | None = Field(
        default=None,
        description="Qdrant Cloud URL",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Qdrant Cloud API key",
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

    @classmethod
    def load_from_doppler(
        cls, project: str = "ai-log-analytics", config: str = "dev"
    ) -> "Settings":
        """Load settings from Doppler."""
        if doppler_sdk is None:
            # Doppler SDK not available, use environment variables
            return cls()
        try:
            client = doppler_sdk.Doppler(
                api_key=doppler_sdk.get_secret("DOPPLER_TOKEN") or "",
            )
            secrets = client.secrets.get(project=project, config=config)
            # Convert Doppler secrets to environment variables
            env_vars = {k.upper().replace("-", "_"): v for k, v in secrets.items()}
            return cls(**env_vars)
        except Exception as e:
            # Fallback to environment variables if Doppler fails
            print(f"Warning: Failed to load from Doppler: {e}. Using environment variables.")
            return cls()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    # Try to load from Doppler first, fallback to environment
    try:
        return Settings.load_from_doppler()
    except Exception:
        return Settings()
