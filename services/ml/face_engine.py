"""
Face Engine — Détection (RetinaFace) + Embedding (ArcFace)
Conforme à AGENT_ML_IA.md §3 Pipeline d'inférence
"""
import time
import os
import numpy as np
import insightface
from insightface.app import FaceAnalysis
from typing import Optional
import structlog

from metrics import (
    ML_INFERENCE_LATENCY,
    ML_CONFIDENCE_SCORE,
)

log = structlog.get_logger()

THRESHOLD_AUTHORIZED = float(os.getenv("ML_THRESHOLD_AUTHORIZED", 0.85))
THRESHOLD_SUSPECT = float(os.getenv("ML_THRESHOLD_SUSPECT", 0.70))
INFERENCE_TIMEOUT_MS = float(os.getenv("ML_INFERENCE_TIMEOUT_MS", 200))
CTX_ID = int(os.getenv("INSIGHTFACE_CTX_ID", 0))  # 0=GPU, -1=CPU
MODEL_NAME = os.getenv("INSIGHTFACE_MODEL", "buffalo_l")


class FaceEngine:
    """
    Charge InsightFace buffalo_l (RetinaFace + ArcFace) et expose :
    - detect_and_embed(image) → liste de FaceResult
    - classify(score) → "authorized" | "suspect" | "unknown"
    """

    def __init__(self):
        log.info("Chargement du modèle InsightFace", model=MODEL_NAME, ctx=CTX_ID)
        self._app = FaceAnalysis(
            name=MODEL_NAME,
            allowed_modules=["detection", "recognition"],
        )
        self._app.prepare(ctx_id=CTX_ID, det_size=(640, 640))
        log.info("Modèle InsightFace chargé")

    def detect_and_embed(self, image_rgb: np.ndarray) -> list[dict]:
        """
        Détecte les visages dans une image RGB et retourne les embeddings.

        Args:
            image_rgb: Image numpy uint8 (H, W, 3) en RGB

        Returns:
            Liste de dicts {bbox, landmark, embedding, det_score}
            embedding est un vecteur float32 de dimension 512
        """
        t0 = time.perf_counter()

        if image_rgb is None or image_rgb.size == 0:
            log.warning("Image vide reçue par face_engine")
            return []

        try:
            faces = self._app.get(image_rgb)
        except Exception as exc:
            log.error("Erreur d'inférence InsightFace", error=str(exc))
            return []

        elapsed_ms = (time.perf_counter() - t0) * 1000
        ML_INFERENCE_LATENCY.observe(elapsed_ms / 1000)

        if elapsed_ms > INFERENCE_TIMEOUT_MS:
            log.warning(
                "Inférence trop lente",
                elapsed_ms=round(elapsed_ms, 1),
                limit_ms=INFERENCE_TIMEOUT_MS,
            )

        results = []
        for face in faces:
            if face.embedding is None:
                continue
            embedding = face.embedding.astype(np.float32)
            # Assertion défensive : dimension 512d obligatoire
            assert embedding.shape == (512,), f"Embedding inattendu : {embedding.shape}"

            results.append(
                {
                    "bbox": face.bbox.tolist(),          # [x1, y1, x2, y2]
                    "landmark": face.kps.tolist() if face.kps is not None else None,
                    "embedding": embedding,
                    "det_score": float(face.det_score),
                }
            )

        log.debug(
            "Inférence terminée",
            n_faces=len(results),
            elapsed_ms=round(elapsed_ms, 1),
        )
        return results

    @staticmethod
    def cosine_similarity(emb_a: np.ndarray, emb_b: np.ndarray) -> float:
        """Similarité cosinus entre deux embeddings normalisés."""
        norm_a = np.linalg.norm(emb_a)
        norm_b = np.linalg.norm(emb_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(emb_a, emb_b) / (norm_a * norm_b))

    @staticmethod
    def classify(score: float) -> str:
        """
        Classifie un score de similarité.
        Returns: "authorized" | "suspect" | "unknown"
        """
        if score >= THRESHOLD_AUTHORIZED:
            return "authorized"
        if score >= THRESHOLD_SUSPECT:
            return "suspect"
        return "unknown"

    @staticmethod
    def normalize(embedding: np.ndarray) -> np.ndarray:
        """Normalise un embedding L2 pour la comparaison cosinus."""
        norm = np.linalg.norm(embedding)
        if norm == 0:
            return embedding
        return embedding / norm
