"""
faiss_retrieval_service.py
─────────────────────────────
ClinGPT — FAISS Similarity Retrieval

Loads the FAISS index + metadata built by `python manage.py build_faiss_index`
ONCE per process (lazy singleton — first call loads it, every call after
reuses the same in-memory index). Exposes a single method that takes a
query vector and returns the K most similar historical cases.

IMPORTANT: this service returns FAISS row IDs, distances, and metadata
records (raw clinical values) — it NEVER returns or exposes the raw
normalized vectors of the neighbors beyond what's needed to compute
distance. Callers (ReportContextService) resolve real clinical values
from the returned metadata, not from any vector math.

Position in the pipeline:
    ValidationService → RuleEngineService → FeatureNormalizationService
                                                      ↓
                                          FAISSRetrievalService  ←── YOU ARE HERE
                                                      ↓
                                          ReportContextService → LLM

Usage:
    from apps.clin_gpt.services.faiss_retrieval_service import FAISSRetrievalService

    neighbors = FAISSRetrievalService.search(query_vector, k=5)
    # neighbors = [
    #     {"faiss_row": 39, "distance": 0.045, "risk_label": "high",
    #      "vitals": {...}, "age_group": "46-60", ...},
    #     ...
    # ]
"""

import json
import logging
import threading
from pathlib import Path

import numpy as np
import faiss

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
INDEX_PATH = DATA_DIR / "faiss_index.bin"
METADATA_PATH = DATA_DIR / "faiss_metadata.json"

EXPECTED_DIM = 16


class FAISSRetrievalService:

    _index = None
    _metadata = None
    _lock = threading.Lock()

    # ── Lazy singleton loader ────────────────────────────────────────────────

    @classmethod
    def _ensure_loaded(cls):
        if cls._index is not None:
            return

        with cls._lock:
            # Double-checked locking: another thread may have loaded it while
            # this one was waiting on the lock.
            if cls._index is not None:
                return

            if not INDEX_PATH.exists() or not METADATA_PATH.exists():
                raise FileNotFoundError(
                    f"FAISS index not found at {INDEX_PATH} / {METADATA_PATH}. "
                    f"Run `python manage.py build_faiss_index` first."
                )

            logger.info("Loading FAISS index from %s ...", INDEX_PATH)
            index = faiss.read_index(str(INDEX_PATH))
            if index.d != EXPECTED_DIM:
                raise ValueError(
                    f"Loaded FAISS index has dim={index.d}, expected {EXPECTED_DIM}. "
                    f"Rebuild the index — FEATURE_ORDER may have changed."
                )

            metadata = json.loads(METADATA_PATH.read_text())
            if index.ntotal != len(metadata):
                raise ValueError(
                    f"Index/metadata mismatch: index has {index.ntotal} vectors, "
                    f"metadata has {len(metadata)} records. Rebuild the index."
                )

            cls._index = index
            cls._metadata = metadata
            logger.info("FAISS index loaded: %d vectors, dim=%d", index.ntotal, index.d)

    @classmethod
    def reload(cls):
        """Force a fresh load on the next search() call — call this after
        re-running build_faiss_index without restarting the server."""
        with cls._lock:
            cls._index = None
            cls._metadata = None

    # ── Search ────────────────────────────────────────────────────────────────

    @classmethod
    def search(cls, query_vector: list, k: int = 5) -> list:
        """
        Parameters
        ----------
        query_vector : list of 16 floats
            Output of FeatureNormalizationService.normalize()["vector"].
            This is the ONLY normalized-vector input this service accepts —
            it is used purely for the FAISS distance search and is never
            included in the returned results.

        k : int
            Number of neighbors to retrieve.

        Returns
        -------
        list of dicts, ordered nearest-first, each containing the metadata
        record for that neighbor (raw clinical values, risk_label, etc.)
        plus the L2 distance. No normalized vectors in the output.
        """
        cls._ensure_loaded()

        if len(query_vector) != EXPECTED_DIM:
            raise ValueError(
                f"query_vector has {len(query_vector)} dims, expected {EXPECTED_DIM}."
            )

        vec = np.array([query_vector], dtype="float32")
        distances, indices = cls._index.search(vec, k)

        results = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue  # FAISS pads with -1 if k > ntotal
            record = dict(cls._metadata[idx])  # copy, don't mutate cached metadata
            record["distance"] = round(float(distance), 4)
            results.append(record)

        return results
