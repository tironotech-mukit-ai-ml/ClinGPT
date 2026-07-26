"""
report_context_service.py
────────────────────────────
ClinGPT — Report Context Builder

Final stage before the LLM. Takes the OUTPUTS of RuleEngineService,
FAISSRetrievalService, and the XGBoost model — all of which deal in
numbers, vectors, and IDs — and resolves everything back to raw,
human-readable clinical values before it ever reaches a prompt.

HARD RULE: no normalized 0.0-1.0 feature values are ever included in
the LLM context. Every number handed to the LLM has a real unit
attached (bpm, %, mmHg, etc.) and comes from the raw VitalReading /
case record, looked up by ID — never from the FAISS vector itself.

Position in the pipeline:
    ValidationService → RuleEngineService → FeatureNormalizationService
                                                      ↓
                                            FAISSRetrievalService (returns IDs + distances)
                                            XGBoost (returns risk_label + probability)
                                                      ↓
                                            ReportContextService  ←── YOU ARE HERE
                                                      ↓
                                                  LLM prompt

Usage:
    context = ReportContextService.build_context(
        current_case_raw=raw_vitals_dict,        # this patient's real values
        demographics=demo_dict,
        rule_engine_result=rule_result,           # from RuleEngineService.evaluate()
        ml_prediction={"risk_label": "high", "probability": 0.87},
        faiss_neighbors=[(row_id, distance), ...], # from FAISSRetrievalService
        metadata_lookup=metadata_list,             # clingpt_metadata.json, loaded
    )
    prompt_text = ReportContextService.to_prompt_text(context)
"""

import json


