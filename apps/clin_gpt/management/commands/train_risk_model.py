"""
train_risk_model.py  (v2 — matches the ML Risk Prediction spec)
──────────────────────────────────────────────────────────────────
python manage.py train_risk_model

Purpose (per spec): the Rule Engine is reactive — fixed per-parameter
thresholds. XGBoost looks at ALL parameters together, PLUS how this
reading compares to similar historical cases, and produces a
probabilistic second opinion: {"risk_score": 0.0-1.0, "risk_label": ...}.
It runs in PARALLEL with the Rule Engine, never replaces it.

INPUT — 21 floats per row, built from two sources combined:
    [0:16]  the reading's own 16-float FeatureNormalizationService vector
    [16:21] FAISS-derived aggregate features from its 5 nearest neighbors:
              - avg_neighbor_risk        (mean of neighbor risk_label, 0/0.5/1)
              - avg_neighbor_alert_count (normalized, capped at 1.0)
              - most_common_severity     (mode of neighbor highest_severity, 0/0.5/1)
              - avg_similarity           (1 / (1 + mean L2 distance))
              - closest_similarity       (1 / (1 + min L2 distance))

OUTPUT — risk_score (continuous, weighted class probability) AND
risk_label (argmax of the 3-class prediction). Both are useful: the
LLM report stage can say "high risk (0.82)" instead of just "high".

IMPORTANT: when building each row's FAISS neighbors for TRAINING, the
row's own entry in the index must be excluded (it would trivially
match itself at distance 0) — this uses k=6 and drops the self-match.

Requires the FAISS index to already be built (build_faiss_index) AND
loaded — this command computes neighbor features from it directly.
"""

import json
from pathlib import Path
from collections import Counter

import numpy as np
import faiss
import xgboost as xgb
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
from django.core.management.base import BaseCommand

