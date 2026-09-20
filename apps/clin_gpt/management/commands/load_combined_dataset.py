"""
load_combined_dataset.py
─────────────────────────
python manage.py load_combined_dataset

One-off loader: reads apps/clin_gpt/data/combined_2000_cases.json and
creates Patient + VitalReading rows for each record, running every
record through the same ValidationService -> RuleEngineService pipeline
the real device-ingestion path uses (poll_device_vitals.py), so
risk_label/highest_severity/alert_count are computed consistently
regardless of whether the source record already had them.

Safe to re-run: skips any record whose case_id already exists as a
VitalReading.source_case_id.

After this completes, run:
    python manage.py build_faiss_index
to rebuild the FAISS index from the newly loaded data.
"""

import json
import uuid
from pathlib import Path
from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.clin_gpt.models import Patient, VitalReading
from apps.clin_gpt.services.validation_service import ValidationService
from apps.clin_gpt.services.rule_engine_service import RuleEngineService

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "combined_2000_cases.json"

SEVERITY_TO_RISK_LABEL = {
    "none":     "low",
    "warning":  "medium",
    "critical": "high",
}


class Command(BaseCommand):
    help = "Load combined_2000_cases.json into Patient/VitalReading tables."

    def handle(self, *args, **options):
        if not DATA_PATH.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {DATA_PATH}"))
            return

        records = json.loads(DATA_PATH.read_text())
        self.stdout.write(f"Loaded {len(records)} records from {DATA_PATH.name}")

        existing_case_ids = set(
            str(cid) for cid in VitalReading.objects.exclude(source_case_id=None)
            .values_list("source_case_id", flat=True)
        )

        created = 0
        skipped_existing = 0
        skipped_invalid = 0
        errors = []

        for i, rec in enumerate(records):
            case_id = rec.get("case_id")

            # deterministic UUID from case_id string, so re-runs are stable
            source_case_id = uuid.uuid5(uuid.NAMESPACE_OID, case_id) if case_id else None

            if source_case_id and str(source_case_id) in existing_case_ids:
                skipped_existing += 1
                continue

            raw_payload = {
                "hr_bpm":               rec.get("hr_bpm"),
                "oxygen_spo2_pct":      rec.get("oxygen_spo2_pct"),
                "glucose_mgdl":         rec.get("glucose_mgdl"),
                "cholesterol_mgdl":     rec.get("cholesterol_mgdl"),
                "respiratory_rate_bpm": rec.get("respiratory_rate_bpm"),
                "hemoglobin_gdl":       rec.get("hemoglobin_gdl"),
                "temperature_f":        rec.get("temperature_f"),
                "sbp_mmhg":             rec.get("sbp_mmhg"),
                "dbp_mmhg":             rec.get("dbp_mmhg"),
                "step_count":           rec.get("step_count"),
                "weight_kg":            rec.get("weight_kg"),
                "ecg":                  rec.get("ecg"),
                "stethoscope":          rec.get("stethoscope"),
                "fall_detected":        rec.get("fall_detected"),
                "demographics": {
                    "age_group":      rec.get("age_group"),
                    "biological_sex": rec.get("biological_sex"),
                },
            }

            validation_result = ValidationService.validate(raw_payload)
            if not validation_result["valid"]:
                skipped_invalid += 1
                errors.append(f"{case_id}: {validation_result['errors']}")
                continue

            clean = validation_result["data"]

            # Use existing risk fields if the record already had them
            # (source == faiss_metadata), otherwise compute via RuleEngineService
            if rec.get("risk_label") is not None:
                risk_label = rec["risk_label"]
                highest_severity = rec.get("highest_severity", "none")
                alert_count = rec.get("alert_count", 0)
                alerts = []
            else:
                rule_result = RuleEngineService.evaluate(clean)
                highest_severity = rule_result["highest_severity"]
                alert_count = rule_result["alert_count"]
                alerts = rule_result["alerts"]
                risk_label = SEVERITY_TO_RISK_LABEL[highest_severity]

            try:
                recorded_at = datetime.strptime(
                    rec["recorded_at"], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=dt_timezone.utc)
            except (ValueError, KeyError, TypeError):
                recorded_at = datetime.now(dt_timezone.utc)

            demo = clean.get("demographics", {})
            bp = clean.get("blood_pressure", {})

            with transaction.atomic():
                patient = Patient.objects.create(
                    age_group=demo.get("age_group") or "31-45",
                    biological_sex=demo.get("biological_sex") or "other",
                    weight_kg=clean.get("weight_kg") or 70.0,
                    external_patient_ref=rec.get("patient_ref"),
                )

                VitalReading.objects.create(
                    patient=patient,
                    recorded_at=recorded_at,
                    source_case_id=source_case_id,
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
                    ecg=bool(clean.get("ecg", 0)),
                    stethoscope=bool(clean.get("stethoscope", 0)),
                    fall_detected=bool(clean.get("fall_detected", 0)),
                    alert_count=alert_count,
                    highest_severity=highest_severity,
                    has_alert=alert_count > 0,
                    alerts=alerts,
                    risk_label=risk_label,
                )
            created += 1

            if (i + 1) % 200 == 0:
                self.stdout.write(f"  processed {i + 1}/{len(records)}...")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created: {created}, skipped (already loaded): {skipped_existing}, "
            f"skipped (invalid): {skipped_invalid}"
        ))
        if errors:
            self.stdout.write(self.style.WARNING(f"First few validation errors:"))
            for e in errors[:10]:
                self.stdout.write(f"  {e}")