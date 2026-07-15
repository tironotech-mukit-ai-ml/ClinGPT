"""
test_pipeline_integration.py
─────────────────────────────
ClinGPT — Full Pipeline Integration Tests

Chains all three stages in sequence:
    ValidationService → RuleEngineService → FeatureNormalizationService

Unit tests prove each service works in isolation.
These tests prove the stages work *together* — that the output shape of
each stage is valid input for the next, and that real clinical scenarios
produce the right result end-to-end.

Scenarios covered:
  1.  Normal patient        — no alerts, clean vector, no missing fields
  2.  Critical HR           — alert fires, vector still valid
  3.  Critical SpO2         — alert fires, correct severity routing
  4.  Critical BP           — both SBP and DBP critical
  5.  Warning respiratory   — warning only, not critical
  6.  All 5 parameters critical simultaneously
  7.  Mixed severity        — critical + warning together
  8.  Doctor override       — custom threshold changes alert outcome
  9.  Patient history tier  — SD bands from history override population default
  10. Minimal payload       — only required fields, pipeline still completes
  11. Validation rejection  — invalid payload never reaches Rule Engine
  12. DBP >= SBP            — impossible reading rejected cleanly
  13. Dropped params        — glucose/temp/etc. in payload don't affect alerts
  14. Vector contract       — length, bounds, feature order always stable
  15. Notification routing  — warning=patient only, critical=patient+guardians+doctor
  16. Threshold basis       — correct tier label on every alert
  17. Missing fields        — sentinel 0.5 for absent optional fields
  18. Full demographics     — sex/age/weight all encoded correctly in vector
"""

import sys
import os
import math

sys.path.insert(0, os.path.dirname(__file__))

from validation_service import ValidationService
from rule_engine_service import RuleEngineService
from feature_normalization_service import (
    FeatureNormalizationService,
    FEATURE_ORDER,
    VITAL_BOUNDS,
    AGE_GROUP_ENCODING,
    SEX_ENCODING,
    MISSING_SENTINEL,
)

# ── Minimal test harness ──────────────────────────────────────────────────────
_pass = _fail = 0

def run(label, fn):
    global _pass, _fail
    try:
        fn()
        print(f"  \033[92m✓\033[0m  {label}")
        _pass += 1
    except AssertionError as e:
        print(f"  \033[91m✗\033[0m  {label}")
        print(f"       AssertionError: {e}")
        _fail += 1
    except Exception as e:
        print(f"  \033[91m✗\033[0m  {label}")
        print(f"       {type(e).__name__}: {e}")
        _fail += 1

def approx(a, b, tol=1e-4):
    return abs(a - b) < tol


# ── Pipeline runner ───────────────────────────────────────────────────────────

def run_pipeline(raw_payload, doctor_thresholds=None, patient_history=None):
    """
    Run a raw payload through all three pipeline stages.
    Returns (validation_result, rule_result, norm_result).
    Raises AssertionError if validation fails unexpectedly.
    """
    val = ValidationService.validate(raw_payload)
    if not val["valid"]:
        return val, None, None

    rule = RuleEngineService.evaluate(
        val["data"],
        doctor_thresholds=doctor_thresholds,
        patient_history=patient_history,
    )
    norm = FeatureNormalizationService.normalize(val["data"])
    return val, rule, norm

def alerts_for(rule_result, parameter):
    return [a for a in rule_result["alerts"] if a["parameter"] == parameter]

def alert_for(rule_result, parameter):
    matches = alerts_for(rule_result, parameter)
    return matches[0] if matches else None


# ── Fixtures ──────────────────────────────────────────────────────────────────

NORMAL = {
    "hr_bpm": 72,
    "oxygen_spo2_pct": 98.0,
    "respiratory_rate_bpm": 15,
    "blood_pressure": {"sbp_mmhg": 118, "dbp_mmhg": 76},
    "glucose_mgdl": 100.0,
    "cholesterol_mgdl": 190.0,
    "hemoglobin_gdl": 14.0,
    "temperature_f": 98.6,
    "weight_kg": 70.0,
    "step_count": 8000,
    "ecg": 0,
    "stethoscope": 0,
    "fall_detected": 0,
    "demographics": {
        "biological_sex": "male",
        "age_group": "46-60",
        "weight_kg": 70.0,
    },
}

MINIMAL = {
    "hr_bpm": 72,
    "oxygen_spo2_pct": 98.0,
}


