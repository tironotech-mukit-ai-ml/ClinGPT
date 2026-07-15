"""
test_rule_engine_service.py
────────────────────────────
Unit tests for RuleEngineService.

SCOPE: HR, SpO2, Respiratory, BP only.
Covers all three threshold tiers:
  - Population default (Tier 3)
  - Historical SD — 2σ warning / 3σ critical (Tier 2)
  - Doctor-set override (Tier 1)

Run with:
    py test_modules/test_rule_engine_service.py
"""

import sys, os, statistics
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
    return next((a for a in alerts if a["parameter"] == parameter), None)


# ── Fixtures ──────────────────────────────────────────────────────────────────

NORMAL_VITALS = {
    "hr_bpm": 78,
    "oxygen_spo2_pct": 97.2,
    "respiratory_rate_bpm": 15,
    "blood_pressure": {"sbp_mmhg": 118, "dbp_mmhg": 76},
}

OUT_OF_SCOPE_VITALS = {
    "glucose_mgdl": 45.0,
    "cholesterol_mgdl": 280.0,
    "hemoglobin_gdl": 5.0,
    "temperature_f": 105.0,
    "fall_detected": 1,
    "ecg": 1,
    "stethoscope": 1,
}

# Clean 30-day HR history: mean≈75, sd≈3
HR_HISTORY = [72, 75, 78, 74, 76, 73, 77, 75, 74, 76,
              78, 72, 75, 74, 76, 75, 73, 77, 74, 75,
              76, 73, 75, 78, 74, 76, 72, 75, 74, 77]

# Clean 30-day SpO2 history: mean≈97, sd≈1
SPO2_HISTORY = [97, 98, 97, 96, 97, 98, 97, 97, 96, 98,
                97, 97, 98, 96, 97, 97, 98, 97, 96, 97,
                97, 98, 97, 97, 96, 98, 97, 97, 98, 97]


# ── TIER 3: Population default ─────────────────────────────────────────────

print("\n── TIER 3 — Population default: Heart rate (hr_bpm) ────────────────")

def test_hr_normal():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 78})
    assert alert_for(r["alerts"], "hr_bpm") is None

def test_hr_critical_low():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 35})
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "critical"
    assert a["threshold_basis"] == "default"
    assert a["notify"] == ["patient", "guardians", "doctor"]

def test_hr_warning_low():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 45})
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "warning"
    assert a["notify"] == ["patient"]

def test_hr_warning_high():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 120})
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "warning"
    assert a["notify"] == ["patient"]

def test_hr_critical_high():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 155})
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "critical"
    assert a["notify"] == ["patient", "guardians", "doctor"]

run("HR=78 → no alert", test_hr_normal)
run("HR=35 → critical low, notify=everyone, basis=default", test_hr_critical_low)
run("HR=45 → warning low, notify=patient only", test_hr_warning_low)
run("HR=120 → warning high, notify=patient only", test_hr_warning_high)
run("HR=155 → critical high, notify=everyone", test_hr_critical_high)


print("\n── TIER 3 — Population default: SpO2 (oxygen_spo2_pct) ─────────────")

def test_spo2_normal():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 97.0})
    assert alert_for(r["alerts"], "oxygen_spo2_pct") is None

def test_spo2_warning():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 90.0})
    a = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert a and a["severity"] == "warning" and a["notify"] == ["patient"]

def test_spo2_critical():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "oxygen_spo2_pct": 80.0})
    a = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert a and a["severity"] == "critical" and a["notify"] == ["patient", "guardians", "doctor"]

def test_spo2_critical_boundary():
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
run("SpO2=90% → warning, notify=patient only", test_spo2_warning)
run("SpO2=80% → critical, notify=everyone", test_spo2_critical)
run("SpO2=87% → critical (boundary <88)", test_spo2_critical_boundary)
run("SpO2=88% → warning (boundary 88-91)", test_spo2_warning_boundary)
run("SpO2=92% → no alert (normal floor)", test_spo2_normal_boundary)
run("SpO2=100% → no high-side alert", test_spo2_no_high_alert)


print("\n── TIER 3 — Population default: Respiratory (respiratory_rate_bpm) ──")

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
run("Respiratory=30 → critical high (≥30)", test_resp_critical_high)


print("\n── TIER 3 — Population default: Blood pressure ──────────────────────")

