"""Main ingestion service that orchestrates the log processing pipeline.

Implements a two-track processing pipeline:
- Fast Path: All logs saved to PostgreSQL immediately (appears in dashboard instantly)
- Priority Path: ERROR/WARN logs batched for embedding generation and anomaly detection
"""

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from uuid import UUID

from app.config import get_settings
from app.models.log import ProcessedLogEntry, RawLogEntry
from app.services.kafka_service import kafka_service
from app.services.metadata_extractor import metadata_extractor
from app.services.pii_service import pii_service
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

# Thread pool for running blocking operations
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ingestion")


def _extract_log_message(raw_data: dict) -> str:
    """Extract the actual log message from various Fluent Bit output formats."""
    message_fields = ["message", "log", "msg", "text"]

    for field in message_fields:
        if field in raw_data and raw_data[field]:
            value = raw_data[field]
            if isinstance(value, str) and value.strip().startswith("{"):
                try:
                    nested = json.loads(value)
                    if isinstance(nested, dict):
                        return _extract_log_message(nested)
                except json.JSONDecodeError:
                    pass
            return str(value)

    return ""


def _extract_service_name(raw_data: dict) -> str | None:
    """Extract service name from various log formats."""
    if "container_name" in raw_data and raw_data["container_name"]:
        name = raw_data["container_name"]
        if name.startswith("/"):
            name = name[1:]
        if name.startswith("ai-log-"):
            name = name[7:]
        return name

    if "service" in raw_data and raw_data["service"]:
        return raw_data["service"]

    if "tag" in raw_data and raw_data["tag"]:
        tag = raw_data["tag"]
        if tag.startswith("docker."):
            return tag[7:]

    return None


def _extract_timestamp(raw_data: dict) -> str | None:
    """Extract timestamp from various Fluent Bit output formats."""
    timestamp_fields = ["@timestamp", "timestamp", "time", "date"]
    for field in timestamp_fields:
        if field in raw_data and raw_data[field]:
            return raw_data[field]
    return None


@dataclass
class PriorityLogItem:
    """Item in the priority queue for batch processing."""

    log_id: UUID
    message: str
    log_data: dict
    timestamp: float  # When it was added to queue


