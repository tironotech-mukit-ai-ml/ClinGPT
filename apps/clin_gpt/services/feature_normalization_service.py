"""
feature_normalization_service.py
─────────────────────────────────
ClinGPT — Feature Normalization

Third stage of the pipeline. Takes the cleaned, validated output of
ValidationService (result["data"]) and converts it into a numeric
feature vector for FAISS similarity retrieval and the XGBoost risk model.

Position in the pipeline:
    ValidationService  →  RuleEngineService  →  FeatureNormalizationService
                                                          ↓
                                                 FAISS / KNN retrieval
                                                 XGBoost risk model

Why this stage exists:
    FAISS and XGBoost operate on fixed-length numeric vectors. Raw vitals
    have different units, ranges, and types (int, float, binary, categorical)
    that are not directly comparable. This stage converts everything to a
    consistent 0.0–1.0 scale so distance calculations and feature importances
    are meaningful and not unit-dominated.

Scaling methods by field type:
    Continuous vitals — min-max normalization using the clinical physiological
        bounds already defined in ValidationService.VITAL_RANGES. Preferred
        over z-score because:
        (a) bounds are clinically known and don't require a large dataset,
        (b) FAISS L2 distance works well on [0,1] bounded vectors,
        (c) results are interpretable (0 = physiological minimum, 1 = maximum).

    Binary fields (ecg, stethoscope, fall_detected) — already 0/1, passed
        through directly as 0.0 or 1.0. No scaling needed.

    biological_sex — ordinal: male → 1.0, female → 0.0, other → 0.5.

    age_group — ordinal mapping to [0.0, 1.0] by life stage. Strings must
        match AGE_GROUP_ENCODING keys exactly (case-insensitive). Unknown
        strings receive MISSING_SENTINEL (0.5).

Missing fields:
    Optional fields absent from the payload receive MISSING_SENTINEL = 0.5
    (midpoint of [0,1]), representing "unknown" rather than 0 (falsely
    implying a very low reading) or 1 (very high reading).

Change from original version:
    demographics_weight_kg has been removed from FEATURE_ORDER.
    demographics.weight_kg and the top-level weight_kg measure the same
    physical value — including both as separate features would give
    XGBoost a duplicate signal and waste a FAISS dimension. The top-level
    weight_kg (device-measured) is retained as the single weight feature.
    Vector length is now 16 (was 17).

Output:
    {
        "vector":         [float, ...],   # fixed-order list, length == 16
        "features":       {str: float},   # same values keyed by field name
        "missing_fields": [str],          # fields that received sentinel 0.5
    }

    The "vector" list order is defined by FEATURE_ORDER — this order must
    remain stable across all versions so the FAISS index and XGBoost model
    trained on it stay valid. Never reorder FEATURE_ORDER without retraining.

Usage:
    from apps.clin_gpt.services.feature_normalization_service import (
        FeatureNormalizationService,
    )

    validated = ValidationService.validate(raw_payload)
    if not validated["valid"]:
        ...

    norm = FeatureNormalizationService.normalize(validated["data"])

    vector         = norm["vector"]          # numpy-ready list of 16 floats
    features       = norm["features"]        # dict for logging / inspection
    missing_fields = norm["missing_fields"]  # fields that got sentinel 0.5
"""

import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Physiological min/max bounds for min-max normalization.
# Must stay in sync with ValidationService.VITAL_RANGES.
# Stored explicitly here so this service has no import-time dependency on
# ValidationService (avoids circular imports; keeps bounds visible in one
# place for the ML engineer configuring the feature pipeline).
# ─────────────────────────────────────────────────────────────────────────────
VITAL_BOUNDS = {
    "hr_bpm":               (20,    300),
    "oxygen_spo2_pct":      (50,    100),
    "glucose_mgdl":         (20,    700),
    "cholesterol_mgdl":     (50,    500),
    "respiratory_rate_bpm": (4,     60),
    "hemoglobin_gdl":       (3.0,   25.0),
    "temperature_f":        (86.0,  109.4),
    "sbp_mmhg":             (50,    300),
    "dbp_mmhg":             (20,    200),
    "step_count":           (0,     100_000),
    "weight_kg":            (1.0,   300.0),
}

# Binary fields: already 0/1 — no scaling required.
BINARY_FIELDS = {"ecg", "stethoscope", "fall_detected"}

# biological_sex encoding.
SEX_ENCODING = {
    "male":   1.0,
    "female": 0.0,
    "other":  0.5,
}

# age_group ordinal encoding — evenly spaced across [0.0, 1.0].
# Strings are matched case-insensitively against these keys.
AGE_GROUP_ENCODING = {
    "0-15":  0.0,
    "18-30": 0.2,
    "31-45": 0.4,
    "46-60": 0.6,
    "61-75": 0.8,
    "75+":   1.0,
}

# Sentinel value for missing/unknown fields.
# 0.5 = midpoint of [0,1] — avoids falsely implying a low or high reading.
MISSING_SENTINEL = 0.5

# ─────────────────────────────────────────────────────────────────────────────
# Fixed feature order for the output vector — 16 features.
# CRITICAL: this order defines the column layout of the FAISS index and the
# XGBoost feature matrix. Never change this once training has begun.
# To add a new feature: append to the end and retrain both models.
# ─────────────────────────────────────────────────────────────────────────────
FEATURE_ORDER = [
    # ── Continuous vitals ──────────────────────────────
    "hr_bpm",
    "oxygen_spo2_pct",
    "respiratory_rate_bpm",
    "sbp_mmhg",
    "dbp_mmhg",
    "glucose_mgdl",
    "temperature_f",
    "cholesterol_mgdl",
    "hemoglobin_gdl",
    "weight_kg",
    "step_count",
    # ── Binary flags ───────────────────────────────────
    "ecg",
    "stethoscope",
    "fall_detected",
    # ── Demographics ───────────────────────────────────
    "biological_sex",
    "age_group",
    # demographics.weight_kg intentionally excluded — same physical value
    # as top-level weight_kg (device-measured). Including both would give
    # XGBoost a duplicate signal and waste a FAISS dimension.
]