from apps.clin_gpt.models import VitalReading
from apps.clin_gpt.services.feature_normalization_service import (
    FeatureNormalizationService, FEATURE_ORDER,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
INDEX_PATH = DATA_DIR / "faiss_index.bin"
FAISS_METADATA_PATH = DATA_DIR / "faiss_metadata.json"
MODEL_PATH = DATA_DIR / "xgboost_risk_model.json"
METADATA_PATH = DATA_DIR / "risk_model_metadata.json"

LABEL_TO_INT = {"low": 0, "medium": 1, "high": 2}
INT_TO_LABEL = {v: k for k, v in LABEL_TO_INT.items()}
LABEL_TO_SCORE = {"low": 0.0, "medium": 0.5, "high": 1.0}
SEVERITY_TO_SCORE = {"none": 0.0, "warning": 0.5, "critical": 1.0}

N_FAISS_NEIGHBORS = 5
MIN_TRAINING_ROWS = 20
RECOMMENDED_ROWS = 200


class Command(BaseCommand):
    help = "Train the XGBoost risk model (16-float vector + 5 FAISS-aggregate features -> risk_score + risk_label)."

    def handle(self, *args, **options):
        if not INDEX_PATH.exists() or not FAISS_METADATA_PATH.exists():
            self.stderr.write(self.style.ERROR(
                "FAISS index not found — run build_faiss_index first (this "
                "command needs it to compute neighbor-aggregate features)."
            ))
            return

        index = faiss.read_index(str(INDEX_PATH))
        faiss_metadata = json.loads(FAISS_METADATA_PATH.read_text())

        readings = list(
            VitalReading.objects.select_related("patient").exclude(risk_label__isnull=True)
        )
        total = len(readings)
        if total < MIN_TRAINING_ROWS:
            self.stderr.write(self.style.ERROR(f"Only {total} labeled rows — too few to train."))
            return
        if total < RECOMMENDED_ROWS:
            self.stdout.write(self.style.WARNING(
                f"Training on {total} rows — spec recommends 200+. Proceeding anyway; "
                f"treat CV numbers as a proof-of-concept signal, not a production accuracy claim. "
                f"Re-run this command once more data is available."
            ))

        self.stdout.write(f"Building {16 + 5}-dim training set from {total} rows "
                           f"(16 base + 5 FAISS-aggregate)...")

        # Build a row_id -> vital_reading_id lookup so we can find and
        # exclude each row's own self-match in the FAISS index.
        vital_reading_id_by_faiss_row = {
            m["faiss_row"]: m["vital_reading_id"] for m in faiss_metadata
        }

        X, y = [], []
        skipped = 0
        for r in readings:
            base_vector = self._reading_to_vector(r)

            neighbor_feats = self._faiss_aggregate_features(
                base_vector, index, faiss_metadata, vital_reading_id_by_faiss_row,
                exclude_vital_reading_id=r.id,
            )
            if neighbor_feats is None:
                skipped += 1
                continue

            X.append(base_vector + neighbor_feats)
            y.append(LABEL_TO_INT[r.risk_label])

        if skipped:
            self.stdout.write(f"Skipped {skipped} row(s) with no valid neighbors.")

        X = np.array(X, dtype="float32")
        y = np.array(y, dtype="int32")

        class_counts = {INT_TO_LABEL[i]: int((y == i).sum()) for i in range(3)}
        self.stdout.write(f"Class distribution: {class_counts}")

        # ── Held-out split ────────────────────────────────────────────────
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=42
        )
        model = self._build_model()
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        report = classification_report(
            y_test, y_pred, target_names=["low", "medium", "high"], output_dict=True
        )
        cm = confusion_matrix(y_test, y_pred).tolist()
        self.stdout.write("\n── Held-out test set (20%) ──")
        self.stdout.write(classification_report(y_test, y_pred, target_names=["low", "medium", "high"]))
        self.stdout.write("Confusion matrix (rows=actual, cols=predicted, order=low/medium/high):")
        for row in cm:
            self.stdout.write(f"  {row}")

        # ── 5-fold CV ─────────────────────────────────────────────────────
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        cv_scores = cross_val_score(self._build_model(), X, y, cv=cv, scoring="accuracy")
        self.stdout.write(f"\n5-fold CV accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")
        self.stdout.write(f"Fold scores: {[round(s, 3) for s in cv_scores]}")

        # ── Retrain on ALL data for the saved model ─────────────────────
        final_model = self._build_model()
        final_model.fit(X, y)

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        final_model.save_model(str(MODEL_PATH))

        metadata = {
            "feature_order":            FEATURE_ORDER,
            "faiss_aggregate_features": [
                "avg_neighbor_risk", "avg_neighbor_alert_count",
                "most_common_severity", "avg_similarity", "closest_similarity",
            ],
            "total_input_dims":  X.shape[1],
            "label_to_int":      LABEL_TO_INT,
            "int_to_label":      INT_TO_LABEL,
            "label_to_score":    LABEL_TO_SCORE,
            "training_rows":     total,
            "class_distribution": class_counts,
            "held_out_test_report": report,
            "held_out_confusion_matrix": cm,
            "cv_accuracy_mean":  float(cv_scores.mean()),
            "cv_accuracy_std":   float(cv_scores.std()),
            "n_faiss_neighbors": N_FAISS_NEIGHBORS,
        }
        METADATA_PATH.write_text(json.dumps(metadata, indent=2))

        self.stdout.write(self.style.SUCCESS(
            f"\nSaved model to {MODEL_PATH} and metadata to {METADATA_PATH}"
        ))

    # ── Model factory (keeps train/test and CV models identically configured) ──

    @staticmethod
    def _build_model():
        return xgb.XGBClassifier(
            objective="multi:softprob",
            num_class=3,
            max_depth=3,
            n_estimators=100,
            learning_rate=0.1,
            eval_metric="mlogloss",
            random_state=42,
        )

    # ── Feature building ──────────────────────────────────────────────────

    @staticmethod
    def _reading_to_vector(reading: VitalReading) -> list:
        data = {
            "hr_bpm":               reading.hr_bpm,
            "oxygen_spo2_pct":      reading.oxygen_spo2_pct,
            "respiratory_rate_bpm": reading.respiratory_rate_bpm,
            "blood_pressure": {"sbp_mmhg": reading.sbp_mmhg, "dbp_mmhg": reading.dbp_mmhg},
            "glucose_mgdl":     reading.glucose_mgdl,
            "cholesterol_mgdl": reading.cholesterol_mgdl,
            "hemoglobin_gdl":   reading.hemoglobin_gdl,
            "temperature_f":    reading.temperature_f,
            "weight_kg":        reading.weight_kg,
            "step_count":       reading.step_count,
            "ecg":              int(reading.ecg),
            "stethoscope":      int(reading.stethoscope),
            "fall_detected":    int(reading.fall_detected),
            "demographics": {
                "biological_sex": reading.patient.biological_sex,
                "age_group":      reading.patient.age_group,
            },
        }
        return FeatureNormalizationService.normalize(data)["vector"]

    @staticmethod
    def _faiss_aggregate_features(
        query_vector, index, faiss_metadata, vital_reading_id_by_faiss_row,
        exclude_vital_reading_id,
    ):
        """Search FAISS for k=N_FAISS_NEIGHBORS+1, drop the row's own
        self-match (if present), then aggregate the remaining neighbors
        into 5 summary features. Returns None if too few neighbors remain."""
        vec = np.array([query_vector], dtype="float32")
        k = N_FAISS_NEIGHBORS + 1
        distances, indices = index.search(vec, k)

        neighbors = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            meta = faiss_metadata[idx]
            if vital_reading_id_by_faiss_row.get(idx) == exclude_vital_reading_id:
                continue  # exclude self-match
            neighbors.append((meta, float(dist)))

        neighbors = neighbors[:N_FAISS_NEIGHBORS]
        if len(neighbors) < 1:
            return None

        risk_scores = [LABEL_TO_SCORE[m["risk_label"]] for m, _ in neighbors]
        alert_counts = [m["alert_count"] for m, _ in neighbors]
        severities = [m["highest_severity"] for m, _ in neighbors]
        dists = [d for _, d in neighbors]

        avg_neighbor_risk = float(np.mean(risk_scores))
        avg_neighbor_alert_count = float(min(np.mean(alert_counts) / 5.0, 1.0))  # normalize, cap at 1.0
        most_common_severity = SEVERITY_TO_SCORE[Counter(severities).most_common(1)[0][0]]
        avg_similarity = 1.0 / (1.0 + float(np.mean(dists)))
        closest_similarity = 1.0 / (1.0 + float(np.min(dists)))

        return [
            avg_neighbor_risk, avg_neighbor_alert_count,
            most_common_severity, avg_similarity, closest_similarity,
        ]
