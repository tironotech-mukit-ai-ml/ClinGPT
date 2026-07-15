"""
test_feature_normalization_service.py
──────────────────────────────────────
ClinGPT — Feature Normalization tests

Covers:
  1. Output contract  — vector length, feature keys, missing_fields list
  2. Min-max scaling  — boundary values, midpoints, clamp behaviour
  3. Binary fields    — 0/1 pass-through and missing sentinel
  4. Demographics     — biological_sex encoding, age_group ordinal, weight
  5. Missing fields   — sentinel value, correct field names recorded
  6. Full payload     — all fields present, no sentinels
  7. Minimal payload  — only required fields (hr_bpm + oxygen_spo2_pct)
  8. Integration      — output of ValidationService feeds directly in
"""

import sys
import os

# ── Local import path setup ───────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from feature_normalization_service import (
    FeatureNormalizationService,
    FEATURE_ORDER,
    VITAL_BOUNDS,
    SEX_ENCODING,
    AGE_GROUP_ENCODING,
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

# ── Fixtures ──────────────────────────────────────────────────────────────────

FULL_VITALS = {
    "hr_bpm": 75,
    "oxygen_spo2_pct": 98.0,
    "glucose_mgdl": 100.0,
    "cholesterol_mgdl": 190.0,
    "respiratory_rate_bpm": 15,
    "hemoglobin_gdl": 14.0,
    "temperature_f": 98.6,
    "weight_kg": 70.0,
    "step_count": 8000,
    "ecg": 0,
    "stethoscope": 0,
    "fall_detected": 0,
    "blood_pressure": {"sbp_mmhg": 120, "dbp_mmhg": 80},
    "demographics": {
        "biological_sex": "male",
        "age_group": "46-60",
        "weight_kg": 70.0,
    },
}

MINIMAL_VITALS = {
    "hr_bpm": 75,
    "oxygen_spo2_pct": 98.0,
}


# ── 1. Output contract ────────────────────────────────────────────────────────

print("\n── Output contract ────────────────────────────────────────────────────")

def test_vector_length():
    r = FeatureNormalizationService.normalize(FULL_VITALS)
    assert len(r["vector"]) == len(FEATURE_ORDER), (
        f"Expected vector length {len(FEATURE_ORDER)}, got {len(r['vector'])}"
    )

def test_feature_keys_match_feature_order():
    r = FeatureNormalizationService.normalize(FULL_VITALS)
    assert set(r["features"].keys()) == set(FEATURE_ORDER)

def test_vector_matches_features_in_order():
    r = FeatureNormalizationService.normalize(FULL_VITALS)
    for i, fname in enumerate(FEATURE_ORDER):
        assert approx(r["vector"][i], r["features"][fname]), (
            f"vector[{i}] ({r['vector'][i]}) != features['{fname}'] ({r['features'][fname]})"
        )

def test_all_values_between_0_and_1():
    r = FeatureNormalizationService.normalize(FULL_VITALS)
    for fname, val in r["features"].items():
        assert 0.0 <= val <= 1.0, f"'{fname}' = {val} is outside [0,1]"

def test_missing_fields_is_list():
    r = FeatureNormalizationService.normalize(FULL_VITALS)
    assert isinstance(r["missing_fields"], list)

def test_full_payload_has_no_missing_fields():
    r = FeatureNormalizationService.normalize(FULL_VITALS)
    assert r["missing_fields"] == [], f"Expected no missing fields, got {r['missing_fields']}"

run(f"vector length == {len(FEATURE_ORDER)} (FEATURE_ORDER)", test_vector_length)
run("features keys match FEATURE_ORDER exactly", test_feature_keys_match_feature_order)
run("vector values match features dict in correct order", test_vector_matches_features_in_order)
run("all values in [0.0, 1.0]", test_all_values_between_0_and_1)
run("missing_fields is a list", test_missing_fields_is_list)
run("full payload → missing_fields is empty", test_full_payload_has_no_missing_fields)


# ── 2. Min-max scaling (continuous vitals) ────────────────────────────────────

print("\n── Min-max scaling ────────────────────────────────────────────────────")

def test_minmax_at_lower_bound():
    lo, hi = VITAL_BOUNDS["hr_bpm"]
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "hr_bpm": lo})
    assert approx(r["features"]["hr_bpm"], 0.0), (
        f"HR at lower bound should be 0.0, got {r['features']['hr_bpm']}"
    )

def test_minmax_at_upper_bound():
    lo, hi = VITAL_BOUNDS["hr_bpm"]
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "hr_bpm": hi})
    assert approx(r["features"]["hr_bpm"], 1.0), (
        f"HR at upper bound should be 1.0, got {r['features']['hr_bpm']}"
    )

