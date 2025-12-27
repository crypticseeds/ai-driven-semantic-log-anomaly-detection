"""Presidio PII detection and redaction service."""

import logging
import re

from presidio_anonymizer.entities import OperatorConfig

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Minimum confidence score for PII detection
PII_CONFIDENCE_THRESHOLD = 0.7

# Entity types that produce too many false positives in log data
EXCLUDED_ENTITY_TYPES = {
    "US_DRIVER_LICENSE",  # Matches numeric sequences like process IDs
    "DATE_TIME",  # Matches timestamps which are expected in logs
    "URL",  # URLs in logs are usually not PII (endpoints, docs)
    "PERSON",  # Too many false positives with service names, hostnames
    "LOCATION",  # Matches service names, hostnames (e.g., "presidio" = SF neighborhood)
    "NRP",  # Nationalities, religious, political groups - not relevant for logs
}

# Patterns that indicate kernel/system log data
KERNEL_LOG_INDICATORS = [
    r"kernel:\s*\[",
    r"\[\s*\d+\.\d+\]",
    r"pid=\d+|uid=\d+|gid=\d+",
]

# Regex patterns for sensitive data redaction
IP_PORT_PATTERN = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d{1,5})?\b")

UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

SENSITIVE_HOST_PATTERN = re.compile(
    r"[a-zA-Z0-9.-]*\.(qdrant\.io|pinecone\.io|weaviate\.cloud|"
    r"openai\.azure\.com|milvus\.io|chroma\.cloud)(:\d+)?",
    re.IGNORECASE,
)


class PIIService:
    """Service for PII detection and redaction using Presidio."""

    _analyzer = None
    _anonymizer = None
    _kernel_log_regex = None

    def __init__(self):
        if PIIService._kernel_log_regex is None:
            PIIService._kernel_log_regex = re.compile(
                "|".join(KERNEL_LOG_INDICATORS), re.IGNORECASE
            )

    def _is_kernel_log(self, text: str) -> bool:
        if not text:
            return False
        return bool(PIIService._kernel_log_regex.search(text))

    def _redact_ip_addresses(self, text: str) -> tuple[str, int]:
        count = 0

        def replace_ip(match):
            nonlocal count
            count += 1
            if match.group(2):
                return "[IP]:[PORT]"
            return "[IP]"

        redacted = IP_PORT_PATTERN.sub(replace_ip, text)
        return redacted, count

    def _redact_uuids(self, text: str) -> tuple[str, int]:
        count = len(UUID_PATTERN.findall(text))
        redacted = UUID_PATTERN.sub("[UUID]", text)
        return redacted, count

    def _redact_sensitive_hosts(self, text: str) -> tuple[str, int]:
        count = len(SENSITIVE_HOST_PATTERN.findall(text))
        redacted = SENSITIVE_HOST_PATTERN.sub("[CLOUD_HOST]", text)
        return redacted, count

    @property
    def analyzer(self):
        if PIIService._analyzer is None:
            from presidio_analyzer import AnalyzerEngine

            PIIService._analyzer = AnalyzerEngine()
        return PIIService._analyzer

    @property
    def anonymizer(self):
        if PIIService._anonymizer is None:
            from presidio_anonymizer import AnonymizerEngine

            PIIService._anonymizer = AnonymizerEngine()
        return PIIService._anonymizer

    def _get_operator_config(self) -> dict[str, OperatorConfig]:
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
            logger.error(f"PII detection error: {e}", exc_info=True)
            return []

    def redact_pii(self, text: str, _entities: list[dict] | None = None) -> tuple[str, dict]:
        """Redact PII from text using multi-phase approach."""
        entity_summary = {}

        # Phase 1: Always redact IP addresses
        text, ip_count = self._redact_ip_addresses(text)
        if ip_count > 0:
            entity_summary["IP_ADDRESS"] = ip_count

        # Phase 2: Always redact UUIDs (cluster IDs, API keys, tokens)
        text, uuid_count = self._redact_uuids(text)
        if uuid_count > 0:
            entity_summary["UUID"] = uuid_count

        # Phase 3: Always redact sensitive cloud hostnames
        text, host_count = self._redact_sensitive_hosts(text)
        if host_count > 0:
            entity_summary["CLOUD_HOST"] = host_count

        # Phase 4: Skip Presidio for kernel logs
        if self._is_kernel_log(text):
            return text, entity_summary

        # Run Presidio for other PII types
        try:
            analyzer_results = self.analyzer.analyze(text=text, language="en")
        except Exception as e:
            logger.error(f"PII analysis error: {e}", exc_info=True)
            return text, entity_summary

        if not analyzer_results:
            return text, entity_summary

        filtered_results = [
            result
            for result in analyzer_results
            if result.entity_type not in EXCLUDED_ENTITY_TYPES
            and result.entity_type != "IP_ADDRESS"
            and result.score >= PII_CONFIDENCE_THRESHOLD
        ]

        if not filtered_results:
            return text, entity_summary

        operator_config = self._get_operator_config()

        try:
            anonymized_result = self.anonymizer.anonymize(
                text=text,
                analyzer_results=filtered_results,
                operators=operator_config,
            )
            redacted_text = anonymized_result.text

            for result in filtered_results:
                entity_type = result.entity_type
                if entity_type not in entity_summary:
                    entity_summary[entity_type] = 0
                entity_summary[entity_type] += 1

            return redacted_text, entity_summary
        except Exception as e:
            logger.error(f"PII redaction error: {e}", exc_info=True)
            return text, entity_summary


# Global instance
pii_service = PIIService()
