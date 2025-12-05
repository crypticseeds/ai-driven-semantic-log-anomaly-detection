"""Storage service for saving processed log entries to PostgreSQL."""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.postgres import LogEntry
from app.db.session import get_db
from app.models.log import ProcessedLogEntry

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


# Global instance
storage_service = StorageService()