def test_bp_normal():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 118, "dbp_mmhg": 76}})
    assert alert_for(r["alerts"], "sbp_mmhg") is None
    assert alert_for(r["alerts"], "dbp_mmhg") is None

def test_bp_crisis_critical():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 185, "dbp_mmhg": 125}})
    assert alert_for(r["alerts"], "sbp_mmhg")["severity"] == "critical"
    assert alert_for(r["alerts"], "dbp_mmhg")["severity"] == "critical"

def test_bp_hypotension_critical():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 85, "dbp_mmhg": 55}})
    assert alert_for(r["alerts"], "sbp_mmhg")["severity"] == "critical"
    assert alert_for(r["alerts"], "dbp_mmhg")["severity"] == "critical"

def test_bp_warning_high():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 150, "dbp_mmhg": 95}})
    assert alert_for(r["alerts"], "sbp_mmhg")["severity"] == "warning"
    assert alert_for(r["alerts"], "dbp_mmhg")["severity"] == "warning"

def test_sbp_normal_ceiling():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 129, "dbp_mmhg": 76}})
    assert alert_for(r["alerts"], "sbp_mmhg") is None

def test_sbp_warning_at_boundary():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 130, "dbp_mmhg": 76}})
    assert alert_for(r["alerts"], "sbp_mmhg")["severity"] == "warning"

def test_dbp_normal_ceiling():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 118, "dbp_mmhg": 79}})
    assert alert_for(r["alerts"], "dbp_mmhg") is None

def test_dbp_warning_at_boundary():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "blood_pressure": {"sbp_mmhg": 118, "dbp_mmhg": 80}})
    assert alert_for(r["alerts"], "dbp_mmhg")["severity"] == "warning"

run("BP=118/76 → no alerts", test_bp_normal)
run("BP=185/125 → both critical", test_bp_crisis_critical)
run("BP=85/55 → both critical (hypotension)", test_bp_hypotension_critical)
run("BP=150/95 → both warning", test_bp_warning_high)
run("SBP=129 → no alert (normal ceiling)", test_sbp_normal_ceiling)
run("SBP=130 → warning (boundary)", test_sbp_warning_at_boundary)
run("DBP=79 → no alert (normal ceiling)", test_dbp_normal_ceiling)
run("DBP=80 → warning (boundary)", test_dbp_warning_at_boundary)


# ── TIER 2: Historical SD ──────────────────────────────────────────────────

print("\n── TIER 2 — Historical SD: basics ──────────────────────────────────")

# HR_HISTORY: mean≈75.1, sd≈1.8 → 2sd≈71.5/78.7, 3sd≈69.7/80.5
_hr_mean = statistics.mean(HR_HISTORY)
_hr_sd   = statistics.stdev(HR_HISTORY)

def test_sd_normal_within_2sd():
    # Value inside 2sd band → no alert (uses SD tier, not default)
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": round(_hr_mean)},
        patient_history={"hr_bpm": HR_HISTORY}
    )
    assert alert_for(r["alerts"], "hr_bpm") is None

def test_sd_warning_beyond_2sd_high():
    # Value >2sd above mean → warning, patient only
    trigger = _hr_mean + 2.5 * _hr_sd
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": round(trigger)},
        patient_history={"hr_bpm": HR_HISTORY}
    )
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "warning"
    assert a["threshold_basis"] == "historical_sd"
    assert a["notify"] == ["patient"]
    assert "baseline_mean" in a and "baseline_sd" in a

def test_sd_critical_beyond_3sd_high():
    # Value >3sd above mean → critical, everyone notified
    trigger = _hr_mean + 3.5 * _hr_sd
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": round(trigger)},
        patient_history={"hr_bpm": HR_HISTORY}
    )
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "critical"
    assert a["threshold_basis"] == "historical_sd"
    assert a["notify"] == ["patient", "guardians", "doctor"]

def test_sd_warning_beyond_2sd_low():
    # Value >2sd below mean → warning
    trigger = _hr_mean - 2.5 * _hr_sd
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": max(20, round(trigger))},
        patient_history={"hr_bpm": HR_HISTORY}
    )
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "warning"
    assert a["threshold_basis"] == "historical_sd"

