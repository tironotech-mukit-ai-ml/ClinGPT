"""
rule_engine_service.py
───────────────────────
ClinGPT — Rule Engine

Second stage of the pipeline. Takes the cleaned, validated output of
ValidationService and evaluates it against clinical threshold bands to
produce a list of alerts.

SCOPE: critical alerting covers exactly four parameters —
hr_bpm, oxygen_spo2_pct, respiratory_rate_bpm, and blood pressure
(sbp_mmhg / dbp_mmhg). All other fields are ignored by this engine.

Threshold source hierarchy (resolution order):
  1. Doctor-set      — full per-parameter table via doctor_thresholds arg
  2. Historical SD   — calculated from patient's own clean readings
                       (abnormal readings excluded, 30-day preferred,
                        15-day minimum; activates only if minimum met)
  3. Population default — fixed clinical thresholds, always available

Alert severity and notification routing (consistent across all tiers):
  - warning  → notify: ["patient"]
  - critical → notify: ["patient", "guardians", "doctor"]

The Rule Engine does NOT send notifications — it only declares who
should be notified. A separate notification service acts on that.

Usage:
    from apps.clin_gpt.services.rule_engine_service import RuleEngineService

    result = RuleEngineService.evaluate(
        validated_data,
        doctor_thresholds=None,   # optional dict, full table per parameter
        patient_history=None,     # optional dict, list of clean readings per param
    )

    # doctor_thresholds shape:
    # {
    #     "oxygen_spo2_pct": {
    #         "critical_low": 85, "warning_low": 88,
    #         "warning_high": None, "critical_high": None,
    #     }
    # }

    # patient_history shape (abnormal readings already excluded by DB layer):
    # {
    #     "hr_bpm":               [72, 75, 78, 71, 74, ...],
    #     "oxygen_spo2_pct":      [97, 98, 96, 97, ...],
    #     "respiratory_rate_bpm": [14, 15, 16, 15, ...],
    #     "sbp_mmhg":             [118, 122, 115, 120, ...],
    #     "dbp_mmhg":             [76, 78, 74, 77, ...],
    # }

    alerts           = result["alerts"]
    alert_count      = result["alert_count"]
    highest_severity = result["highest_severity"]
"""

import logging
import math
import statistics

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Population default two-tier thresholds (Tier 3 — always-on safety net).
# AHA/ACC/ADA/NEWS2-aligned, tuned for RPM alert fatigue (June 2026).
# Keys: critical_low, warning_low, warning_high, critical_high, unit
# None on either end = no alert in that direction.
# ─────────────────────────────────────────────────────────────────────────────
PARAM_THRESHOLDS = {
    "hr_bpm": {
        "critical_low": 40,  "warning_low": 50,
        "warning_high": 100, "critical_high": 150,
        "unit": "BPM",
    },
    "oxygen_spo2_pct": {
        "critical_low": 88,  "warning_low": 92,
        "warning_high": None, "critical_high": None,
        "unit": "%",
        # SpO2 cannot physically exceed 100% — no high-side alert defined.
    },
    "respiratory_rate_bpm": {
        "critical_low": 8,  "warning_low": 11,
        "warning_high": 21, "critical_high": 30,
        "unit": "breaths/min",
        # NOTE: ">24 sustained" escalation requires reading history.
        # Implemented as instantaneous-only: warning 21-29, critical ≥30.
    },
}

# sbp_mmhg / dbp_mmhg nested under data["blood_pressure"], evaluated separately
BP_THRESHOLDS = {
    "sbp_mmhg": {
        "critical_low": 90,  "warning_low": 100,
        "warning_high": 130, "critical_high": 180,
        "unit": "mmHg",
        # NOTE: clinical guidance says "<90 + symptoms" for critical-low.
        # No symptom field in schema — implemented as unqualified <90.
    },
    "dbp_mmhg": {
        "critical_low": 60, "warning_low": 70,
        "warning_high": 80, "critical_high": 120,
        "unit": "mmHg",
    },
}

# All parameters eligible for doctor-set and historical-SD overrides.
OVERRIDABLE_PARAMS = {
    "hr_bpm", "oxygen_spo2_pct", "respiratory_rate_bpm", "sbp_mmhg", "dbp_mmhg"
}

# Notification routing by severity — consistent across all three tiers.
NOTIFY_BY_SEVERITY = {
    "warning":  ["patient"],
    "critical": ["patient", "guardians", "doctor"],
}

