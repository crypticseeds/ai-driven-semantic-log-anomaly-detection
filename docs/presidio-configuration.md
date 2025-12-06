# Presidio PII Detection and Redaction Configuration

This document describes the Presidio configuration for PII (Personally Identifiable Information) detection and redaction in the AI-driven Semantic Log Anomaly Detection system.

## Overview

Presidio is integrated into the log processing pipeline to automatically detect and redact PII from log entries. This ensures that sensitive information is not stored or displayed in logs, while preserving the original logs for audit purposes.

## Architecture

PII redaction occurs at multiple points in the pipeline:

1. **During Ingestion**: Logs are analyzed and redacted before being stored in PostgreSQL
2. **During Search**: Search results are redacted before being returned via the API
3. **Dashboard Display**: Logs displayed in the dashboard are automatically redacted (via API)

## Configuration

### PII Service Location

The PII service is located at: `backend/app/services/pii_service.py`

### Supported PII Types

The system is configured to detect and redact the following PII types:

| PII Type | Redaction Placeholder | Description |
|----------|----------------------|-------------|
| `EMAIL_ADDRESS` | `[EMAIL]` | Email addresses (e.g., user@example.com) |
| `PHONE_NUMBER` | `[PHONE]` | Phone numbers in various formats |
| `CREDIT_CARD` | `[CREDIT_CARD]` | Credit card numbers |
| `SSN` | `[SSN]` | Social Security Numbers (US format) |
| `IP_ADDRESS` | `[IP]` | IP addresses (IPv4 and IPv6) |
| `US_PASSPORT` | `[PASSPORT]` | US passport numbers |
| `UK_PASSPORT` | `[PASSPORT]` | UK passport numbers |
| `US_DRIVER_LICENSE` | `[DRIVER_LICENSE]` | US driver's license numbers |
| `DATE_TIME` | `[DATE]` | Date/time information |
| `PERSON` | `[PERSON]` | Person names |
| `URL` | `[URL]` | URLs (may contain sensitive information) |
| `IBAN_CODE` | `[IBAN]` | International Bank Account Numbers |
| `CRYPTO` | `[CRYPTO]` | Cryptocurrency addresses |
| `DEFAULT` | `[REDACTED]` | Default for any other detected PII |

### Operator Configuration

The redaction operators are configured in the `_get_operator_config()` method of the `PIIService` class. Each PII type uses a "replace" operator that substitutes the detected PII with a placeholder.

Example configuration:

```python
{
    "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
    "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
    # ... other types
}
```

## Integration Points

### 1. Log Ingestion (`ingestion_service.py`)

PII redaction occurs during log processing:

```python
# Detect and redact PII
message_to_check = raw_log.message or raw_log.raw_log
redacted_message, pii_entities = pii_service.redact_pii(message_to_check)

# Create processed log entry with redacted message
processed_log = ProcessedLogEntry(
    message=redacted_message,  # Redacted
    raw_log=raw_log.raw_log,   # Original preserved
    pii_redacted=len(pii_entities) > 0,
    pii_entities=pii_entities,
)
```

**Key Points:**
- The `message` field is redacted before storage
- The `raw_log` field preserves the original log for audit purposes
- The `pii_redacted` flag indicates if PII was detected
- The `pii_entities` dictionary contains counts of detected PII types

### 2. Search Endpoint (`api/v1/logs.py`)

Search results are redacted before being returned:

```python
# Redact PII from the message field before returning
redacted_message, pii_entities = pii_service.redact_pii(entry.message)

result = {
    "message": redacted_message,  # PII-redacted
    "pii_entities_detected": pii_entities,
    # ...
}
```

**Key Points:**
- All search results have PII redacted from the `message` field
- The `raw_log` field is only returned in individual log retrieval (for authorized users)
- PII detection results are included in the response

### 3. Database Schema

The database schema includes a `pii_redacted` flag:

```python
class LogEntry(Base):
    message = Column(Text, nullable=False)  # Redacted message
    raw_log = Column(Text, nullable=False)  # Original log
    pii_redacted = Column(Boolean, default=False, nullable=False)
```

## Usage

### Detecting PII

```python
from app.services.pii_service import pii_service

text = "Contact user@example.com at 555-123-4567"
entities = pii_service.detect_pii(text)

# Returns list of detected entities:
# [
#     {"entity_type": "EMAIL_ADDRESS", "start": 8, "end": 24, "score": 0.95},
#     {"entity_type": "PHONE_NUMBER", "start": 28, "end": 40, "score": 0.92}
# ]
```

### Redacting PII

```python
from app.services.pii_service import pii_service

text = "Contact user@example.com at 555-123-4567"
redacted, entities = pii_service.redact_pii(text)

# redacted: "Contact [EMAIL] at [PHONE]"
# entities: {"EMAIL_ADDRESS": 1, "PHONE_NUMBER": 1}
```

## Error Handling

The PII service is designed to be fault-tolerant:

- If PII detection fails, an empty list is returned
- If PII redaction fails, the original text is returned unchanged
- Errors are logged but do not interrupt the log processing pipeline

## Testing

Comprehensive tests are available in:

- `backend/tests/integration/test_ingestion_flow.py` - Integration tests for PII detection
- `backend/tests/unit/test_pii_service.py` - Unit tests for PII service

Test coverage includes:
- Detection of various PII types (email, phone, SSN, credit card, IP, etc.)
- Redaction accuracy
- Multiple PII types in one text
- Edge cases (empty text, special characters, etc.)

## Customization

### Adding New PII Types

To add support for additional PII types:

1. Ensure Presidio supports the entity type (check Presidio documentation)
2. Add the operator configuration in `_get_operator_config()`:

```python
"NEW_ENTITY_TYPE": OperatorConfig("replace", {"new_value": "[NEW_TYPE]"}),
```

3. Update tests to verify detection of the new type
4. Update this documentation

### Modifying Redaction Placeholders

To change the redaction placeholders, modify the `_get_operator_config()` method:

```python
"EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED_EMAIL]"}),
```

## Dependencies

- `presidio-analyzer>=2.2.0` - PII detection engine
- `presidio-anonymizer>=2.2.0` - PII redaction engine
- `en-core-web-lg` - spaCy language model for NLP (required by Presidio)

## Performance Considerations

- Presidio analyzer and anonymizer are lazily initialized (created on first use)
- The analyzer uses spaCy's English language model which is loaded into memory
- PII detection adds minimal latency to log processing (< 100ms per log entry typically)

## Security Notes

1. **Original Logs Preserved**: The `raw_log` field preserves original logs for audit purposes. Access to this field should be restricted to authorized personnel.

2. **PII Detection Accuracy**: Presidio uses pattern matching and NLP, which may have false positives/negatives. Regular testing and tuning may be required.

3. **Compliance**: This implementation helps with GDPR, CCPA, and other privacy regulations, but compliance should be verified by legal/security teams.

## Troubleshooting

### PII Not Being Detected

- Verify that the spaCy model (`en-core-web-lg`) is installed
- Check that Presidio analyzer is initialized correctly
- Review Presidio logs for detection confidence scores
- Some PII types may require custom recognizers (see Presidio documentation)

### Performance Issues

- Consider caching analyzer/anonymizer instances (already implemented)
- For high-volume scenarios, consider batch processing
- Monitor memory usage (spaCy model is ~500MB)

## References

- [Presidio Documentation](https://microsoft.github.io/presidio/)
- [Presidio Analyzer](https://github.com/microsoft/presidio/tree/main/presidio-analyzer)
- [Presidio Anonymizer](https://github.com/microsoft/presidio/tree/main/presidio-anonymizer)
