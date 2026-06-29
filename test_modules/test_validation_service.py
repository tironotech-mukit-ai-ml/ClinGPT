"""
test_validation_service.py
──────────────────────────
Unit tests for ValidationService.

Run with:
    py test_modules/test_validation_service.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from apps.clin_gpt.services.validation_service import ValidationService

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


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_FULL = {
    "case_id": "abc-123",
    "demographics": {"age_group": "46-60", "biological_sex": "male", "weight_kg": 72.0},
    "hr_bpm": 78,
    "oxygen_spo2_pct": 97.2,
    "glucose_mgdl": 105.0,
    "cholesterol_mgdl": 195.0,
    "respiratory_rate_bpm": 15,
    "hemoglobin_gdl": 14.2,
    "temperature_f": 98.6,
    "blood_pressure": {"sbp_mmhg": 118, "dbp_mmhg": 76},
    "fall_detected": 0,
    "step_count": 6200,
    "weight_kg": 72.0,
    "ecg": 0,
    "stethoscope": 0,
}

VALID_MINIMAL = {
    "hr_bpm": 72,
    "oxygen_spo2_pct": 98.0,
}


# ── Tests ─────────────────────────────────────────────────────────────────────

print("\n── Required fields ─────────────────────────────────────────────────")

def test_missing_hr():
    r = ValidationService.validate({"oxygen_spo2_pct": 97.0})
    assert not r["valid"]
    assert any("hr_bpm" in e for e in r["errors"])

def test_missing_spo2():
    r = ValidationService.validate({"hr_bpm": 75})
    assert not r["valid"]
    assert any("oxygen_spo2_pct" in e for e in r["errors"])

def test_minimal_valid():
    r = ValidationService.validate(VALID_MINIMAL)
    assert r["valid"], r["errors"]
    assert r["data"]["hr_bpm"] == 72

run("Missing hr_bpm → rejected", test_missing_hr)
run("Missing oxygen_spo2_pct → rejected", test_missing_spo2)
run("Minimal valid payload (hr + spo2 only) → accepted", test_minimal_valid)


print("\n── Type coercion ────────────────────────────────────────────────────")

def test_string_int_coercion():
    r = ValidationService.validate({**VALID_MINIMAL, "hr_bpm": "82"})
    assert r["valid"], r["errors"]
    assert r["data"]["hr_bpm"] == 82
    assert isinstance(r["data"]["hr_bpm"], int)

def test_string_float_coercion():
    r = ValidationService.validate({**VALID_MINIMAL, "glucose_mgdl": "110.5"})
    assert r["valid"], r["errors"]
    assert r["data"]["glucose_mgdl"] == 110.5

def test_bad_type_rejected():
    r = ValidationService.validate({**VALID_MINIMAL, "hr_bpm": "not-a-number"})
    assert not r["valid"]
    assert any("hr_bpm" in e for e in r["errors"])

run("hr_bpm as string '82' → coerced to int", test_string_int_coercion)
run("glucose_mgdl as string '110.5' → coerced to float", test_string_float_coercion)
run("hr_bpm='not-a-number' → rejected", test_bad_type_rejected)


print("\n── Physiological range checks ───────────────────────────────────────")

def test_hr_too_low():
    r = ValidationService.validate({**VALID_MINIMAL, "hr_bpm": 5})
    assert not r["valid"]

def test_hr_too_high():
    r = ValidationService.validate({**VALID_MINIMAL, "hr_bpm": 350})
    assert not r["valid"]

def test_spo2_too_low():
    r = ValidationService.validate({**VALID_MINIMAL, "oxygen_spo2_pct": 30.0})
    assert not r["valid"]

def test_glucose_normal():
    r = ValidationService.validate({**VALID_MINIMAL, "glucose_mgdl": 95.0})
    assert r["valid"]
    assert r["data"]["glucose_mgdl"] == 95.0

def test_glucose_critical_low():
    r = ValidationService.validate({**VALID_MINIMAL, "glucose_mgdl": 45.0})
    assert r["valid"]  # critical but physiologically possible — Rule Engine handles alert

def test_glucose_impossible():
    r = ValidationService.validate({**VALID_MINIMAL, "glucose_mgdl": 5.0})
    assert not r["valid"]

run("HR=5 → rejected (below 20 BPM)", test_hr_too_low)
run("HR=350 → rejected (above 300 BPM)", test_hr_too_high)
run("SpO2=30% → rejected (below 50%)", test_spo2_too_low)
run("Glucose=95 mg/dL → accepted", test_glucose_normal)
run("Glucose=45 mg/dL → accepted (critical low but possible)", test_glucose_critical_low)
run("Glucose=5 mg/dL → rejected (impossible)", test_glucose_impossible)


print("\n── Temperature stored as °F (no conversion) ─────────────────────────")

def test_temp_normal():
    r = ValidationService.validate({**VALID_MINIMAL, "temperature_f": 98.6})
    assert r["valid"], r["errors"]
    assert r["data"]["temperature_f"] == 98.6
    # quality warning may appear on minimal payload — temp itself has no warning
    assert not any("temperature" in w for w in r["warnings"])

def test_temp_fever():
    r = ValidationService.validate({**VALID_MINIMAL, "temperature_f": 102.5})
    assert r["valid"], r["errors"]
    assert r["data"]["temperature_f"] == 102.5
    assert not any("temperature" in w for w in r["warnings"])

def test_temp_no_conversion_field():
    r = ValidationService.validate({**VALID_MINIMAL, "temperature_f": 98.6})
    assert "temperature_c" not in r["data"]  # no celsius field in output

def test_temp_too_low():
    r = ValidationService.validate({**VALID_MINIMAL, "temperature_f": 80.0})
    assert not r["valid"]
    assert any("temperature_f" in e for e in r["errors"])

def test_temp_too_high():
    r = ValidationService.validate({**VALID_MINIMAL, "temperature_f": 115.0})
    assert not r["valid"]

run("temperature_f=98.6°F → stored as-is, no warnings", test_temp_normal)
run("temperature_f=102.5°F (fever) → stored as-is, no warnings", test_temp_fever)
run("No temperature_c field in output", test_temp_no_conversion_field)
run("temperature_f=80.0°F → rejected (below 86°F range)", test_temp_too_low)
run("temperature_f=115.0°F → rejected (above 109.4°F range)", test_temp_too_high)


print("\n── Boolean field normalisation (ECG / Stethoscope / Fall) ──────────")

def test_ecg_zero():
    r = ValidationService.validate({**VALID_MINIMAL, "ecg": 0})
    assert r["valid"] and r["data"]["ecg"] == 0

def test_ecg_one():
    r = ValidationService.validate({**VALID_MINIMAL, "ecg": 1})
    assert r["valid"] and r["data"]["ecg"] == 1

def test_ecg_invalid():
    r = ValidationService.validate({**VALID_MINIMAL, "ecg": 2})
    assert not r["valid"]
    assert any("ecg" in e for e in r["errors"])

def test_fall_string_one():
    r = ValidationService.validate({**VALID_MINIMAL, "fall_detected": "1"})
    assert r["valid"] and r["data"]["fall_detected"] == 1

def test_stethoscope_invalid():
    r = ValidationService.validate({**VALID_MINIMAL, "stethoscope": -1})
    assert not r["valid"]

run("ecg=0 → accepted", test_ecg_zero)
run("ecg=1 → accepted", test_ecg_one)
run("ecg=2 → rejected (not 0 or 1)", test_ecg_invalid)
run("fall_detected='1' (string) → coerced to int 1", test_fall_string_one)
run("stethoscope=-1 → rejected", test_stethoscope_invalid)


print("\n── Blood pressure validation ────────────────────────────────────────")

def test_bp_nested_dict():
    r = ValidationService.validate({**VALID_MINIMAL, "blood_pressure": {"sbp_mmhg": 120, "dbp_mmhg": 80}})
    assert r["valid"]
    assert r["data"]["blood_pressure"]["sbp_mmhg"] == 120
    assert r["data"]["blood_pressure"]["dbp_mmhg"] == 80

def test_dbp_greater_than_sbp():
    r = ValidationService.validate({
        **VALID_MINIMAL,
        "blood_pressure": {"sbp_mmhg": 80, "dbp_mmhg": 120}
    })
    assert not r["valid"]
    assert any("DBP" in e for e in r["errors"])

def test_bp_crisis():
    r = ValidationService.validate({**VALID_MINIMAL, "blood_pressure": {"sbp_mmhg": 185, "dbp_mmhg": 115}})
    assert r["valid"]  # Crisis BP is physiologically possible — Rule Engine handles alert

run("Nested blood_pressure dict → flattened and validated", test_bp_nested_dict)
run("DBP > SBP → rejected", test_dbp_greater_than_sbp)
run("Crisis BP (185/115) → accepted (Rule Engine handles alert)", test_bp_crisis)


print("\n── Data quality score ───────────────────────────────────────────────")

def test_quality_minimal():
    r = ValidationService.validate(VALID_MINIMAL)
    assert r["valid"]
    assert r["quality_score"] < 0.3
    assert any("quality" in w.lower() for w in r["warnings"])

def test_quality_full():
    r = ValidationService.validate(VALID_FULL)
    assert r["valid"]
    assert r["quality_score"] >= 0.6

run("Minimal payload → low quality score + warning", test_quality_minimal)
run("Full payload → quality score ≥ 0.6", test_quality_full)


print("\n── Full valid payload ───────────────────────────────────────────────")

def test_full_valid_payload():
    r = ValidationService.validate(VALID_FULL)
    assert r["valid"], r["errors"]
    assert r["data"]["hr_bpm"] == 78
    assert r["data"]["oxygen_spo2_pct"] == 97.2
    assert r["data"]["temperature_f"] == 98.6     # stored as °F
    assert "temperature_c" not in r["data"]        # no celsius field
    assert r["data"]["blood_pressure"]["sbp_mmhg"] == 118
    assert r["data"]["ecg"] == 0
    assert r["data"]["fall_detected"] == 0
    assert r["data"]["demographics"]["biological_sex"] == "male"
    assert len(r["errors"]) == 0
    assert len(r["warnings"]) == 0                 # no warnings on clean full payload

run("Full payload → all fields clean, no errors, no warnings", test_full_valid_payload)


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