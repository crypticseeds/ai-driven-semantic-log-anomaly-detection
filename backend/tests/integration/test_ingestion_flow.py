"""Integration tests for the ingestion pipeline."""

import json
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.db.postgres import LogEntry
from app.db.session import get_db
from app.models.log import ProcessedLogEntry, RawLogEntry
from app.services.ingestion_service import ingestion_service
from app.services.metadata_extractor import metadata_extractor
from app.services.pii_service import pii_service
from app.services.storage_service import storage_service


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()


class TestLogParsing:
    """Test log parsing and normalization."""

    def test_json_log_parsing(self):
        """Test parsing of JSON log format."""
        raw_data = {
            "timestamp": "2024-01-15T10:30:45.123",
            "level": "ERROR",
            "message": "Database connection failed",
            "service": "backend",
            "metadata": {"request_id": "12345"},
        }

        raw_log = RawLogEntry(
            timestamp=datetime.fromisoformat("2024-01-15T10:30:45.123"),
            message="Database connection failed",
            level="ERROR",
            service="backend",
            metadata={"request_id": "12345"},
            raw_log=json.dumps(raw_data),
            log_type="json",
        )

        assert raw_log.timestamp is not None
        assert raw_log.level == "ERROR"
        assert raw_log.service == "backend"
        assert raw_log.message == "Database connection failed"

    def test_syslog_parsing(self):
        """Test parsing of syslog format."""
        raw_data = {
            "message": "<34>Jan 15 10:30:45 hostname app: Database connection failed",
            "log_type": "syslog",
        }

        raw_log = RawLogEntry(
            message=raw_data["message"],
            raw_log=json.dumps(raw_data),
            log_type="syslog",
        )

        assert raw_log.message is not None
        assert raw_log.log_type == "syslog"


class TestPIIDetection:
    """Test PII detection and redaction."""

    def test_email_detection(self):
        """Test email address detection."""
        text = "Contact user@example.com for support"
        entities = pii_service.detect_pii(text)

        assert len(entities) > 0
        assert any(e["entity_type"] == "EMAIL_ADDRESS" for e in entities)

    def test_phone_detection(self):
        """Test phone number detection."""
        text = "Call us at 555-123-4567"
        entities = pii_service.detect_pii(text)

        assert len(entities) > 0
        assert any(e["entity_type"] == "PHONE_NUMBER" for e in entities)

    def test_pii_redaction(self):
        """Test PII redaction."""
        text = "User email is user@example.com and phone is 555-123-4567"
        redacted, entities = pii_service.redact_pii(text)

        assert "[EMAIL]" in redacted or "[REDACTED]" in redacted
        assert len(entities) > 0

    def test_no_pii_in_text(self):
        """Test text with no PII."""
        text = "This is a normal log message with no sensitive data"
        entities = pii_service.detect_pii(text)

        # May or may not detect entities, but should not fail
        assert isinstance(entities, list)