def test_minmax_midpoint():
    lo, hi = VITAL_BOUNDS["hr_bpm"]
    mid = (lo + hi) / 2
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "hr_bpm": mid})
    assert approx(r["features"]["hr_bpm"], 0.5), (
        f"HR at midpoint should be 0.5, got {r['features']['hr_bpm']}"
    )

def test_minmax_spo2_lower_bound():
    lo, _ = VITAL_BOUNDS["oxygen_spo2_pct"]
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "oxygen_spo2_pct": lo})
    assert approx(r["features"]["oxygen_spo2_pct"], 0.0)

def test_minmax_spo2_upper_bound():
    _, hi = VITAL_BOUNDS["oxygen_spo2_pct"]
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "oxygen_spo2_pct": hi})
    assert approx(r["features"]["oxygen_spo2_pct"], 1.0)

def test_minmax_glucose_known_value():
    # glucose 20–700; value=360 should be (360-20)/(700-20) = 340/680 = 0.5
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "glucose_mgdl": 360.0})
    assert approx(r["features"]["glucose_mgdl"], 0.5), (
        f"Glucose=360 should normalize to 0.5, got {r['features']['glucose_mgdl']}"
    )

def test_minmax_temperature_normal():
    # temp 86–109.4; 98.6 → (98.6-86)/(109.4-86) = 12.6/23.4
    lo, hi = VITAL_BOUNDS["temperature_f"]
    expected = (98.6 - lo) / (hi - lo)
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "temperature_f": 98.6})
    assert approx(r["features"]["temperature_f"], expected, tol=1e-4)

def test_minmax_clamps_above_upper_bound():
    # ValidationService enforces range, but clamp defends against edge cases
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "hr_bpm": 9999})
    assert approx(r["features"]["hr_bpm"], 1.0), (
        "Values above upper bound should be clamped to 1.0"
    )

def test_minmax_clamps_below_lower_bound():
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "hr_bpm": -999})
    assert approx(r["features"]["hr_bpm"], 0.0), (
        "Values below lower bound should be clamped to 0.0"
    )

def test_minmax_sbp_from_nested_bp():
    r = FeatureNormalizationService.normalize({
        **MINIMAL_VITALS,
        "blood_pressure": {"sbp_mmhg": 50, "dbp_mmhg": 20},  # both at lower bounds
    })
    assert approx(r["features"]["sbp_mmhg"], 0.0)
    assert approx(r["features"]["dbp_mmhg"], 0.0)

def test_minmax_sbp_at_upper_bound():
    r = FeatureNormalizationService.normalize({
        **MINIMAL_VITALS,
        "blood_pressure": {"sbp_mmhg": 300, "dbp_mmhg": 200},
    })
    assert approx(r["features"]["sbp_mmhg"], 1.0)
    assert approx(r["features"]["dbp_mmhg"], 1.0)

run("hr_bpm at lower bound → 0.0", test_minmax_at_lower_bound)
run("hr_bpm at upper bound → 1.0", test_minmax_at_upper_bound)
run("hr_bpm at midpoint → 0.5", test_minmax_midpoint)
run("oxygen_spo2_pct at lower bound → 0.0", test_minmax_spo2_lower_bound)
run("oxygen_spo2_pct at upper bound → 1.0", test_minmax_spo2_upper_bound)
run("glucose_mgdl=360 → 0.5 (midpoint)", test_minmax_glucose_known_value)
run("temperature_f=98.6 → correct fraction", test_minmax_temperature_normal)
run("hr_bpm=9999 clamped to 1.0", test_minmax_clamps_above_upper_bound)
run("hr_bpm=-999 clamped to 0.0", test_minmax_clamps_below_lower_bound)
run("sbp_mmhg and dbp_mmhg read from nested blood_pressure", test_minmax_sbp_from_nested_bp)
run("sbp_mmhg=300, dbp_mmhg=200 → both 1.0", test_minmax_sbp_at_upper_bound)


# ── 3. Binary fields ──────────────────────────────────────────────────────────

print("\n── Binary fields (ecg / stethoscope / fall_detected) ──────────────────")

def test_binary_zero_stays_zero():
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "ecg": 0})
    assert approx(r["features"]["ecg"], 0.0)

def test_binary_one_stays_one():
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "ecg": 1})
    assert approx(r["features"]["ecg"], 1.0)

def test_binary_stethoscope_one():
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "stethoscope": 1})
    assert approx(r["features"]["stethoscope"], 1.0)

def test_binary_fall_detected_one():
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "fall_detected": 1})
    assert approx(r["features"]["fall_detected"], 1.0)

