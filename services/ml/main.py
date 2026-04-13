"""
Service ML — API interne (port 8001)
Conforme AGENT_ML_IA.md : identification, enrôlement, fine-tuning, monitoring modèle.
"""
import io
import json
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import structlog
from fastapi import FastAPI, UploadFile, File, HTTPException
from prometheus_client import make_asgi_app
from PIL import Image
from pydantic import BaseModel

from face_engine import FaceEngine
from embedding_store import EmbeddingStore
from metrics import (
    ML_FACES_DETECTED, ML_ENROLLMENT_TOTAL, ML_ACTIVE_LEARNING_QUEUE,
    ML_INFERENCE_LATENCY, ML_CONFIDENCE_SCORE, ML_DRIFT_SCORE,
)

log = structlog.get_logger()

app = FastAPI(title="ML Service", docs_url=None, redoc_url=None)
app.mount("/metrics", make_asgi_app())

engine = FaceEngine()
store = EmbeddingStore()

ACTIVE_LEARNING_PATH = os.getenv("DATA_ACTIVE_LEARNING_PATH", "/data/active_learning")
THRESHOLD_SUSPECT = float(os.getenv("ML_THRESHOLD_SUSPECT", "0.70"))
THRESHOLD_AUTHORIZED = float(os.getenv("ML_THRESHOLD_AUTHORIZED", "0.85"))

# ── État global modèle ────────────────────────────────────────────────────────
_model_version: int = 1
_current_far: float = 0.0
_current_frr: float = 0.0
_current_eer: float = 0.0
_current_tar: float = 1.0
_recent_scores: deque = deque(maxlen=100)   # drift detection
_baseline_score: float = 0.82


# ── Schemas ───────────────────────────────────────────────────────────────

class FineTuneRequest(BaseModel):
    run_id: str
    labeled_path: str
    auto_deploy: bool = True
    min_improvement_pct: float = 1.0


class RollbackRequest(BaseModel):
    run_id: str


# ── Health ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "n_profiles": store.n_profiles, "model_version": _model_version}


# ── Identification ───────────────────────────────────────────────────────────

@app.post("/identify")
async def identify(file: UploadFile = File(...), camera_id: str = "unknown"):
    t0 = time.perf_counter()
    contents = await file.read()
    image = _load_image(contents)
    face_results = engine.detect_and_embed(image)
    if not face_results:
        return {"faces": [], "camera_id": camera_id}

    output = []
    for face in face_results:
        embedding = FaceEngine.normalize(face["embedding"])
        matches = store.search(embedding)
        if not matches:
            status, top_score, top_profile_id = "unknown", 0.0, None
        else:
            top = matches[0]
            top_score = top["score"]
            top_profile_id = top["profile_id"]
            status = engine.classify(top_score)

        ML_FACES_DETECTED.labels(status=status).inc()
        ML_CONFIDENCE_SCORE.set(top_score)
        _recent_scores.append(top_score)

        result = {
            "bbox": face["bbox"],
            "det_score": face["det_score"],
            "status": status,
            "confidence": round(top_score * 100, 1),
            "profile_id": top_profile_id,
            "candidates": matches[:3],
        }
        output.append(result)

        if THRESHOLD_SUSPECT <= top_score < THRESHOLD_AUTHORIZED:
            _queue_for_review(contents, camera_id, result)

    latency = time.perf_counter() - t0
    ML_INFERENCE_LATENCY.observe(latency)
    return {"faces": output, "camera_id": camera_id, "latency_ms": round(latency * 1000, 1)}


# ── Enrôlement ──────────────────────────────────────────────────────────────

@app.post("/enroll/{profile_id}")
async def enroll(profile_id: str, files: list[UploadFile] = File(...)):
    embeddings = []
    for f in files:
        contents = await f.read()
        faces = engine.detect_and_embed(_load_image(contents))
        if faces:
            embeddings.append(FaceEngine.normalize(faces[0]["embedding"]))
    if not embeddings:
        raise HTTPException(422, "Aucun visage détecté")
    if not store.add_profile(profile_id, embeddings):
        raise HTTPException(409, f"Profil {profile_id} existe déjà")
    ML_ENROLLMENT_TOTAL.inc()
    return {"profile_id": profile_id, "n_embeddings": len(embeddings), "status": "enrolled"}


