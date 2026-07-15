"""
seed_historical_cases.py
──────────────────────────
python manage.py seed_historical_cases

Loads apps/clin_gpt/data/all_100_cases.json into Patient + VitalReading.
For each case:
  - flattens the authored JSON shape into the flat dict RuleEngineService expects
  - runs RuleEngineService.evaluate() at write time (NOT hardcoded) to get
    alerts / alert_count / highest_severity
  - derives risk_label 1:1 from highest_severity (none->low, warning->medium,
    critical->high) — same mapping used when we validated this in JSON earlier
  - creates one Patient per case (this is cross-sectional seed data, not
    longitudinal readings for a shared patient)

Idempotent: matches on source_case_id, so re-running the command updates
existing rows instead of duplicating them.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.clin_gpt.models import Patient, VitalReading
from apps.clin_gpt.services.rule_engine_service import RuleEngineService

DEFAULT_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "all_100_cases.json"

SEVERITY_TO_RISK_LABEL = {
    "none":     "low",
    "warning":  "medium",
    "critical": "high",
}


class Command(BaseCommand):
    help = "Seed Patient/VitalReading tables from all_100_cases.json, computing alerts via RuleEngineService."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", type=str, default=str(DEFAULT_DATA_PATH),
            help="Path to the cases JSON file (default: apps/clin_gpt/data/all_100_cases.json)",
        )

    def handle(self, *args, **options):
        data_path = Path(options["file"])
        if not data_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {data_path}"))
            return

        cases = json.loads(data_path.read_text())
        self.stdout.write(f"Loaded {len(cases)} cases from {data_path}")

        created, updated = 0, 0

        with transaction.atomic():
            for case in cases:
                created_flag = self._seed_one_case(case)
                if created_flag:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {created}, updated {updated}, total {created + updated}."
        ))

    def _seed_one_case(self, case: dict) -> bool:
        vitals = case["vitals"]
        demo = case["demographics"]
        bp = vitals.get("blood_pressure", {})

        # ── Flatten into the shape RuleEngineService.evaluate() expects ─────
        rule_input = {
            "hr_bpm":               vitals.get("hr_bpm"),
            "oxygen_spo2_pct":      vitals.get("oxygen_spo2_pct"),
            "respiratory_rate_bpm": vitals.get("respiratory_rate_bpm"),
            "blood_pressure":       bp,
        }
        rule_result = RuleEngineService.evaluate(rule_input)
        risk_label = SEVERITY_TO_RISK_LABEL[rule_result["highest_severity"]]

        # ── Patient: one per case (cross-sectional seed data) ───────────────
        patient, _ = Patient.objects.update_or_create(
            id=self._patient_id_for_case(case["case_id"]),
            defaults={
                "age_group":      demo["age_group"],
                "biological_sex": demo["biological_sex"],
                "weight_kg":      demo["weight_kg"],
            },
        )

        # ── VitalReading: matched on source_case_id for idempotency ─────────
        _, was_created = VitalReading.objects.update_or_create(
            source_case_id=case["case_id"],
            defaults={
                "patient":               patient,
                "recorded_at":           case["recorded_at"],
                "hr_bpm":                vitals.get("hr_bpm"),
                "oxygen_spo2_pct":       vitals.get("oxygen_spo2_pct"),
                "respiratory_rate_bpm":  vitals.get("respiratory_rate_bpm"),
                "sbp_mmhg":              bp.get("sbp_mmhg"),
                "dbp_mmhg":              bp.get("dbp_mmhg"),
                "glucose_mgdl":          vitals.get("glucose_mgdl"),
                "cholesterol_mgdl":      vitals.get("cholesterol_mgdl"),
                "hemoglobin_gdl":        vitals.get("hemoglobin_gdl"),
                "temperature_f":         vitals.get("temperature_f"),
                "weight_kg":             demo["weight_kg"],  # no separate device reading in seed data
                "step_count":            vitals.get("step_count"),
                "ecg":                   bool(vitals.get("ecg")),
                "stethoscope":           bool(vitals.get("stethoscope")),
                "fall_detected":         bool(vitals.get("fall_detected")),
                "alert_count":           rule_result["alert_count"],
                "highest_severity":      rule_result["highest_severity"],
                "has_alert":             rule_result["alert_count"] > 0,
                "alerts":                rule_result["alerts"],
                "risk_label":            risk_label,
            },
        )
        return was_created

    @staticmethod
    def _patient_id_for_case(case_id: str) -> int:
        """
        Deterministic small integer PK derived from the case_id UUID, so
        update_or_create on Patient is stable across re-runs without needing
        a separate source_case_id column on Patient itself.
        """
        import uuid
        return uuid.UUID(case_id).int % (2**31 - 1)