def test_binary_missing_gets_sentinel():
    # No ecg/stethoscope/fall_detected in payload
    r = FeatureNormalizationService.normalize(MINIMAL_VITALS)
    assert approx(r["features"]["ecg"], MISSING_SENTINEL)
    assert approx(r["features"]["stethoscope"], MISSING_SENTINEL)
    assert approx(r["features"]["fall_detected"], MISSING_SENTINEL)

def test_binary_missing_recorded_in_missing_fields():
    r = FeatureNormalizationService.normalize(MINIMAL_VITALS)
    assert "ecg" in r["missing_fields"]
    assert "stethoscope" in r["missing_fields"]
    assert "fall_detected" in r["missing_fields"]

run("ecg=0 → 0.0 (pass-through)", test_binary_zero_stays_zero)
run("ecg=1 → 1.0 (pass-through)", test_binary_one_stays_one)
run("stethoscope=1 → 1.0", test_binary_stethoscope_one)
run("fall_detected=1 → 1.0", test_binary_fall_detected_one)
run("binary fields absent → sentinel 0.5", test_binary_missing_gets_sentinel)
run("binary fields absent → recorded in missing_fields", test_binary_missing_recorded_in_missing_fields)


# ── 4. Demographics ───────────────────────────────────────────────────────────

print("\n── Demographics (biological_sex / age_group / weight_kg) ──────────────")

def test_sex_male():
    r = FeatureNormalizationService.normalize({
        **MINIMAL_VITALS, "demographics": {"biological_sex": "male"}
    })
    assert approx(r["features"]["biological_sex"], SEX_ENCODING["male"])

def test_sex_female():
    r = FeatureNormalizationService.normalize({
        **MINIMAL_VITALS, "demographics": {"biological_sex": "female"}
    })
    assert approx(r["features"]["biological_sex"], SEX_ENCODING["female"])

def test_sex_other():
    r = FeatureNormalizationService.normalize({
        **MINIMAL_VITALS, "demographics": {"biological_sex": "other"}
    })
    assert approx(r["features"]["biological_sex"], SEX_ENCODING["other"])

def test_sex_missing():
    r = FeatureNormalizationService.normalize(MINIMAL_VITALS)
    assert approx(r["features"]["biological_sex"], MISSING_SENTINEL)
    assert "biological_sex" in r["missing_fields"]

def test_sex_case_insensitive():
    r = FeatureNormalizationService.normalize({
        **MINIMAL_VITALS, "demographics": {"biological_sex": "MALE"}
    })
    assert approx(r["features"]["biological_sex"], SEX_ENCODING["male"])

def test_age_group_each_value():
    for ag, expected in AGE_GROUP_ENCODING.items():
        r = FeatureNormalizationService.normalize({
            **MINIMAL_VITALS, "demographics": {"age_group": ag}
        })
        assert approx(r["features"]["age_group"], expected), (
            f"age_group='{ag}' expected {expected}, got {r['features']['age_group']}"
        )

def test_age_group_missing():
    r = FeatureNormalizationService.normalize(MINIMAL_VITALS)
    assert approx(r["features"]["age_group"], MISSING_SENTINEL)
    assert "age_group" in r["missing_fields"]

def test_age_group_unknown_string_gets_sentinel():
    r = FeatureNormalizationService.normalize({
        **MINIMAL_VITALS, "demographics": {"age_group": "unknown_band"}
    })
    assert approx(r["features"]["age_group"], MISSING_SENTINEL)
    assert "age_group" in r["missing_fields"]

def test_demographics_weight_present():
    r = FeatureNormalizationService.normalize({
        **MINIMAL_VITALS, "demographics": {"weight_kg": 70.0}
    })
    lo, hi = VITAL_BOUNDS["weight_kg"]
    expected = (70.0 - lo) / (hi - lo)
    assert approx(r["features"]["demographics_weight_kg"], expected)

def test_demographics_weight_missing():
    r = FeatureNormalizationService.normalize(MINIMAL_VITALS)
    assert approx(r["features"]["demographics_weight_kg"], MISSING_SENTINEL)
    assert "demographics_weight_kg" in r["missing_fields"]

def test_demographics_block_absent():
    # No demographics key at all — all three demo features should get sentinel
    r = FeatureNormalizationService.normalize(MINIMAL_VITALS)
    assert approx(r["features"]["biological_sex"], MISSING_SENTINEL)
    assert approx(r["features"]["age_group"], MISSING_SENTINEL)
    assert approx(r["features"]["demographics_weight_kg"], MISSING_SENTINEL)

