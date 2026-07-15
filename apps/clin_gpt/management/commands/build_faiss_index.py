"""
build_faiss_index.py
──────────────────────
python manage.py build_faiss_index

Reads ALL VitalReading rows (joined with Patient for demographics),
runs each through FeatureNormalizationService, and builds a
faiss.IndexFlatL2. This is the DB-backed replacement for the earlier
JSON-based prototype — same vector shape (16 floats, same FEATURE_ORDER),
same metadata contract.

Outputs (to apps/clin_gpt/data/):
    faiss_index.bin       — the FAISS index
    faiss_metadata.json    — FAISS row -> VitalReading identity + raw
                             clinical values + risk_label, so retrieved
                             neighbors can be resolved back to real data
                             (see report_context_service.py — it looks
                             up neighbors by this metadata, NEVER by the
                             vector itself).

Re-run this any time VitalReading rows change (new seed batch, new
approved live readings you want in the reference corpus) — it always
rebuilds from scratch, it does not append incrementally.
"""

import json
from pathlib import Path

import numpy as np
import faiss
from django.core.management.base import BaseCommand

from apps.clin_gpt.models import VitalReading
from apps.clin_gpt.services.feature_normalization_service import FeatureNormalizationService

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
INDEX_PATH = DATA_DIR / "faiss_index.bin"
METADATA_PATH = DATA_DIR / "faiss_metadata.json"


class Command(BaseCommand):
    help = "Build the FAISS similarity index from VitalReading DB rows."

    def handle(self, *args, **options):
        readings = VitalReading.objects.select_related("patient").all()
        total = readings.count()
        if total == 0:
            self.stderr.write(self.style.ERROR("No VitalReading rows found — seed the DB first."))
            return

        self.stdout.write(f"Building FAISS index from {total} VitalReading rows...")

        vectors = []
        metadata = []
        missing_field_total = 0

        for reading in readings:
            data = self._reading_to_pipeline_input(reading)
            norm = FeatureNormalizationService.normalize(data)
            missing_field_total += len(norm["missing_fields"])

            vectors.append(norm["vector"])
            metadata.append({
                "faiss_row":         len(metadata),
                "vital_reading_id":  reading.id,
                "patient_id":        reading.patient_id,
                "source_case_id":    str(reading.source_case_id) if reading.source_case_id else None,
                "recorded_at":       reading.recorded_at.isoformat(),
                "risk_label":        reading.risk_label,
                "highest_severity":  reading.highest_severity,
                "alert_count":       reading.alert_count,
                "age_group":         reading.patient.age_group,
                "biological_sex":    reading.patient.biological_sex,
                "vitals": {
                    "hr_bpm":               reading.hr_bpm,
                    "oxygen_spo2_pct":      reading.oxygen_spo2_pct,
                    "respiratory_rate_bpm": reading.respiratory_rate_bpm,
                    "sbp_mmhg":             reading.sbp_mmhg,
                    "dbp_mmhg":             reading.dbp_mmhg,
                    "glucose_mgdl":         reading.glucose_mgdl,
                    "cholesterol_mgdl":     reading.cholesterol_mgdl,
                    "hemoglobin_gdl":       reading.hemoglobin_gdl,
                    "temperature_f":        reading.temperature_f,
                    "weight_kg":            reading.weight_kg,
                    "step_count":           reading.step_count,
                },
            })

        vectors = np.array(vectors, dtype="float32")
        if vectors.shape[1] != 16:
            self.stderr.write(self.style.ERROR(
                f"Expected 16-dim vectors, got {vectors.shape[1]}. Aborting — check FEATURE_ORDER."
            ))
            return

        index = faiss.IndexFlatL2(16)
        index.add(vectors)

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(INDEX_PATH))
        METADATA_PATH.write_text(json.dumps(metadata, indent=2))

        self.stdout.write(self.style.SUCCESS(
            f"Built index: {index.ntotal} vectors, dim={index.d}. "
            f"Missing-field fallouts: {missing_field_total}. "
            f"Saved to {INDEX_PATH} and {METADATA_PATH}"
        ))

    @staticmethod
    def _reading_to_pipeline_input(reading: VitalReading) -> dict:
        """Flattens a VitalReading + its Patient into the flat dict shape
        FeatureNormalizationService.normalize() expects."""
        return {
            "hr_bpm":               reading.hr_bpm,
            "oxygen_spo2_pct":      reading.oxygen_spo2_pct,
            "respiratory_rate_bpm": reading.respiratory_rate_bpm,
            "blood_pressure": {
                "sbp_mmhg": reading.sbp_mmhg,
                "dbp_mmhg": reading.dbp_mmhg,
            },
            "glucose_mgdl":     reading.glucose_mgdl,
            "cholesterol_mgdl": reading.cholesterol_mgdl,
            "hemoglobin_gdl":   reading.hemoglobin_gdl,
            "temperature_f":    reading.temperature_f,
            "weight_kg":        reading.weight_kg,   # device-measured, from VitalReading itself
            "step_count":       reading.step_count,
            "ecg":              int(reading.ecg),
            "stethoscope":      int(reading.stethoscope),
            "fall_detected":    int(reading.fall_detected),
            "demographics": {
                "biological_sex": reading.patient.biological_sex,
                "age_group":      reading.patient.age_group,
            },
        }