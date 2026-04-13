"""
Embedding Store — Gestion de l'index FAISS
Conforme à AGENT_ML_IA.md §4 Gestion des embeddings
"""
import os
import json
import threading
import numpy as np
import faiss
import structlog
from pathlib import Path
from typing import Optional

log = structlog.get_logger()

FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "/data/faiss/index.faiss")
FAISS_META_PATH = FAISS_INDEX_PATH.replace(".faiss", "_meta.json")
FAISS_TOP_K = int(os.getenv("FAISS_TOP_K", 5))
EMBEDDING_DIM = 512


class EmbeddingStore:
    """
    Wraps un index FAISS IndexFlatIP (inner product = cosine sur vecteurs L2-normalisés).
    Thread-safe via RLock.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._index: faiss.IndexFlatIP = faiss.IndexFlatIP(EMBEDDING_DIM)
        # Mapping faiss_id (int) → profile_id (str)
        self._id_map: list[str] = []
        self._load()

    # ── Persistence ─────────────────────────────────────────

    def _load(self):
        """Charge l'index et les métadonnées depuis le disque."""
        index_path = Path(FAISS_INDEX_PATH)
        meta_path = Path(FAISS_META_PATH)
        if index_path.exists() and meta_path.exists():
            self._index = faiss.read_index(str(index_path))
            with open(meta_path, "r") as f:
                self._id_map = json.load(f)
            log.info("Index FAISS chargé", n_profiles=len(self._id_map))
        else:
            log.info("Nouvel index FAISS initialisé")

    def _save(self):
        """Persiste l'index et les métadonnées sur le disque."""
        Path(FAISS_INDEX_PATH).parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, FAISS_INDEX_PATH)
        with open(FAISS_META_PATH, "w") as f:
            json.dump(self._id_map, f)

    # ── Enrôlement ──────────────────────────────────────────

    def add_profile(self, profile_id: str, embeddings: list[np.ndarray]) -> bool:
        """
        Ajoute un profil en calculant le centroïde de ses embeddings.
        Retourne False si un profil avec ce profile_id existe déjà.
        """
        if profile_id in self._id_map:
            log.warning("Profil déjà existant", profile_id=profile_id)
            return False

        centroid = self._compute_centroid(embeddings)
        with self._lock:
            self._index.add(centroid.reshape(1, -1))
            self._id_map.append(profile_id)
            self._save()

        log.info("Profil enrôlé", profile_id=profile_id, n_images=len(embeddings))
        return True

    def update_profile(self, profile_id: str, new_embeddings: list[np.ndarray]) -> bool:
        """
        Recalcule le centroïde d'un profil existant avec de nouvelles images.
        Reconstruit l'index entier (FAISS IndexFlatIP ne supporte pas la mise à jour partielle).
        """
        if profile_id not in self._id_map:
            log.warning("Profil introuvable pour mise à jour", profile_id=profile_id)
            return False

        # Récupérer tous les vecteurs existants sauf le profil à mettre à jour
        with self._lock:
            all_vectors = self._index.reconstruct_n(0, self._index.ntotal)
            idx = self._id_map.index(profile_id)

            new_centroid = self._compute_centroid(new_embeddings)
            all_vectors[idx] = new_centroid

            # Reconstruire l'index
            self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
            self._index.add(all_vectors)
            self._save()

        log.info("Profil mis à jour", profile_id=profile_id)
        return True

    def remove_profile(self, profile_id: str) -> bool:
        """Supprime un profil de l'index (droit à l'oubli)."""
        if profile_id not in self._id_map:
            return False

        with self._lock:
            idx = self._id_map.index(profile_id)
            all_vectors = self._index.reconstruct_n(0, self._index.ntotal)

            # Retirer le vecteur et reconstruire
            remaining = np.delete(all_vectors, idx, axis=0)
            self._id_map.pop(idx)
            self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
            if len(remaining) > 0:
                self._index.add(remaining)
            self._save()

        log.info("Profil supprimé", profile_id=profile_id)
        return True

    # ── Recherche ───────────────────────────────────────────

    def search(self, query_embedding: np.ndarray, top_k: int = FAISS_TOP_K) -> list[dict]:
        """
        Recherche les top_k profils les plus similaires.

        Returns:
            Liste de dicts {profile_id, score} triée par score décroissant
        """
        if self._index.ntotal == 0:
            return []

        query = query_embedding.reshape(1, -1).astype(np.float32)
        k = min(top_k, self._index.ntotal)

        with self._lock:
            scores, indices = self._index.search(query, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            results.append(
                {
                    "profile_id": self._id_map[idx],
                    "score": float(score),  # Cosine similarity [-1, 1]
                }
            )
        return results

    # ── Utilitaires ─────────────────────────────────────────

    @staticmethod
    def _compute_centroid(embeddings: list[np.ndarray]) -> np.ndarray:
        """Calcule le centroïde normalisé L2 de N embeddings."""
        stacked = np.stack(embeddings, axis=0).astype(np.float32)
        centroid = stacked.mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid /= norm
        return centroid

    @property
    def n_profiles(self) -> int:
        return self._index.ntotal
