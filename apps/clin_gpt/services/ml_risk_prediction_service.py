"""
ml_risk_prediction_service.py
──────────────────────────────
ClinGPT — ML Risk Prediction (XGBoost)

Loads the model trained by `python manage.py train_risk_model` ONCE per
process (lazy singleton, same pattern as FAISSRetrievalService). Given a
reading's 16-float FeatureNormalizationService vector PLUS its FAISS
neighbors (already retrieved by FAISSRetrievalService), builds the same
21-dim input used at training time and returns a probabilistic second
opinion — NOT a replacement for the Rule Engine, a parallel signal.

Position in the pipeline:
    ValidationService → RuleEngineService → FeatureNormalizationService
                                                      ↓
                                          FAISSRetrievalService.search()
                                                      ↓
                                   MLRiskPredictionService  ←── YOU ARE HERE
                                                      ↓
                                          ReportContextService → LLM

IMPORTANT: the 5 FAISS-aggregate features here must be computed with the
exact same formulas used in train_risk_model.py, or the model will see
out-of-distribution inputs and produce garbage predictions. Both live
here and in the training command import nothing from each other (the
training command runs standalone as a management command) — if you ever
change the aggregate feature formulas, update BOTH places.

Usage:
    from apps.clin_gpt.services.ml_risk_prediction_service import MLRiskPredictionService

    prediction = MLRiskPredictionService.predict(
        base_vector=norm["vector"],          # 16 floats, from FeatureNormalizationService
        faiss_neighbors=faiss_neighbors,      # output of FAISSRetrievalService.search()
    )
    # prediction = {
    #     "risk_score": 0.82,
    #     "risk_label": "high",
    #     "class_probabilities": {"low": 0.05, "medium": 0.13, "high": 0.82},
    # }
"""

import json
import logging
import threading
from collections import Counter
from pathlib import Path

import numpy as np
import xgboost as xgb

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MODEL_PATH = DATA_DIR / "xgboost_risk_model.json"
METADATA_PATH = DATA_DIR / "risk_model_metadata.json"

LABEL_TO_SCORE = {"low": 0.0, "medium": 0.5, "high": 1.0}
SEVERITY_TO_SCORE = {"none": 0.0, "warning": 0.5, "critical": 1.0}
N_FAISS_NEIGHBORS = 5


class MLRiskPredictionService:

    _model = None
    _metadata = None
    _lock = threading.Lock()

    # ── Lazy singleton loader ────────────────────────────────────────────────

    @classmethod
    def _ensure_loaded(cls):
        if cls._model is not None:
            return

        with cls._lock:
            if cls._model is not None:
                return

            if not MODEL_PATH.exists() or not METADATA_PATH.exists():
                raise FileNotFoundError(
                    f"Risk model not found at {MODEL_PATH} / {METADATA_PATH}. "
                    f"Run `python manage.py train_risk_model` first."
                )

            logger.info("Loading XGBoost risk model from %s ...", MODEL_PATH)
            model = xgb.XGBClassifier()
            model.load_model(str(MODEL_PATH))

            metadata = json.loads(METADATA_PATH.read_text())

            expected_dims = metadata.get("total_input_dims")
            if expected_dims and model.n_features_in_ != expected_dims:
                raise ValueError(
                    f"Loaded model expects {model.n_features_in_} features, "
                    f"but metadata says training used {expected_dims}. Retrain."
                )

            cls._model = model
            cls._metadata = metadata
            logger.info("Risk model loaded: %d input dims", model.n_features_in_)

    @classmethod
    def reload(cls):
        """Force a fresh load on the next predict() call — call this after
        re-running train_risk_model without restarting the server."""
        with cls._lock:
            cls._model = None
            cls._metadata = None

    # ── Prediction ────────────────────────────────────────────────────────────

    @classmethod
    def predict(cls, base_vector: list, faiss_neighbors: list) -> dict:
        """
        Parameters
        ----------
        base_vector : list of 16 floats
            FeatureNormalizationService.normalize()["vector"] output.

        faiss_neighbors : list of dicts
            Output of FAISSRetrievalService.search() — each dict must have
            'risk_label', 'alert_count', 'highest_severity', 'distance'.

        Returns
        -------
        dict with risk_score (float 0.0-1.0), risk_label (str), and
        class_probabilities (dict) for transparency in the LLM report.
        """
        cls._ensure_loaded()

        if len(base_vector) != 16:
            raise ValueError(f"base_vector has {len(base_vector)} dims, expected 16.")

        agg_features = cls._aggregate_faiss_features(faiss_neighbors)
        full_input = np.array([list(base_vector) + agg_features], dtype="float32")

        probs = cls._model.predict_proba(full_input)[0]  # [p_low, p_medium, p_high]
        int_to_label = cls._metadata["int_to_label"]
        # JSON keys are strings ("0","1","2") after round-tripping through json.loads
        class_probs = {int_to_label[str(i)]: float(probs[i]) for i in range(len(probs))}

        risk_score = sum(LABEL_TO_SCORE[label] * p for label, p in class_probs.items())
        risk_label = max(class_probs, key=class_probs.get)

        return {
            "risk_score": round(risk_score, 4),
            "risk_label": risk_label,
            "class_probabilities": {k: round(v, 4) for k, v in class_probs.items()},
        }

    # ── Feature building (MUST match train_risk_model.py exactly) ───────────

    @staticmethod
    def _aggregate_faiss_features(faiss_neighbors: list) -> list:
        """Builds the same 5 aggregate features used at training time.
        Unlike training, there's no self-match to exclude here — the
        incoming reading isn't in the index yet — so all neighbors are used
        as-is, capped at N_FAISS_NEIGHBORS."""
        neighbors = faiss_neighbors[:N_FAISS_NEIGHBORS]
        if not neighbors:
            # No FAISS index available / empty result — neutral fallback
            # (mid-point values) rather than crashing the whole prediction.
            logger.warning("No FAISS neighbors available for ML prediction — using neutral fallback features.")
            return [0.5, 0.5, 0.5, 0.5, 0.5]

        risk_scores = [LABEL_TO_SCORE[n["risk_label"]] for n in neighbors]
        alert_counts = [n["alert_count"] for n in neighbors]
        severities = [n["highest_severity"] for n in neighbors]
        dists = [n["distance"] for n in neighbors]

        avg_neighbor_risk = float(np.mean(risk_scores))
        avg_neighbor_alert_count = float(min(np.mean(alert_counts) / 5.0, 1.0))
        most_common_severity = SEVERITY_TO_SCORE[Counter(severities).most_common(1)[0][0]]
        avg_similarity = 1.0 / (1.0 + float(np.mean(dists)))
        closest_similarity = 1.0 / (1.0 + float(np.min(dists)))

        return [
            avg_neighbor_risk, avg_neighbor_alert_count,
            most_common_severity, avg_similarity, closest_similarity,
        ]
