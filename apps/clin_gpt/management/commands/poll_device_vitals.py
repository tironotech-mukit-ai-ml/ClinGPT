"""
poll_device_vitals.py
────────────────────────
python manage.py poll_device_vitals

Manually-triggered polling command. Reads unprocessed rows from the
external `device_vitals_raw` MySQL table (the 'device_vitals' DB
connection), runs each through the full pipeline, writes the result to
Patient/VitalReading (the 'default' DB), and marks the source row
processed=1 so it isn't picked up again.

Pipeline per row:
    raw MySQL row → ValidationService.validate()
                   → RuleEngineService.evaluate()
                   → FeatureNormalizationService.normalize()  (vector, FAISS-only)
                   → FAISSRetrievalService.search()            (optional, logged only)
                   → Patient / VitalReading write (default DB)
                   → UPDATE device_vitals_raw SET processed=1 (device_vitals DB)

Note: does NOT rebuild the FAISS index automatically — run
`python manage.py build_faiss_index` separately if you want newly
polled readings included in the similarity index.
"""

from django.core.management.base import BaseCommand
from django.db import connections, transaction

from apps.clin_gpt.models import Patient, VitalReading
from apps.clin_gpt.services.validation_service import ValidationService
from apps.clin_gpt.services.rule_engine_service import RuleEngineService
from apps.clin_gpt.services.feature_normalization_service import FeatureNormalizationService
from apps.clin_gpt.services.faiss_retrieval_service import FAISSRetrievalService

SEVERITY_TO_RISK_LABEL = {
    "none":     "low",
    "warning":  "medium",
    "critical": "high",
}

SELECT_UNPROCESSED_SQL = """
    SELECT id, device_id, external_patient_ref, recorded_at,
           hr_bpm, oxygen_spo2_pct, glucose_mgdl, cholesterol_mgdl,
           respiratory_rate_bpm, hemoglobin_gdl, temperature_f,
           sbp_mmhg, dbp_mmhg, step_count, weight_kg,
           ecg, stethoscope, fall_detected,
           demographics_age_group, demographics_biological_sex
    FROM device_vitals_raw
    WHERE processed = 0
    ORDER BY id
"""

MARK_PROCESSED_SQL = """
    UPDATE device_vitals_raw
    SET processed = 1, processed_at = NOW()
    WHERE id = %s
"""


class Command(BaseCommand):
    help = "Poll device_vitals_raw for unprocessed rows and run them through the full ClinGPT pipeline."

    def handle(self, *args, **options):
        rows = self._fetch_unprocessed_rows()
        if not rows:
            self.stdout.write("No unprocessed rows found.")
            return

        self.stdout.write(f"Found {len(rows)} unprocessed row(s).")

        succeeded, failed = 0, 0
        for row in rows:
            try:
                self._process_row(row)
                self._mark_processed(row["id"])
                succeeded += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  row {row['id']} ({row['device_id']}): OK"
                ))
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(
                    f"  row {row['id']} ({row['device_id']}): FAILED — {exc}"
                ))
                # Deliberately NOT marking this row processed — it should be
                # retried on the next poll, not silently dropped.

        self.stdout.write(self.style.SUCCESS(
            f"Done. {succeeded} succeeded, {failed} failed, {len(rows)} total."
        ))

    # ── DB access (raw SQL — external table, Django doesn't own its schema) ──

    def _fetch_unprocessed_rows(self):
        cursor = connections["device_vitals"].cursor()
        cursor.execute(SELECT_UNPROCESSED_SQL)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _mark_processed(self, row_id):
        cursor = connections["device_vitals"].cursor()
        cursor.execute(MARK_PROCESSED_SQL, [row_id])

    # ── Pipeline ──────────────────────────────────────────────────────────

    @transaction.atomic
    def _process_row(self, row):
        # ── 1. Build raw payload -> ValidationService ────────────────────
        raw_payload = {
            "hr_bpm":               row["hr_bpm"],
            "oxygen_spo2_pct":      row["oxygen_spo2_pct"],
            "glucose_mgdl":         row["glucose_mgdl"],
            "cholesterol_mgdl":     row["cholesterol_mgdl"],
            "respiratory_rate_bpm": row["respiratory_rate_bpm"],
            "hemoglobin_gdl":       row["hemoglobin_gdl"],
            "temperature_f":        row["temperature_f"],
            "sbp_mmhg":             row["sbp_mmhg"],
            "dbp_mmhg":             row["dbp_mmhg"],
            "step_count":           row["step_count"],
            "weight_kg":            row["weight_kg"],
            "ecg":                  row["ecg"],
            "stethoscope":          row["stethoscope"],
            "fall_detected":        row["fall_detected"],
            "demographics": {
                "age_group":      row["demographics_age_group"],
                "biological_sex": row["demographics_biological_sex"],
            },
        }

        validation_result = ValidationService.validate(raw_payload)
        if not validation_result["valid"]:
            raise ValueError(f"Validation failed: {validation_result['errors']}")

        clean = validation_result["data"]

        # ── 2. Rule Engine (on validated, clean values) ───────────────────
        rule_result = RuleEngineService.evaluate(clean)
        risk_label = SEVERITY_TO_RISK_LABEL[rule_result["highest_severity"]]

        # ── 3. Normalize -> vector (FAISS-search only, never stored raw) ──
        norm_input = dict(clean)
        norm_input["demographics"] = clean.get("demographics", {})
        norm = FeatureNormalizationService.normalize(norm_input)

        # ── 4. FAISS retrieval (logged for now; wired into reports later) ─
        try:
            neighbors = FAISSRetrievalService.search(norm["vector"], k=5)
            top = neighbors[0] if neighbors else None
            if top:
                self.stdout.write(
                    f"    nearest historical case: risk={top['risk_label']} "
                    f"distance={top['distance']}"
                )
        except FileNotFoundError:
            self.stdout.write(self.style.WARNING(
                "    FAISS index not found — skipping retrieval (run build_faiss_index)."
            ))

        # ── 5. Patient — resolve by external_patient_ref ──────────────────
        demo = clean.get("demographics", {})
        patient, _ = Patient.objects.update_or_create(
            external_patient_ref=row["external_patient_ref"],
            defaults={
                "age_group":      demo.get("age_group"),
                "biological_sex": demo.get("biological_sex"),
                "weight_kg":      row["weight_kg"],
            },
        )

        # ── 6. VitalReading ─────────────────────────────────────────────
        bp = clean.get("blood_pressure", {})
        VitalReading.objects.create(
            patient=patient,
            recorded_at=row["recorded_at"],
            hr_bpm=clean.get("hr_bpm"),
            oxygen_spo2_pct=clean.get("oxygen_spo2_pct"),
            respiratory_rate_bpm=clean.get("respiratory_rate_bpm"),
            sbp_mmhg=bp.get("sbp_mmhg"),
            dbp_mmhg=bp.get("dbp_mmhg"),
            glucose_mgdl=clean.get("glucose_mgdl"),
            cholesterol_mgdl=clean.get("cholesterol_mgdl"),
            hemoglobin_gdl=clean.get("hemoglobin_gdl"),
            temperature_f=clean.get("temperature_f"),
            weight_kg=clean.get("weight_kg"),
            step_count=clean.get("step_count"),
            ecg=bool(clean.get("ecg")),
            stethoscope=bool(clean.get("stethoscope")),
            fall_detected=bool(clean.get("fall_detected")),
            alert_count=rule_result["alert_count"],
            highest_severity=rule_result["highest_severity"],
            has_alert=rule_result["alert_count"] > 0,
            alerts=rule_result["alerts"],
            risk_label=risk_label,
        )