def test_sd_critical_beyond_3sd_low():
    # Value >3sd below mean → critical
    trigger = _hr_mean - 3.5 * _hr_sd
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": max(20, round(trigger))},
        patient_history={"hr_bpm": HR_HISTORY}
    )
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "critical"
    assert a["threshold_basis"] == "historical_sd"

def test_sd_message_contains_baseline_info():
    trigger = _hr_mean + 2.5 * _hr_sd
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": round(trigger)},
        patient_history={"hr_bpm": HR_HISTORY}
    )
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and "personal baseline" in a["message"]
    assert "μ=" in a["message"] and "σ=" in a["message"]

run(f"HR=mean({round(_hr_mean)}) → no alert (within 2σ)", test_sd_normal_within_2sd)
run("HR>2σ above mean → warning, basis=historical_sd, notify=patient", test_sd_warning_beyond_2sd_high)
run("HR>3σ above mean → critical, notify=everyone", test_sd_critical_beyond_3sd_high)
run("HR>2σ below mean → warning", test_sd_warning_beyond_2sd_low)
run("HR>3σ below mean → critical", test_sd_critical_beyond_3sd_low)
run("SD alert message contains μ, σ, 'personal baseline'", test_sd_message_contains_baseline_info)


print("\n── TIER 2 — Historical SD: fallback conditions ──────────────────────")

def test_sd_fallback_insufficient_readings():
    # Fewer than HISTORY_MIN_READINGS → falls through to default
    short_history = {"hr_bpm": [72, 75, 78, 74, 76]}  # only 5 readings
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": 155},
        patient_history=short_history
    )
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["threshold_basis"] == "default"

def test_sd_fallback_zero_variance():
    # All identical readings → SD=0, falls through to default
    flat_history = {"hr_bpm": [75] * 20}
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": 155},
        patient_history=flat_history
    )
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["threshold_basis"] == "default"

def test_sd_no_history_uses_default():
    # No patient_history at all → default
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 155})
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["threshold_basis"] == "default"

def test_sd_history_for_one_param_default_for_others():
    # History only for hr_bpm — SpO2 should still use default
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": round(_hr_mean), "oxygen_spo2_pct": 80.0},
        patient_history={"hr_bpm": HR_HISTORY}
    )
    spo2_alert = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert spo2_alert and spo2_alert["threshold_basis"] == "default"

run("< min readings → falls through to default", test_sd_fallback_insufficient_readings)
run("SD=0 (all identical) → falls through to default", test_sd_fallback_zero_variance)
run("No patient_history passed → default used", test_sd_no_history_uses_default)
run("History for HR only → SpO2 still uses default", test_sd_history_for_one_param_default_for_others)


# ── TIER 1: Doctor-set overrides ───────────────────────────────────────────

print("\n── TIER 1 — Doctor-set overrides ────────────────────────────────────")

def test_doctor_override_beats_sd_and_default():
    # Doctor override wins even when history is also available
    doctor_thresholds = {
        "hr_bpm": {
            "critical_low": 45, "warning_low": 55,
            "warning_high": 110, "critical_high": 140,
        }
    }
    # 142 BPM — would be critical under default (≥150 is default critical,
    # but 142 is warning 101-149 under default). Under doctor override it IS critical (≥140).
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": 142},
        doctor_thresholds=doctor_thresholds,
        patient_history={"hr_bpm": HR_HISTORY}
    )
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["severity"] == "critical"
    assert a["threshold_basis"] == "doctor_set"

def test_doctor_override_spo2_cobd_patient():
    # COPD patient: doctor lowers critical threshold to 85
    doctor_thresholds = {
        "oxygen_spo2_pct": {
            "critical_low": 85, "warning_low": 88,
            "warning_high": None, "critical_high": None,
        }
    }
    # 86% is critical under default (<88), warning under doctor override (<85 is critical)
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "oxygen_spo2_pct": 86.0},
        doctor_thresholds=doctor_thresholds
    )
    a = alert_for(r["alerts"], "oxygen_spo2_pct")
    assert a and a["severity"] == "warning"
    assert a["threshold_basis"] == "doctor_set"
    assert a["notify"] == ["patient"]

def test_doctor_override_chf_sbp():
    # CHF patient: lower SBP baseline — 85 mmHg should not be critical for them
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
    assert alert_for(r["alerts"], "sbp_mmhg") is None

