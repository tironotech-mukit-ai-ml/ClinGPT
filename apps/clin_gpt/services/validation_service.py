"""
validation_service.py
─────────────────────
ClinGPT — Validation Layer

First stage of the pipeline. Every incoming wearable reading passes through
here before touching the Rule Engine, RAG, or ML model.

Responsibilities:
  1. Required-field check        — reject if mandatory fields are missing
  2. Type coercion               — cast strings to int/float where safe
  3. Physiological range check   — flag or reject biologically impossible values
  4. Temperature validation      — validate °F range, store as °F (no conversion)
  5. Boolean normalisation       — ensure ecg / stethoscope / fall_detected are 0 or 1
  6. Data quality score          — 0.0–1.0 representing % of optional fields present
  7. Return a clean, typed dict  — downstream services never see raw input

Usage:
    from apps.clin_gpt.services.validation_service import ValidationService

    result = ValidationService.validate(raw_payload)

    if not result["valid"]:
        return Response({"error": result["errors"]}, status=400)

    clean = result["data"]          # fully validated, normalised payload
    quality = result["quality_score"]
    warnings = result["warnings"]   # non-fatal issues worth logging
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Physiological range table
# (min, max, unit)  —  values outside → rejected
# ──────────────────────────────────────────────
VITAL_RANGES = {
    "hr_bpm":               (20,    300,    "BPM"),
    "oxygen_spo2_pct":      (50,    100,    "%"),
    "glucose_mgdl":         (20,    700,    "mg/dL"),
    "cholesterol_mgdl":     (50,    500,    "mg/dL"),
    "respiratory_rate_bpm": (4,     60,     "breaths/min"),
    "hemoglobin_gdl":       (3.0,   25.0,   "g/dL"),
    "temperature_f":        (86.0,  109.4,  "°F"),
    "sbp_mmhg":             (50,    300,    "mmHg"),
    "dbp_mmhg":             (20,    200,    "mmHg"),
    "step_count":           (0,     100_000,"steps"),
    "weight_kg":            (1.0,   300.0,  "kg"),
    "ecg":                  (0,     1,      "0/1"),
    "stethoscope":          (0,     1,      "0/1"),
    "fall_detected":        (0,     1,      "0/1"),
}

# Fields that MUST be present in every payload
REQUIRED_FIELDS = ["hr_bpm", "oxygen_spo2_pct"]

# All optional vital fields — used for quality score calculation
OPTIONAL_VITALS = [
    "glucose_mgdl", "cholesterol_mgdl", "respiratory_rate_bpm",
    "hemoglobin_gdl", "temperature_f",
    "sbp_mmhg", "dbp_mmhg",
    "step_count", "weight_kg",
    "ecg", "stethoscope", "fall_detected",
]


class ValidationService:

    @staticmethod
    def validate(raw: dict) -> dict:
        """
        Validate and normalise a raw incoming payload.

        Parameters
        ----------
        raw : dict
            The raw JSON payload from the wearable / device layer.

        Returns
        -------
        dict with keys:
            valid         (bool)   — False means reject with 400
            data          (dict)   — cleaned, typed, normalised vitals
            errors        (list)   — fatal issues; non-empty when valid=False
            warnings      (list)   — non-fatal issues logged but not rejected
            quality_score (float)  — 0.0–1.0, % of optional fields present
        """
        errors   = []
        warnings = []
        clean    = {}

        # ── 1. Flatten nested blood_pressure if present ──────────────────
        if "blood_pressure" in raw and isinstance(raw["blood_pressure"], dict):
            bp = raw["blood_pressure"]
            if "sbp_mmhg" in bp:
                raw["sbp_mmhg"] = bp["sbp_mmhg"]
            if "dbp_mmhg" in bp:
                raw["dbp_mmhg"] = bp["dbp_mmhg"]

        # ── 2. Required field check ───────────────────────────────────────
        for field in REQUIRED_FIELDS:
            if field not in raw or raw[field] is None:
                errors.append(f"Missing required field: '{field}'")

        if errors:
            return ValidationService._result(False, {}, errors, warnings, 0.0)

        # ── 3. Type coercion + range validation for each vital ────────────
        vital_fields = {
            "hr_bpm":               (int,   True),
            "oxygen_spo2_pct":      (float, True),
            "glucose_mgdl":         (float, False),
            "cholesterol_mgdl":     (float, False),
            "respiratory_rate_bpm": (int,   False),
            "hemoglobin_gdl":       (float, False),
            "temperature_f":        (float, False),
            "sbp_mmhg":             (int,   False),
            "dbp_mmhg":             (int,   False),
            "step_count":           (int,   False),
            "weight_kg":            (float, False),
            "ecg":                  (int,   False),
            "stethoscope":          (int,   False),
            "fall_detected":        (int,   False),
        }

        for field, (cast_type, required) in vital_fields.items():
            if field not in raw or raw[field] is None:
                if required:
                    errors.append(f"Missing required field: '{field}'")
                continue

            # Coerce type
            value, coerce_err = ValidationService._coerce(raw[field], cast_type, field)
            if coerce_err:
                errors.append(coerce_err)
                continue

            # Boolean fields — must be exactly 0 or 1
            if field in ("ecg", "stethoscope", "fall_detected"):
                if value not in (0, 1):
                    errors.append(f"'{field}' must be 0 or 1, got {value}")
                    continue
            else:
                range_err = ValidationService._check_range(field, value)
                if range_err:
                    errors.append(range_err)
                    continue

            clean[field] = value

        if errors:
            return ValidationService._result(False, {}, errors, warnings, 0.0)

        # ── 4. DBP < SBP sanity check ─────────────────────────────────────
        if "sbp_mmhg" in clean and "dbp_mmhg" in clean:
            if clean["dbp_mmhg"] >= clean["sbp_mmhg"]:
                errors.append(
                    f"DBP ({clean['dbp_mmhg']}) must be less than SBP ({clean['sbp_mmhg']})."
                )

        if errors:
            return ValidationService._result(False, {}, errors, warnings, 0.0)

        # ── 5. Rebuild blood_pressure as nested dict for downstream ────────
        if "sbp_mmhg" in clean and "dbp_mmhg" in clean:
            clean["blood_pressure"] = {
                "sbp_mmhg": clean.pop("sbp_mmhg"),
                "dbp_mmhg": clean.pop("dbp_mmhg"),
            }

        # ── 6. Pass through demographics if present ───────────────────────
        if "demographics" in raw and isinstance(raw["demographics"], dict):
            demo = raw["demographics"]
            clean_demo = {}
            if "age_group" in demo:
                clean_demo["age_group"] = str(demo["age_group"])
            if "biological_sex" in demo:
                sex = str(demo["biological_sex"]).lower()
                if sex not in ("male", "female", "other"):
                    warnings.append(
                        f"biological_sex='{sex}' is not one of male/female/other — stored as-is."
                    )
                clean_demo["biological_sex"] = sex
            if "weight_kg" in demo and demo["weight_kg"] is not None:
                w, err = ValidationService._coerce(demo["weight_kg"], float, "demographics.weight_kg")
                if not err:
                    clean_demo["weight_kg"] = w
            if clean_demo:
                clean["demographics"] = clean_demo

        # ── 7. Pass through metadata fields if present ────────────────────
        for meta_field in ("case_id", "recorded_at", "device_id", "device_type"):
            if meta_field in raw and raw[meta_field] is not None:
                clean[meta_field] = str(raw[meta_field])

        # ── 8. Data quality score ─────────────────────────────────────────
        present = sum(
            1 for f in OPTIONAL_VITALS
            if f in clean
            or (f in ("sbp_mmhg", "dbp_mmhg") and "blood_pressure" in clean)
        )
        quality_score = round(present / len(OPTIONAL_VITALS), 2)

        if quality_score < 0.3:
            warnings.append(
                f"Data quality score is low ({quality_score}) — "
                f"only {present}/{len(OPTIONAL_VITALS)} optional vital fields present. "
                f"RAG retrieval quality may be reduced."
            )

        logger.info(
            "Validation passed | quality=%.2f | warnings=%d",
            quality_score, len(warnings)
        )

        return ValidationService._result(True, clean, errors, warnings, quality_score)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _coerce(value: Any, cast_type: type, field: str):
        """Try to cast value to cast_type. Returns (value, error_or_None)."""
        try:
            return cast_type(value), None
        except (TypeError, ValueError):
            return None, (
                f"'{field}' expects {cast_type.__name__}, "
                f"got {type(value).__name__} value '{value}'."
            )

    @staticmethod
    def _check_range(field: str, value: float):
        """Return an error string if value is outside the physiological range."""
        if field not in VITAL_RANGES:
            return None
        lo, hi, unit = VITAL_RANGES[field]
        if not (lo <= value <= hi):
            return (
                f"'{field}' value {value} {unit} is outside the "
                f"physiological range [{lo}–{hi} {unit}]."
            )
        return None

    @staticmethod
    def _result(valid, data, errors, warnings, quality_score):
        return {
            "valid":         valid,
            "data":          data,
            "errors":        errors,
            "warnings":      warnings,
            "quality_score": quality_score,
        }