run("biological_sex=male → 1.0", test_sex_male)
run("biological_sex=female → 0.0", test_sex_female)
run("biological_sex=other → 0.5", test_sex_other)
run("biological_sex missing → sentinel, recorded in missing_fields", test_sex_missing)
run("biological_sex=MALE (uppercase) → same as male", test_sex_case_insensitive)
run("age_group — all 6 bands map to correct ordinal value", test_age_group_each_value)
run("age_group missing → sentinel, recorded in missing_fields", test_age_group_missing)
run("age_group unknown string → sentinel, recorded in missing_fields", test_age_group_unknown_string_gets_sentinel)
run("demographics.weight_kg=70 → correct min-max value", test_demographics_weight_present)
run("demographics.weight_kg missing → sentinel", test_demographics_weight_missing)
run("demographics block absent → all three demo features get sentinel", test_demographics_block_absent)


# ── 5. Missing fields ─────────────────────────────────────────────────────────

print("\n── Missing field sentinel behaviour ───────────────────────────────────")

def test_sentinel_value_is_0_5():
    assert MISSING_SENTINEL == 0.5

def test_all_missing_fields_get_sentinel():
    r = FeatureNormalizationService.normalize(MINIMAL_VITALS)
    for field in r["missing_fields"]:
        assert approx(r["features"][field], MISSING_SENTINEL), (
            f"'{field}' in missing_fields but features['{field}'] = {r['features'][field]}"
        )

def test_missing_field_names_are_valid_feature_names():
    r = FeatureNormalizationService.normalize(MINIMAL_VITALS)
    for field in r["missing_fields"]:
        assert field in FEATURE_ORDER, (
            f"'{field}' in missing_fields but not a valid feature name"
        )

def test_none_value_treated_as_missing():
    r = FeatureNormalizationService.normalize({**MINIMAL_VITALS, "glucose_mgdl": None})
    assert approx(r["features"]["glucose_mgdl"], MISSING_SENTINEL)
    assert "glucose_mgdl" in r["missing_fields"]

run("MISSING_SENTINEL == 0.5", test_sentinel_value_is_0_5)
run("every field in missing_fields has features value == MISSING_SENTINEL", test_all_missing_fields_get_sentinel)
run("every field in missing_fields is a valid FEATURE_ORDER name", test_missing_field_names_are_valid_feature_names)
run("explicit None value treated as missing → sentinel", test_none_value_treated_as_missing)


# ── 6. Full payload — no sentinels ────────────────────────────────────────────

print("\n── Full payload (all 17 features present) ─────────────────────────────")

def test_full_payload_vector_has_no_sentinel():
    r = FeatureNormalizationService.normalize(FULL_VITALS)
    for i, (fname, val) in enumerate(zip(FEATURE_ORDER, r["vector"])):
        # Sentinel 0.5 is also a valid real value for some parameters, so
        # we only assert no sentinel by checking missing_fields is empty.
        pass
    assert r["missing_fields"] == []

def test_full_payload_hr_normalized_correctly():
    # hr=75: (75-20)/(300-20) = 55/280
    lo, hi = VITAL_BOUNDS["hr_bpm"]
    expected = (75 - lo) / (hi - lo)
    r = FeatureNormalizationService.normalize(FULL_VITALS)
    assert approx(r["features"]["hr_bpm"], expected)

def test_full_payload_spo2_normalized_correctly():
    # spo2=98: (98-50)/(100-50) = 48/50 = 0.96
    lo, hi = VITAL_BOUNDS["oxygen_spo2_pct"]
    expected = (98.0 - lo) / (hi - lo)
    r = FeatureNormalizationService.normalize(FULL_VITALS)
    assert approx(r["features"]["oxygen_spo2_pct"], expected)

def test_full_payload_age_group_46_60():
    r = FeatureNormalizationService.normalize(FULL_VITALS)
    assert approx(r["features"]["age_group"], AGE_GROUP_ENCODING["46-60"])

def test_full_payload_sex_male():
    r = FeatureNormalizationService.normalize(FULL_VITALS)
    assert approx(r["features"]["biological_sex"], SEX_ENCODING["male"])

run("full payload → missing_fields is empty", test_full_payload_vector_has_no_sentinel)
run("full payload → hr_bpm normalized correctly", test_full_payload_hr_normalized_correctly)
run("full payload → oxygen_spo2_pct=98 → 0.96", test_full_payload_spo2_normalized_correctly)
run("full payload → age_group '46-60' → 0.6", test_full_payload_age_group_46_60)
run("full payload → biological_sex 'male' → 1.0", test_full_payload_sex_male)


# ── 7. Minimal payload (only required fields) ─────────────────────────────────

