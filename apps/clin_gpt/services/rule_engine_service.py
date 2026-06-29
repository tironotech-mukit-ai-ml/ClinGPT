"""
rule_engine_service.py
───────────────────────
ClinGPT — Rule Engine

Second stage of the pipeline. Takes the cleaned, validated output of
ValidationService and evaluates it against clinical threshold bands to
produce a list of alerts. The Rule Engine never rejects data — by the
time a payload reaches here it has already passed physiological-range
checks. Its job is purely to flag what's clinically concerning.

Scope: critical alerting is currently limited to the four parameters
confirmed for this round — heart rate, SpO2, respiratory rate, and
blood pressure (SBP/DBP). Glucose, temperature, cholesterol, hemoglobin,
and the binary flags (fall_detected / ecg / stethoscope) are NOT
evaluated here; if present in the input payload they are simply ignored
(passed through, never alerted on).

Responsibilities:
  1. Two-tier severity evaluation — critical / warning bands per vital
     (HR, SpO2, respiratory rate, SBP, DBP)
  2. Threshold source resolution  — doctor-set override, else population default
  3. Return ALL triggered alerts  — no single "winner" alert is selected
  4. Summary fields               — alert_count, highest_severity

Threshold source hierarchy (currently implemented tiers):
  1. Doctor-set   — full per-parameter table, passed in via doctor_thresholds
  2. Default      — population clinical thresholds (this module's constants)

  A third tier — auto-calculated from a patient's own historical readings —
  is planned but not yet implemented. When added, it will sit between
  doctor-set and default in the resolution order. See PARAM_THRESHOLDS for
  where that tier will plug in.

Explicitly excluded from alerting (passed through untouched):
  - weight_kg
  - step_count
  - glucose_mgdl, temperature_f, cholesterol_mgdl, hemoglobin_gdl
  - fall_detected, ecg, stethoscope

Usage:
    from apps.clin_gpt.services.rule_engine_service import RuleEngineService

    result = RuleEngineService.evaluate(validated_data)

    # With a doctor-set override for this patient (full table per parameter;
    # only parameters present in the dict are overridden — others fall back
    # to the population default):
    doctor_thresholds = {
        "oxygen_spo2_pct": {
            "critical_low": 85, "warning_low": 88,
            "warning_high": None, "critical_high": None,
        },
    }
    result = RuleEngineService.evaluate(validated_data, doctor_thresholds=doctor_thresholds)

    alerts           = result["alerts"]            # list of alert dicts
    alert_count      = result["alert_count"]
    highest_severity = result["highest_severity"]   # "critical" | "warning" | "none"
"""

import logging

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Default (population) two-tier thresholds.
# Keys: critical_low, warning_low, warning_high, critical_high, unit
# None on either end means "no alert in that direction".
#
# These are the fallback values used whenever no doctor-set override exists
# for a given parameter. SpO2, respiratory, SBP, and DBP reflect the
# AHA/ACC/ADA/NEWS2-aligned refinements (June 2026); HR keeps its prior
# values pending separate sign-off on the sustained-duration logic.
# ──────────────────────────────────────────────
PARAM_THRESHOLDS = {
    "hr_bpm": {
        "critical_low": 40, "warning_low": 50,
        "warning_high": 100, "critical_high": 150,
        "unit": "BPM",
    },
    "oxygen_spo2_pct": {
        "critical_low": 88, "warning_low": 92,
        "warning_high": None, "critical_high": None,  # no high-side alert — SpO2 cannot exceed 100%
        "unit": "%",
    },
    "respiratory_rate_bpm": {
        "critical_low": 8, "warning_low": 11,
        "warning_high": 21, "critical_high": 30,
        "unit": "breaths/min",
        # NOTE: clinical guidance distinguishes ">24 sustained" (critical) from
        # "25-29 instantaneous" (warning) and "\u226530 any single reading" (critical
        # immediate). Sustained-duration tracking requires reading history that
        # isn't available to this stateless evaluator yet, so this is currently
        # implemented as instantaneous-only: warning 21-29, critical \u226530.
    },
}

# sbp_mmhg / dbp_mmhg are nested under data["blood_pressure"], evaluated separately
BP_THRESHOLDS = {
    "sbp_mmhg": {
        "critical_low": 90, "warning_low": 100,
        "warning_high": 130, "critical_high": 180,
        "unit": "mmHg",
        # NOTE: clinical guidance qualifies critical-low as "<90 + symptoms".
        # No symptom field exists in the current schema, so this implements
        # the unqualified <90 condition alone.
    },
    "dbp_mmhg": {
        "critical_low": 60, "warning_low": 70,
        "warning_high": 80, "critical_high": 120,
        "unit": "mmHg",
    },
}

# Fields explicitly excluded from rule-engine alerting.
# weight_kg / step_count were never in scope. glucose_mgdl, temperature_f,
# cholesterol_mgdl, hemoglobin_gdl, and the binary flags (fall_detected,
# ecg, stethoscope) were dropped from the critical-alert system per scope
# cut — critical alerting is now HR / SpO2 / respiratory / BP only.
EXCLUDED_FIELDS = [
    "weight_kg", "step_count",
    "glucose_mgdl", "temperature_f", "cholesterol_mgdl", "hemoglobin_gdl",
    "fall_detected", "ecg", "stethoscope",
]

# Parameters currently eligible for doctor-set threshold overrides.
# (Scope: the 4 critical-alert parameters confirmed for this round.
# HR is included since it shares the same two-tier shape; expand this set
# as more parameters get doctor-override support.)
OVERRIDABLE_PARAMS = {"hr_bpm", "oxygen_spo2_pct", "respiratory_rate_bpm", "sbp_mmhg", "dbp_mmhg"}

