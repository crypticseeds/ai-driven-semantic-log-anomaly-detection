"""Log aggregation service for grouping multiline logs like stack traces.

Docker's logging driver sends each line as a separate log entry via the forward
protocol. This service aggregates related lines (like Python stack traces) into
single log entries before processing.
"""

import logging
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LogBuffer:
    """Buffer for accumulating multiline log entries."""

    lines: list[str] = field(default_factory=list)
    first_timestamp: float = 0.0
    last_timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)
    is_error: bool = False


class LogAggregator:
    """Aggregates multiline logs (stack traces) into single entries.

    Uses pattern matching to detect:
    - Start of a new log entry (timestamp, log level, or new traceback)
    - Continuation lines (indented lines, File references, exception chains)

    Buffers are flushed when:
    - A new log entry starts
    - Timeout is reached (default 2 seconds)
    - Buffer is explicitly flushed
    """

    # Patterns that indicate the START of a new log entry
    NEW_ENTRY_PATTERNS = [
        re.compile(r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL):"),
        re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"),
        re.compile(r"^\[\d{4}-\d{2}-\d{2}"),
        re.compile(r"^\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\]"),
    ]

    # Patterns that indicate CONTINUATION of current entry (stack trace lines)
    CONTINUATION_PATTERNS = [
        re.compile(r"^\s{2,}"),
        re.compile(r"^File \""),
        re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*Error:"),
        re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*Exception:"),
        re.compile(r"^The above exception was the direct cause"),
        re.compile(r"^During handling of the above exception"),
        re.compile(r"^Traceback \(most recent call last\):"),
        re.compile(r"^\s*[\^~]+\s*$"),
        re.compile(r"^\s*\|"),
    ]

    # Patterns that indicate ERROR level (must be actual error indicators, not just the word)
    ERROR_INDICATORS = [
        re.compile(r"Traceback \(most recent call last\):"),
        re.compile(r"^(ERROR|CRITICAL|FATAL):", re.MULTILINE),  # At start of line
        re.compile(r"^\[(ERROR|CRITICAL|FATAL)\]", re.MULTILINE),  # Bracketed at start
        re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*Error:", re.MULTILINE),  # Exception type
        re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*Exception:", re.MULTILINE),  # Exception type
        re.compile(r"raise \w+Error\("),  # Raising an error
        re.compile(r"raise \w+Exception\("),  # Raising an exception
    ]

    def __init__(self, flush_timeout: float = 2.0, max_lines: int = 100):
        """Initialize the log aggregator."""
        self.flush_timeout = flush_timeout
        self.max_lines = max_lines
        self._buffers: dict[str, LogBuffer] = defaultdict(LogBuffer)
        self._lock = threading.Lock()

    def _get_buffer_key(self, raw_data: dict) -> str:
        """Generate a unique key for buffering logs from the same source."""
        service = raw_data.get("container_name", raw_data.get("service", "unknown"))
        container_id = raw_data.get("container_id", "")[:12]
        return f"{service}:{container_id}"

    def _is_new_entry(self, line: str) -> bool:
        """Check if line starts a new log entry."""
        return any(pattern.match(line) for pattern in self.NEW_ENTRY_PATTERNS)

    def _is_continuation(self, line: str) -> bool:
        """Check if line is a continuation of current entry."""
        return any(pattern.match(line) for pattern in self.CONTINUATION_PATTERNS)

    def _is_traceback_start(self, line: str) -> bool:
        """Check if line starts a traceback."""
        return "Traceback (most recent call last):" in line

    def _has_error_indicators(self, text: str) -> bool:
        """Check if text contains error indicators."""
        return any(pattern.search(text) for pattern in self.ERROR_INDICATORS)

    def _extract_line(self, raw_data: dict) -> str:
        """Extract the log line from raw data."""
        for key in ["log", "message", "msg", "text"]:
            if key in raw_data and raw_data[key]:
                return str(raw_data[key]).rstrip("\n")
        return ""

    def _flush_buffer(self, key: str) -> dict | None:
        """Flush a buffer and return the aggregated log entry."""
        buffer = self._buffers.get(key)
        if not buffer or not buffer.lines:
            return None

        combined_message = "\n".join(buffer.lines)
        is_error = buffer.is_error or self._has_error_indicators(combined_message)

        result = {
            **buffer.metadata,
            "message": combined_message,
            "log": combined_message,
            "_aggregated": True,
            "_line_count": len(buffer.lines),
        }

        if is_error:
            result["level"] = "ERROR"
            result["_detected_error"] = True

        self._buffers[key] = LogBuffer()
        return result

    def process(self, raw_data: dict) -> list[dict]:
        """Process a raw log entry, potentially aggregating with previous lines.

        Args:
            raw_data: Raw log data from Kafka/Fluent Bit

        Returns:
            List of complete log entries (may be empty if buffering,
            or contain multiple entries if buffer was flushed)
        """
        results = []
        line = self._extract_line(raw_data)

        if not line:
            return results

        key = self._get_buffer_key(raw_data)

        with self._lock:
            buffer = self._buffers[key]
            now = time.time()

            # Check if we should flush due to timeout
            if buffer.lines and (now - buffer.last_timestamp) > self.flush_timeout:
                flushed = self._flush_buffer(key)
                if flushed:
                    results.append(flushed)
                buffer = self._buffers[key]

            # Check if this is a new entry or continuation
            is_new = self._is_new_entry(line)
            is_continuation = self._is_continuation(line)
            is_traceback = self._is_traceback_start(line)

            # Special case: Traceback starts a new error sequence
            if is_traceback:
                if buffer.lines:
                    flushed = self._flush_buffer(key)
                    if flushed:
                        results.append(flushed)
                    buffer = self._buffers[key]

                buffer.lines = [line]
                buffer.first_timestamp = now
                buffer.last_timestamp = now
                buffer.metadata = {k: v for k, v in raw_data.items() if k not in ["log", "message"]}
                buffer.is_error = True
                return results

            # If we have a buffer and this is a continuation, append
            if buffer.lines and (is_continuation or not is_new):
                buffer.lines.append(line)
                buffer.last_timestamp = now

                if self._has_error_indicators(line):
                    buffer.is_error = True

                if len(buffer.lines) >= self.max_lines:
                    flushed = self._flush_buffer(key)
                    if flushed:
                        results.append(flushed)

                return results

            # This is a new entry - flush existing buffer first
            if buffer.lines:
                flushed = self._flush_buffer(key)
                if flushed:
                    results.append(flushed)
                buffer = self._buffers[key]

            # Check if this line might start a multiline sequence
            # Only buffer if it looks like an actual error/exception start
            might_have_continuation = (
                self._has_error_indicators(line)
                or self._is_traceback_start(line)
                # Line starts with a log level followed by colon (e.g., "ERROR:module:")
                or re.match(r"^(ERROR|WARN|WARNING|CRITICAL|FATAL):", line)
            )

            if might_have_continuation:
                buffer.lines = [line]
                buffer.first_timestamp = now
                buffer.last_timestamp = now
                buffer.metadata = {k: v for k, v in raw_data.items() if k not in ["log", "message"]}
                buffer.is_error = self._has_error_indicators(line)
            else:
                results.append(raw_data)

        return results

    def flush_all(self) -> list[dict]:
        """Flush all buffers and return any pending entries."""
        results = []

        with self._lock:
            keys = list(self._buffers.keys())
            for key in keys:
                flushed = self._flush_buffer(key)
                if flushed:
                    results.append(flushed)

        return results

    def flush_expired(self) -> list[dict]:
        """Flush only buffers that have exceeded the timeout."""
        results = []
        now = time.time()

        with self._lock:
            keys = list(self._buffers.keys())
            for key in keys:
                buffer = self._buffers.get(key)
                if buffer and buffer.lines and (now - buffer.last_timestamp) > self.flush_timeout:
                    flushed = self._flush_buffer(key)
                    if flushed:
                        results.append(flushed)

        return results


# Global instance
log_aggregator = LogAggregator()