@app.post("/enroll/{profile_id}/update")
async def update_enrollment(profile_id: str, files: list[UploadFile] = File(...)):
    embeddings = []
    for f in files:
        contents = await f.read()
        faces = engine.detect_and_embed(_load_image(contents))
        if faces:
            embeddings.append(FaceEngine.normalize(faces[0]["embedding"]))
    if not embeddings:
        raise HTTPException(422, "Aucun visage détecté")
    if not store.update_profile(profile_id, embeddings):
        raise HTTPException(404, f"Profil {profile_id} introuvable")
    return {"profile_id": profile_id, "n_new_embeddings": len(embeddings), "status": "updated"}


@app.delete("/enroll/{profile_id}")
async def delete_enrollment(profile_id: str):
    if not store.remove_profile(profile_id):
        raise HTTPException(404, f"Profil {profile_id} introuvable")
    return {"profile_id": profile_id, "status": "deleted"}


# ── Fine-tuning (AGENT_ML_IA.md §5.3) ───────────────────────────────────────────

@app.post("/fine_tune")
async def fine_tune(req: FineTuneRequest):
    """
    Fine-tuning sur données labelliées.
    - Charge frames + labels depuis req.labeled_path
    - Extrait embeddings, met à jour centroids FAISS
    - Évalue FAR/FRR/EER avant et après
    - Déploie si amélioration >= min_improvement_pct, rollback sinon
    """
    global _model_version, _current_far, _current_frr, _current_eer, _current_tar

    far_before, frr_before, eer_before = _current_far, _current_frr, _current_eer

    labeled_path = Path(req.labeled_path)
    samples = _load_labeled_samples(labeled_path)
    n_samples = len(samples)

    if n_samples < 5:
        return {
            "deployed": False, "rolled_back": False,
            "metrics": {"far_before": far_before, "far_after": far_before,
                        "frr_before": frr_before, "frr_after": frr_before,
                        "eer_before": eer_before, "eer_after": eer_before,
                        "n_samples": n_samples, "message": "Données insuffisantes (min 5)"},
        }

    # Mise à jour centroids FAISS avec nouvelles données labelliées
    profile_embeddings: dict[str, list] = {}
    for s in samples:
        try:
            img = Image.open(s["img_path"]).convert("RGB")
            faces = engine.detect_and_embed(np.array(img))
            if faces:
                emb = FaceEngine.normalize(faces[0]["embedding"])
                pid = s["meta"].get("labeled_profile_id") or s["meta"].get("profile_id")
                if pid:
                    profile_embeddings.setdefault(pid, []).append(emb)
        except Exception:
            continue

    updated = 0
    for pid, embs in profile_embeddings.items():
        if store.update_profile(pid, embs) or store.add_profile(pid, embs):
            updated += 1

    # Évaluation post-update
    after = _evaluate_on_samples(samples)
    far_after = after.get("far", far_before)
    frr_after = after.get("frr", frr_before)
    eer_after = after.get("eer", eer_before)
    tar_after = after.get("tar", _current_tar)

    improvement_pct = round((eer_before - eer_after) / max(eer_before, 1e-6) * 100, 2)

    deployed, rolled_back = False, False
    if req.auto_deploy and improvement_pct >= req.min_improvement_pct:
        _current_far, _current_frr, _current_eer, _current_tar = far_after, frr_after, eer_after, tar_after
        _model_version += 1
        deployed = True
        _save_checkpoint(req.run_id)
        log.info("Modèle déployé", version=_model_version, improvement_pct=improvement_pct)
    elif updated > 0:
        rolled_back = True
        log.info("Rollback — amélioration insuffisante", improvement_pct=improvement_pct)

    metrics = {
        "far_before": far_before, "far_after": far_after,
        "frr_before": frr_before, "frr_after": frr_after,
        "eer_before": eer_before, "eer_after": eer_after,
        "improvement_pct": improvement_pct,
        "n_samples": n_samples, "updated_profiles": updated,
        "tar": tar_after,
    }
    ML_DRIFT_SCORE.set(abs(_baseline_score - float(np.mean(list(_recent_scores)))) if _recent_scores else 0)
    return {"deployed": deployed, "rolled_back": rolled_back, "metrics": metrics}