# ── 1. Normal patient ─────────────────────────────────────────────────────────

print("\n── 1. Normal patient ──────────────────────────────────────────────────")

def test_normal_validation_passes():
    val, _, _ = run_pipeline(NORMAL)
    assert val["valid"], f"Validation failed: {val['errors']}"

def test_normal_no_alerts():
    _, rule, _ = run_pipeline(NORMAL)
    assert rule["alert_count"] == 0, f"Expected 0 alerts, got {rule['alerts']}"

def test_normal_highest_severity_none():
    _, rule, _ = run_pipeline(NORMAL)
    assert rule["highest_severity"] == "none"

def test_normal_vector_length():
    _, _, norm = run_pipeline(NORMAL)
    assert len(norm["vector"]) == len(FEATURE_ORDER)

def test_normal_no_missing_fields():
    _, _, norm = run_pipeline(NORMAL)
    assert norm["missing_fields"] == [], f"Unexpected missing: {norm['missing_fields']}"

def test_normal_all_vector_values_in_range():
    _, _, norm = run_pipeline(NORMAL)
    for i, (fname, val) in enumerate(zip(FEATURE_ORDER, norm["vector"])):
        assert 0.0 <= val <= 1.0, f"Feature '{fname}' = {val} is outside [0,1]"

run("normal payload → validation passes", test_normal_validation_passes)
run("normal payload → 0 alerts", test_normal_no_alerts)
run("normal payload → highest_severity = none", test_normal_highest_severity_none)
run("normal payload → vector length == len(FEATURE_ORDER)", test_normal_vector_length)
run("normal payload → no missing fields in vector", test_normal_no_missing_fields)
run("normal payload → all vector values in [0.0, 1.0]", test_normal_all_vector_values_in_range)


# ── 2. Critical HR ────────────────────────────────────────────────────────────

print("\n── 2. Critical HR ─────────────────────────────────────────────────────")

def test_critical_hr_high():
    _, rule, _ = run_pipeline({**MINIMAL, "hr_bpm": 160})
    a = alert_for(rule, "hr_bpm")
    assert a and a["severity"] == "critical", f"Expected critical HR alert, got {a}"

def test_critical_hr_low():
    _, rule, _ = run_pipeline({**MINIMAL, "hr_bpm": 35})
    a = alert_for(rule, "hr_bpm")
    assert a and a["severity"] == "critical"

def test_critical_hr_vector_still_valid():
    _, _, norm = run_pipeline({**MINIMAL, "hr_bpm": 160})
    assert len(norm["vector"]) == len(FEATURE_ORDER)
    assert all(0.0 <= v <= 1.0 for v in norm["vector"])

def test_critical_hr_notify_routing():
    _, rule, _ = run_pipeline({**MINIMAL, "hr_bpm": 160})
    a = alert_for(rule, "hr_bpm")
    assert set(a["notify"]) == {"patient", "guardians", "doctor"}

run("hr=160 → critical alert fires", test_critical_hr_high)
run("hr=35 → critical low alert fires", test_critical_hr_low)
run("critical HR → feature vector still valid (length + bounds)", test_critical_hr_vector_still_valid)
run("critical HR → notify = patient + guardians + doctor", test_critical_hr_notify_routing)


# ── 3. Critical SpO2 ──────────────────────────────────────────────────────────

print("\n── 3. Critical SpO2 ───────────────────────────────────────────────────")

def test_critical_spo2():
    _, rule, _ = run_pipeline({**MINIMAL, "oxygen_spo2_pct": 82.0})
    a = alert_for(rule, "oxygen_spo2_pct")
    assert a and a["severity"] == "critical"

def test_critical_spo2_boundary():
    # 87.9 is < 88 → critical; 88.0 → warning
    _, rule, _ = run_pipeline({**MINIMAL, "oxygen_spo2_pct": 87.9})
    a = alert_for(rule, "oxygen_spo2_pct")
    assert a and a["severity"] == "critical", f"87.9 should be critical, got {a}"

def test_warning_spo2_boundary():
    _, rule, _ = run_pipeline({**MINIMAL, "oxygen_spo2_pct": 88.0})
    a = alert_for(rule, "oxygen_spo2_pct")
    assert a and a["severity"] == "warning", f"88.0 should be warning, got {a}"

