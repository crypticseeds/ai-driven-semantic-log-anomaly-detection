"""Tests for configuration loading with Doppler integration."""

import os

from app.config import Settings, get_settings


def test_settings_loads_from_environment():
    """Test that settings load from environment variables (Doppler CLI injection)."""
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
    os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:9093"

    settings = Settings()
    assert settings.database_url == "postgresql://test:test@localhost:5432/test"
    assert settings.kafka_bootstrap_servers == "localhost:9093"

    # Cleanup
    del os.environ["DATABASE_URL"]
    del os.environ["KAFKA_BOOTSTRAP_SERVERS"]


def test_settings_uses_defaults():
    """Test that settings use default values when env vars are not set."""
    settings = Settings()
    assert settings.database_url == "postgresql://ailog:changeme@localhost:5432/ailog"
    assert settings.kafka_bootstrap_servers == "localhost:9092"
    assert settings.app_name == "AI Driven Semantic Log Anomaly Detection"


def test_get_settings_loads_from_environment():
    """Test get_settings loads from environment variables."""
    # Clear the lru_cache to ensure fresh settings are loaded
    get_settings.cache_clear()

    os.environ["DATABASE_URL"] = "postgresql://env:test@localhost:5432/db"

    settings = get_settings()
    assert settings.database_url == "postgresql://env:test@localhost:5432/db"

    # Cleanup
    del os.environ["DATABASE_URL"]
    get_settings.cache_clear()  # Reset cache for other tests


def test_get_settings_uses_defaults():
    """Test get_settings uses defaults when no environment variables are set."""
    # Ensure we're not using any env vars
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]

    settings = get_settings()
    assert settings.database_url == "postgresql://ailog:changeme@localhost:5432/ailog"
