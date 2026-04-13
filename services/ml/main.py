"""
Service ML — API interne (port 8001)
Consommé uniquement par l'Agent Backend, jamais exposé publiquement.
"""
import io
import os
import numpy as np
import structlog
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from PIL import Image

from face_engine import FaceEngine
from embedding_store import EmbeddingStore
from metrics import ML_FACES_DETECTED, ML_ENROLLMENT_TOTAL, ML_ACTIVE_LEARNING_QUEUE

log = structlog.get_logger()

app = FastAPI(title="ML Service", docs_url=None, redoc_url=None)

# ── Montage métriques Prometheus ────────────────────────────
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ── Singletons (chargés au démarrage) ───────────────────────
engine = FaceEngine()
store = EmbeddingStore()

ACTIVE_LEARNING_PATH = os.getenv("DATA_ACTIVE_LEARNING_PATH", "/data/active_learning")
THRESHOLD_SUSPECT = float(os.getenv("ML_THRESHOLD_SUSPECT", 0.70))
THRESHOLD_AUTHORIZED = float(os.getenv("ML_THRESHOLD_AUTHORIZED", 0.85))


# ── Health ──────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "n_profiles": store.n_profiles}


# ── Identification ───────────────────────────────────────────

@app.post("/identify")
async def identify(
    file: UploadFile = File(...),
    camera_id: str = "unknown",
):
    """
    Identifie les visages dans une image.
    Retourne la liste des visages détectés avec score et statut.
    """
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
            status = "unknown"
            top_score = 0.0
            top_profile_id = None
        else:
            top = matches[0]
            top_score = top["score"]
            top_profile_id = top["profile_id"]
            status = engine.classify(top_score)

        ML_FACES_DETECTED.labels(status=status).inc()

        result = {
            "bbox": face["bbox"],
            "det_score": face["det_score"],
            "status": status,
            "confidence": round(top_score * 100, 1),
            "profile_id": top_profile_id,
            "candidates": matches[:3],
        }
        output.append(result)

        # Active learning : zone d'incertitude → file de review
        if THRESHOLD_SUSPECT <= top_score < THRESHOLD_AUTHORIZED:
            _queue_for_review(contents, camera_id, result)

    return {"faces": output, "camera_id": camera_id}


# ── Enrôlement ──────────────────────────────────────────────

@app.post("/enroll/{profile_id}")
async def enroll(
    profile_id: str,
    files: list[UploadFile] = File(...),
):
    """
    Enrôle un nouveau profil à partir de N images.
    Minimum 1 image avec visage détectable.
    """
    embeddings = []
    for f in files:
        contents = await f.read()
        image = _load_image(contents)
        faces = engine.detect_and_embed(image)
        if faces:
            emb = FaceEngine.normalize(faces[0]["embedding"])
            embeddings.append(emb)

    if not embeddings:
        raise HTTPException(status_code=422, detail="Aucun visage détecté dans les images fournies")

    success = store.add_profile(profile_id, embeddings)
    if not success:
        raise HTTPException(status_code=409, detail=f"Profil {profile_id} déjà existant")

    ML_ENROLLMENT_TOTAL.inc()
    log.info("Profil enrôlé", profile_id=profile_id, n_embeddings=len(embeddings))
    return {"profile_id": profile_id, "n_embeddings": len(embeddings), "status": "enrolled"}


@app.post("/enroll/{profile_id}/update")
async def update_enrollment(
    profile_id: str,
    files: list[UploadFile] = File(...),
):
    """Ajoute de nouvelles photos à un profil existant."""
    embeddings = []
    for f in files:
        contents = await f.read()
        image = _load_image(contents)
        faces = engine.detect_and_embed(image)
        if faces:
            emb = FaceEngine.normalize(faces[0]["embedding"])
            embeddings.append(emb)

    if not embeddings:
        raise HTTPException(status_code=422, detail="Aucun visage détecté")

    success = store.update_profile(profile_id, embeddings)
    if not success:
        raise HTTPException(status_code=404, detail=f"Profil {profile_id} introuvable")

    return {"profile_id": profile_id, "n_new_embeddings": len(embeddings), "status": "updated"}


@app.delete("/enroll/{profile_id}")
async def delete_enrollment(profile_id: str):
    """Supprime un profil de l'index FAISS (droit à l'oubli)."""
    success = store.remove_profile(profile_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Profil {profile_id} introuvable")
    return {"profile_id": profile_id, "status": "deleted"}


# ── Utilitaires internes ─────────────────────────────────────

def _load_image(contents: bytes) -> np.ndarray:
    """Convertit des bytes en array RGB numpy."""
    try:
        pil_img = Image.open(io.BytesIO(contents)).convert("RGB")
        return np.array(pil_img)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Image invalide : {exc}")


def _queue_for_review(image_bytes: bytes, camera_id: str, result: dict):
    """Stocke une frame incertaine pour l'active learning."""
    import uuid, json
    from pathlib import Path

    review_id = str(uuid.uuid4())
    pending_dir = Path(ACTIVE_LEARNING_PATH) / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    img_path = pending_dir / f"{review_id}.jpg"
    meta_path = pending_dir / f"{review_id}.json"

    img_path.write_bytes(image_bytes)
    meta_path.write_text(json.dumps({
        "review_id": review_id,
        "camera_id": camera_id,
        "confidence": result["confidence"],
        "status": result["status"],
        "profile_id": result["profile_id"],
        "candidates": result["candidates"],
    }))

    ML_ACTIVE_LEARNING_QUEUE.inc()
    log.info("Frame envoyée en active learning", review_id=review_id, score=result["confidence"])