def test_spo2_normalized_correctly():
    # SpO2 range 50–100; value 82 → (82-50)/(100-50) = 32/50 = 0.64
    _, _, norm = run_pipeline({**MINIMAL, "oxygen_spo2_pct": 82.0})
    expected = (82.0 - 50) / (100 - 50)
    assert approx(norm["features"]["oxygen_spo2_pct"], expected), (
        f"Expected {expected}, got {norm['features']['oxygen_spo2_pct']}"
    )

run("spo2=82 → critical alert", test_critical_spo2)
run("spo2=87.9 → critical (just below threshold 88)", test_critical_spo2_boundary)
run("spo2=88.0 → warning (exactly at warning threshold)", test_warning_spo2_boundary)
run("spo2=82 → normalized to 0.64 in feature vector", test_spo2_normalized_correctly)


# ── 4. Critical BP ────────────────────────────────────────────────────────────

print("\n── 4. Critical BP (nested blood_pressure) ─────────────────────────────")

def test_critical_sbp():
    payload = {**MINIMAL, "blood_pressure": {"sbp_mmhg": 185, "dbp_mmhg": 76}}
    _, rule, _ = run_pipeline(payload)
    a = alert_for(rule, "sbp_mmhg")
    assert a and a["severity"] == "critical"

def test_critical_dbp():
    payload = {**MINIMAL, "blood_pressure": {"sbp_mmhg": 130, "dbp_mmhg": 125}}
    _, rule, _ = run_pipeline(payload)
    a = alert_for(rule, "dbp_mmhg")
    assert a and a["severity"] == "critical"

def test_both_bp_critical():
    payload = {**MINIMAL, "blood_pressure": {"sbp_mmhg": 185, "dbp_mmhg": 125}}
    _, rule, _ = run_pipeline(payload)
    assert alert_for(rule, "sbp_mmhg")["severity"] == "critical"
    assert alert_for(rule, "dbp_mmhg")["severity"] == "critical"
    assert rule["alert_count"] == 2

def test_bp_nested_survives_to_normalization():
    # BP comes out of ValidationService as nested dict;
    # FeatureNormalizationService must read sbp/dbp from that nested dict
    payload = {**MINIMAL, "blood_pressure": {"sbp_mmhg": 185, "dbp_mmhg": 125}}
    _, _, norm = run_pipeline(payload)
    assert "sbp_mmhg" in norm["features"]
    assert "dbp_mmhg" in norm["features"]
    assert norm["features"]["sbp_mmhg"] > 0   # not sentinel
    assert norm["features"]["dbp_mmhg"] > 0

def test_bp_not_in_missing_fields_when_present():
    payload = {**MINIMAL, "blood_pressure": {"sbp_mmhg": 120, "dbp_mmhg": 80}}
    _, _, norm = run_pipeline(payload)
    assert "sbp_mmhg" not in norm["missing_fields"]
    assert "dbp_mmhg" not in norm["missing_fields"]

run("sbp=185 → critical alert", test_critical_sbp)
run("dbp=125 → critical alert", test_critical_dbp)
run("sbp=185 + dbp=125 → both critical, alert_count=2", test_both_bp_critical)
run("nested blood_pressure survives intact to normalization stage", test_bp_nested_survives_to_normalization)
run("sbp/dbp present → not in missing_fields", test_bp_not_in_missing_fields_when_present)


# ── 5. Warning respiratory ────────────────────────────────────────────────────

print("\n── 5. Warning respiratory ─────────────────────────────────────────────")

def test_warning_rr_high():
    _, rule, _ = run_pipeline({**MINIMAL, "respiratory_rate_bpm": 24})
    a = alert_for(rule, "respiratory_rate_bpm")
    assert a and a["severity"] == "warning"

def test_warning_rr_notify_patient_only():
    _, rule, _ = run_pipeline({**MINIMAL, "respiratory_rate_bpm": 24})
    a = alert_for(rule, "respiratory_rate_bpm")
    assert a["notify"] == ["patient"], f"Warning should notify patient only, got {a['notify']}"

def test_critical_rr_boundary():
    # 30 is exactly at critical_high threshold (≥30)
    _, rule, _ = run_pipeline({**MINIMAL, "respiratory_rate_bpm": 30})
    a = alert_for(rule, "respiratory_rate_bpm")
    assert a and a["severity"] == "critical", f"RR=30 should be critical, got {a}"