SEVERITY_RANK = {"none": 0, "warning": 1, "critical": 2}


class RuleEngineService:

    @staticmethod
    def evaluate(data: dict, doctor_thresholds: dict = None) -> dict:
        """
        Evaluate validated vital data against clinical threshold bands.

        Parameters
        ----------
        data : dict
            The cleaned, validated payload — i.e. result["data"] from
            ValidationService.validate(). blood_pressure is nested as
            {"sbp_mmhg": ..., "dbp_mmhg": ...}. Only hr_bpm, oxygen_spo2_pct,
            respiratory_rate_bpm, and blood_pressure are evaluated; any other
            fields present (glucose, temperature, cholesterol, hemoglobin,
            demographics, binary flags, etc.) are ignored by this module.

        doctor_thresholds : dict, optional
            Per-patient doctor-set threshold overrides. Keyed by parameter
            name (e.g. "hr_bpm", "oxygen_spo2_pct", "sbp_mmhg"). Each value
            is a full threshold dict: {critical_low, warning_low,
            warning_high, critical_high}. Only parameters present in this
            dict are overridden — any parameter not included falls back to
            the population default in PARAM_THRESHOLDS / BP_THRESHOLDS.
            Doctor input is trusted as-is and is not validated here.

        Returns
        -------
        dict with keys:
            alerts           (list)  — every triggered alert, no winner selected
            alert_count      (int)
            highest_severity (str)   — "critical" | "warning" | "none"
        """
        doctor_thresholds = doctor_thresholds or {}
        alerts = []

        # ── 1. Two-tier vitals (HR, SpO2, respiratory) ──────────────────────
        for field, defaults in PARAM_THRESHOLDS.items():
            if field not in data or data[field] is None:
                continue
            bands = RuleEngineService._resolve_thresholds(field, defaults, doctor_thresholds)
            alert = RuleEngineService._evaluate_two_tier(field, data[field], bands)
            if alert:
                alerts.append(alert)

        # ── 2. Blood pressure (nested) ──────────────────────────────────────
        bp = data.get("blood_pressure", {})
        for field, defaults in BP_THRESHOLDS.items():
            if field not in bp or bp[field] is None:
                continue
            bands = RuleEngineService._resolve_thresholds(field, defaults, doctor_thresholds)
            alert = RuleEngineService._evaluate_two_tier(field, bp[field], bands)
            if alert:
                alerts.append(alert)

        # ── 3. Summary fields ───────────────────────────────────────────────
        highest_severity = "none"
        for a in alerts:
            if SEVERITY_RANK[a["severity"]] > SEVERITY_RANK[highest_severity]:
                highest_severity = a["severity"]

        logger.info(
            "Rule engine evaluated | alert_count=%d | highest_severity=%s | doctor_overrides=%s",
            len(alerts), highest_severity, sorted(doctor_thresholds.keys())
        )

        return {
            "alerts": alerts,
            "alert_count": len(alerts),
            "highest_severity": highest_severity,
        }

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_thresholds(field, defaults, doctor_thresholds):
        """
        Resolve which threshold table to use for this parameter and patient.

        Resolution order:
          1. Doctor-set override — used in full if present for this field
             (and the field is in OVERRIDABLE_PARAMS).
          2. Population default — this module's PARAM_THRESHOLDS / BP_THRESHOLDS.

        A future "auto-calculated from patient history" tier will be
        inserted between these two once that data is available; this
        function is the single place that ordering will need to change.

        Doctor input is trusted as-is (not validated for internal
        consistency) per current scope.
        """
        if field in OVERRIDABLE_PARAMS and field in doctor_thresholds:
            override = doctor_thresholds[field]
            return {
                "critical_low": override.get("critical_low"),
                "warning_low": override.get("warning_low"),
                "warning_high": override.get("warning_high"),
                "critical_high": override.get("critical_high"),
                "unit": defaults["unit"],
                "basis": "doctor_set",
            }
        bands = dict(defaults)
        bands["basis"] = "default"
        return bands

    @staticmethod
    def _evaluate_two_tier(field, value, bands):
        """Evaluate a vital against a resolved threshold dict (low/high bands)."""
        crit_low = bands["critical_low"]
        warn_low = bands["warning_low"]
        warn_high = bands["warning_high"]
        crit_high = bands["critical_high"]
        unit = bands["unit"]
        basis = bands.get("basis", "default")

        alert = None
        if crit_low is not None and value < crit_low:
            alert = RuleEngineService._alert(field, value, "critical",
                f"'{field}' value {value} {unit} is critically low (<{crit_low} {unit}).")
        elif warn_low is not None and value < warn_low:
            alert = RuleEngineService._alert(field, value, "warning",
                f"'{field}' value {value} {unit} is low (<{warn_low} {unit}).")
        elif crit_high is not None and value >= crit_high:
            alert = RuleEngineService._alert(field, value, "critical",
                f"'{field}' value {value} {unit} is critically high (\u2265{crit_high} {unit}).")
        elif warn_high is not None and value >= warn_high:
            alert = RuleEngineService._alert(field, value, "warning",
                f"'{field}' value {value} {unit} is elevated (\u2265{warn_high} {unit}).")

        if alert is not None:
            alert["threshold_basis"] = basis
        return alert

    @staticmethod
    def _alert(parameter, value, severity, message):
        return {
            "parameter": parameter,
            "value": value,
            "severity": severity,
            "message": message,
        }
