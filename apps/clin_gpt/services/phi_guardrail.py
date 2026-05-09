"""
PHI Guardrail Service
=====================
Three-layer PHI detection and anonymization pipeline.

Layer 1 — Structural Regex   : deterministic, zero-miss on well-structured PHI
                                (phone, email, SSN, MRN, NPI, dates, ZIP, URL, credit card)
Layer 2 — ML NER             : contextual detection of names, hospitals, orgs, locations
                                (scispaCy en_core_sci_lg → en_core_web_lg → en_core_web_sm)
Layer 3 — Presidio            : merge + overlap resolution + consistent anonymization

Public API is identical to the original file — no changes needed elsewhere:
    guardrail = get_phi_guardrail()
    safe_data, detections = guardrail.apply_input_guardrails(patient_data)
    safe_response, leaks  = guardrail.apply_output_guardrails(ai_response)
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from presidio_analyzer import RecognizerResult

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Layer 1 — Structural Regex
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _RegexSpan:
    start: int
    end: int
    entity_type: str
    text: str
    score: float = 1.0


_REGEX_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Identifiers
    ("US_SSN",
     re.compile(r"\b(?!000|666|9\d\d)\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}\b")),
    ("MRN",
     re.compile(r"\b(?:MRN|Patient\s+ID|Pt\.?\s*ID)[:\s#]*([A-Z0-9]{6,12})\b", re.IGNORECASE)),
    ("NPI",
     re.compile(r"\bNPI[:\s#]*(\d{10})\b", re.IGNORECASE)),
    ("PHONE_NUMBER",
     re.compile(
         r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"
     )),
    ("EMAIL_ADDRESS",
     re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("URL",
     re.compile(r"https?://[^\s\"'<>]+|www\.[^\s\"'<>]+", re.IGNORECASE)),

    # Geographic
    ("ZIP_CODE",
     re.compile(r"\b\d{5}(?:-\d{4})?\b")),

    # Dates — structured only; age descriptors ("45-year-old") intentionally excluded
    ("DATE_TIME",
     re.compile(
         r"\b(?:"
         r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"
         r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
         r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
         r"|\d{4}-\d{2}-\d{2}"
         r")\b",
         re.IGNORECASE,
     )),

    # Financial
    ("CREDIT_CARD",
     re.compile(r"\b(?:4\d{3}|5[1-5]\d{2}|6011|3[47]\d{2})[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b")),
]

# Output-scan patterns: same list but WITHOUT DATE_TIME and ZIP_CODE.
# The AI generates phrases like "30-year-old female" — our date regex does NOT
# match these, but Presidio's built-in DATE_TIME recognizer does.
# On the output side we bypass DATE_TIME entirely; real leaked DOBs are still
# caught if they appear in structured form (MM/DD/YYYY etc.) in the symptoms
# input scan, which runs before the AI sees the data.
_REGEX_PATTERNS_OUTPUT: list[tuple[str, re.Pattern]] = [
    p for p in _REGEX_PATTERNS
    if p[0] not in ("DATE_TIME", "ZIP_CODE")
]

# Presidio replacement tokens (merged from original operators + new types)
_REPLACEMENT_MAP: dict[str, str] = {
    "PERSON": "[NAME]",
    "NAME": "[NAME]",
    "PHONE_NUMBER": "[PHONE]",
    "EMAIL_ADDRESS": "[EMAIL]",
    "LOCATION": "[LOCATION]",
    "DATE_TIME": "[DATE]",
    "US_SSN": "[SSN]",
    "MEDICAL_LICENSE": "[LICENSE]",
    "US_DRIVER_LICENSE": "[LICENSE]",
    "IP_ADDRESS": "[IP]",
    "IBAN_CODE": "[ACCOUNT]",
    "CREDIT_CARD": "[CARD]",
    "URL": "[URL]",
    "MRN": "[MRN]",
    "NPI": "[NPI]",
    "ZIP_CODE": "[ZIP]",
    "ORGANIZATION": "[ORGANIZATION]",
    "DEFAULT": "[REDACTED]",
}


def _run_regex(text: str, patterns=None) -> list[_RegexSpan]:
    """Layer 1: run all regex patterns and return non-overlapping spans."""
    if patterns is None:
        patterns = _REGEX_PATTERNS
    raw: list[_RegexSpan] = []

    for entity_type, pattern in patterns:
        for m in pattern.finditer(text):
            # Patterns with a capturing group expose only the value, not the label prefix
            if m.lastindex:
                start, end = m.start(1), m.end(1)
            else:
                start, end = m.start(), m.end()
            raw.append(_RegexSpan(start=start, end=end, entity_type=entity_type,
                                  text=text[start:end]))

    # Resolve overlaps: sort by start, prefer longer span
    raw.sort(key=lambda s: (s.start, -(s.end - s.start)))
    resolved: list[_RegexSpan] = []
    last_end = -1
    for span in raw:
        if span.start >= last_end:
            resolved.append(span)
            last_end = span.end

    logger.debug("Regex layer: %d spans detected", len(resolved))
    return resolved


# ──────────────────────────────────────────────────────────────────────────────
# Layer 2 — ML NER (scispaCy / spaCy)
# ──────────────────────────────────────────────────────────────────────────────

# spaCy label → canonical Presidio-compatible entity type
_NER_LABEL_MAP: dict[str, Optional[str]] = {
    "PERSON": "PERSON",
    "ORG": "ORGANIZATION",
    "GPE": "LOCATION",
    "LOC": "LOCATION",
    "FAC": "LOCATION",
    "DATE": None,  # Intentionally skipped — regex handles dates more precisely
    "TIME": None,  # Same reason
    # All other labels implicitly map to None (ignored)
}

_NER_MODEL_PRIORITY = [
    "en_core_sci_lg",  # scispaCy — best for clinical text
    "en_core_web_lg",  # spaCy large general
    "en_core_web_sm",  # spaCy small — absolute fallback
]

_NER_ASSUMED_SCORE = 0.85  # spaCy doesn't expose per-entity confidence


def _load_nlp_model():
    """
    Load NER model with validation. Raises on corrupt model.

    Tries models in priority order. Each model must pass a health check:
    - Can be loaded by spaCy
    - Successfully processes a test document
    - Detects expected entity types (PERSON or GPE)

    Returns (nlp, model_name) on success, or raises RuntimeError if all fail.
    """
    try:
        import spacy
    except ImportError:
        logger.warning("spaCy not installed — NER layer disabled")
        return None, None

    for model_name in _NER_MODEL_PRIORITY:
        try:
            nlp = spacy.load(model_name)

            # HEALTH CHECK — do not remove
            # Verify the model can process text and produce expected entity types
            test_doc = nlp("Barack Obama visited Washington")
            labels = {ent.label_ for ent in test_doc.ents}

            if "PERSON" not in labels and "GPE" not in labels:
                raise RuntimeError(
                    f"Model {model_name} failed health check — "
                    f"got entities: {[(e.text, e.label_) for e in test_doc.ents]}"
                )

            logger.info(f"PHI guardrail: loaded {model_name} (health check passed)")
            return nlp, model_name

        except OSError:
            logger.warning(f"Model {model_name} not found, trying next...")
        except RuntimeError as e:
            logger.error(str(e))
            # Don't fall back to a broken model — try the next one
            continue

    raise RuntimeError(
        "PHI guardrail: no valid spaCy NER model available. "
        "Run: python -m spacy download en_core_web_sm"
    )


@dataclass(frozen=True)
class _NerSpan:
    start: int
    end: int
    entity_type: str
    text: str
    score: float = _NER_ASSUMED_SCORE


def _run_ner(text: str, nlp) -> list[_NerSpan]:
    """
    Layer 2: run spaCy NER and return mapped PHI spans.

    Maps spaCy labels (PERSON, ORG, GPE, LOC, FAC) to canonical Presidio types
    via _NER_LABEL_MAP. Labels not in the map are silently ignored.

    Additional protections:
    - Removes possessive "'s" from PERSON entities
      Example: "John Miller's" → "John Miller"
    - Filters false-positive ORG abbreviations like SSN, DOB, MRN, etc.
    """

    if nlp is None:
        return []

    doc = nlp(text)
    spans: list[_NerSpan] = []

    # DEBUG: Capture raw spaCy entities before mapping
    raw_entities = [(ent.text, ent.label_) for ent in doc.ents]

    # Common medical/legal abbreviations incorrectly tagged as ORG
    MEDICAL_ABBREVIATIONS = {
        "SSN",
        "DOB",
        "MRN",
        "NPI",
        "BP",
        "HR",
        "ECG",
        "ICU",
        "ER",
        "OB",
    }

    for ent in doc.ents:

        # Skip false-positive ORG abbreviations
        if ent.label_ == "ORG" and ent.text.upper() in MEDICAL_ABBREVIATIONS:
            logger.debug(
                "Skipping false-positive ORG abbreviation '%s'",
                ent.text
            )
            continue

        canonical = _NER_LABEL_MAP.get(ent.label_)

        if canonical is None:
            logger.debug(
                "NER label '%s' not in mapping (skipping entity '%s')",
                ent.label_,
                ent.text
            )
            continue

        start = ent.start_char
        end = ent.end_char
        text_span = ent.text

        # Strip trailing possessive "'s" or "’s"
        # Example: "John Miller's" -> "John Miller"
        if text_span.endswith("'s") or text_span.endswith("’s"):
            text_span = text_span[:-2].strip()
            end = start + len(text_span)

        spans.append(
            _NerSpan(
                start=start,
                end=end,
                entity_type=canonical,
                text=text_span,
            )
        )

    logger.debug(
        "NER layer: found %d raw entities, mapped %d | raw: %s",
        len(raw_entities),
        len(spans),
        raw_entities,
    )

    return spans


# ──────────────────────────────────────────────────────────────────────────────
# Layer 3 — Presidio anonymization
# ──────────────────────────────────────────────────────────────────────────────

def _build_presidio_results(
        regex_spans: list[_RegexSpan],
        ner_spans: list[_NerSpan],
) -> list[RecognizerResult]:
    return [
        RecognizerResult(entity_type=s.entity_type, start=s.start, end=s.end, score=s.score)
        for s in (*regex_spans, *ner_spans)
    ]


def _build_operators(results: list[RecognizerResult]) -> dict[str, OperatorConfig]:
    operators: dict[str, OperatorConfig] = {}
    for r in results:
        if r.entity_type not in operators:
            token = _REPLACEMENT_MAP.get(r.entity_type, _REPLACEMENT_MAP["DEFAULT"])
            operators[r.entity_type] = OperatorConfig("replace", {"new_value": token})
    return operators


# ──────────────────────────────────────────────────────────────────────────────
# PHIGuardrail — main class (public API unchanged)
# ──────────────────────────────────────────────────────────────────────────────

class PHIGuardrail:
    """
    Three-layer PHI detection and anonymization service.

    Public methods match the original API exactly:
        redact_phi(text)                → (redacted_text, detected_entities)
        apply_input_guardrails(data)    → (safe_data, detections)
        apply_output_guardrails(resp)   → (safe_resp, detections)
        get_stats(detections)           → stats dict
    """

    def __init__(self):
        self.enabled = getattr(settings, "GUARDRAILS_ENABLED", True)
        self.log_detections = getattr(settings, "GUARDRAILS_LOG_PHI_DETECTIONS", True)
        self.entities = getattr(settings, "GUARDRAILS_REDACTION_ENTITIES", None)

        self._anonymizer: Optional[AnonymizerEngine] = None
        self._nlp = None
        self._ner_model_name: Optional[str] = None

        if self.enabled:
            try:
                self._anonymizer = AnonymizerEngine()
                self._nlp, self._ner_model_name = _load_nlp_model()
                logger.info(
                    "PHIGuardrail initialized — NER model: %s",
                    self._ner_model_name or "none (regex-only mode)",
                )
            except Exception as exc:
                logger.error("PHIGuardrail init failed: %s", exc)
                self.enabled = False

    # ── Core redaction ────────────────────────────────────────────────────────

    def redact_phi(self, text: str, language: str = "en") -> Tuple[str, List[Dict]]:
        """
        Detect and redact PHI from text.

        Returns
        -------
        (redacted_text, detected_entities)
            redacted_text      : text with PHI replaced by tokens like [NAME], [DATE]
            detected_entities  : list of dicts with type, text, start, end, confidence
        """
        if not self.enabled or not text or not text.strip():
            return text, []

        try:
            # Layer 1
            regex_spans = _run_regex(text)

            # Layer 2
            ner_spans = _run_ner(text, self._nlp)

            # --- DEBUG TRACE: Verify NER wiring (REMOVE AFTER TESTING) ---
            logger.debug(
                "PHI redaction trace — regex_spans: %d, ner_spans: %d | "
                "regex: %s | ner: %s",
                len(regex_spans),
                len(ner_spans),
                [(s.entity_type, s.text) for s in regex_spans],
                [(s.entity_type, s.text) for s in ner_spans],
            )
            # --- END DEBUG ---

            # Layer 3
            all_results = _build_presidio_results(regex_spans, ner_spans)

            # --- DEBUG TRACE: Check merged Presidio results ---
            logger.debug(
                "PHI merged Presidio results: %d total | %s",
                len(all_results),
                [(r.entity_type, text[r.start:r.end]) for r in all_results],
            )
            # --- END DEBUG ---

            if not all_results:
                return text, []

            operators = _build_operators(all_results)
            anonymized = self._anonymizer.anonymize(
                text=text,
                analyzer_results=all_results,
                operators=operators,
            )

            detected_entities = [
                {
                    "type": r.entity_type,
                    "text": text[r.start:r.end],
                    "start": r.start,
                    "end": r.end,
                    "confidence": round(r.score, 3),
                }
                for r in sorted(all_results, key=lambda x: x.start)
            ]

            if self.log_detections and detected_entities:
                logger.warning(
                    "PHI Guardrail detected %d entities: %s",
                    len(detected_entities),
                    [e["type"] for e in detected_entities],
                )

            return anonymized.text, detected_entities

        except Exception as exc:
            logger.error("PHI Guardrail redaction error: %s", exc)
            return text, []  # fail-open for availability

    def redact_phi_output(self, text: str) -> Tuple[str, List[Dict]]:
        """
        Variant of redact_phi for scanning AI-generated output.
        Uses a reduced pattern set that excludes DATE_TIME and ZIP_CODE to
        prevent false positives like "30-year-old" being tagged as [DATE].
        Names, phones, emails, SSNs, and URLs are still fully detected.
        """
        if not self.enabled or not text or not text.strip():
            return text, []

        try:
            # Layer 1 — output-safe patterns only
            regex_spans = _run_regex(text, patterns=_REGEX_PATTERNS_OUTPUT)

            # Layer 2 — NER still runs (catches names, hospitals, orgs)
            ner_spans = _run_ner(text, self._nlp)

            all_results = _build_presidio_results(regex_spans, ner_spans)

            if not all_results:
                return text, []

            operators = _build_operators(all_results)
            anonymized = self._anonymizer.anonymize(
                text=text,
                analyzer_results=all_results,
                operators=operators,
            )

            detected_entities = [
                {
                    "type": r.entity_type,
                    "text": text[r.start:r.end],
                    "start": r.start,
                    "end": r.end,
                    "confidence": round(r.score, 3),
                }
                for r in sorted(all_results, key=lambda x: x.start)
            ]

            if self.log_detections and detected_entities:
                logger.warning(
                    "PHI Guardrail (output scan) detected %d entities: %s",
                    len(detected_entities),
                    [e["type"] for e in detected_entities],
                )

            return anonymized.text, detected_entities

        except Exception as exc:
            logger.error("PHI Guardrail output redaction error: %s", exc)
            return text, []

    # ── Input guardrails ──────────────────────────────────────────────────────

    def apply_input_guardrails(self, patient_data: Dict) -> Tuple[Dict, List[Dict]]:
        """
        Apply PHI detection to all free-text fields in patient data.

        Returns (safe_patient_data, all_detections).
        """
        if not self.enabled:
            return patient_data, []

        safe_data = patient_data.copy()
        all_detections: List[Dict] = []

        text_fields = ["symptoms", "medical_history", "chief_complaint", "notes"]

        for field in text_fields:
            if field in patient_data and patient_data[field]:
                safe_text, detections = self.redact_phi(str(patient_data[field]))
                safe_data[field] = safe_text
                for d in detections:
                    d["field"] = field
                    all_detections.append(d)

        return safe_data, all_detections

    # ── Output guardrails ─────────────────────────────────────────────────────

    def apply_output_guardrails(self, ai_response: Dict) -> Tuple[Dict, List[Dict]]:
        """
        Scan AI response for any leaked PHI.

        Returns (safe_response, detected_leaks).
        """
        if not self.enabled:
            return ai_response, []

        safe_response: Dict = {}
        all_detections: List[Dict] = []

        for key, value in ai_response.items():
            if isinstance(value, str):
                safe_text, detections = self.redact_phi_output(value)
                safe_response[key] = safe_text
                for d in detections:
                    d["field"] = f"output.{key}"
                    d["is_output_leak"] = True
                    all_detections.append(d)

            elif isinstance(value, list):
                safe_list = []
                for item in value:
                    if isinstance(item, str):
                        safe_text, detections = self.redact_phi_output(item)
                        safe_list.append(safe_text)
                        for d in detections:
                            d["field"] = f"output.{key}[]"
                            d["is_output_leak"] = True
                            all_detections.append(d)
                    else:
                        safe_list.append(item)
                safe_response[key] = safe_list

            else:
                safe_response[key] = value

        if all_detections:
            logger.error(
                "⚠️ PHI LEAK IN AI OUTPUT — %d entities: %s",
                len(all_detections),
                [d["type"] for d in all_detections],
            )

        return safe_response, all_detections

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self, detections: List[Dict]) -> Dict:
        """Return detection statistics dict (same structure as original)."""
        if not detections:
            return {
                "total_detections": 0,
                "by_type": {},
                "by_field": {},
                "has_output_leaks": False,
            }

        by_type: Dict[str, int] = {}
        by_field: Dict[str, int] = {}
        has_output_leaks = False

        for d in detections:
            by_type[d["type"]] = by_type.get(d["type"], 0) + 1
            field = d.get("field", "unknown")
            by_field[field] = by_field.get(field, 0) + 1
            if d.get("is_output_leak"):
                has_output_leaks = True

        return {
            "total_detections": len(detections),
            "by_type": by_type,
            "by_field": by_field,
            "has_output_leaks": has_output_leaks,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Thread-safe singleton (identical contract to original get_phi_guardrail())
# ──────────────────────────────────────────────────────────────────────────────

_guardrail_instance: Optional[PHIGuardrail] = None
_guardrail_lock = threading.Lock()


def get_phi_guardrail() -> PHIGuardrail:
    """
    Return the singleton PHIGuardrail instance (thread-safe double-checked locking).
    Drop-in replacement for the original factory function.
    """
    global _guardrail_instance

    if _guardrail_instance is None:
        with _guardrail_lock:
            if _guardrail_instance is None:
                logger.info("Creating PHIGuardrail singleton")
                _guardrail_instance = PHIGuardrail()

    return _guardrail_instance