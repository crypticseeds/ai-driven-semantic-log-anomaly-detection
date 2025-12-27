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

from pydantic import Field, field_validator
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

    @field_validator("embedding_log_levels", mode="before")
    @classmethod
    def parse_embedding_log_levels(cls, v):
        """Parse embedding_log_levels from JSON string or return default."""
        if v is None or v == "":
            return ["ERROR", "WARN", "WARNING", "CRITICAL", "FATAL"]
        if isinstance(v, str):
            try:
                import json

                return json.loads(v)
            except json.JSONDecodeError:
                # If it's not valid JSON, treat as comma-separated string
                return [level.strip().upper() for level in v.split(",") if level.strip()]
        return v

    @field_validator(
        "openai_api_key",
        "openai_budget",
        "qdrant_url",
        "qdrant_api_key",
        "langfuse_secret_key",
        "langfuse_public_key",
        "sentry_dsn",
        "hdbscan_max_cluster_size",
        "hdbscan_sample_size",
        "cors_debug_logging",
        "clustering_max_embeddings",
        "clustering_max_llm_outliers",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty strings to None for optional fields."""
        if v == "" or v is None:
            return None
        return v

    @field_validator(
        "clustering_skip_llm_default",
        "clustering_use_float32",
        mode="before",
    )
    @classmethod
    def parse_bool_str(cls, v):
        """Parse boolean from string (for env vars)."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

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
    qdrant_timeout: int = Field(
        default=60,
        description="Qdrant client timeout in seconds",
    )
    qdrant_scroll_batch_size: int = Field(
        default=1000,
        description="Batch size for Qdrant scroll operations (lower = more reliable over network)",
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

    # HDBSCAN Clustering
    hdbscan_min_cluster_size: int = Field(
        default=5,
        description="Minimum cluster size for HDBSCAN",
    )
    hdbscan_min_samples: int = Field(
        default=3,
        description="Minimum samples for HDBSCAN",
    )
    hdbscan_cluster_selection_epsilon: float = Field(
        default=0.0,
        description="Cluster selection epsilon for HDBSCAN",
    )
    hdbscan_max_cluster_size: int | None = Field(
        default=None,
        description="Maximum cluster size for HDBSCAN (None = no limit)",
    )
    hdbscan_sample_size: int | None = Field(
        default=None,
        description="Sample size for large datasets (None = use all data)",
    )

    # Clustering Performance Settings
    clustering_max_embeddings: int = Field(
        default=2000,
        description="Maximum embeddings to process for clustering (memory safety limit)",
    )
    clustering_skip_llm_default: bool = Field(
        default=True,
        description="Skip LLM analysis by default for faster clustering",
    )
    clustering_max_llm_outliers: int = Field(
        default=5,
        description="Maximum outliers to analyze with LLM (0-50)",
    )
    clustering_use_float32: bool = Field(
        default=True,
        description="Use float32 instead of float64 for embeddings (reduces memory by 50%)",
    )

    # Anomaly Detection Thresholds
    anomaly_score_threshold: float = Field(
        default=0.7,
        description="Anomaly score threshold for triggering LLM validation (0.0 to 1.0)",
    )
    llm_validation_enabled: bool = Field(
        default=True,
        description="Enable LLM validation for high-scoring anomalies",
    )
    llm_validation_confidence_threshold: float = Field(
        default=0.6,
        description="Minimum LLM confidence to confirm anomaly (0.0 to 1.0)",
    )

    # Embedding Pipeline Configuration
    embedding_enabled: bool = Field(
        default=True,
        description="Enable embedding generation (can be disabled to speed up ingestion)",
    )
    embedding_log_levels: list[str] = Field(
        default_factory=lambda: ["ERROR", "WARN", "WARNING", "CRITICAL", "FATAL"],
        description="Log levels that trigger embedding generation (selective processing)",
    )
    embedding_batch_size: int = Field(
        default=50,
        description="Number of logs to batch before sending to OpenAI (1-2048)",
    )
    embedding_batch_timeout_seconds: float = Field(
        default=5.0,
        description="Max seconds to wait before processing incomplete batch",
    )
    embedding_parallel_batches: int = Field(
        default=3,
        description="Number of batches to process in parallel",
    )

    # Application
    app_name: str = Field(
        default="AI Driven Semantic Log Anomaly Detection",
        description="Application name",
    )
    app_version: str = Field(
        default="0.1.0",
        description="Application version",
    )
    developer_name: str = Field(
        default="Femi Akinlotan",
        description="Developer name for API attribution",
    )
    debug: bool = Field(
        default=False,
        description="Debug mode",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://0.0.0.0:3000",
            "http://0.0.0.0:3001",
        ],
        description="Allowed CORS origins (comma-separated or JSON array)",
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests",
    )
    cors_max_age: int = Field(
        default=3600,
        description="CORS preflight cache duration in seconds",
    )
    cors_debug_logging: bool | None = Field(
        default=None,
        description="Enable detailed CORS debug logging (defaults to debug mode)",
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