def test_unoverridden_param_uses_next_tier():
    # Doctor overrides SpO2, but HR has history → HR uses SD tier
    doctor_thresholds = {
        "oxygen_spo2_pct": {
            "critical_low": 85, "warning_low": 88,
            "warning_high": None, "critical_high": None,
        }
    }
    trigger = _hr_mean + 2.5 * _hr_sd
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": round(trigger)},
        doctor_thresholds=doctor_thresholds,
        patient_history={"hr_bpm": HR_HISTORY}
    )
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["threshold_basis"] == "historical_sd"

def test_empty_doctor_thresholds_falls_through():
    r = RuleEngineService.evaluate(
        {**NORMAL_VITALS, "hr_bpm": 155},
        doctor_thresholds={}
    )
    a = alert_for(r["alerts"], "hr_bpm")
    assert a and a["threshold_basis"] == "default"

run("Doctor override wins even when history also available", test_doctor_override_beats_sd_and_default)
run("Doctor override (SpO2 COPD) → 86% is warning, not critical", test_doctor_override_spo2_cobd_patient)
run("Doctor override (SBP CHF) → 85 mmHg not flagged", test_doctor_override_chf_sbp)
run("Doctor overrides SpO2 → HR falls through to SD tier", test_unoverridden_param_uses_next_tier)
run("Empty doctor_thresholds → falls through to next tier", test_empty_doctor_thresholds_falls_through)


# ── Out-of-scope parameters ────────────────────────────────────────────────

print("\n── Out-of-scope parameters (ignored entirely) ─────────────────────")

def test_out_of_scope_produce_no_alerts():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, **OUT_OF_SCOPE_VITALS})
    out_of_scope = {"glucose_mgdl","cholesterol_mgdl","hemoglobin_gdl",
                    "temperature_f","fall_detected","ecg","stethoscope"}
    alerted = {a["parameter"] for a in r["alerts"]}
    assert not (alerted & out_of_scope), f"leaked: {alerted & out_of_scope}"

def test_out_of_scope_dont_affect_severity():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, **OUT_OF_SCOPE_VITALS})
    assert r["highest_severity"] == "none"
    assert r["alert_count"] == 0

run("All out-of-scope critical values → none in alerts", test_out_of_scope_produce_no_alerts)
run("Out-of-scope fields → highest_severity=none, alert_count=0", test_out_of_scope_dont_affect_severity)


# ── Multi-alert / notify routing ────────────────────────────────────────────

print("\n── Multi-alert behaviour & notify routing ───────────────────────────")

def test_multiple_alerts_all_returned():
    r = RuleEngineService.evaluate({
        **NORMAL_VITALS,
        "oxygen_spo2_pct": 80.0,
        "respiratory_rate_bpm": 30,
        "hr_bpm": 45,
    })
    params = {a["parameter"] for a in r["alerts"]}
    assert "oxygen_spo2_pct" in params
    assert "respiratory_rate_bpm" in params
    assert "hr_bpm" in params
    assert r["alert_count"] == 3

def test_highest_severity_critical_when_mixed():
    r = RuleEngineService.evaluate({
        **NORMAL_VITALS,
        "oxygen_spo2_pct": 80.0,
        "hr_bpm": 45,
    })
    assert r["highest_severity"] == "critical"

def test_clean_payload_no_alerts():
    r = RuleEngineService.evaluate(NORMAL_VITALS)
    assert r["alert_count"] == 0
    assert r["highest_severity"] == "none"

def test_warning_notify_patient_only():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 45})
    a = alert_for(r["alerts"], "hr_bpm")
    assert a["notify"] == ["patient"]

def test_critical_notify_everyone():
    r = RuleEngineService.evaluate({**NORMAL_VITALS, "hr_bpm": 35})
    a = alert_for(r["alerts"], "hr_bpm")
    assert a["notify"] == ["patient", "guardians", "doctor"]

run("Multiple simultaneous alerts → all returned", test_multiple_alerts_all_returned)
run("Mixed critical+warning → highest_severity=critical", test_highest_severity_critical_when_mixed)
run("Clean payload → alert_count=0, highest_severity=none", test_clean_payload_no_alerts)
run("Warning alert → notify=['patient'] only", test_warning_notify_patient_only)
run("Critical alert → notify=['patient','guardians','doctor']", test_critical_notify_everyone)


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