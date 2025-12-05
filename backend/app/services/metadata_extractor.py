"""Metadata extraction service for log entries."""

import re
from datetime import datetime

from app.models.log import RawLogEntry


class MetadataExtractor:
    """Extract metadata from log entries."""

    # Common log level patterns
    LEVEL_PATTERNS = [
        (r"\b(ERROR|CRITICAL|FATAL)\b", "ERROR"),
        (r"\b(WARN|WARNING)\b", "WARN"),
        (r"\b(INFO|INFORMATION)\b", "INFO"),
        (r"\b(DEBUG|TRACE)\b", "DEBUG"),
    ]

    # Common service name patterns
    SERVICE_PATTERNS = [
        (r"service[=:]\s*([^\s,]+)", "service"),
        (r"app[=:]\s*([^\s,]+)", "app"),
        (r"component[=:]\s*([^\s,]+)", "component"),
    ]

    def extract_level(self, message: str, metadata: dict, level: str | None = None) -> str:
        """Extract log level from message or metadata."""
        # Check raw_log.level first (highest priority)
        if level:
            level_upper = str(level).upper()
            if level_upper in ["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"]:
                return level_upper if level_upper != "WARNING" else "WARN"

        # Check metadata
        if "level" in metadata:
            level = str(metadata["level"]).upper()
            if level in ["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"]:
                return level if level != "WARNING" else "WARN"

        # Check message for level patterns
        message_upper = message.upper()
        for pattern, level in self.LEVEL_PATTERNS:
            if re.search(pattern, message_upper):
                return level

        # Default to INFO
        return "INFO"

    def extract_service(self, message: str, metadata: dict, log_type: str | None = None, service: str | None = None) -> str:
        """Extract service name from message, metadata, or log type."""
        # Check raw_log.service first (highest priority)
        if service:
            return str(service)

        # Check metadata
        if "service" in metadata:
            return str(metadata["service"])

        # Check for service patterns in message
        for pattern, _ in self.SERVICE_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1)

        # Use log type as fallback
        if log_type:
            return log_type

        # Check for common service indicators
        if "nginx" in message.lower():
            return "nginx"
        if "postgres" in message.lower() or "database" in message.lower():
            return "postgres"
        if "kafka" in message.lower():
            return "kafka"

        # Default
        return "unknown"

    def extract_timestamp(self, raw_log: RawLogEntry) -> datetime:
        """Extract or generate timestamp."""
        if raw_log.timestamp:
            return raw_log.timestamp

        # Try to extract from message
        timestamp_patterns = [
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})",
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",
        ]

        for pattern in timestamp_patterns:
            match = re.search(pattern, raw_log.message)
            if match:
                try:
                    ts_str = match.group(1)
                    if "T" in ts_str:
                        return datetime.fromisoformat(ts_str)
                    else:
                        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

        # Default to now
        return datetime.utcnow()

    def extract_metadata(self, raw_log: RawLogEntry) -> dict:
        """Extract all metadata from raw log entry."""
        timestamp = self.extract_timestamp(raw_log)
        level = self.extract_level(raw_log.message, raw_log.metadata, raw_log.level)
        service = self.extract_service(raw_log.message, raw_log.metadata, raw_log.log_type, raw_log.service)

        # Merge with existing metadata
        metadata = raw_log.metadata.copy()
        metadata.update(
            {
                "extracted_level": level,
                "extracted_service": service,
                "log_type": raw_log.log_type or "unknown",
            }
        )

        return {
            "timestamp": timestamp,
            "level": level,
            "service": service,
            "metadata": metadata,
        }


# Global instance
metadata_extractor = MetadataExtractor()