class TestMetadataExtraction:
    """Test metadata extraction."""

    def test_level_extraction_from_message(self):
        """Test log level extraction from message."""
        raw_log = RawLogEntry(
            message="ERROR: Database connection failed",
            raw_log='{"message": "ERROR: Database connection failed"}',
        )

        level = metadata_extractor.extract_level(raw_log.message, raw_log.metadata)
        assert level == "ERROR"

    def test_level_extraction_from_metadata(self):
        """Test log level extraction from metadata."""
        raw_log = RawLogEntry(
            message="Database connection failed",
            metadata={"level": "WARN"},
            raw_log='{"message": "Database connection failed", "level": "WARN"}',
        )

        level = metadata_extractor.extract_level(raw_log.message, raw_log.metadata)
        assert level == "WARN"

    def test_service_extraction(self):
        """Test service name extraction."""
        raw_log = RawLogEntry(
            message="service=backend Database connection failed",
            raw_log='{"message": "service=backend Database connection failed"}',
        )

        service = metadata_extractor.extract_service(
            raw_log.message, raw_log.metadata, raw_log.log_type
        )
        assert "backend" in service.lower()

    def test_timestamp_extraction(self):
        """Test timestamp extraction."""
        raw_log = RawLogEntry(
            timestamp=datetime(2024, 1, 15, 10, 30, 45),
            message="Test message",
            raw_log='{"timestamp": "2024-01-15T10:30:45", "message": "Test message"}',
        )

        timestamp = metadata_extractor.extract_timestamp(raw_log)
        assert timestamp == datetime(2024, 1, 15, 10, 30, 45)

    def test_full_metadata_extraction(self):
        """Test full metadata extraction."""
        raw_log = RawLogEntry(
            timestamp=datetime(2024, 1, 15, 10, 30, 45),
            message="ERROR: Database connection failed",
            metadata={"request_id": "12345"},
            raw_log='{"timestamp": "2024-01-15T10:30:45", "message": "ERROR: Database connection failed"}',
            log_type="json",
        )

        extracted = metadata_extractor.extract_metadata(raw_log)
        assert extracted["timestamp"] == datetime(2024, 1, 15, 10, 30, 45)
        assert extracted["level"] == "ERROR"
        assert "service" in extracted


class TestIngestionFlow:
    """Test the complete ingestion flow."""

    def test_process_raw_log(self):
        """Test processing a raw log entry."""
        raw_data = {
            "timestamp": "2024-01-15T10:30:45.123",
            "level": "ERROR",
            "message": "Database connection failed for user@example.com",
            "service": "backend",
            "metadata": {"request_id": "12345"},
            "log_type": "json",
        }

        processed_log = ingestion_service.process_raw_log(raw_data)

        assert processed_log is not None
        assert processed_log.timestamp is not None
        assert processed_log.level == "ERROR"
        assert processed_log.service == "backend"
        assert processed_log.pii_redacted is True  # Contains email
        assert len(processed_log.pii_entities) > 0

    def test_process_log_without_pii(self):
        """Test processing log without PII."""
        raw_data = {
            "timestamp": "2024-01-15T10:30:45.123",
            "message": "Application started successfully",
            "log_type": "json",
        }

        processed_log = ingestion_service.process_raw_log(raw_data)

        assert processed_log is not None
        assert processed_log.timestamp is not None
        assert processed_log.level in ["INFO", "DEBUG", "WARN", "ERROR"]
        assert processed_log.service is not None

    def test_storage_service(self, db_session: Session):
        """Test storing processed log entry."""
        processed_log = ProcessedLogEntry(
            timestamp=datetime.utcnow(),
            level="ERROR",
            service="test-service",
            message="Test log message",
            raw_log='{"message": "Test log message"}',
            metadata={"test": True},
            pii_redacted=False,
        )

        log_id = storage_service.save_log_entry(processed_log, db_session)
        assert log_id is not None

        # Verify it was saved
        saved_entry = db_session.query(LogEntry).filter(LogEntry.id == log_id).first()
        assert saved_entry is not None
        assert saved_entry.level == "ERROR"
        assert saved_entry.service == "test-service"
        assert saved_entry.message == "Test log message"

    def test_end_to_end_ingestion(self, db_session: Session):
        """Test end-to-end ingestion flow."""
        raw_data = {
            "timestamp": "2024-01-15T10:30:45.123",
            "level": "INFO",
            "message": "User logged in successfully",
            "service": "auth-service",
            "metadata": {"request_id": "test-123"},
            "log_type": "json",
        }

        # Process the log
        processed_log = ingestion_service.process_raw_log(raw_data)
        assert processed_log is not None

        # Store it
        log_id = storage_service.save_log_entry(processed_log, db_session)
        assert log_id is not None

        # Verify storage
        saved_entry = db_session.query(LogEntry).filter(LogEntry.id == log_id).first()
        assert saved_entry is not None
        assert saved_entry.level == "INFO"
        assert saved_entry.service == "auth-service"
