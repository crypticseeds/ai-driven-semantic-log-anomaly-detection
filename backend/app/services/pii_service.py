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

# Patterns that indicate the text is kernel/system log data
# These specific patterns rarely contain user PII and produce false positives
# Note: We do NOT skip HTTP access logs as they contain IP addresses to redact
KERNEL_LOG_INDICATORS = [
    r"kernel:\s*\[",  # Kernel logs
    r"\[\s*\d+\.\d+\]",  # Kernel timestamp format
    r"pid=\d+|uid=\d+|gid=\d+",  # Process/user IDs in kernel logs
]

# Regex to match IP:PORT patterns for selective redaction
# This catches both IPv4 addresses with ports (e.g., 192.168.1.1:8080)
# and standalone IPv4 addresses
IP_PORT_PATTERN = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d{1,5})?\b")


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
    _kernel_log_regex = None

    def __init__(self):
        """Initialize Presidio analyzer and anonymizer lazily."""
        # Compile kernel log pattern regex for performance
        if PIIService._kernel_log_regex is None:
            PIIService._kernel_log_regex = re.compile(
                "|".join(KERNEL_LOG_INDICATORS), re.IGNORECASE
            )

    def _is_kernel_log(self, text: str) -> bool:
        """Check if text appears to be kernel/system log data.

        Kernel logs typically don't contain user PII and produce many false positives.
        Note: HTTP access logs are NOT considered kernel logs - they contain IPs to redact.

        Args:
            text: Text to check

        Returns:
            True if text appears to be kernel log data
        """
        if not text:
            return False
        return bool(PIIService._kernel_log_regex.search(text))

    def _redact_ip_addresses(self, text: str) -> tuple[str, int]:
        """Redact IP addresses and IP:PORT patterns from text.

        This is a targeted redaction that catches IP addresses that Presidio might miss,
        especially in HTTP access log formats.

        Args:
            text: Text to redact IPs from

        Returns:
            Tuple of (redacted_text, count_of_ips_redacted)
        """
        count = 0

        def replace_ip(match):
            nonlocal count
            count += 1
            # If there's a port, redact both IP and port
            if match.group(2):
                return "[IP]:[PORT]"
            return "[IP]"

        redacted = IP_PORT_PATTERN.sub(replace_ip, text)
        return redacted, count

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

        Uses a two-phase approach:
        1. Always redact IP addresses using regex (reliable, no false positives)
        2. For non-kernel logs, also run Presidio for other PII types

        Args:
            text: Text to redact PII from
            _entities: Unused parameter (kept for API compatibility)

        Returns:
            Tuple of (redacted_text, entity_summary) where:
            - redacted_text: Text with PII replaced by placeholders
            - entity_summary: Dictionary mapping entity types to counts
        """
        entity_summary = {}

        # Phase 1: Always redact IP addresses (this is critical for security)
        # This catches IPs in HTTP access logs that might be skipped by Presidio
        text, ip_count = self._redact_ip_addresses(text)
        if ip_count > 0:
            entity_summary["IP_ADDRESS"] = ip_count

        # Phase 2: Skip additional PII detection for kernel log data
        # Kernel logs produce many false positives and rarely contain user PII
        if self._is_kernel_log(text):
            logger.debug("Skipping Presidio PII detection for kernel log data")
            return text, entity_summary

        # Run Presidio for other PII types (email, phone, SSN, credit card, etc.)
        try:
            analyzer_results = self.analyzer.analyze(text=text, language="en")
        except Exception as e:
            logger.error(f"PII analysis error: {e}", exc_info=True)
            return text, entity_summary

        if not analyzer_results:
            return text, entity_summary

        # Filter out excluded entity types, low-confidence detections, and IP_ADDRESS
        # (IP addresses already handled by regex above)
        filtered_results = [
            result
            for result in analyzer_results
            if result.entity_type not in EXCLUDED_ENTITY_TYPES
            and result.entity_type != "IP_ADDRESS"  # Already handled
            and result.score >= PII_CONFIDENCE_THRESHOLD
        ]

        if not filtered_results:
            return text, entity_summary

        # Get operator configuration for redaction
        operator_config = self._get_operator_config()

        try:
            anonymized_result = self.anonymizer.anonymize(
                text=text,
                analyzer_results=filtered_results,
                operators=operator_config,
            )
            redacted_text = anonymized_result.text

            # Build entity summary (add to existing IP count)
            for result in filtered_results:
                entity_type = result.entity_type
                if entity_type not in entity_summary:
                    entity_summary[entity_type] = 0
                entity_summary[entity_type] += 1

            return redacted_text, entity_summary
        except Exception as e:
            # Log error but return text with IPs already redacted
            logger.error(f"PII redaction error: {e}", exc_info=True)
            return text, entity_summary


# Global instance
pii_service = PIIService()