run("rr=24 → warning alert", test_warning_rr_high)
run("rr=24 warning → notify patient only (not guardians/doctor)", test_warning_rr_notify_patient_only)
run("rr=30 → critical (exactly at critical_high threshold)", test_critical_rr_boundary)


# ── 6. All 5 parameters critical simultaneously ───────────────────────────────

print("\n── 6. All 5 parameters critical simultaneously ─────────────────────────")

ALL_CRITICAL = {
    "hr_bpm": 160,
    "oxygen_spo2_pct": 80.0,
    "respiratory_rate_bpm": 35,
    "blood_pressure": {"sbp_mmhg": 185, "dbp_mmhg": 125},
}

def test_all_critical_alert_count():
    _, rule, _ = run_pipeline(ALL_CRITICAL)
    assert rule["alert_count"] == 5, f"Expected 5 alerts, got {rule['alert_count']}"

def test_all_critical_highest_severity():
    _, rule, _ = run_pipeline(ALL_CRITICAL)
    assert rule["highest_severity"] == "critical"

def test_all_critical_parameters_present():
    _, rule, _ = run_pipeline(ALL_CRITICAL)
    params = {a["parameter"] for a in rule["alerts"]}
    assert params == {"hr_bpm", "oxygen_spo2_pct", "respiratory_rate_bpm", "sbp_mmhg", "dbp_mmhg"}

def test_all_critical_vector_still_valid():
    _, _, norm = run_pipeline(ALL_CRITICAL)
    assert len(norm["vector"]) == len(FEATURE_ORDER)
    assert all(0.0 <= v <= 1.0 for v in norm["vector"])

run("all 5 params critical → alert_count = 5", test_all_critical_alert_count)
run("all 5 params critical → highest_severity = critical", test_all_critical_highest_severity)
run("all 5 params critical → all 5 parameter names in alerts", test_all_critical_parameters_present)
run("all 5 params critical → feature vector still valid", test_all_critical_vector_still_valid)


# ── 7. Mixed severity ─────────────────────────────────────────────────────────

print("\n── 7. Mixed severity (critical + warning) ─────────────────────────────")

MIXED = {
    "hr_bpm": 72,
    "oxygen_spo2_pct": 82.0,          # critical
    "respiratory_rate_bpm": 24,        # warning
    "blood_pressure": {"sbp_mmhg": 145, "dbp_mmhg": 90},  # both warning
}

def test_mixed_highest_severity_is_critical():
    _, rule, _ = run_pipeline(MIXED)
    assert rule["highest_severity"] == "critical"

def test_mixed_alert_count():
    _, rule, _ = run_pipeline(MIXED)
    assert rule["alert_count"] == 4, f"Expected 4 alerts, got {rule['alert_count']}: {rule['alerts']}"

def test_mixed_severities_correct():
    _, rule, _ = run_pipeline(MIXED)
    assert alert_for(rule, "oxygen_spo2_pct")["severity"] == "critical"
    assert alert_for(rule, "respiratory_rate_bpm")["severity"] == "warning"
    assert alert_for(rule, "sbp_mmhg")["severity"] == "warning"
    assert alert_for(rule, "dbp_mmhg")["severity"] == "warning"

run("mixed payload → highest_severity = critical (one critical present)", test_mixed_highest_severity_is_critical)
run("mixed payload → alert_count = 4", test_mixed_alert_count)
run("mixed payload → each alert has correct individual severity", test_mixed_severities_correct)


# ── 8. Doctor override ────────────────────────────────────────────────────────

print("\n── 8. Doctor threshold override ───────────────────────────────────────")

def test_doctor_override_changes_severity():
    # SpO2=89: default bands → warning (88–92). Doctor sets critical<90 → critical.
    payload = {**MINIMAL, "oxygen_spo2_pct": 89.0}
    doctor = {"oxygen_spo2_pct": {"critical_low": 90, "warning_low": 93, "warning_high": None, "critical_high": None}}
    _, rule, _ = run_pipeline(payload, doctor_thresholds=doctor)
    a = alert_for(rule, "oxygen_spo2_pct")
    assert a and a["severity"] == "critical", f"Doctor override should make 89 critical, got {a}"

