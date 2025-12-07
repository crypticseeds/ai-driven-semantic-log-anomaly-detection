"""Storage service for saving processed log entries to PostgreSQL and Qdrant."""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.postgres import LogEntry
from app.db.session import get_db
from app.models.log import ProcessedLogEntry
from app.services.embedding_service import embedding_service
from app.services.qdrant_service import qdrant_service

logger = logging.getLogger(__name__)


class StorageService:
    """Service for storing processed log entries in PostgreSQL."""

    def save_log_entry(
        self, processed_log: ProcessedLogEntry, db: Session | None = None
    ) -> UUID | None:
        """Save processed log entry to database."""
        try:
            if db is None:
                db = next(get_db())

            log_entry = LogEntry(
                timestamp=processed_log.timestamp,
                level=processed_log.level,
                service=processed_log.service,
                message=processed_log.message,
                raw_log=processed_log.raw_log,
                log_metadata=processed_log.metadata,  # Renamed from 'metadata' to 'log_metadata'
                pii_redacted=processed_log.pii_redacted,
            )

            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)

            logger.debug(f"Saved log entry with ID: {log_entry.id}")

            # Store vector embedding in Qdrant
            self._store_vector_embedding(log_entry.id, processed_log)

            return log_entry.id
        except Exception as e:
            logger.error(f"Failed to save log entry: {e}")
            if db:
                db.rollback()
            return None

    def save_log_entry_async(self, processed_log: ProcessedLogEntry) -> UUID | None:
        """Save processed log entry asynchronously (creates new session)."""
        db = next(get_db())
        try:
            return self.save_log_entry(processed_log, db)
        finally:
            db.close()

    def _store_vector_embedding(self, log_id: UUID, processed_log: ProcessedLogEntry) -> None:
        """Store vector embedding in Qdrant.

        Args:
            log_id: UUID of the log entry
            processed_log: Processed log entry
        """
        try:
            # Generate embedding from the message
            embedding = embedding_service.generate_embedding(processed_log.message)
            if not embedding:
                logger.warning(f"Failed to generate embedding for log_id: {log_id}")
                return

            # Prepare payload with metadata for filtering
            payload = {
                "level": processed_log.level,
                "service": processed_log.service,
                "timestamp": processed_log.timestamp.isoformat(),
                "pii_redacted": processed_log.pii_redacted,
            }

            # Store in Qdrant
            success = qdrant_service.store_vector(log_id, embedding, payload)
            if success:
                logger.debug(f"Stored vector embedding for log_id: {log_id}")
            else:
                logger.warning(f"Failed to store vector embedding for log_id: {log_id}")
        except Exception as e:
            logger.error(f"Error storing vector embedding: {e}", exc_info=True)


# Global instance
storage_service = StorageService()