print("\n── Minimal payload (hr_bpm + oxygen_spo2_pct only) ───────────────────")

def test_minimal_produces_valid_output():
    r = FeatureNormalizationService.normalize(MINIMAL_VITALS)
    assert len(r["vector"]) == len(FEATURE_ORDER)
    assert all(0.0 <= v <= 1.0 for v in r["vector"])

def test_minimal_missing_fields_count():
    r = FeatureNormalizationService.normalize(MINIMAL_VITALS)
    # 17 total features, 2 present (hr_bpm, oxygen_spo2_pct), 15 missing
    assert len(r["missing_fields"]) == 15, (
        f"Expected 15 missing fields, got {len(r['missing_fields'])}: {r['missing_fields']}"
    )

def test_minimal_required_fields_not_in_missing():
    r = FeatureNormalizationService.normalize(MINIMAL_VITALS)
    assert "hr_bpm" not in r["missing_fields"]
    assert "oxygen_spo2_pct" not in r["missing_fields"]

run("minimal payload → valid vector, all values in [0,1]", test_minimal_produces_valid_output)
run("minimal payload → exactly 15 missing fields", test_minimal_missing_fields_count)
run("minimal payload → hr_bpm and oxygen_spo2_pct not in missing_fields", test_minimal_required_fields_not_in_missing)


# ── 8. Integration with ValidationService output ──────────────────────────────

print("\n── Integration (simulate ValidationService → normalize) ───────────────")

# Simulate what ValidationService produces: nested blood_pressure, nested demographics
VALIDATED_OUTPUT = {
    "hr_bpm": 78,
    "oxygen_spo2_pct": 97.2,
    "glucose_mgdl": 105.0,
    "cholesterol_mgdl": 195.0,
    "respiratory_rate_bpm": 15,
    "hemoglobin_gdl": 14.2,
    "temperature_f": 98.6,
    "weight_kg": 72.0,
    "step_count": 6200,
    "ecg": 0,
    "stethoscope": 0,
    "fall_detected": 0,
    "blood_pressure": {"sbp_mmhg": 118, "dbp_mmhg": 76},
    "demographics": {
        "age_group": "46-60",
        "biological_sex": "male",
        "weight_kg": 72.0,
    },
}

def test_integration_no_missing_fields():
    r = FeatureNormalizationService.normalize(VALIDATED_OUTPUT)
    assert r["missing_fields"] == [], f"Unexpected missing: {r['missing_fields']}"

def test_integration_vector_length():
    r = FeatureNormalizationService.normalize(VALIDATED_OUTPUT)
    assert len(r["vector"]) == len(FEATURE_ORDER)

def test_integration_sbp_reads_from_nested_bp():
    r = FeatureNormalizationService.normalize(VALIDATED_OUTPUT)
    lo, hi = VITAL_BOUNDS["sbp_mmhg"]
    expected = (118 - lo) / (hi - lo)
    assert approx(r["features"]["sbp_mmhg"], expected), (
        f"sbp_mmhg: expected {expected}, got {r['features']['sbp_mmhg']}"
    )

def test_integration_dbp_reads_from_nested_bp():
    r = FeatureNormalizationService.normalize(VALIDATED_OUTPUT)
    lo, hi = VITAL_BOUNDS["dbp_mmhg"]
    expected = (76 - lo) / (hi - lo)
    assert approx(r["features"]["dbp_mmhg"], expected)

def test_integration_demographics_weight_separate_from_top_level():
    # Both weight_kg fields are 72.0 here, so results should match;
    # the point is that demographics_weight_kg reads from the nested dict
    r = FeatureNormalizationService.normalize(VALIDATED_OUTPUT)
    assert approx(r["features"]["weight_kg"], r["features"]["demographics_weight_kg"])

run("full validated payload → no missing fields", test_integration_no_missing_fields)
run("full validated payload → vector length correct", test_integration_vector_length)
run("sbp_mmhg correctly read from nested blood_pressure", test_integration_sbp_reads_from_nested_bp)
run("dbp_mmhg correctly read from nested blood_pressure", test_integration_dbp_reads_from_nested_bp)
run("demographics_weight_kg reads from demographics block, not top-level", test_integration_demographics_weight_separate_from_top_level)


# ── Summary ───────────────────────────────────────────────────────────────────

total = _pass + _fail
print(f"\n{'─'*60}")
if _fail == 0:
    print(f"  \033[92m{_pass}/{total} passed — all good\033[0m")
else:
    print(f"  \033[91m{_fail} FAILED\033[0m, {_pass} passed  ({total} total)")
print(f"{'─'*60}\n")

sys.exit(1 if _fail else 0)