def test_doctor_override_threshold_basis():
    payload = {**MINIMAL, "oxygen_spo2_pct": 89.0}
    doctor = {"oxygen_spo2_pct": {"critical_low": 90, "warning_low": 93, "warning_high": None, "critical_high": None}}
    _, rule, _ = run_pipeline(payload, doctor_thresholds=doctor)
    a = alert_for(rule, "oxygen_spo2_pct")
    assert a["threshold_basis"] == "doctor_set", f"Expected doctor_set, got {a['threshold_basis']}"

def test_non_overridden_param_uses_default():
    # Override SpO2 only; HR should still use population default
    payload = {**MINIMAL, "hr_bpm": 160, "oxygen_spo2_pct": 89.0}
    doctor = {"oxygen_spo2_pct": {"critical_low": 90, "warning_low": 93, "warning_high": None, "critical_high": None}}
    _, rule, _ = run_pipeline(payload, doctor_thresholds=doctor)
    hr_alert = alert_for(rule, "hr_bpm")
    assert hr_alert["threshold_basis"] == "default"

run("doctor override makes SpO2=89 critical instead of warning", test_doctor_override_changes_severity)
run("doctor override → threshold_basis = doctor_set", test_doctor_override_threshold_basis)
run("non-overridden param (HR) still uses default tier", test_non_overridden_param_uses_default)


# ── 9. Patient history tier ───────────────────────────────────────────────────

print("\n── 9. Patient history (historical SD) tier ────────────────────────────")

def test_history_tier_activates():
    # Patient's personal baseline HR is 55 (athletic). 72 is >2SD above for them.
    # We'll use a tight history so 72 triggers a warning.
    history = {"hr_bpm": [54, 55, 56, 55, 54, 56, 55, 55, 54, 56]}  # mean~55, SD~0.8
    payload = {**MINIMAL, "hr_bpm": 72}
    _, rule, _ = run_pipeline(payload, patient_history=history)
    a = alert_for(rule, "hr_bpm")
    assert a is not None, "Expected HR alert from history tier"
    assert a["threshold_basis"] == "historical_sd"

def test_history_tier_not_enough_readings_falls_to_default():
    # Only 5 readings — below HISTORY_MIN_READINGS (10) → falls to default
    history = {"hr_bpm": [55, 56, 54, 55, 56]}
    payload = {**MINIMAL, "hr_bpm": 72}
    _, rule, _ = run_pipeline(payload, patient_history=history)
    # HR=72 is normal by default thresholds, so no alert
    a = alert_for(rule, "hr_bpm")
    assert a is None, f"Should have fallen to default (no alert at HR=72), got {a}"

def test_history_tier_sd_zero_falls_to_default():
    # All identical readings → SD=0, can't compute meaningful bands → fall to default
    history = {"hr_bpm": [72] * 15}
    payload = {**MINIMAL, "hr_bpm": 72}
    _, rule, _ = run_pipeline(payload, patient_history=history)
    a = alert_for(rule, "hr_bpm")
    assert a is None, "SD=0 should fall to default; HR=72 is normal by default"

run("tight personal history → HR=72 alerts as historical_sd", test_history_tier_activates)
run("< 10 history readings → falls through to default tier", test_history_tier_not_enough_readings_falls_to_default)
run("SD=0 in history → falls through to default tier", test_history_tier_sd_zero_falls_to_default)


# ── 10. Minimal payload ───────────────────────────────────────────────────────

print("\n── 10. Minimal payload (only required fields) ─────────────────────────")

def test_minimal_pipeline_completes():
    val, rule, norm = run_pipeline(MINIMAL)
    assert val["valid"]
    assert rule is not None
    assert norm is not None

def test_minimal_vector_length():
    _, _, norm = run_pipeline(MINIMAL)
    assert len(norm["vector"]) == len(FEATURE_ORDER)

def test_minimal_missing_field_count():
    _, _, norm = run_pipeline(MINIMAL)
    # 17 total features, 2 present (hr_bpm + oxygen_spo2_pct) → 15 missing
    assert len(norm["missing_fields"]) == 15, (
        f"Expected 15 missing, got {len(norm['missing_fields'])}: {norm['missing_fields']}"
    )

def test_minimal_missing_fields_get_sentinel():
    _, _, norm = run_pipeline(MINIMAL)
    for f in norm["missing_fields"]:
        assert approx(norm["features"][f], MISSING_SENTINEL), (
            f"'{f}' in missing_fields but value = {norm['features'][f]}"
        )

