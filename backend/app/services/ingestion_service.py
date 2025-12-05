"""Main ingestion service that orchestrates the log processing pipeline."""

import asyncio
import json
import logging

from app.models.log import ProcessedLogEntry, RawLogEntry
from app.services.kafka_service import kafka_service
from app.services.metadata_extractor import metadata_extractor
from app.services.pii_service import pii_service
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)


class IngestionService:
    """Main service for processing logs through the ingestion pipeline."""

    def __init__(self):
        """Initialize ingestion service."""
        self.running = False

    def process_raw_log(self, raw_data: dict) -> ProcessedLogEntry | None:
        """Process a single raw log entry through the pipeline."""
        try:
            # 1. Parse raw log entry
            raw_log = RawLogEntry(
                timestamp=raw_data.get("timestamp"),
                message=raw_data.get("message", ""),
                level=raw_data.get("level"),
                service=raw_data.get("service"),
                metadata=raw_data.get("metadata", {}),
                raw_log=json.dumps(raw_data),
                log_type=raw_data.get("log_type"),
            )

            # 2. Extract metadata
            extracted = metadata_extractor.extract_metadata(raw_log)

            # 3. Detect and redact PII
            message_to_check = raw_log.message or raw_log.raw_log
            redacted_message, pii_entities = pii_service.redact_pii(message_to_check)

            # 4. Create processed log entry
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
        """Process raw log and store it in database and Kafka."""
        try:
            # Process the log
            processed_log = self.process_raw_log(raw_data)
            if not processed_log:
                return False

            # Store in PostgreSQL
            log_id = storage_service.save_log_entry_async(processed_log)
            if not log_id:
                logger.warning("Failed to save log entry to database")
                # Continue anyway to send to Kafka

            # Send to logs-processed topic
            processed_data = processed_log.model_dump()
            success = kafka_service.produce_message("logs-processed", processed_data)

            if success and log_id:
                logger.debug(f"Successfully processed and stored log entry: {log_id}")
                return True
            else:
                logger.warning("Log processed but storage/Kafka may have failed")
                return False
        except Exception as e:
            logger.error(f"Error in process_and_store: {e}")
            return False

    async def start_consuming(self):
        """Start consuming messages from Kafka and processing them."""
        self.running = True
        logger.info("Starting log ingestion service...")

        def process_message(raw_data: dict):
            """Process a single message from Kafka."""
            if not self.running:
                return
            self.process_and_store(raw_data)

        # Run consumer in a loop
        while self.running:
            try:
                # Consume messages (non-blocking with timeout)
                kafka_service.consume_messages(process_message, max_messages=100)
                # Small sleep to prevent tight loop
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in consumption loop: {e}")
                await asyncio.sleep(1)  # Wait before retrying

    def stop(self):
        """Stop the ingestion service."""
        logger.info("Stopping log ingestion service...")
        self.running = False
        kafka_service.close()


# Global instance
ingestion_service = IngestionService()
