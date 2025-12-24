"""Presidio PII detection and redaction service."""

import logging
import re

from presidio_anonymizer.entities import OperatorConfig

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Minimum confidence score for PII detection
# Higher threshold reduces false positives but may miss some real PII
PII_CONFIDENCE_THRESHOLD = 0.7

# Entity types that produce too many false positives in log data
# These are excluded from detection entirely
EXCLUDED_ENTITY_TYPES = {
    "US_DRIVER_LICENSE",  # Matches numeric sequences like process IDs
    "DATE_TIME",  # Matches timestamps which are expected in logs
    "URL",  # URLs in logs are usually not PII (endpoints, docs)
    "PERSON",  # Too many false positives with service names, hostnames
}

# Patterns that indicate the text is technical/log data, not user content
# If these patterns are found, we skip PII redaction entirely
LOG_PATTERN_INDICATORS = [
    r"kernel:\s*\[",  # Kernel logs
    r"\[\s*\d+\.\d+\]",  # Kernel timestamp format
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",  # ISO timestamp at start
    r"(INFO|DEBUG|WARN|ERROR|TRACE)\s*[:\-\|]",  # Log level indicators
    r"pid=\d+|uid=\d+|gid=\d+",  # Process/user IDs
]


class PIIService:
    """Service for PII detection and redaction using Presidio.

    Configured to detect and redact common PII types with high confidence:
    - Email addresses
    - Phone numbers
    - Credit card numbers
    - Social Security Numbers (SSN)
    - IP addresses

    Excluded entity types (too many false positives in log data):
    - US_DRIVER_LICENSE (matches process IDs, numeric sequences)
    - DATE_TIME (timestamps are expected in logs)
    - URL (endpoints, documentation links are not PII)
    - PERSON (matches service names, hostnames)
    """

    _analyzer = None
    _anonymizer = None
    _log_pattern_regex = None

    def __init__(self):
        """Initialize Presidio analyzer and anonymizer lazily."""
        # Compile log pattern regex for performance
        if PIIService._log_pattern_regex is None:
            PIIService._log_pattern_regex = re.compile(
                "|".join(LOG_PATTERN_INDICATORS), re.IGNORECASE
            )

    def _is_technical_log(self, text: str) -> bool:
        """Check if text appears to be technical log data.

        Technical logs (kernel messages, system logs) typically don't contain
        user PII and produce many false positives with Presidio.

        Args:
            text: Text to check

        Returns:
            True if text appears to be technical log data
        """
        if not text:
            return False
        return bool(PIIService._log_pattern_regex.search(text))

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
        # Skip PII detection for technical log data (kernel logs, system logs)
        # These produce many false positives and rarely contain user PII
        if self._is_technical_log(text):
            logger.debug("Skipping PII detection for technical log data")
            return text, {}

        # Always re-analyze to get proper RecognizerResult objects for anonymizer
        try:
            analyzer_results = self.analyzer.analyze(text=text, language="en")
        except Exception as e:
            logger.error(f"PII analysis error: {e}", exc_info=True)
            return text, {}

        if not analyzer_results:
            return text, {}

        # Filter out excluded entity types and low-confidence detections
        filtered_results = [
            result
            for result in analyzer_results
            if result.entity_type not in EXCLUDED_ENTITY_TYPES
            and result.score >= PII_CONFIDENCE_THRESHOLD
        ]

        if not filtered_results:
            return text, {}

        # Get operator configuration for redaction
        operator_config = self._get_operator_config()

        try:
            anonymized_result = self.anonymizer.anonymize(
                text=text,
                analyzer_results=filtered_results,
                operators=operator_config,
            )
            redacted_text = anonymized_result.text

            # Build entity summary
            entity_summary = {}
            for result in filtered_results:
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