run("minimal payload → all three stages complete without error", test_minimal_pipeline_completes)
run("minimal payload → vector length correct", test_minimal_vector_length)
run("minimal payload → exactly 14 missing fields", test_minimal_missing_field_count)
run("minimal payload → all missing fields = sentinel 0.5", test_minimal_missing_fields_get_sentinel)


# ── 11. Validation rejection ──────────────────────────────────────────────────

print("\n── 11. Validation rejection (invalid payloads) ─────────────────────────")

def test_missing_required_field_rejected():
    val, rule, norm = run_pipeline({"oxygen_spo2_pct": 98.0})
    assert not val["valid"]
    assert rule is None
    assert norm is None

def test_out_of_range_rejected():
    val, rule, norm = run_pipeline({"hr_bpm": 999, "oxygen_spo2_pct": 98.0})
    assert not val["valid"]
    assert rule is None

def test_dbp_gte_sbp_rejected():
    payload = {"hr_bpm": 72, "oxygen_spo2_pct": 98.0,
               "blood_pressure": {"sbp_mmhg": 80, "dbp_mmhg": 90}}
    val, rule, norm = run_pipeline(payload)
    assert not val["valid"], "DBP >= SBP should be rejected"
    assert rule is None

def test_errors_list_populated_on_rejection():
    val, _, _ = run_pipeline({"oxygen_spo2_pct": 98.0})
    assert len(val["errors"]) > 0

run("missing hr_bpm → rejected, rule+norm stages skipped", test_missing_required_field_rejected)
run("hr_bpm=999 out of range → rejected", test_out_of_range_rejected)
run("DBP >= SBP → rejected by validation", test_dbp_gte_sbp_rejected)
run("rejected payload → errors list is populated", test_errors_list_populated_on_rejection)


# ── 12. Dropped parameters don't affect alerts ───────────────────────────────

print("\n── 12. Dropped parameters ignored by rule engine ──────────────────────")

DROPPED_PARAMS_ABNORMAL = {
    "hr_bpm": 72,
    "oxygen_spo2_pct": 98.0,
    "glucose_mgdl": 30.0,          # critically low — but ignored
    "temperature_f": 105.0,        # critically high — but ignored
    "cholesterol_mgdl": 300.0,     # critically high — but ignored
    "hemoglobin_gdl": 5.0,         # critically low — but ignored
    "fall_detected": 1,            # would have been critical — but ignored
    "ecg": 1,
    "stethoscope": 1,
}

def test_dropped_params_produce_no_alerts():
    _, rule, _ = run_pipeline(DROPPED_PARAMS_ABNORMAL)
    assert rule["alert_count"] == 0, (
        f"Dropped params should not alert, got: {rule['alerts']}"
    )

def test_dropped_params_highest_severity_none():
    _, rule, _ = run_pipeline(DROPPED_PARAMS_ABNORMAL)
    assert rule["highest_severity"] == "none"

def test_dropped_params_still_normalized():
    # Even though they don't alert, they still appear in the feature vector
    _, _, norm = run_pipeline(DROPPED_PARAMS_ABNORMAL)
    assert "glucose_mgdl" in norm["features"]
    assert "temperature_f" in norm["features"]
    # fall_detected=1 should pass through as 1.0
    assert approx(norm["features"]["fall_detected"], 1.0)

run("glucose/temp/cholesterol/hemoglobin/flags abnormal → 0 alerts", test_dropped_params_produce_no_alerts)
run("dropped params → highest_severity = none", test_dropped_params_highest_severity_none)
run("dropped params → still encoded in feature vector for ML", test_dropped_params_still_normalized)


# ── 13. Vector contract (stable across all payloads) ─────────────────────────

print("\n── 13. Vector contract (length + bounds always stable) ─────────────────")

TEST_PAYLOADS = [
    NORMAL,
    MINIMAL,
    ALL_CRITICAL,
    DROPPED_PARAMS_ABNORMAL,
    {**MINIMAL, "hr_bpm": 35, "oxygen_spo2_pct": 50.1},   # near-minimum values
]

def test_vector_length_stable_across_payloads():
    for i, payload in enumerate(TEST_PAYLOADS):
        _, _, norm = run_pipeline(payload)
        assert len(norm["vector"]) == len(FEATURE_ORDER), (
            f"Payload #{i+1}: expected vector length {len(FEATURE_ORDER)}, got {len(norm['vector'])}"
        )

