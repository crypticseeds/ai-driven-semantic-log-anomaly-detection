"""Pydantic models for log normalization."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RawLogEntry(BaseModel):
    """Raw log entry from Kafka (logs-raw topic)."""

    timestamp: datetime | None = None
    message: str
    level: str | None = None
    service: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_log: str
    log_type: str | None = None  # json, syslog, nginx, opentelemetry

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> datetime | None:
        """Parse timestamp from various formats."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            # Try common timestamp formats
            for fmt in [
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%b %d %H:%M:%S",
            ]:
                try:
                    return datetime.strptime(v, fmt)
                except ValueError:
                    continue
        return None


class ProcessedLogEntry(BaseModel):
    """Processed log entry after PII redaction and normalization."""

    timestamp: datetime
    level: str
    service: str
    message: str  # PII-redacted message
    raw_log: str  # Original raw log
    metadata: dict[str, Any] = Field(default_factory=dict)
    pii_redacted: bool = False
    pii_entities: dict[str, Any] = Field(default_factory=dict)  # Detected PII entities

    class Config:
        """Pydantic config."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
