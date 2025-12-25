"""Metadata extraction service for log entries."""

import re
from datetime import datetime

from app.models.log import RawLogEntry


class MetadataExtractor:
    """Extract metadata from log entries."""

    # Patterns for log level at the START of a message (high confidence)
    # These indicate the actual log level, not just a mention of the word
    LEVEL_START_PATTERNS = [
        # Python logging: "ERROR:module:message" or "INFO:module:message"
        (re.compile(r"^(ERROR|CRITICAL|FATAL):"), "ERROR"),
        (re.compile(r"^(WARN|WARNING):"), "WARN"),
        (re.compile(r"^(INFO|INFORMATION):"), "INFO"),
        (re.compile(r"^(DEBUG|TRACE):"), "DEBUG"),
        # Uvicorn/ASGI format: "INFO: 127.0.0.1:8000 - ..."
        (re.compile(r"^(ERROR|CRITICAL|FATAL):\s"), "ERROR"),
        (re.compile(r"^(WARN|WARNING):\s"), "WARN"),
        (re.compile(r"^(INFO):\s"), "INFO"),
        (re.compile(r"^(DEBUG):\s"), "DEBUG"),
        # Bracketed format: "[ERROR]", "[INFO]", etc.
        (re.compile(r"^\[(ERROR|CRITICAL|FATAL)\]"), "ERROR"),
        (re.compile(r"^\[(WARN|WARNING)\]"), "WARN"),
        (re.compile(r"^\[(INFO|INFORMATION)\]"), "INFO"),
        (re.compile(r"^\[(DEBUG|TRACE)\]"), "DEBUG"),
        # Log4j/Java style: "ERROR - message" or "INFO - message"
        (re.compile(r"^(ERROR|CRITICAL|FATAL)\s+-\s+"), "ERROR"),
        (re.compile(r"^(WARN|WARNING)\s+-\s+"), "WARN"),
        (re.compile(r"^(INFO)\s+-\s+"), "INFO"),
        (re.compile(r"^(DEBUG)\s+-\s+"), "DEBUG"),
        # Timestamp followed by level: "2024-01-01 12:00:00 ERROR ..."
        (
            re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\w]*(ERROR|CRITICAL|FATAL)\b"),
            "ERROR",
        ),
        (re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\w]*(WARN|WARNING)\b"), "WARN"),
        (re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\w]*(INFO)\b"), "INFO"),
        (re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\w]*(DEBUG)\b"), "DEBUG"),
    ]

    # Stack trace indicators - these should be classified as ERROR
    STACK_TRACE_PATTERNS = [
        re.compile(r"Traceback \(most recent call last\):"),
        re.compile(r"^\s+File \"[^\"]+\", line \d+", re.MULTILINE),
        re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*Error:", re.MULTILINE),
        re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*Exception:", re.MULTILINE),
        re.compile(r"The above exception was the direct cause"),
        re.compile(r"During handling of the above exception"),
        re.compile(r"raise \w+Error\("),
        re.compile(r"raise \w+Exception\("),
    ]

    # HTTP status code patterns - use status code to determine level
    HTTP_STATUS_PATTERN = re.compile(r'HTTP/[\d.]+"\s+(\d{3})')

    # Common service name patterns
    SERVICE_PATTERNS = [
        (r"service[=:]\s*([^\s,]+)", "service"),
        (r"app[=:]\s*([^\s,]+)", "app"),
        (r"component[=:]\s*([^\s,]+)", "component"),
    ]

    def _is_stack_trace(self, message: str) -> bool:
        """Check if message contains stack trace indicators."""
        return any(pattern.search(message) for pattern in self.STACK_TRACE_PATTERNS)

    def _extract_level_from_http_status(self, message: str) -> str | None:
        """Extract log level based on HTTP status code in the message."""
        match = self.HTTP_STATUS_PATTERN.search(message)
        if match:
            status_code = int(match.group(1))
            if status_code >= 500:
                return "ERROR"
            elif status_code >= 400:
                return "WARN"
            elif status_code >= 200:
                return "INFO"
            else:
                return "DEBUG"
        return None

    def extract_level(self, message: str, metadata: dict, level: str | None = None) -> str:
        """Extract log level from message or metadata.

        Priority order:
        1. Explicit level parameter (from raw log)
        2. Level in metadata
        3. Stack trace detection (always ERROR)
        4. Log level at START of message (high confidence patterns)
        5. HTTP status code in message
        6. Default to INFO
        """
        # Check raw_log.level first (highest priority)
        if level:
            level_upper = str(level).upper()
            if level_upper in ["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"]:
                return level_upper if level_upper != "WARNING" else "WARN"

        # Check metadata
        if "level" in metadata:
            meta_level = str(metadata["level"]).upper()
            if meta_level in ["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "FATAL"]:
                return meta_level if meta_level != "WARNING" else "WARN"

        # Check for stack trace patterns - these are always errors
        if self._is_stack_trace(message):
            return "ERROR"

        # Check for level at the START of the message (high confidence)
        message_upper = message.upper()
        for pattern, detected_level in self.LEVEL_START_PATTERNS:
            if pattern.match(message_upper):
                return detected_level

        # Check HTTP status code in message
        http_level = self._extract_level_from_http_status(message)
        if http_level:
            return http_level

        # Default to INFO (don't guess based on words appearing anywhere in message)
        return "INFO"

    def extract_service(
        self, message: str, metadata: dict, log_type: str | None = None, service: str | None = None
    ) -> str:
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
        service = self.extract_service(
            raw_log.message, raw_log.metadata, raw_log.log_type, raw_log.service
        )

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