# Historical SD tier configuration.
HISTORY_WINDOW_PREFERRED_DAYS = 30
HISTORY_WINDOW_MINIMUM_DAYS   = 15
HISTORY_MIN_READINGS           = 10   # absolute minimum readings regardless of window

SEVERITY_RANK = {"none": 0, "warning": 1, "critical": 2}


class RuleEngineService:

    @staticmethod
    def evaluate(
        data: dict,
        doctor_thresholds: dict = None,
        patient_history: dict = None,
    ) -> dict:
        """
        Evaluate validated vital data against clinical threshold bands.

        Only four parameters are evaluated: hr_bpm, oxygen_spo2_pct,
        respiratory_rate_bpm, and blood_pressure (sbp_mmhg / dbp_mmhg).
        All other fields in `data` are ignored by this engine.

        Parameters
        ----------
        data : dict
            Cleaned, validated payload from ValidationService.validate().
            blood_pressure nested as {"sbp_mmhg": ..., "dbp_mmhg": ...}.

        doctor_thresholds : dict, optional
            Per-patient doctor-set threshold overrides. Full table per
            parameter. Only present parameters are overridden; others fall
            through to the next tier. Doctor input is trusted as-is.

        patient_history : dict, optional
            Per-parameter list of clean historical readings (abnormal
            readings already excluded by the DB layer before being passed
            here). Used to compute mean and SD for the historical tier.
            Shape: {"hr_bpm": [72, 75, ...], "sbp_mmhg": [118, 122, ...]}
            At least HISTORY_MIN_READINGS values required per parameter
            for that parameter's SD tier to activate.

        Returns
        -------
        dict with keys:
            alerts           (list)  — every triggered alert, no winner selected
            alert_count      (int)
            highest_severity (str)   — "critical" | "warning" | "none"
        """
        doctor_thresholds = doctor_thresholds or {}
        patient_history   = patient_history   or {}
        alerts = []

        # ── 1. Two-tier vitals (HR, SpO2, respiratory) ──────────────────────
        for field, defaults in PARAM_THRESHOLDS.items():
            if field not in data or data[field] is None:
                continue
            tier, bands = RuleEngineService._resolve_thresholds(
                field, defaults, doctor_thresholds, patient_history
            )
            alert = RuleEngineService._evaluate_bands(field, data[field], bands, tier)
            if alert:
                alerts.append(alert)

        # ── 2. Blood pressure (nested) ──────────────────────────────────────
        bp = data.get("blood_pressure", {})
        for field, defaults in BP_THRESHOLDS.items():
            if field not in bp or bp[field] is None:
                continue
            tier, bands = RuleEngineService._resolve_thresholds(
                field, defaults, doctor_thresholds, patient_history
            )
            alert = RuleEngineService._evaluate_bands(field, bp[field], bands, tier)
            if alert:
                alerts.append(alert)

        # ── 3. Summary fields ────────────────────────────────────────────────
        highest_severity = "none"
        for a in alerts:
            if SEVERITY_RANK[a["severity"]] > SEVERITY_RANK[highest_severity]:
                highest_severity = a["severity"]

        logger.info(
            "Rule engine evaluated | alert_count=%d | highest_severity=%s"
            " | doctor_overrides=%s | history_params=%s",
            len(alerts), highest_severity,
            sorted(doctor_thresholds.keys()),
            sorted(patient_history.keys()),
        )

        return {
            "alerts":           alerts,
            "alert_count":      len(alerts),
            "highest_severity": highest_severity,
        }

    # ── Threshold resolution ──────────────────────────────────────────────────

    @staticmethod
    def _resolve_thresholds(field, defaults, doctor_thresholds, patient_history):
        """
        Resolve which threshold source to use for this parameter.

        Resolution order:
          1. Doctor-set      — present in doctor_thresholds for this field
          2. Historical SD   — enough clean readings exist in patient_history
          3. Population default — this module's PARAM_THRESHOLDS / BP_THRESHOLDS

        Returns (tier_name, bands_dict).
        """
        # Tier 1 — Doctor-set
        if field in OVERRIDABLE_PARAMS and field in doctor_thresholds:
            override = doctor_thresholds[field]
            return "doctor_set", {
                "critical_low":  override.get("critical_low"),
                "warning_low":   override.get("warning_low"),
                "warning_high":  override.get("warning_high"),
                "critical_high": override.get("critical_high"),
                "unit":          defaults["unit"],
            }

        # Tier 2 — Historical SD
        if field in OVERRIDABLE_PARAMS and field in patient_history:
            sd_bands = RuleEngineService._compute_sd_bands(
                patient_history[field], defaults["unit"]
            )
            if sd_bands is not None:
                return "historical_sd", sd_bands

        # Tier 3 — Population default
        return "default", dict(defaults)

    @staticmethod
    def _compute_sd_bands(readings, unit):
        """
        Compute warning (2SD) and critical (3SD) bands from clean readings.

        Returns a bands dict if enough readings exist, else None (which
        causes the caller to fall through to the population default).

        readings : list of numeric values (abnormal already excluded)
        """
        if len(readings) < HISTORY_MIN_READINGS:
            return None

        try:
            mean = statistics.mean(readings)
            sd   = statistics.stdev(readings)   # sample SD (N-1 denominator)
        except statistics.StatisticsError:
            return None

        # Guard: if SD is zero (all readings identical), fall through to default
        # since 2σ/3σ bands would both equal the mean — not a useful threshold.
        if sd == 0:
            return None

        return {
            "critical_low":  round(mean - 3 * sd, 2),
            "warning_low":   round(mean - 2 * sd, 2),
            "warning_high":  round(mean + 2 * sd, 2),
            "critical_high": round(mean + 3 * sd, 2),
            "unit":          unit,
            # Store mean/sd on bands for transparent alert messages
            "_mean": round(mean, 2),
            "_sd":   round(sd, 2),
        }

    # ── Alert evaluation ──────────────────────────────────────────────────────

    @staticmethod
    def _evaluate_bands(field, value, bands, tier):
        """
        Evaluate a value against a resolved threshold dict.
        Attaches tier, threshold_basis, and notify routing to each alert.
        """
        crit_low  = bands.get("critical_low")
        warn_low  = bands.get("warning_low")
        warn_high = bands.get("warning_high")
        crit_high = bands.get("critical_high")
        unit      = bands.get("unit", "")

        severity = None
        message  = None

        if crit_low is not None and value < crit_low:
            severity = "critical"
            if tier == "historical_sd":
                message = (
                    f"'{field}' value {value} {unit} is critically low "
                    f"(>{3}\u03c3 below personal baseline "
                    f"\u03bc={bands['_mean']} {unit}, \u03c3={bands['_sd']})."
                )
            else:
                message = (
                    f"'{field}' value {value} {unit} is critically low "
                    f"(<{crit_low} {unit})."
                )

        elif warn_low is not None and value < warn_low:
            severity = "warning"
            if tier == "historical_sd":
                message = (
                    f"'{field}' value {value} {unit} is low "
                    f"(>{2}\u03c3 below personal baseline "
                    f"\u03bc={bands['_mean']} {unit}, \u03c3={bands['_sd']})."
                )
            else:
                message = (
                    f"'{field}' value {value} {unit} is low "
                    f"(<{warn_low} {unit})."
                )

        elif crit_high is not None and value >= crit_high:
            severity = "critical"
            if tier == "historical_sd":
                message = (
                    f"'{field}' value {value} {unit} is critically high "
                    f"(>{3}\u03c3 above personal baseline "
                    f"\u03bc={bands['_mean']} {unit}, \u03c3={bands['_sd']})."
                )
            else:
                message = (
                    f"'{field}' value {value} {unit} is critically high "
                    f"(\u2265{crit_high} {unit})."
                )

        elif warn_high is not None and value >= warn_high:
            severity = "warning"
            if tier == "historical_sd":
                message = (
                    f"'{field}' value {value} {unit} is elevated "
                    f"(>{2}\u03c3 above personal baseline "
                    f"\u03bc={bands['_mean']} {unit}, \u03c3={bands['_sd']})."
                )
            else:
                message = (
                    f"'{field}' value {value} {unit} is elevated "
                    f"(\u2265{warn_high} {unit})."
                )

        if severity is None:
            return None

        alert = {
            "parameter":       field,
            "value":           value,
            "severity":        severity,
            "message":         message,
            "threshold_basis": tier,
            "notify":          NOTIFY_BY_SEVERITY[severity],
        }

        # Attach SD context on historical alerts for transparency/logging
        if tier == "historical_sd":
            alert["baseline_mean"] = bands["_mean"]
            alert["baseline_sd"]   = bands["_sd"]

        return alert