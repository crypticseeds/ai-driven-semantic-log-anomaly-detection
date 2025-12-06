"""Unit tests for PII service."""

from app.services.pii_service import pii_service


class TestPIIService:
    """Unit tests for PII service functionality."""

    def test_analyzer_lazy_initialization(self):
        """Test that analyzer is lazily initialized."""
        # First access should create the analyzer
        analyzer1 = pii_service.analyzer
        assert analyzer1 is not None

        # Second access should return the same instance
        analyzer2 = pii_service.analyzer
        assert analyzer1 is analyzer2

    def test_anonymizer_lazy_initialization(self):
        """Test that anonymizer is lazily initialized."""
        # First access should create the anonymizer
        anonymizer1 = pii_service.anonymizer
        assert anonymizer1 is not None

        # Second access should return the same instance
        anonymizer2 = pii_service.anonymizer
        assert anonymizer1 is anonymizer2

    def test_detect_pii_returns_list(self):
        """Test that detect_pii always returns a list."""
        text = "Test message"
        entities = pii_service.detect_pii(text)

        assert isinstance(entities, list)

    def test_redact_pii_returns_tuple(self):
        """Test that redact_pii returns a tuple of (text, dict)."""
        text = "Test message"
        redacted, entities = pii_service.redact_pii(text)

        assert isinstance(redacted, str)
        assert isinstance(entities, dict)

    def test_redact_pii_handles_errors_gracefully(self):
        """Test that redact_pii handles errors without crashing."""
        # This should not raise an exception
        redacted, entities = pii_service.redact_pii("")

        assert isinstance(redacted, str)
        assert isinstance(entities, dict)

    def test_operator_config(self):
        """Test that operator configuration includes common PII types."""
        operator_config = pii_service._get_operator_config()

        assert isinstance(operator_config, dict)
        # Check for common PII types
        assert "EMAIL_ADDRESS" in operator_config
        assert "PHONE_NUMBER" in operator_config
        assert "SSN" in operator_config
        assert "CREDIT_CARD" in operator_config
        assert "IP_ADDRESS" in operator_config
        assert "DEFAULT" in operator_config
