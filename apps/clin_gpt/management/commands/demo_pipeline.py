"""
demo_pipeline.py
───────────────────
python manage.py demo_pipeline --external-ref ext-pt-1003
python manage.py demo_pipeline --reading-id 103

Prints the ENTIRE pipeline for one VitalReading, stage by stage, in
plain readable text — meant to be screenshotted or read directly to
show the pipeline actually working end-to-end:

    1. Raw values (what came in)
    2. Validation
    3. Rule Engine alerts (what fired, and why)
    4. Risk label (low/medium/high)
    5. FAISS similarity search — 5 most similar historical cases
    6. ML risk prediction (XGBoost, parallel second opinion)
    7. Final assembled context — exactly what would be handed to the LLM
    8. LLM-generated clinical report (real GPT-4o-mini call)

This is the full 8-stage pipeline, end to end, with real data.
"""

from django.core.management.base import BaseCommand

from apps.clin_gpt.models import VitalReading
from apps.clin_gpt.services.validation_service import ValidationService
from apps.clin_gpt.services.rule_engine_service import RuleEngineService
from apps.clin_gpt.services.feature_normalization_service import FeatureNormalizationService
from apps.clin_gpt.services.faiss_retrieval_service import FAISSRetrievalService
from apps.clin_gpt.services.ml_risk_prediction_service import MLRiskPredictionService
from apps.clin_gpt.services.report_context_service import ReportContextService
from apps.clin_gpt.services.openai_service import get_openai_service


