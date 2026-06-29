"""
test_rule_engine_service.py
────────────────────────────
Unit tests for RuleEngineService.

Run with:
    py test_modules/test_rule_engine_service.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from apps.clin_gpt.services.rule_engine_service import RuleEngineService

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
results = []

def run(name, fn):
    try:
        fn()
        print(f"  {PASS}  {name}")
        results.append(True)
    except AssertionError as e:
        print(f"  {FAIL}  {name}")
        print(f"       → {e}")
        results.append(False)


def alert_for(alerts, parameter):
    """Helper: find the alert dict for a given parameter, or None."""
    return next((a for a in alerts if a["parameter"] == parameter), None)


# ── Fixtures ──────────────────────────────────────────────────────────────────

NORMAL_VITALS = {
    "hr_bpm": 78,
    "oxygen_spo2_pct": 97.2,
    "respiratory_rate_bpm": 15,
    "blood_pressure": {"sbp_mmhg": 118, "dbp_mmhg": 76},
}


# ── HR ────────────────────────────────────────────────────────────────────────

print("\n── Heart rate (hr_bpm) ─────────────────────────────────────────────")

def test_hr_normal():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 78})
    assert alert_for(r["alerts"], "hr_bpm") is None

def test_hr_critical_low():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 35})
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "critical"

def test_hr_warning_low():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 45})
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "warning"

def test_hr_warning_high():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 120})
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "warning"

def test_hr_critical_high():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 155})
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "critical"

run("HR=78 → no alert", test_hr_normal)
run("HR=35 → critical low", test_hr_critical_low)
run("HR=45 → warning low", test_hr_warning_low)
run("HR=120 → warning high", test_hr_warning_high)
run("HR=155 → critical high", test_hr_critical_high)


# ── SpO2 ──────────────────────────────────────────────────────────────────────

print("\n── Oxygen saturation (oxygen_spo2_pct) ──────────────────────────────")

def test_spo2_normal():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 97.0})
    assert alert_for(r["alerts"], "oxygen_spo2_pct") is None

def test_spo2_warning():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 90.0})
    a = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert a and a["severity"] == "warning"

def test_spo2_critical():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 80.0})
    a = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert a and a["severity"] == "critical"

def test_spo2_critical_boundary():
    # 87 is critical (<88), 88 is warning (88-91), 92 is normal
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 87.0})
    a = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert a and a["severity"] == "critical"

def test_spo2_warning_boundary():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 88.0})
    a = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert a and a["severity"] == "warning"

def test_spo2_normal_boundary():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 92.0})
    assert alert_for(r["alerts"], "oxygen_spo2_pct") is None

def test_spo2_no_high_alert():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 100.0})
    assert alert_for(r["alerts"], "oxygen_spo2_pct") is None

run("SpO2=97% → no alert", test_spo2_normal)
run("SpO2=90% → warning", test_spo2_warning)
run("SpO2=80% → critical", test_spo2_critical)
run("SpO2=87% → critical (boundary, <88)", test_spo2_critical_boundary)
run("SpO2=88% → warning (boundary, 88-91)", test_spo2_warning_boundary)
run("SpO2=92% → no alert (boundary, normal floor)", test_spo2_normal_boundary)
run("SpO2=100% → no high-side alert (none defined, cannot exceed 100%)", test_spo2_no_high_alert)


# ── Respiratory rate ──────────────────────────────────────────────────────────

print("\n── Respiratory rate (respiratory_rate_bpm) ──────────────────────────")

def test_resp_normal():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "respiratory_rate_bpm": 15})
    assert alert_for(r["alerts"], "respiratory_rate_bpm") is None

def test_resp_critical_low():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "respiratory_rate_bpm": 6})
    a = alert_for(r["alerts"], "respiratory_rate_bpm")
    assert a and a["severity"] == "critical"

def test_resp_warning_low():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "respiratory_rate_bpm": 9})
    a = alert_for(r["alerts"], "respiratory_rate_bpm")
    assert a and a["severity"] == "warning"

def test_resp_warning_high():
    # 25-29 is warning (instantaneous) per current scope — sustained-duration
    # escalation to critical is not yet implemented (needs reading history)
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "respiratory_rate_bpm": 27})
    a = alert_for(r["alerts"], "respiratory_rate_bpm")
    assert a and a["severity"] == "warning"

def test_resp_critical_high():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "respiratory_rate_bpm": 30})
    a = alert_for(r["alerts"], "respiratory_rate_bpm")
    assert a and a["severity"] == "critical"

run("Respiratory=15 → no alert", test_resp_normal)
run("Respiratory=6 → critical low", test_resp_critical_low)
run("Respiratory=9 → warning low", test_resp_warning_low)
run("Respiratory=27 → warning high (25-29 band)", test_resp_warning_high)
run("Respiratory=30 → critical high (\u226530)", test_resp_critical_high)


# ── Blood pressure ────────────────────────────────────────────────────────────

print("\n── Blood pressure (sbp_mmhg / dbp_mmhg) ──────────────────────────────")

def test_bp_normal():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 118, "dbp_mmhg": 76}})
    assert alert_for(r["alerts"], "sbp_mmhg") is None
    assert alert_for(r["alerts"], "dbp_mmhg") is None

def test_bp_crisis_critical():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 185, "dbp_mmhg": 125}})
    sbp_alert = alert_for(r["alerts"], "sbp_mmhg")
    dbp_alert = alert_for(r["alerts"], "dbp_mmhg")
    assert sbp_alert and sbp_alert["severity"] == "critical"
    assert dbp_alert and dbp_alert["severity"] == "critical"

def test_bp_hypotension_critical():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 85, "dbp_mmhg": 55}})
    sbp_alert = alert_for(r["alerts"], "sbp_mmhg")
    dbp_alert = alert_for(r["alerts"], "dbp_mmhg")
    assert sbp_alert and sbp_alert["severity"] == "critical"
    assert dbp_alert and dbp_alert["severity"] == "critical"

def test_bp_warning_high():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 150, "dbp_mmhg": 95}})
    sbp_alert = alert_for(r["alerts"], "sbp_mmhg")
    dbp_alert = alert_for(r["alerts"], "dbp_mmhg")
    assert sbp_alert and sbp_alert["severity"] == "warning"
    assert dbp_alert and dbp_alert["severity"] == "warning"

def test_sbp_normal_ceiling():
    # Normal band is now 100-129 (tightened from 100-139)
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 129, "dbp_mmhg": 76}})
    assert alert_for(r["alerts"], "sbp_mmhg") is None

def test_sbp_warning_at_new_boundary():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 130, "dbp_mmhg": 76}})
    a = alert_for(r["alerts"], "sbp_mmhg")
    assert a and a["severity"] == "warning"

def test_dbp_normal_ceiling():
    # Normal band is now 70-79 (tightened from 70-89)
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 118, "dbp_mmhg": 79}})
    assert alert_for(r["alerts"], "dbp_mmhg") is None

def test_dbp_warning_at_new_boundary():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 118, "dbp_mmhg": 80}})
    a = alert_for(r["alerts"], "dbp_mmhg")
    assert a and a["severity"] == "warning"

run("BP=118/76 → no alerts", test_bp_normal)
run("BP=185/125 → both critical (hypertensive crisis)", test_bp_crisis_critical)
run("BP=85/55 → both critical (hypotension)", test_bp_hypotension_critical)
run("BP=150/95 → both warning", test_bp_warning_high)
run("SBP=129 → no alert (new normal ceiling)", test_sbp_normal_ceiling)
run("SBP=130 → warning (new boundary)", test_sbp_warning_at_new_boundary)
run("DBP=79 → no alert (new normal ceiling)", test_dbp_normal_ceiling)
run("DBP=80 → warning (new boundary)", test_dbp_warning_at_new_boundary)


# ── Excluded fields ───────────────────────────────────────────────────────────
# Critical alerting is now scoped to HR / SpO2 / respiratory / BP only.
# Glucose, temperature, cholesterol, hemoglobin, and the binary flags
# (fall_detected, ecg, stethoscope) were dropped from the alert system —
# if present in the payload they must be ignored, not alerted on.

print("\n── Excluded fields (out-of-scope parameters) ──────────────────────────")

def test_weight_never_alerts():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "weight_kg": 250.0})
    assert alert_for(r["alerts"], "weight_kg") is None

def test_step_count_never_alerts():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "step_count": 0})
    assert alert_for(r["alerts"], "step_count") is None

def test_glucose_never_alerts():
    # Even a wildly abnormal glucose reading must not produce an alert now
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "glucose_mgdl": 30.0})
    assert alert_for(r["alerts"], "glucose_mgdl") is None

def test_temperature_never_alerts():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "temperature_f": 105.0})
    assert alert_for(r["alerts"], "temperature_f") is None

def test_cholesterol_never_alerts():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "cholesterol_mgdl": 300.0})
    assert alert_for(r["alerts"], "cholesterol_mgdl") is None

def test_hemoglobin_never_alerts():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hemoglobin_gdl": 5.0})
    assert alert_for(r["alerts"], "hemoglobin_gdl") is None

def test_fall_detected_never_alerts():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "fall_detected": 1})
    assert alert_for(r["alerts"], "fall_detected") is None

def test_ecg_never_alerts():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "ecg": 1})
    assert alert_for(r["alerts"], "ecg") is None

def test_stethoscope_never_alerts():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "stethoscope": 1})
    assert alert_for(r["alerts"], "stethoscope") is None

def test_dropped_params_dont_affect_alert_count():
    # alert_count should reflect only HR/SpO2/Respiratory/BP, even with every
    # dropped parameter present and abnormal
    r = RuleEngineService.evaluate({
        **NORMAL_VITALS,
        "glucose_mgdl": 30.0,
        "temperature_f": 105.0,
        "cholesterol_mgdl": 300.0,
        "hemoglobin_gdl": 5.0,
        "fall_detected": 1,
        "ecg": 1,
        "stethoscope": 1,
    })
    assert r["alert_count"] == 0
    assert r["highest_severity"] == "none"

run("weight_kg=250.0 → no alert (excluded)", test_weight_never_alerts)
run("step_count=0 → no alert (excluded)", test_step_count_never_alerts)
run("glucose_mgdl=30 → no alert (removed from scope)", test_glucose_never_alerts)
run("temperature_f=105 → no alert (removed from scope)", test_temperature_never_alerts)
run("cholesterol_mgdl=300 → no alert (removed from scope)", test_cholesterol_never_alerts)
run("hemoglobin_gdl=5.0 → no alert (removed from scope)", test_hemoglobin_never_alerts)
run("fall_detected=1 → no alert (removed from scope)", test_fall_detected_never_alerts)
run("ecg=1 → no alert (removed from scope)", test_ecg_never_alerts)
run("stethoscope=1 → no alert (removed from scope)", test_stethoscope_never_alerts)
run("All dropped params abnormal at once → alert_count=0, highest_severity=none", test_dropped_params_dont_affect_alert_count)


# ── Multi-alert behaviour (no single winner) ──────────────────────────────────

print("\n── Multi-alert behaviour ──────────────────────────────────────────────")

def test_multiple_simultaneous_alerts_all_returned():
    r = RuleEngineService.evaluate({
        **NORMAL_VITALS,
        "oxygen_spo2_pct": 80.0,         # critical
        "respiratory_rate_bpm": 32,      # critical
        "hr_bpm": 45,                     # warning
    })
    params = {a["parameter"] for a in r["alerts"]}
    assert "oxygen_spo2_pct" in params
    assert "respiratory_rate_bpm" in params
    assert "hr_bpm" in params
    assert r["alert_count"] == 3

def test_highest_severity_critical_when_mixed():
    r = RuleEngineService.evaluate({
        **NORMAL_VITALS,
        "oxygen_spo2_pct": 80.0,   # critical
        "hr_bpm": 45,               # warning
    })
    assert r["highest_severity"] == "critical"

def test_highest_severity_warning_when_no_critical():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 45})
    assert r["highest_severity"] == "warning"

def test_highest_severity_none_when_clean():
    r = RuleEngineService.evaluate(NORMAL_VITALS)
    assert r["highest_severity"] == "none"
    assert r["alert_count"] == 0

run("Multiple simultaneous alerts → all returned, none suppressed", test_multiple_simultaneous_alerts_all_returned)
run("Mixed critical+warning → highest_severity=critical", test_highest_severity_critical_when_mixed)
run("Only warning present → highest_severity=warning", test_highest_severity_warning_when_no_critical)
run("Fully normal payload → highest_severity=none, alert_count=0", test_highest_severity_none_when_clean)


# ── Doctor-set threshold overrides ────────────────────────────────────────────

print("\n── Doctor-set threshold overrides ─────────────────────────────────────")

def test_doctor_override_replaces_default_for_overridden_param():
    # COPD patient: doctor sets SpO2 critical at <85 instead of default <88
    doctor_thresholds = {
        "oxygen_spo2_pct": {
            "critical_low": 85, "warning_low": 88,
            "warning_high": None, "critical_high": None,
        }
    }
    # 86% would be critical under the population default (<88) but should be
    # only a warning under this doctor's override (critical is <85)
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "oxygen_spo2_pct": 86.0},
        doctor_thresholds=doctor_thresholds
    )
    a = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert a and a["severity"] == "warning", a
    assert a["threshold_basis"] == "doctor_set"

def test_doctor_override_critical_at_new_threshold():
    doctor_thresholds = {
        "oxygen_spo2_pct": {
            "critical_low": 85, "warning_low": 88,
            "warning_high": None, "critical_high": None,
        }
    }
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "oxygen_spo2_pct": 84.0},
        doctor_thresholds=doctor_thresholds
    )
    a = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert a and a["severity"] == "critical"
    assert a["threshold_basis"] == "doctor_set"

def test_unoverridden_param_still_uses_default():
    # Doctor only overrides SpO2 — HR should still use the population default
    doctor_thresholds = {
        "oxygen_spo2_pct": {
            "critical_low": 85, "warning_low": 88,
            "warning_high": None, "critical_high": None,
        }
    }
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": 155},
        doctor_thresholds=doctor_thresholds
    )
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "critical"
    assert a["threshold_basis"] == "default"

def test_no_doctor_thresholds_uses_default():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 87.0})
    a = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert a and a["severity"] == "critical"
    assert a["threshold_basis"] == "default"

def test_doctor_override_on_blood_pressure():
    # CHF patient: doctor sets a lower SBP baseline so 85 isn't flagged critical
    doctor_thresholds = {
        "sbp_mmhg": {
            "critical_low": 75, "warning_low": 80,
            "warning_high": 130, "critical_high": 180,
        }
    }
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 85, "dbp_mmhg": 76}},
        doctor_thresholds=doctor_thresholds
    )
    a = alert_for(r["alerts"], "sbp_mmhg")
    assert a is None  # 85 is within this patient's doctor-set normal range now

def test_doctor_thresholds_empty_dict_uses_default():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 87.0}, doctor_thresholds={})
    a = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert a and a["threshold_basis"] == "default"

run("Doctor override (SpO2 critical<85) → 86% is warning, not critical", test_doctor_override_replaces_default_for_overridden_param)
run("Doctor override (SpO2 critical<85) → 84% is critical, basis=doctor_set", test_doctor_override_critical_at_new_threshold)
run("Doctor overrides SpO2 only → HR still uses default, basis=default", test_unoverridden_param_still_uses_default)
run("No doctor_thresholds passed → default used, basis=default", test_no_doctor_thresholds_uses_default)
run("Doctor override on SBP (CHF baseline) → no false alert at 85 mmHg", test_doctor_override_on_blood_pressure)
run("Empty doctor_thresholds dict → falls through to default", test_doctor_thresholds_empty_dict_uses_default)


# ── Summary ───────────────────────────────────────────────────────────────────
total  = len(results)
passed = sum(results)
failed = total - passed
print(f"\n{'─'*50}")
print(f"  {passed}/{total} tests passed", end="")
if failed:
    print(f"  ({failed} failed)")
else:
    print("  — all good ✓")
print(f"{'─'*50}\n")

sys.exit(0 if failed == 0 else 1)