class IngestionService:
    """Main service for processing logs through the ingestion pipeline.

    Implements two-track processing:
    - Fast track: All logs saved to PostgreSQL immediately
    - Priority track: ERROR/WARN logs queued for batch embedding + anomaly detection
    """

    def __init__(self):
        """Initialize ingestion service."""
        self.running = False
        self._settings = get_settings()

        # Priority queue for ERROR/WARN logs
        self._priority_queue: deque[PriorityLogItem] = deque()
        self._queue_lock = threading.Lock()

        # Batch processing state
        self._last_batch_time = time.time()
        self._batch_processor_running = False

    def _is_priority_log(self, level: str | None) -> bool:
        """Check if log level qualifies for priority processing (embedding).

        Args:
            level: Log level string

        Returns:
            True if log should get embedding, False otherwise
        """
        if not self._settings.embedding_enabled:
            return False

        if not level:
            return False

        return level.upper() in [lvl.upper() for lvl in self._settings.embedding_log_levels]

    def process_raw_log(self, raw_data: dict) -> ProcessedLogEntry | None:
        """Process a single raw log entry through the pipeline."""
        try:
            extracted_message = _extract_log_message(raw_data)
            extracted_timestamp = _extract_timestamp(raw_data)
            extracted_service = _extract_service_name(raw_data)

            raw_log = RawLogEntry(
                timestamp=extracted_timestamp,
                message=extracted_message,
                level=raw_data.get("level"),
                service=extracted_service or raw_data.get("service"),
                metadata=raw_data.get("metadata", {}),
                raw_log=json.dumps(raw_data),
                log_type=raw_data.get("log_type"),
            )

            extracted = metadata_extractor.extract_metadata(raw_log)

            message_to_redact = raw_log.message if raw_log.message else ""
            if not message_to_redact and raw_log.raw_log:
                try:
                    raw_parsed = json.loads(raw_log.raw_log)
                    message_to_redact = _extract_log_message(raw_parsed)
                except json.JSONDecodeError:
                    message_to_redact = raw_log.raw_log

            redacted_message, pii_entities = pii_service.redact_pii(message_to_redact)

            processed_log = ProcessedLogEntry(
                timestamp=extracted["timestamp"],
                level=extracted["level"],
                service=extracted["service"],
                message=redacted_message,
                raw_log=raw_log.raw_log,
                metadata=extracted["metadata"],
                pii_redacted=len(pii_entities) > 0,
                pii_entities=pii_entities,
            )

            return processed_log
        except Exception as e:
            logger.error(f"Error processing raw log: {e}")
            return None

    def process_and_store(self, raw_data: dict) -> bool:
        """Process raw log and store it using two-track pipeline.

        Fast track: Save to PostgreSQL immediately (all logs)
        Priority track: Queue for batch embedding (ERROR/WARN only)
        """
        try:
            # Process the log (PII redaction, metadata extraction)
            processed_log = self.process_raw_log(raw_data)
            if not processed_log:
                return False

            # FAST TRACK: Save to PostgreSQL immediately (no embedding)
            log_id = storage_service.save_log_entry_fast(processed_log)
            if not log_id:
                logger.warning("Failed to save log entry to database")
                return False

            # Send to logs-processed topic
            processed_data = processed_log.model_dump()
            kafka_service.produce_message("logs-processed", processed_data)

            # PRIORITY TRACK: Queue for batch embedding if ERROR/WARN
            if self._is_priority_log(processed_log.level):
                self._add_to_priority_queue(
                    log_id=log_id,
                    message=processed_log.message,
                    log_data={
                        "level": processed_log.level,
                        "service": processed_log.service,
                        "timestamp": processed_log.timestamp.isoformat()
                        if processed_log.timestamp
                        else None,
                        "pii_redacted": processed_log.pii_redacted,
                    },
                )

            logger.debug(f"Processed log entry: {log_id} (level: {processed_log.level})")
            return True
        except Exception as e:
            logger.error(f"Error in process_and_store: {e}")
            return False

    def _add_to_priority_queue(self, log_id: UUID, message: str, log_data: dict) -> None:
        """Add a log to the priority queue for batch processing."""
        with self._queue_lock:
            self._priority_queue.append(
                PriorityLogItem(
                    log_id=log_id,
                    message=message,
                    log_data=log_data,
                    timestamp=time.time(),
                )
            )
            queue_size = len(self._priority_queue)

        logger.debug(f"Added to priority queue: {log_id} (queue size: {queue_size})")

    def _should_process_batch(self) -> bool:
        """Check if we should process the priority queue batch."""
        with self._queue_lock:
            queue_size = len(self._priority_queue)

        if queue_size == 0:
            return False

        # Process if batch is full
        if queue_size >= self._settings.embedding_batch_size:
            return True

        # Process if timeout exceeded
        time_since_last = time.time() - self._last_batch_time
        return time_since_last >= self._settings.embedding_batch_timeout_seconds

    def _process_priority_batch(self) -> None:
        """Process a batch of priority logs with embeddings."""
        # Get batch from queue
        batch: list[PriorityLogItem] = []
        with self._queue_lock:
            batch_size = min(len(self._priority_queue), self._settings.embedding_batch_size)
            for _ in range(batch_size):
                if self._priority_queue:
                    batch.append(self._priority_queue.popleft())

        if not batch:
            return

        self._last_batch_time = time.time()

        # Extract data for batch processing
        log_ids = [item.log_id for item in batch]
        messages = [item.message for item in batch]
        log_entries_data = [item.log_data for item in batch]

        logger.info(f"Processing priority batch: {len(batch)} logs")

        # Process batch with embeddings and anomaly detection
        try:
            results = storage_service.process_priority_logs_batch(
                log_ids=log_ids,
                messages=messages,
                log_entries_data=log_entries_data,
            )
            logger.info(
                f"Priority batch complete: {results['embeddings_generated']} embeddings, "
                f"{results['anomalies_detected']} anomalies"
            )
        except Exception as e:
            logger.error(f"Error processing priority batch: {e}", exc_info=True)

    async def _batch_processor_loop(self):
        """Background loop to process priority batches."""
        self._batch_processor_running = True
        logger.info("Starting batch processor loop...")

        while self.running:
            try:
                if self._should_process_batch():
                    # Run batch processing in thread pool
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(_executor, self._process_priority_batch)

                # Short sleep to check frequently
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error in batch processor loop: {e}")
                await asyncio.sleep(1)

        self._batch_processor_running = False
        logger.info("Batch processor loop stopped")

    async def start_consuming(self):
        """Start consuming messages from Kafka and processing them."""
        self.running = True
        logger.info("Starting log ingestion service (two-track pipeline)...")
        logger.info(
            f"Embedding enabled: {self._settings.embedding_enabled}, "
            f"Priority levels: {self._settings.embedding_log_levels}, "
            f"Batch size: {self._settings.embedding_batch_size}"
        )

        # Start batch processor in background
        batch_task = asyncio.create_task(self._batch_processor_loop())

        def process_message(raw_data: dict):
            """Process a single message from Kafka."""
            if not self.running:
                return
            self.process_and_store(raw_data)

        def consume_batch():
            """Consume multiple messages (runs in thread pool)."""
            if not self.running:
                return
            try:
                # Process more messages at once since we're not doing OpenAI calls inline
                kafka_service.consume_messages(process_message, max_messages=10)
            except Exception as e:
                logger.error(f"Error consuming batch: {e}")

        loop = asyncio.get_event_loop()

        # Run consumer in a loop
        while self.running:
            try:
                await loop.run_in_executor(_executor, consume_batch)
                # Shorter sleep since fast path is much faster
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in consumption loop: {e}")
                await asyncio.sleep(2)

        # Wait for batch processor to finish
        batch_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await batch_task

    def stop(self):
        """Stop the ingestion service."""
        logger.info("Stopping log ingestion service...")
        self.running = False

        # Process any remaining items in priority queue
        with self._queue_lock:
            remaining = len(self._priority_queue)
        if remaining > 0:
            logger.info(f"Processing {remaining} remaining priority logs...")
            self._process_priority_batch()

        kafka_service.close()

    def get_queue_stats(self) -> dict:
        """Get statistics about the priority queue."""
        with self._queue_lock:
            queue_size = len(self._priority_queue)
            oldest_age = 0.0
            if self._priority_queue:
                oldest_age = time.time() - self._priority_queue[0].timestamp

        return {
            "queue_size": queue_size,
            "oldest_item_age_seconds": oldest_age,
            "batch_size_config": self._settings.embedding_batch_size,
            "batch_timeout_config": self._settings.embedding_batch_timeout_seconds,
            "embedding_enabled": self._settings.embedding_enabled,
            "priority_levels": self._settings.embedding_log_levels,
        }


# Global instance
ingestion_service = IngestionService()