class ReportContextService:

    @staticmethod
    def build_context(
        current_case_raw: dict,
        demographics: dict,
        rule_engine_result: dict,
        ml_prediction: dict,
        faiss_neighbors: list,      # [(faiss_row_id, distance), ...]
        metadata_lookup: list,      # indexable by faiss_row_id -> raw case metadata
    ) -> dict:
        """
        Resolves FAISS row IDs -> raw clinical values via metadata_lookup.
        Never touches a normalized vector. Returns a structured dict ready
        to be rendered into a prompt.
        """

        # ── Current patient reading — already raw, just pass through ─────────
        bp = current_case_raw.get("blood_pressure", {})
        current_reading = {
            "hr_bpm":               current_case_raw.get("hr_bpm"),
            "oxygen_spo2_pct":      current_case_raw.get("oxygen_spo2_pct"),
            "respiratory_rate_bpm": current_case_raw.get("respiratory_rate_bpm"),
            "sbp_mmhg":             bp.get("sbp_mmhg"),
            "dbp_mmhg":             bp.get("dbp_mmhg"),
            "glucose_mgdl":         current_case_raw.get("glucose_mgdl"),
            "cholesterol_mgdl":     current_case_raw.get("cholesterol_mgdl"),
            "hemoglobin_gdl":       current_case_raw.get("hemoglobin_gdl"),
            "temperature_f":        current_case_raw.get("temperature_f"),
            "weight_kg":            current_case_raw.get("weight_kg"),
            "step_count":           current_case_raw.get("step_count"),
            "ecg":                  current_case_raw.get("ecg"),
            "stethoscope":          current_case_raw.get("stethoscope"),
            "fall_detected":        current_case_raw.get("fall_detected"),
            "age_group":            demographics.get("age_group"),
            "biological_sex":       demographics.get("biological_sex"),
        }

        # ── Rule Engine alerts — already human-readable strings, pass through ─
        alerts = [a["message"] for a in rule_engine_result.get("alerts", [])]
        highest_severity = rule_engine_result.get("highest_severity", "none")

        # ── ML prediction — plain sentence, not a raw label ───────────────────
        ml_summary = {
            "risk_label":          ml_prediction.get("risk_label"),
            "risk_score":          ml_prediction.get("risk_score"),
            "class_probabilities": ml_prediction.get("class_probabilities"),
        }

        # ── FAISS neighbors — RESOLVE ID -> raw values here. This is the key step. ─
        similar_cases = []
        for faiss_row_id, distance in faiss_neighbors:
            record = metadata_lookup[faiss_row_id]     # <- lookup by ID, not the vector
            similar_cases.append({
                "similarity_distance": round(float(distance), 4),
                "age_group":           record.get("age_group"),
                "biological_sex":      record.get("biological_sex"),
                "vitals":              record.get("vitals", {}),   # RAW values
                "risk_label":          record.get("risk_label"),
                "doctor_suggestion":   record.get("doctor_suggestion"),  # None for DB-backed metadata (no such column yet)
            })

        return {
            "current_reading":  current_reading,
            "alerts":           alerts,
            "highest_severity": highest_severity,
            "ml_prediction":    ml_summary,
            "similar_cases":    similar_cases,
        }

    @staticmethod
    def to_prompt_text(context: dict) -> str:
        """Renders the structured context into plain text for the LLM prompt."""
        cr = context["current_reading"]
        lines = []

        lines.append("Current patient reading:")
        lines.append(
            f"  HR: {cr['hr_bpm']} bpm, SpO2: {cr['oxygen_spo2_pct']}%, "
            f"RR: {cr['respiratory_rate_bpm']}/min, "
            f"BP: {cr['sbp_mmhg']}/{cr['dbp_mmhg']} mmHg"
        )
        lines.append(
            f"  Glucose: {cr['glucose_mgdl']} mg/dL, Cholesterol: {cr['cholesterol_mgdl']} mg/dL, "
            f"Hemoglobin: {cr['hemoglobin_gdl']} g/dL"
        )
        lines.append(
            f"  Temp: {cr['temperature_f']}°F, Weight: {cr['weight_kg']} kg, "
            f"Steps: {cr['step_count']}"
        )
        lines.append(
            f"  ECG flag: {cr['ecg']}, Stethoscope flag: {cr['stethoscope']}, "
            f"Fall detected: {cr['fall_detected']}"
        )
        lines.append(f"  Age group: {cr['age_group']}, Sex: {cr['biological_sex']}")
        lines.append("")

        lines.append("Rule Engine alerts:")
        if context["alerts"]:
            for a in context["alerts"]:
                lines.append(f"  - {a}")
        else:
            lines.append("  - None. All monitored parameters within normal range.")
        lines.append(f"  Highest severity: {context['highest_severity']}")
        lines.append("")

        mp = context["ml_prediction"]
        if mp.get("risk_score") is not None:
            probs = mp.get("class_probabilities") or {}
            probs_str = ", ".join(f"{k}={v:.2f}" for k, v in probs.items())
            lines.append(
                f"ML risk prediction: {mp['risk_label']} "
                f"(risk_score={mp['risk_score']:.2f}) [{probs_str}]"
            )
        else:
            lines.append(f"ML risk prediction: {mp['risk_label']} (score unavailable)")
        lines.append("")

        lines.append(f"{len(context['similar_cases'])} most similar historical cases:")
        for i, sc in enumerate(context["similar_cases"], start=1):
            v = sc["vitals"]
            # blood pressure may be nested (JSON-prototype metadata) or flat
            # (real DB-backed metadata from build_faiss_index.py) — handle both.
            bp = v.get("blood_pressure") or {"sbp_mmhg": v.get("sbp_mmhg"), "dbp_mmhg": v.get("dbp_mmhg")}
            lines.append(
                f"  {i}. Age {sc['age_group']}, {sc['biological_sex']} — "
                f"HR {v.get('hr_bpm')}, SpO2 {v.get('oxygen_spo2_pct')}%, "
                f"BP {bp.get('sbp_mmhg')}/{bp.get('dbp_mmhg')} → risk={sc['risk_label']}"
            )
            if sc.get("doctor_suggestion"):
                lines.append(f"     Doctor note: \"{sc['doctor_suggestion']}\"")

        return "\n".join(lines)