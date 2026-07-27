"""
Runs the FULL real pipeline stage-by-stage and prints output at each step:
Validation -> Rule Engine -> Normalization -> FAISS (KNN) -> ML (XGBoost)
-> Report Context -> LLM Report

Run directly in PyCharm: Right-click -> Run 'run_full_pipeline'
"""
import os
import json
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.clin_gpt.services.validation_service import ValidationService
from apps.clin_gpt.services.rule_engine_service import RuleEngineService
from apps.clin_gpt.services.feature_normalization_service import FeatureNormalizationService
from apps.clin_gpt.services.faiss_retrieval_service import FAISSRetrievalService
from apps.clin_gpt.services.ml_risk_prediction_service import MLRiskPredictionService
from apps.clin_gpt.services.report_context_service import ReportContextService
from apps.clin_gpt.services.openai_service import get_openai_service


def show(title, data):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print(json.dumps(data, indent=2, default=str))


# ── 0. Raw input data (what the pipeline receives) ─────────────────────────
RAW_INPUT = {
    "hr_bpm": 155,
    "oxygen_spo2_pct": 91.0,
    "respiratory_rate_bpm": 26,
    "blood_pressure": {"sbp_mmhg": 150, "dbp_mmhg": 95},
    "glucose_mgdl": 140.0,
    "cholesterol_mgdl": 220.0,
    "hemoglobin_gdl": 13.5,
    "temperature_f": 99.1,
    "weight_kg": 82.0,
    "step_count": 3000,
    "ecg": 0,
    "stethoscope": 0,
    "fall_detected": 0,
    "demographics": {
        "biological_sex": "male",
        "age_group": "46-60",
        "weight_kg": 82.0,
    },
}
show("STAGE 0: RAW INPUT", RAW_INPUT)

# ── 1. Validation ────────────────────────────────────────────────────────
val = ValidationService.validate(RAW_INPUT)
show("STAGE 1: AFTER VALIDATION", val)
if not val["valid"]:
    print("\nValidation failed — stopping here. Fix RAW_INPUT and re-run.")
    exit(1)

# ── 2. Rule Engine (critical/warning alerts) ────────────────────────────
rule_result = RuleEngineService.evaluate(val["data"])
show("STAGE 2: AFTER RULE ENGINE (alerts)", rule_result)

# ── 3. Normalization ─────────────────────────────────────────────────────
norm = FeatureNormalizationService.normalize(val["data"])
show("STAGE 3: AFTER NORMALIZATION (feature vector)", norm)

# ── 4. FAISS KNN search ──────────────────────────────────────────────────
faiss_neighbors = FAISSRetrievalService.search(norm["vector"], k=5)
show("STAGE 4: AFTER FAISS / KNN (nearest neighbors)", faiss_neighbors)

# ── 5. ML risk prediction (XGBoost) ──────────────────────────────────────
ml_result = MLRiskPredictionService.predict(norm["vector"], faiss_neighbors)
show("STAGE 5: AFTER ML PREDICTION (XGBoost)", ml_result)

# ── 6. Report Context (final data assembled for the LLM) ────────────────
metadata_path = os.path.join("apps", "clin_gpt", "data", "faiss_metadata.json")
with open(metadata_path) as f:
    metadata_lookup = json.load(f)

context = ReportContextService.build_context(
    current_case_raw=val["data"],
    demographics=val["data"].get("demographics", {}),
    rule_engine_result=rule_result,
    ml_prediction=ml_result,
    faiss_neighbors=[(n.get("faiss_row"), n.get("distance")) for n in faiss_neighbors],    metadata_lookup=metadata_lookup,
)
show("STAGE 6: FINAL DATA SENT TO LLM (report context)", context)

# ── 7. LLM report ─────────────────────────────────────────────────────────
openai_service = get_openai_service()
report = openai_service.generate_vitals_report(context)
show("STAGE 7: LLM REPORT (final output)", report)