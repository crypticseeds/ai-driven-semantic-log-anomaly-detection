"""Presidio PII detection and redaction service."""

import logging

from presidio_anonymizer.entities import OperatorConfig

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class PIIService:
    """Service for PII detection and redaction using Presidio.

    Configured to detect and redact common PII types:
    - Email addresses
    - Phone numbers
    - Credit card numbers
    - Social Security Numbers (SSN)
    - IP addresses
    - US/UK passport numbers
    - US driver's license numbers
    - Date of birth
    - Person names
    - URLs (may contain sensitive info)
    - IBAN codes
    - Crypto addresses
    """

    _analyzer = None
    _anonymizer = None

    def __init__(self):
        """Initialize Presidio analyzer and anonymizer lazily."""
        # Lazy initialization - engines are created on first use
        pass

    @property
    def analyzer(self):
        """Lazily initialize and return the AnalyzerEngine."""
        if PIIService._analyzer is None:
            from presidio_analyzer import AnalyzerEngine

            PIIService._analyzer = AnalyzerEngine()
        return PIIService._analyzer

    @property
    def anonymizer(self):
        """Lazily initialize and return the AnonymizerEngine."""
        if PIIService._anonymizer is None:
            from presidio_anonymizer import AnonymizerEngine

            PIIService._anonymizer = AnonymizerEngine()
        return PIIService._anonymizer

    def _get_operator_config(self) -> dict[str, OperatorConfig]:
        """Get operator configuration for PII redaction.

        Returns:
            Dictionary mapping entity types to their redaction operators.
        """
        return {
            "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
            "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[CREDIT_CARD]"}),
            "SSN": OperatorConfig("replace", {"new_value": "[SSN]"}),
            "IP_ADDRESS": OperatorConfig("replace", {"new_value": "[IP]"}),
            "US_PASSPORT": OperatorConfig("replace", {"new_value": "[PASSPORT]"}),
            "UK_PASSPORT": OperatorConfig("replace", {"new_value": "[PASSPORT]"}),
            "US_DRIVER_LICENSE": OperatorConfig("replace", {"new_value": "[DRIVER_LICENSE]"}),
            "DATE_TIME": OperatorConfig("replace", {"new_value": "[DATE]"}),
            "PERSON": OperatorConfig("replace", {"new_value": "[PERSON]"}),
            "URL": OperatorConfig("replace", {"new_value": "[URL]"}),
            "IBAN_CODE": OperatorConfig("replace", {"new_value": "[IBAN]"}),
            "CRYPTO": OperatorConfig("replace", {"new_value": "[CRYPTO]"}),
        }

    def detect_pii(self, text: str) -> list[dict]:
        """Detect PII entities in text.

        Args:
            text: Text to analyze for PII

        Returns:
            List of detected PII entities with their types, positions, and confidence scores
        """
        try:
            results = self.analyzer.analyze(text=text, language="en")
            return [
                {
                    "entity_type": result.entity_type,
                    "start": result.start,
                    "end": result.end,
                    "score": result.score,
                }
                for result in results
            ]
        except Exception as e:
            # Log error but don't fail the pipeline
            logger.error(f"PII detection error: {e}", exc_info=True)
            return []

    def redact_pii(self, text: str, _entities: list[dict] | None = None) -> tuple[str, dict]:
        """Redact PII from text.

        Args:
            text: Text to redact PII from
            _entities: Unused parameter (kept for API compatibility)

        Returns:
            Tuple of (redacted_text, entity_summary) where:
            - redacted_text: Text with PII replaced by placeholders
            - entity_summary: Dictionary mapping entity types to counts
        """
        # Always re-analyze to get proper RecognizerResult objects for anonymizer
        try:
            analyzer_results = self.analyzer.analyze(text=text, language="en")
        except Exception as e:
            logger.error(f"PII analysis error: {e}", exc_info=True)
            return text, {}

        if not analyzer_results:
            return text, {}

        # Get operator configuration for redaction
        operator_config = self._get_operator_config()

        try:
            anonymized_result = self.anonymizer.anonymize(
                text=text,
                analyzer_results=analyzer_results,
                operators=operator_config,
            )
            redacted_text = anonymized_result.text

            # Build entity summary
            entity_summary = {}
            for result in analyzer_results:
                entity_type = result.entity_type
                if entity_type not in entity_summary:
                    entity_summary[entity_type] = 0
                entity_summary[entity_type] += 1

            return redacted_text, entity_summary
        except Exception as e:
            # Log error but return original text
            logger.error(f"PII redaction error: {e}", exc_info=True)
            return text, {}


# Global instance
pii_service = PIIService()