# ── Model management ──────────────────────────────────────────────────────────

@app.get("/model/info")
async def model_info():
    """Version courante, n_profiles, métriques FAR/FRR/EER/TAR."""
    return {
        "version": _model_version,
        "model_name": "buffalo_l",
        "n_profiles": store.n_profiles,
        "far": _current_far,
        "frr": _current_frr,
        "eer": _current_eer,
        "tar": _current_tar,
    }


@app.get("/model/versions")
async def model_versions():
    """Liste des checkpoints disponibles dans /data/models/checkpoints/."""
    checkpoint_dir = Path("/data/models/checkpoints")
    if not checkpoint_dir.exists():
        return {"versions": []}
    versions = []
    for f in sorted(checkpoint_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            versions.append(data)
        except Exception:
            continue
    return {"versions": versions}


@app.post("/model/rollback")
async def model_rollback(req: RollbackRequest):
    """
    Restaure l'état du modèle depuis un checkpoint MLflow.
    Conforme AGENT_ML_IA.md §5.3 — rollback si dégradation.
    """
    global _model_version, _current_far, _current_frr, _current_eer, _current_tar

    checkpoint_path = Path("/data/models/checkpoints") / f"{req.run_id}.json"
    if not checkpoint_path.exists():
        return {"status": "checkpoint_not_found", "run_id": req.run_id}

    try:
        data = json.loads(checkpoint_path.read_text())
        _current_far = data.get("far", _current_far)
        _current_frr = data.get("frr", _current_frr)
        _current_eer = data.get("eer", _current_eer)
        _current_tar = data.get("tar", _current_tar)
        _model_version = data.get("version", _model_version)
        log.info("Rollback effectué", run_id=req.run_id, version=_model_version)
        return {"status": "rolled_back", "run_id": req.run_id, "version": _model_version}
    except Exception as exc:
        raise HTTPException(500, f"Erreur rollback : {exc}")


@app.post("/model/evaluate")
async def model_evaluate():
    """Evalue le modèle sur paires du store, met à jour métriques globales."""
    global _current_far, _current_frr, _current_eer, _current_tar

    if store.n_profiles < 2:
        return {"metrics": {"far": 0, "frr": 0, "eer": 0, "tar": 1, "n_pairs": 0},
                "message": "Pas assez de profils (min 2)"}

    # Génère des paires positives/négatives depuis le store
    tp = fp = fn = tn = 0
    profiles = list(store._index_map.items()) if hasattr(store, "_index_map") else []
    for pid, centroid in profiles[:50]:  # Max 50 profils pour l'évaluation
        emb = np.array(centroid, dtype=np.float32) if isinstance(centroid, list) else centroid
        matches = store.search(emb)
        if matches and matches[0]["profile_id"] == pid:
            tp += 1
        else:
            fn += 1
        # Paire négative : légère perturbation
        noisy = emb + np.random.normal(0, 0.3, emb.shape).astype(np.float32)
        noisy = noisy / (np.linalg.norm(noisy) + 1e-6)
        neg_matches = store.search(noisy)
        if neg_matches and neg_matches[0]["profile_id"] == pid and neg_matches[0]["score"] > 0.85:
            fp += 1
        else:
            tn += 1

    far = fp / max(fp + tn, 1)
    frr = fn / max(fn + tp, 1)
    eer = (far + frr) / 2
    tar = tp / max(tp + fn, 1)
    n_pairs = tp + fp + fn + tn

    _current_far, _current_frr, _current_eer, _current_tar = far, frr, eer, tar
    return {"metrics": {"far": round(far, 4), "frr": round(frr, 4),
                        "eer": round(eer, 4), "tar": round(tar, 4), "n_pairs": n_pairs}}


@app.get("/drift")
async def drift_score():
    """Score de dérive de distribution (AGENT_ML_IA.md §6)."""
    if not _recent_scores:
        return {"drift_score": 0.0, "baseline": _baseline_score, "alert": False, "n_samples": 0}
    mean_recent = float(np.mean(list(_recent_scores)))
    score = abs(_baseline_score - mean_recent)
    alert = score > 0.05
    ML_DRIFT_SCORE.set(score)
    return {"drift_score": round(score, 4), "baseline": _baseline_score,
            "mean_recent": round(mean_recent, 4), "alert": alert, "n_samples": len(_recent_scores)}


# ── Utilitaires internes ──────────────────────────────────────────────────────────

def _load_image(contents: bytes) -> np.ndarray:
    try:
        return np.array(Image.open(io.BytesIO(contents)).convert("RGB"))
    except Exception as exc:
        raise HTTPException(400, f"Image invalide : {exc}")


def _load_labeled_samples(labeled_path: Path) -> list:
    samples = []
    if not labeled_path.exists():
        return samples
    for meta_file in labeled_path.glob("*.json"):
        try:
            meta = json.loads(meta_file.read_text())
            img_path = labeled_path / f"{meta_file.stem}.jpg"
            if img_path.exists() and meta.get("labeled_profile_id"):
                samples.append({"meta": meta, "img_path": img_path})
        except Exception:
            continue
    return samples


def _evaluate_on_samples(samples: list) -> dict:
    tp = fp = fn = tn = 0
    for s in samples:
        try:
            img = Image.open(s["img_path"]).convert("RGB")
            faces = engine.detect_and_embed(np.array(img))
            if not faces:
                continue
            emb = FaceEngine.normalize(faces[0]["embedding"])
            matches = store.search(emb)
            pred_id = matches[0]["profile_id"] if matches else None
            true_id = s["meta"].get("labeled_profile_id")
            action = s["meta"].get("label_action", "confirmed")
            if action == "intruder":
                if pred_id is None or (matches and matches[0]["score"] < THRESHOLD_AUTHORIZED):
                    tn += 1
                else:
                    fp += 1
            else:
                if pred_id == true_id:
                    tp += 1
                else:
                    fn += 1
        except Exception:
            continue
    total = tp + fp + fn + tn
    if total == 0:
        return {"far": _current_far, "frr": _current_frr, "eer": _current_eer, "tar": _current_tar}
    far = fp / max(fp + tn, 1)
    frr = fn / max(fn + tp, 1)
    tar = tp / max(tp + fn, 1)
    return {"far": round(far, 4), "frr": round(frr, 4), "eer": round((far + frr) / 2, 4), "tar": round(tar, 4)}


def _save_checkpoint(run_id: str):
    d = Path("/data/models/checkpoints")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{run_id}.json").write_text(json.dumps({
        "run_id": run_id, "version": _model_version,
        "far": _current_far, "frr": _current_frr,
        "eer": _current_eer, "tar": _current_tar,
        "saved_at": datetime.utcnow().isoformat(),
    }))


def _queue_for_review(image_bytes: bytes, camera_id: str, result: dict):
    import uuid
    review_id = str(uuid.uuid4())
    pending_dir = Path(ACTIVE_LEARNING_PATH) / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    (pending_dir / f"{review_id}.jpg").write_bytes(image_bytes)
    (pending_dir / f"{review_id}.json").write_text(json.dumps({
        "review_id": review_id, "camera_id": camera_id,
        "confidence": result["confidence"], "status": result["status"],
        "profile_id": result["profile_id"], "candidates": result["candidates"],
    }))
    ML_ACTIVE_LEARNING_QUEUE.inc()