class Command(BaseCommand):
    help = "Demo the full ClinGPT pipeline end-to-end for one existing VitalReading."

    def add_arguments(self, parser):
        parser.add_argument("--reading-id", type=int, default=None)
        parser.add_argument("--external-ref", type=str, default=None)

    def handle(self, *args, **options):
        reading = self._get_reading(options)
        if reading is None:
            self.stderr.write(self.style.ERROR(
                "No matching reading found. Pass --reading-id or --external-ref."
            ))
            return

        self._line("=")
        self._header("STAGE 1 — RAW INPUT (from device / DB)")
        self._print_raw(reading)

        # ── Stage 0.5: reconstruct the pre-validation raw shape and run it
        # through ValidationService LIVE, so this stage is actually shown
        # executing — not just assumed because it ran earlier at ingestion.
        raw_payload = self._to_raw_payload(reading)
        validation_result = ValidationService.validate(raw_payload)

        self._header("STAGE 2 — VALIDATION LAYER")
        self._print_validation_result(validation_result)

        if not validation_result["valid"]:
            self.stderr.write(self.style.ERROR("Validation failed — stopping demo here."))
            return

        rule_input = validation_result["data"]
        rule_result = RuleEngineService.evaluate(rule_input)

        self._header("STAGE 3 — RULE ENGINE")
        self._print_rule_result(rule_result)

        risk_label = {"none": "low", "warning": "medium", "critical": "high"}[
            rule_result["highest_severity"]
        ]
        self._header("STAGE 4 — RISK LABEL")
        self.stdout.write(f"  risk_label = {risk_label}")

        norm_input = dict(rule_input)
        norm_input["demographics"] = rule_input.get("demographics", {})
        norm = FeatureNormalizationService.normalize(norm_input)

        self._header("STAGE 5 — FAISS SIMILARITY SEARCH (5 nearest historical cases)")
        try:
            neighbors = FAISSRetrievalService.search(norm["vector"], k=5)
            self._print_neighbors(neighbors)
        except FileNotFoundError:
            self.stdout.write(self.style.WARNING("  FAISS index not found — run build_faiss_index."))
            neighbors = []

        self._header("STAGE 6 — ML RISK PREDICTION (XGBoost, parallel second opinion)")
        try:
            ml_prediction = MLRiskPredictionService.predict(norm["vector"], neighbors)
            self._print_ml_prediction(ml_prediction, rule_result)
        except FileNotFoundError:
            self.stdout.write(self.style.WARNING("  Risk model not found — run train_risk_model."))
            ml_prediction = {"risk_label": risk_label, "risk_score": None, "class_probabilities": {}}

        self._header("STAGE 7 — FINAL CONTEXT (this is what would be sent to the LLM)")
        context = ReportContextService.build_context(
            current_case_raw=self._as_vitals_dict(reading),
            demographics={"age_group": reading.patient.age_group,
                          "biological_sex": reading.patient.biological_sex},
            rule_engine_result=rule_result,
            ml_prediction=ml_prediction,
            faiss_neighbors=[(n["faiss_row"], n["distance"]) for n in neighbors],
            metadata_lookup=self._metadata_lookup_from_neighbors(neighbors),
        )
        self.stdout.write(ReportContextService.to_prompt_text(context))

        self._header("STAGE 8 — LLM REPORT GENERATION (real GPT-4o-mini call)")
        report = get_openai_service().generate_vitals_report(context)
        self._print_llm_report(report)

        self._line("=")

    # ── Lookup ────────────────────────────────────────────────────────────

    def _get_reading(self, options):
        if options["reading_id"]:
            return VitalReading.objects.select_related("patient").filter(
                id=options["reading_id"]
            ).first()
        if options["external_ref"]:
            return VitalReading.objects.select_related("patient").filter(
                patient__external_patient_ref=options["external_ref"]
            ).order_by("-recorded_at").first()
        return VitalReading.objects.select_related("patient").order_by("-recorded_at").first()

    # ── Formatting helpers ───────────────────────────────────────────────

    def _line(self, ch="-"):
        self.stdout.write(ch * 70)

    def _header(self, text):
        self._line()
        self.stdout.write(self.style.MIGRATE_HEADING(text))
        self._line()

    def _print_raw(self, r):
        self.stdout.write(f"  Patient ref: {r.patient.external_patient_ref or '(seed data, no external ref)'}")
        self.stdout.write(f"  Age group: {r.patient.age_group}, Sex: {r.patient.biological_sex}")
        self.stdout.write(f"  Recorded at: {r.recorded_at}")
        self.stdout.write("")
        self.stdout.write("  Two-tier alertable vitals:")
        self.stdout.write(f"    hr_bpm:               {r.hr_bpm} BPM")
        self.stdout.write(f"    oxygen_spo2_pct:      {r.oxygen_spo2_pct} %")
        self.stdout.write(f"    respiratory_rate_bpm: {r.respiratory_rate_bpm} breaths/min")
        self.stdout.write(f"    sbp_mmhg:             {r.sbp_mmhg} mmHg")
        self.stdout.write(f"    dbp_mmhg:             {r.dbp_mmhg} mmHg")
        self.stdout.write("")
        self.stdout.write("  Other vitals (feed FAISS/XGBoost, not alerted on):")
        self.stdout.write(f"    glucose_mgdl:         {r.glucose_mgdl} mg/dL")
        self.stdout.write(f"    cholesterol_mgdl:     {r.cholesterol_mgdl} mg/dL")
        self.stdout.write(f"    hemoglobin_gdl:       {r.hemoglobin_gdl} g/dL")
        self.stdout.write(f"    temperature_f:        {r.temperature_f} °F")
        self.stdout.write(f"    weight_kg:            {r.weight_kg} kg")
        self.stdout.write(f"    step_count:           {r.step_count} steps")
        self.stdout.write(f"    ecg:                  {int(r.ecg)}")
        self.stdout.write(f"    stethoscope:          {int(r.stethoscope)}")
        self.stdout.write(f"    fall_detected:        {int(r.fall_detected)}")

    def _print_rule_result(self, result):
        if not result["alerts"]:
            self.stdout.write("  No alerts. All monitored parameters within normal range.")
        for a in result["alerts"]:
            self.stdout.write(f"  [{a['severity'].upper()}] {a['message']}")
        self.stdout.write(f"  Highest severity: {result['highest_severity']}")

    def _print_neighbors(self, neighbors):
        for i, n in enumerate(neighbors, 1):
            v = n["vitals"]
            self.stdout.write(
                f"  {i}. distance={n['distance']:.4f}  risk={n['risk_label']}  "
                f"HR={v.get('hr_bpm')}  SpO2={v.get('oxygen_spo2_pct')}%  "
                f"BP={v.get('sbp_mmhg')}/{v.get('dbp_mmhg')}"
            )

    def _print_ml_prediction(self, prediction, rule_result):
        probs = prediction["class_probabilities"]
        self.stdout.write(f"  risk_score = {prediction['risk_score']}")
        self.stdout.write(f"  risk_label = {prediction['risk_label']}")
        self.stdout.write(f"  class probabilities: low={probs['low']:.4f}  "
                           f"medium={probs['medium']:.4f}  high={probs['high']:.4f}")
        self.stdout.write("")
        rule_risk = {"none": "low", "warning": "medium", "critical": "high"}[rule_result["highest_severity"]]
        agree = "AGREE" if rule_risk == prediction["risk_label"] else "DISAGREE"
        self.stdout.write(
            f"  Rule Engine says: {rule_risk}  |  XGBoost says: {prediction['risk_label']}  "
            f"-> {agree}"
        )

    def _print_llm_report(self, report):
        if report.get("error"):
            self.stderr.write(self.style.ERROR(f"  LLM call failed: {report['error']}"))
            self.stdout.write(f"  Fallback summary: {report.get('summary')}")
            return

        self.stdout.write(f"  Risk level: {report.get('risk_level')}  "
                           f"(confidence: {report.get('confidence')})")
        self.stdout.write("")
        self.stdout.write(f"  Summary: {report.get('summary')}")
        self.stdout.write("")

        concerns = report.get("concerns") or []
        self.stdout.write("  Concerns:")
        if concerns:
            for c in concerns:
                self.stdout.write(f"    - {c}")
        else:
            self.stdout.write("    - None")
        self.stdout.write("")

        recs = report.get("recommendations") or []
        self.stdout.write("  Recommendations:")
        if recs:
            for r in recs:
                self.stdout.write(f"    - {r}")
        else:
            self.stdout.write("    - None")
        self.stdout.write("")

        usage = report.get("usage") or {}
        self.stdout.write(
            f"  Model: {report.get('model')}  |  "
            f"Tokens: {usage.get('total_tokens', '?')} "
            f"(prompt={usage.get('prompt_tokens', '?')}, "
            f"completion={usage.get('completion_tokens', '?')})"
        )

        gr = report.get("guardrails") or {}
        self.stdout.write(
            f"  Guardrails: enabled={gr.get('enabled')}  "
            f"input_phi={gr.get('input_phi_detected', 0)}  "
            f"output_phi={gr.get('output_phi_detected', 0)}  "
            f"types={gr.get('phi_types_detected', [])}"
        )

    # ── Data shaping ─────────────────────────────────────────────────────

    def _to_raw_payload(self, r):
        """Reconstructs the payload shape as it would have looked BEFORE
        validation — flat sbp/dbp, demographics nested — so ValidationService
        actually has real work to do (type coercion, range checks, BP nesting)
        rather than being handed already-clean typed data."""
        return {
            "hr_bpm": r.hr_bpm,
            "oxygen_spo2_pct": r.oxygen_spo2_pct,
            "glucose_mgdl": r.glucose_mgdl,
            "cholesterol_mgdl": r.cholesterol_mgdl,
            "respiratory_rate_bpm": r.respiratory_rate_bpm,
            "hemoglobin_gdl": r.hemoglobin_gdl,
            "temperature_f": r.temperature_f,
            "sbp_mmhg": r.sbp_mmhg,
            "dbp_mmhg": r.dbp_mmhg,
            "step_count": r.step_count,
            "weight_kg": r.weight_kg,
            "ecg": int(r.ecg),
            "stethoscope": int(r.stethoscope),
            "fall_detected": int(r.fall_detected),
            "demographics": {
                "age_group": r.patient.age_group,
                "biological_sex": r.patient.biological_sex,
            },
        }

    def _print_validation_result(self, result):
        self.stdout.write(f"  valid = {result['valid']}")
        self.stdout.write(f"  quality_score = {result['quality_score']}")
        if result["warnings"]:
            for w in result["warnings"]:
                self.stdout.write(f"  [warning] {w}")
        if result["errors"]:
            for e in result["errors"]:
                self.stdout.write(f"  [error] {e}")
        if not result["warnings"] and not result["errors"]:
            self.stdout.write("  No issues — payload passed cleanly.")

    def _as_vitals_dict(self, r):
        return {
            "hr_bpm": r.hr_bpm, "oxygen_spo2_pct": r.oxygen_spo2_pct,
            "respiratory_rate_bpm": r.respiratory_rate_bpm,
            "blood_pressure": {"sbp_mmhg": r.sbp_mmhg, "dbp_mmhg": r.dbp_mmhg},
            "glucose_mgdl": r.glucose_mgdl, "cholesterol_mgdl": r.cholesterol_mgdl,
            "hemoglobin_gdl": r.hemoglobin_gdl, "temperature_f": r.temperature_f,
            "weight_kg": r.weight_kg, "step_count": r.step_count,
            "ecg": int(r.ecg), "stethoscope": int(r.stethoscope),
            "fall_detected": int(r.fall_detected),
        }

    def _metadata_lookup_from_neighbors(self, neighbors):
        """ReportContextService expects a list indexable by faiss_row. Build
        a minimal stand-in from the neighbor records FAISS already returned."""
        lookup = {}
        for n in neighbors:
            lookup[n["faiss_row"]] = n
        max_row = max(lookup.keys(), default=-1)
        return [lookup.get(i, {}) for i in range(max_row + 1)]