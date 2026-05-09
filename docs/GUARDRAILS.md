# InTEAM AI Service - PHI Guardrails System

Complete guide for Protected Health Information (PHI) detection, redaction, and HIPAA compliance.

## Table of Contents

1. [Overview](#overview)
2. [PHI Detection Architecture](#phi-detection-architecture)
3. [Presidio Integration](#presidio-integration)
4. [Detected Entity Types](#detected-entity-types)
5. [Integration Flow](#integration-flow)
6. [Configuration](#configuration)
7. [Testing PHI Detection](#testing-phi-detection)
8. [HIPAA Compliance](#hipaa-compliance)
9. [Monitoring and Auditing](#monitoring-and-auditing)

---

## Overview

The InTEAM AI Service uses **Microsoft Presidio** for automatic PHI detection and redaction. This ensures compliance with HIPAA regulations by preventing sensitive patient information from being logged or sent to external AI services.

### Key Features

- **Automatic PHI Detection**: Identifies names, phone numbers, addresses, SSNs, etc.
- **Input Redaction**: Sanitizes patient data before AI processing
- **Output Scanning**: Detects PHI leaks in AI responses
- **Audit Logging**: Records all PHI detections for compliance
- **Singleton Pattern**: Single Presidio instance for performance
- **Thread-Safe**: Supports concurrent requests

### Technology Stack

```
Presidio Analyzer → Detect PHI entities in text
Presidio Anonymizer → Replace PHI with placeholders
Spacy NLP → Named Entity Recognition (NER)
```

---

## PHI Detection Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    INCOMING REQUEST                         │
│          POST /api/v1/clin-gpt/analyze/                     │
│                                                             │
│  {                                                          │
│    "patient_data": {                                        │
│      "symptoms": "John Doe has chest pain",                 │
│      "phone": "555-123-4567",                               │
│      "address": "123 Main St, Boston, MA"                   │
│    }                                                        │
│  }                                                          │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│            PHI GUARDRAIL SERVICE (Singleton)                │
│         apps/clin_gpt/services/phi_guardrail.py             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────┐      │
│  │ Step 1: Initialize Presidio Engines (Once)        │      │
│  │ - AnalyzerEngine() - Detects PHI entities         │      │
│  │ - AnonymizerEngine() - Redacts PHI                │      │
│  │ - Load Spacy Model (en_core_web_sm)               │      │
│  └───────────────────────────────────────────────────┘      │
│                     ↓                                       │
│  ┌───────────────────────────────────────────────────┐      │
│  │ Step 2: Analyze Text (Presidio Analyzer)          │      │
│  │                                                   │      │
│  │ Input:  "John Doe has chest pain at 555-1234"     │      │
│  │                                                   │      │
│  │ Detection Results:                                │      │
│  │ - PERSON: "John Doe" (confidence: 0.85)           │      │
│  │ - PHONE_NUMBER: "555-1234" (confidence: 1.0)      │      │
│  │                                                   │      │
│  └───────────────────────────────────────────────────┘      │
│                     ↓                                       │
│  ┌───────────────────────────────────────────────────┐      │
│  │ Step 3: Anonymize Text (Presidio Anonymizer)      │      │
│  │                                                   │      │
│  │ Replacements:                                     │      │
│  │ - "John Doe" → "[NAME]"                           │      │
│  │ - "555-1234" → "[PHONE]"                          │      │
│  │                                                   │      │
│  │ Output: "[NAME] has chest pain at [PHONE]"        │      │
│  │                                                   │      │
│  └───────────────────────────────────────────────────┘      │
│                     ↓                                       │
│  ┌───────────────────────────────────────────────────┐      │
│  │ Step 4: Log Detections (if enabled)               │      │
│  │                                                   │      │
│  │ Logger: "PHI Guardrail detected 2 PHI entities:   │      │
│  │          ['PERSON', 'PHONE_NUMBER']"              │      │
│  │                                                   │      │
│  └───────────────────────────────────────────────────┘      │
│                                                             │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│                  SAFE DATA TO AI SERVICE                    │
│                                                             │
│  {                                                          │
│    "patient_data": {                                        │
│      "symptoms": "[NAME] has chest pain",                   │
│      "phone": "[PHONE]",                                    │
│      "address": "[LOCATION]"                                │
│    }                                                        │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
                     ↓
              [OpenAI Processing]
                     ↓
┌─────────────────────────────────────────────────────────────┐
│            OUTPUT GUARDRAIL SCAN (Reverse Check)            │
│                                                             │
│  Scans AI response for any PHI that leaked through          │
│  If detected: Redact + Log critical warning                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Presidio Integration

### Why Presidio?

**Microsoft Presidio** is an industry-standard open-source framework for PII/PHI detection:

- **Production-Ready**: Used by enterprise healthcare applications
- **Accurate NER**: Uses Spacy + custom recognizers
- **Extensible**: Can add custom entity types
- **HIPAA-Aligned**: Detects all 18 PHI identifiers
- **Multi-Language**: Supports multiple languages (currently using English)

### Singleton Pattern

The guardrail service uses a **thread-safe singleton pattern** to optimize performance:

```python
# Module-level singleton instance
_guardrail_instance = None
_guardrail_lock = threading.Lock()

def get_phi_guardrail() -> PHIGuardrail:
    """
    Get or create the singleton PHI Guardrail instance.
    Loads Presidio engines only once, reused across all requests.
    """
    global _guardrail_instance

    if _guardrail_instance is None:
        with _guardrail_lock:
            if _guardrail_instance is None:
                _guardrail_instance = PHIGuardrail()

    return _guardrail_instance
```

**Benefits**:
- **Performance**: Presidio engines loaded once at startup
- **Memory Efficiency**: Single Spacy model in memory
- **Thread-Safe**: Handles concurrent requests safely
- **Fast Response**: No initialization delay per request

---

## Detected Entity Types

### Default PHI Entities

The system detects the following PHI types by default:

| Entity Type | Examples | Placeholder |
|-------------|----------|-------------|
| `PERSON` | John Doe, Mary Smith | `[NAME]` |
| `PHONE_NUMBER` | 555-123-4567, (555) 123-4567 | `[PHONE]` |
| `EMAIL_ADDRESS` | john@example.com | `[EMAIL]` |
| `LOCATION` | 123 Main St, Boston, MA | `[LOCATION]` |
| `DATE_TIME` | 2024-01-15, January 15th | `[DATE]` |
| `US_SSN` | 123-45-6789 | `[SSN]` |
| `MEDICAL_LICENSE` | Medical license numbers | `[LICENSE]` |
| `US_DRIVER_LICENSE` | Driver's license numbers | `[LICENSE]` |
| `IP_ADDRESS` | 192.168.1.1 | `[IP]` |
| `IBAN_CODE` | Bank account numbers | `[ACCOUNT]` |
| `CREDIT_CARD` | Credit card numbers | `[CARD]` |
| `URL` | https://example.com | `[URL]` |

### HIPAA 18 Identifiers Coverage

The system covers all 18 HIPAA Safe Harbor identifiers:

```
✅ 1. Names
✅ 2. Geographic subdivisions (street addresses, cities, states, ZIP codes)
✅ 3. Dates (except year)
✅ 4. Telephone numbers
✅ 5. Fax numbers (detected as PHONE_NUMBER)
✅ 6. Email addresses
✅ 7. Social Security numbers
✅ 8. Medical record numbers (via custom recognizers if needed)
✅ 9. Health plan beneficiary numbers
✅ 10. Account numbers (IBAN_CODE)
✅ 11. Certificate/license numbers (MEDICAL_LICENSE)
✅ 12. Vehicle identifiers
✅ 13. Device identifiers/serial numbers
✅ 14. Web URLs
✅ 15. IP addresses
✅ 16. Biometric identifiers
✅ 17. Full-face photos (not applicable for text)
✅ 18. Other unique identifying numbers
```

---

## Integration Flow

### Input Guardrails (Before AI Processing)

```python
from apps.clin_gpt.services.phi_guardrail import get_phi_guardrail

# Get singleton instance
guardrail = get_phi_guardrail()

# Redact PHI from patient data
safe_data, detections = guardrail.apply_input_guardrails(patient_data)

# Safe data sent to OpenAI
# Detections logged for audit
```

**What gets redacted?**

Text fields that may contain PHI:
- `symptoms`
- `medical_history`
- `chief_complaint`
- `notes`

### Output Guardrails (After AI Response)

```python
# Scan AI response for PHI leaks
safe_response, leaks = guardrail.apply_output_guardrails(ai_response)

if leaks:
    logger.error(f"⚠️ PHI LEAK DETECTED IN AI OUTPUT! {leaks}")
```

**Why scan output?**

- AI may regenerate PHI based on patterns
- Ensures no PHI in logs or cached responses
- Critical for HIPAA compliance

---

## Configuration

### Environment Variables

```bash
# Enable/disable guardrails
GUARDRAILS_ENABLED=True

# Log PHI detections for audit
GUARDRAILS_LOG_PHI_DETECTIONS=True

# Spacy model for NER (used by Presidio)
SPACY_MODEL=en_core_web_sm
```

### Settings (config/settings.py)

```python
# Guardrails Configuration
GUARDRAILS_ENABLED = os.getenv('GUARDRAILS_ENABLED', 'True') == 'True'
GUARDRAILS_LOG_PHI_DETECTIONS = os.getenv('GUARDRAILS_LOG_PHI_DETECTIONS', 'True') == 'True'

# Entity types to detect and redact
GUARDRAILS_REDACTION_ENTITIES = [
    'PERSON', 'PHONE_NUMBER', 'EMAIL_ADDRESS', 'LOCATION',
    'DATE_TIME', 'US_SSN', 'MEDICAL_LICENSE', 'US_DRIVER_LICENSE',
    'IP_ADDRESS', 'IBAN_CODE', 'CREDIT_CARD', 'URL'
]

# Spacy Model (required by Presidio)
SPACY_MODEL = os.getenv('SPACY_MODEL', 'en_core_web_sm')
```

### Installing Spacy Model

The Spacy NER model must be installed before using guardrails:

```bash
# Option 1: Use install script
python scripts/install_spacy.py

# Option 2: Manual installation
python -m spacy download en_core_web_sm

# Option 3: Inside Docker container
docker exec inteam-ai-django python -m spacy download en_core_web_sm
```

**Available Spacy Models**:

| Model | Size | Accuracy | Speed | Use Case |
|-------|------|----------|-------|----------|
| `en_core_web_sm` | 12 MB | Basic | Fast | Development, CI/CD |
| `en_core_web_md` | 40 MB | Better | Medium | Production |
| `en_core_web_lg` | 560 MB | Best | Slow | High-accuracy needs |

**Current Default**: `en_core_web_sm` (good balance for production)

---

## Testing PHI Detection

### Manual Testing

```bash
# Test PHI detection directly (inside container)
docker exec inteam-ai-django python -c "
from apps.clin_gpt.services.phi_guardrail import get_phi_guardrail

g = get_phi_guardrail()

# Test input
text = 'Patient John Doe (DOB: 01/15/1980) called at 555-123-4567. Address: 123 Main St, Boston, MA 02101'

# Redact PHI
redacted, detections = g.redact_phi(text)

print('Original:', text)
print('Redacted:', redacted)
print('Detected PHI:')
for d in detections:
    print(f\"  - {d['type']}: {d['text']} (confidence: {d['confidence']:.2f})\")
"
```

**Expected Output**:
```
Original: Patient John Doe (DOB: 01/15/1980) called at 555-123-4567. Address: 123 Main St, Boston, MA 02101
Redacted: Patient [NAME] (DOB: [DATE]) called at [PHONE]. Address: [LOCATION]
Detected PHI:
  - PERSON: John Doe (confidence: 0.85)
  - DATE_TIME: 01/15/1980 (confidence: 1.00)
  - PHONE_NUMBER: 555-123-4567 (confidence: 1.00)
  - LOCATION: 123 Main St, Boston, MA 02101 (confidence: 0.75)
```

### Automated Tests

```bash
# Run guardrail unit tests (inside container)
docker exec inteam-ai-django python manage.py test apps.clin_gpt.tests.test_guardrails

# Run Layer 2 tests (includes guardrails)
./run_tests.sh layer2

# Test via API endpoint
curl -X POST http://localhost:8001/api/v1/clin-gpt/analyze/ \
  -H "Content-Type: application/json" \
  -d '{
    "patient_data": {
      "symptoms": "John Doe has chest pain and called at 555-1234",
      "age": 45,
      "gender": "male"
    }
  }'
```

### Test Cases

```python
# Example test cases in apps/clin_gpt/tests/test_guardrails.py

def test_detect_person_name():
    guardrail = get_phi_guardrail()
    text = "Patient John Doe was admitted yesterday"
    redacted, detections = guardrail.redact_phi(text)

    assert "[NAME]" in redacted
    assert len(detections) > 0
    assert detections[0]['type'] == 'PERSON'

def test_detect_phone_number():
    guardrail = get_phi_guardrail()
    text = "Call me at 555-123-4567"
    redacted, detections = guardrail.redact_phi(text)

    assert "[PHONE]" in redacted
    assert detections[0]['type'] == 'PHONE_NUMBER'

def test_no_phi_in_medical_terms():
    guardrail = get_phi_guardrail()
    text = "Patient has hypertension and diabetes"
    redacted, detections = guardrail.redact_phi(text)

    assert len(detections) == 0  # Medical terms not PHI
    assert redacted == text  # No redaction needed
```

---

## HIPAA Compliance

### How Guardrails Ensure HIPAA Compliance

```
┌─────────────────────────────────────────────────────────────┐
│          HIPAA SAFE HARBOR METHOD COMPLIANCE                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ De-identification of 18 PHI identifiers                 │
│     - Automatic detection with Presidio                     │
│     - Redaction before logging/external API                 │
│                                                             │
│  ✅ No PHI in logs                                          │
│     - Input redacted before logging                         │
│     - Output scanned for leaks                              │
│                                                             │
│  ✅ Audit trail                                             │
│     - All PHI detections logged                             │
│     - Timestamped detection records                         │
│                                                             │
│  ✅ Risk assessment                                         │
│     - Output leak detection                                 │
│     - Critical warnings for leaks                           │
│                                                             │
│  ✅ Fail-safe design                                        │
│     - If Presidio fails, system continues                   │
│     - Logs warning but doesn't block service                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### What PHI is Protected?

**Protected** (Redacted before AI/logging):
- Patient names
- Phone numbers and contact info
- Addresses and geographic locations
- Dates of birth, admission dates
- Social Security numbers
- Medical record numbers
- Account numbers
- License numbers

**Not Protected** (Medical information for clinical AI):
- Symptoms and diagnoses
- Vital signs (BP, HR, temperature)
- Lab values
- Medical conditions
- Treatment information

**Rationale**: Clinical AI needs medical information to provide recommendations, but not identifying information.

---

## Monitoring and Auditing

### PHI Detection Logs

When `GUARDRAILS_LOG_PHI_DETECTIONS=True`:

```bash
# View PHI detection logs
docker logs inteam-ai-django | grep "PHI Guardrail"

# Example log entries
2025-11-13 10:15:23 WARNING PHI Guardrail detected 3 PHI entities: ['PERSON', 'PHONE_NUMBER', 'LOCATION']
2025-11-13 10:15:24 INFO Request completed in 1.234s (PHI detections: 3)
```

### Output Leak Warnings

Critical warnings when AI response contains PHI:

```bash
# Check for output leaks
docker logs inteam-ai-django | grep "PHI LEAK"

# Example critical warning
2025-11-13 10:20:15 ERROR ⚠️ PHI LEAK DETECTED IN AI OUTPUT! Found 1 PHI entities in AI response: ['PERSON']
```

**Action Required**: Investigate why AI generated PHI (should be rare with proper input redaction)

### Statistics API

```python
from apps.clin_gpt.services.phi_guardrail import get_phi_guardrail

guardrail = get_phi_guardrail()
safe_data, detections = guardrail.apply_input_guardrails(patient_data)

# Get detection statistics
stats = guardrail.get_stats(detections)

print(stats)
# Output:
# {
#     'total_detections': 3,
#     'by_type': {'PERSON': 1, 'PHONE_NUMBER': 1, 'LOCATION': 1},
#     'by_field': {'symptoms': 2, 'notes': 1},
#     'has_output_leaks': False
# }
```

### Compliance Reports

```bash
# Query PHI detections from logs
docker logs inteam-ai-django --since 24h | grep "PHI Guardrail" | wc -l

# Count by entity type
docker logs inteam-ai-django --since 24h | grep "PHI Guardrail" | grep -o "PERSON\|PHONE_NUMBER\|LOCATION" | sort | uniq -c

# Check for any output leaks (should be 0)
docker logs inteam-ai-django --since 7d | grep "PHI LEAK" | wc -l
```

---

## Best Practices

### Development

1. **Test PHI detection regularly**: Add test cases for new entity types
2. **Review redaction placeholders**: Ensure meaningful for AI context
3. **Monitor false positives**: Medical terms shouldn't be flagged
4. **Update Spacy models**: Keep NER models current

### Production

1. **Enable logging**: `GUARDRAILS_LOG_PHI_DETECTIONS=True`
2. **Monitor output leaks**: Set up alerts for PHI LEAK warnings
3. **Regular audits**: Review PHI detection logs weekly
4. **Compliance documentation**: Keep records of detections

### Security

1. **Never log raw PHI**: Always use redacted versions
2. **Secure log storage**: Restrict access to audit logs
3. **Encrypt at rest**: Use encrypted volumes for logs
4. **Rotate logs**: Implement log retention policies

---

## Troubleshooting

### Issue: Spacy model not found

**Error**:
```
OSError: [E050] Can't find model 'en_core_web_sm'
```

**Solution**:
```bash
docker exec inteam-ai-django python -m spacy download en_core_web_sm
docker restart inteam-ai-django
```

### Issue: False positives (medical terms flagged)

**Example**: "Dr. Smith recommends aspirin" → "Dr. [NAME] recommends aspirin"

**Solution**: Medical titles are sometimes flagged. This is acceptable as "Dr. Smith" is still identifying information.

### Issue: Presidio not detecting PHI

**Debugging**:
```python
# Test Presidio directly
from presidio_analyzer import AnalyzerEngine

analyzer = AnalyzerEngine()
results = analyzer.analyze(text="John Doe 555-1234", language='en')
print(results)
```

**Common causes**:
- Unusual formatting (e.g., phone number without dashes)
- Non-English text
- Spacy model not loaded

---

## Resources

- **Presidio Documentation**: https://microsoft.github.io/presidio/
- **Spacy NLP**: https://spacy.io/
- **HIPAA Safe Harbor**: https://www.hhs.gov/hipaa/for-professionals/privacy/special-topics/de-identification/index.html
- **PII Detection Best Practices**: https://github.com/microsoft/presidio/blob/main/docs/tutorial/index.md

---

**Last Updated**: 2025-11-13
**Version**: 2.0
**Covers**: Presidio integration, singleton pattern, HIPAA compliance, Spacy models