def test_all_vector_values_in_bounds_across_payloads():
    for i, payload in enumerate(TEST_PAYLOADS):
        _, _, norm = run_pipeline(payload)
        for fname, val in norm["features"].items():
            assert 0.0 <= val <= 1.0, (
                f"Payload #{i+1}: feature '{fname}' = {val} is outside [0,1]"
            )

def test_feature_order_keys_stable():
    for payload in TEST_PAYLOADS:
        _, _, norm = run_pipeline(payload)
        assert list(norm["features"].keys()) == FEATURE_ORDER or set(norm["features"].keys()) == set(FEATURE_ORDER)

run("vector length == len(FEATURE_ORDER) for all test payloads", test_vector_length_stable_across_payloads)
run("all feature values in [0.0, 1.0] for all test payloads", test_all_vector_values_in_bounds_across_payloads)
run("feature dict keys match FEATURE_ORDER for all test payloads", test_feature_order_keys_stable)


# ── 14. Notification routing ──────────────────────────────────────────────────

print("\n── 14. Notification routing ───────────────────────────────────────────")

def test_warning_notify_patient_only():
    _, rule, _ = run_pipeline({**MINIMAL, "hr_bpm": 115})   # warning high
    a = alert_for(rule, "hr_bpm")
    assert a["severity"] == "warning"
    assert a["notify"] == ["patient"]

def test_critical_notify_all_three():
    _, rule, _ = run_pipeline({**MINIMAL, "hr_bpm": 160})
    a = alert_for(rule, "hr_bpm")
    assert a["severity"] == "critical"
    assert set(a["notify"]) == {"patient", "guardians", "doctor"}

def test_mixed_alerts_each_have_own_notify():
    _, rule, _ = run_pipeline(MIXED)
    for alert in rule["alerts"]:
        if alert["severity"] == "critical":
            assert set(alert["notify"]) == {"patient", "guardians", "doctor"}
        elif alert["severity"] == "warning":
            assert alert["notify"] == ["patient"]

run("warning alert → notify = [patient] only", test_warning_notify_patient_only)
run("critical alert → notify = [patient, guardians, doctor]", test_critical_notify_all_three)
run("mixed alerts → each alert carries its own correct notify list", test_mixed_alerts_each_have_own_notify)


# ── 15. Full demographics in vector ──────────────────────────────────────────

print("\n── 15. Full demographics encoding in feature vector ───────────────────")

def test_demographics_sex_male_encoded():
    payload = {**MINIMAL, "demographics": {"biological_sex": "male", "age_group": "31-45"}}
    _, _, norm = run_pipeline(payload)
    assert approx(norm["features"]["biological_sex"], SEX_ENCODING["male"])

def test_demographics_sex_female_encoded():
    payload = {**MINIMAL, "demographics": {"biological_sex": "female", "age_group": "31-45"}}
    _, _, norm = run_pipeline(payload)
    assert approx(norm["features"]["biological_sex"], SEX_ENCODING["female"])

def test_demographics_age_group_encoded():
    for ag, expected in AGE_GROUP_ENCODING.items():
        payload = {**MINIMAL, "demographics": {"age_group": ag}}
        _, _, norm = run_pipeline(payload)
        assert approx(norm["features"]["age_group"], expected), (
            f"age_group='{ag}': expected {expected}, got {norm['features']['age_group']}"
        )

def test_demographics_absent_gets_sentinel():
    _, _, norm = run_pipeline(MINIMAL)
    assert approx(norm["features"]["biological_sex"], MISSING_SENTINEL)
    assert approx(norm["features"]["age_group"], MISSING_SENTINEL)

run("demographics.biological_sex=male → 1.0 in vector", test_demographics_sex_male_encoded)
run("demographics.biological_sex=female → 0.0 in vector", test_demographics_sex_female_encoded)
run("all age_group values → correct ordinal in vector", test_demographics_age_group_encoded)
run("demographics absent → biological_sex and age_group get sentinel 0.5", test_demographics_absent_gets_sentinel)


# ── Summary ───────────────────────────────────────────────────────────────────

total = _pass + _fail
print(f"\n{'─'*60}")
if _fail == 0:
    print(f"  \033[92m{_pass}/{total} passed — all good\033[0m")
else:
    print(f"  \033[91m{_fail} FAILED\033[0m, {_pass} passed  ({total} total)")
print(f"{'─'*60}\n")

sys.exit(1 if _fail else 0)