# Sanity check: confirm FEATURE_ORDER has no duplicates at import time.
assert len(FEATURE_ORDER) == len(set(FEATURE_ORDER)), \
    "FEATURE_ORDER contains duplicate entries — each feature must appear once."


class FeatureNormalizationService:

    @staticmethod
    def normalize(data: dict) -> dict:
        """
        Normalize a validated vitals payload into a fixed-length feature vector.

        Parameters
        ----------
        data : dict
            The cleaned, validated payload — i.e. result["data"] from
            ValidationService.validate(). Expected shape:
            {
                "hr_bpm": ...,
                "oxygen_spo2_pct": ...,
                "blood_pressure": {"sbp_mmhg": ..., "dbp_mmhg": ...},
                "glucose_mgdl": ...,           # optional
                "temperature_f": ...,          # optional
                "cholesterol_mgdl": ...,       # optional
                "hemoglobin_gdl": ...,         # optional
                "weight_kg": ...,              # optional
                "step_count": ...,             # optional
                "ecg": ...,                    # optional, 0 or 1
                "stethoscope": ...,            # optional, 0 or 1
                "fall_detected": ...,          # optional, 0 or 1
                "demographics": {              # optional block
                    "biological_sex": "male" | "female" | "other",
                    "age_group": "0-15" | "16-30" | "31-45" | "46-60" | "61-75" | "76+",
                    "weight_kg": ...,          # informational only — not used in vector
                },
            }

        Returns
        -------
        dict with keys:
            vector         (list of float, len=16) — normalized values in FEATURE_ORDER
            features       (dict str→float)        — same values keyed by feature name
            missing_fields (list of str)           — features that received MISSING_SENTINEL
        """
        features       = {}
        missing_fields = []

        # Unpack nested blocks once
        bp   = data.get("blood_pressure") or {}
        demo = data.get("demographics")   or {}

        # ── Continuous vitals (top-level) ────────────────────────────────────
        for field in (
            "hr_bpm", "oxygen_spo2_pct", "glucose_mgdl", "cholesterol_mgdl",
            "respiratory_rate_bpm", "hemoglobin_gdl", "temperature_f",
            "weight_kg", "step_count",
        ):
            value = data.get(field)
            features[field] = FeatureNormalizationService._minmax(
                field, value, missing_fields
            )

        # ── BP sub-fields (nested under blood_pressure) ──────────────────────
        for bp_field in ("sbp_mmhg", "dbp_mmhg"):
            value = bp.get(bp_field)
            features[bp_field] = FeatureNormalizationService._minmax(
                bp_field, value, missing_fields
            )

        # ── Binary flags ─────────────────────────────────────────────────────
        for field in ("ecg", "stethoscope", "fall_detected"):
            value = data.get(field)
            if value is None:
                features[field] = MISSING_SENTINEL
                missing_fields.append(field)
            else:
                features[field] = float(value)   # already 0.0 or 1.0

        # ── Demographics ─────────────────────────────────────────────────────
        # biological_sex
        sex = demo.get("biological_sex")
        if sex is None:
            features["biological_sex"] = MISSING_SENTINEL
            missing_fields.append("biological_sex")
        else:
            features["biological_sex"] = SEX_ENCODING.get(
                sex.lower(), MISSING_SENTINEL
            )

        # age_group (ordinal)
        age_group = demo.get("age_group")
        if age_group is None:
            features["age_group"] = MISSING_SENTINEL
            missing_fields.append("age_group")
        else:
            encoded = AGE_GROUP_ENCODING.get(age_group.strip())
            if encoded is None:
                logger.warning(
                    "Unknown age_group '%s' — assigned sentinel %.1f",
                    age_group, MISSING_SENTINEL,
                )
                features["age_group"] = MISSING_SENTINEL
                missing_fields.append("age_group")
            else:
                features["age_group"] = encoded

        # demographics.weight_kg — read for logging/inspection but not
        # added to features dict or vector (duplicate of top-level weight_kg).

        # ── Build fixed-order vector ─────────────────────────────────────────
        vector = [features[f] for f in FEATURE_ORDER]

        logger.info(
            "Feature normalization complete | vector_len=%d | missing=%d: %s",
            len(vector), len(missing_fields), missing_fields,
        )

        return {
            "vector":         vector,
            "features":       features,
            "missing_fields": missing_fields,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _minmax(field: str, value, missing_fields: list) -> float:
        """
        Min-max normalize `value` for `field` using VITAL_BOUNDS.

        Returns MISSING_SENTINEL and appends field to missing_fields if:
          - value is None, or
          - field has no entry in VITAL_BOUNDS.

        Output is clamped to [lo, hi] before scaling so readings that barely
        passed ValidationService's range check never produce values outside
        [0.0, 1.0].
        """
        if value is None:
            missing_fields.append(field)
            return MISSING_SENTINEL

        if field not in VITAL_BOUNDS:
            logger.warning(
                "No bounds defined for field '%s' — assigned sentinel.", field
            )
            missing_fields.append(field)
            return MISSING_SENTINEL

        lo, hi = VITAL_BOUNDS[field]
        clamped = max(lo, min(hi, value))
        return round((clamped - lo) / (hi - lo), 6)