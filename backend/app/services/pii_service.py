"""Presidio PII detection and redaction service."""

from presidio_anonymizer.entities import OperatorConfig

from app.config import get_settings

settings = get_settings()


class PIIService:
    """Service for PII detection and redaction using Presidio."""

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

    def detect_pii(self, text: str) -> list[dict]:
        """Detect PII entities in text."""
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
            print(f"PII detection error: {e}")
            return []

    def redact_pii(self, text: str, _entities: list[dict] | None = None) -> tuple[str, dict]:
        """Redact PII from text.

        Args:
            text: Text to redact PII from
            _entities: Unused parameter (kept for API compatibility)
        """
        # Always re-analyze to get proper RecognizerResult objects for anonymizer
        try:
            analyzer_results = self.analyzer.analyze(text=text, language="en")
        except Exception as e:
            print(f"PII analysis error: {e}")
            return text, {}

        if not analyzer_results:
            return text, {}

        # Redact with default operator (replace with entity type)
        operator_config = {
            "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
            "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[CREDIT_CARD]"}),
            "SSN": OperatorConfig("replace", {"new_value": "[SSN]"}),
            "IP_ADDRESS": OperatorConfig("replace", {"new_value": "[IP]"}),
        }

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
            print(f"PII redaction error: {e}")
            return text, {}


# Global instance
pii_service = PIIService()
