"""
Router /review — Human-in-the-loop active learning.
Conforme AGENT_ML_IA.md §5 : 5 actions, seuil configurable, rollback MLflow.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import ReviewItem, ReviewStatus, get_db
from core.security import require_role

router = APIRouter()
settings = get_settings()

ACTIVE_LEARNING_PATH = os.getenv("DATA_ACTIVE_LEARNING_PATH", "/data/active_learning")
ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://ml:8001")
VALID_ACTIONS = {"confirmed", "corrected", "new_profile", "intruder", "rejected"}


# ── Schemas ───────────────────────────────────────────────────────────────

class LabelRequest(BaseModel):
    action: str
    profile_id: Optional[str] = None
    note: Optional[str] = None


class TrainingConfigRequest(BaseModel):
    trigger_threshold: Optional[int] = None
    confidence_min: Optional[float] = None
    confidence_max: Optional[float] = None
    auto_deploy: Optional[bool] = None
    min_improvement_pct: Optional[float] = None


# ── Helpers ───────────────────────────────────────────────────────────────

def _serialize(item: ReviewItem) -> dict:
    return {
        "id": str(item.id),
        "camera_id": item.camera_id,
        "confidence": item.confidence,
        "suggested_profile_id": item.suggested_profile_id,
        "candidates": getattr(item, "candidates", []) or [],
        "frame_path": str(item.frame_path) if getattr(item, "frame_path", None) else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "status": item.status.value if hasattr(item.status, "value") else str(item.status),
        "operator_note": getattr(item, "operator_note", None),
    }


def _threshold() -> int:
    return int(os.getenv("ML_ACTIVE_LEARNING_TRIGGER", str(getattr(settings, "ml_active_learning_trigger", 50))))


async def _labeled_count(db: AsyncSession) -> int:
    r = await db.execute(
        select(func.count()).where(
            ReviewItem.status.in_([
                ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED, ReviewStatus.INTRUDER
            ])
        )
    )
    return r.scalar() or 0


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/stats")
async def review_stats(db: AsyncSession = Depends(get_db), _=Depends(require_role("operator"))):
    """Statistiques globales de la file de review."""
    statuses = {"pending": ReviewStatus.PENDING, "confirmed": ReviewStatus.CONFIRMED,
                "corrected": ReviewStatus.CORRECTED, "intruder": ReviewStatus.INTRUDER,
                "rejected": ReviewStatus.REJECTED}
    counts = {}
    for name, status in statuses.items():
        r = await db.execute(select(func.count()).where(ReviewItem.status == status))
        counts[name] = r.scalar() or 0

    threshold = _threshold()
    labeled = counts["confirmed"] + counts["corrected"] + counts["intruder"]
    labeled_mod = labeled % threshold if threshold else 0
    return {
        "counts": counts,
        "labeled_total": labeled,
        "labeled_since_last_training": labeled_mod,
        "trigger_threshold": threshold,
        "next_trigger_in": max(0, threshold - labeled_mod) if threshold else 0,
        "progress_pct": round(labeled_mod / threshold * 100, 1) if threshold else 0,
    }


@router.get("/queue")
async def get_queue(
    page: int = 1,
    page_size: int = 20,
    camera_id: Optional[str] = Query(None),
    confidence_min: Optional[float] = Query(None),
    confidence_max: Optional[float] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("operator")),
):
    q = select(ReviewItem).where(ReviewItem.status == ReviewStatus.PENDING)
    if camera_id:
        q = q.where(ReviewItem.camera_id == camera_id)
    if confidence_min is not None:
        q = q.where(ReviewItem.confidence >= confidence_min)
    if confidence_max is not None:
        q = q.where(ReviewItem.confidence <= confidence_max)
    q = q.order_by(ReviewItem.confidence.asc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    items = result.scalars().all()

    count_q = select(func.count()).where(ReviewItem.status == ReviewStatus.PENDING)
    if camera_id:
        count_q = count_q.where(ReviewItem.camera_id == camera_id)
    cnt = await db.execute(count_q)
    total_pending = cnt.scalar() or 0

    threshold = _threshold()
    labeled = await _labeled_count(db)
    labeled_mod = labeled % threshold if threshold else 0
    return {
        "items": [_serialize(i) for i in items],
        "total_pending": total_pending,
        "labeled_count": labeled,
        "trigger_threshold": threshold,
        "next_trigger_in": max(0, threshold - labeled_mod),
        "progress_pct": round(labeled_mod / threshold * 100, 1) if threshold else 0,
        "page": page,
    }


@router.get("/{review_id}/frame")
async def get_frame(review_id: str, _=Depends(require_role("operator"))):
    """Sert l'image d'une frame incertaine."""
    path = Path(ACTIVE_LEARNING_PATH) / "pending" / f"{review_id}.jpg"
    if not path.exists():
        raise HTTPException(404, "Frame introuvable")
    return FileResponse(str(path), media_type="image/jpeg")


@router.post("/{review_id}/label")
async def submit_label(
    review_id: str,
    body: LabelRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("operator")),
):
    """
    Soumet un label humain. Actions : confirmed | corrected | new_profile | intruder | rejected
    Déclenche le fine-tuning automatiquement si le seuil est atteint.
    """
    if body.action not in VALID_ACTIONS:
        raise HTTPException(400, f"Action invalide. Valeurs : {sorted(VALID_ACTIONS)}")
    if body.action == "corrected" and not body.profile_id:
        raise HTTPException(400, "profile_id obligatoire pour action=corrected")

    result = await db.execute(select(ReviewItem).where(ReviewItem.id == review_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Élément introuvable")
    if item.status != ReviewStatus.PENDING:
        raise HTTPException(409, f"Déjà traité (statut: {item.status})")

    status_map = {
        "confirmed": ReviewStatus.CONFIRMED,
        "corrected": ReviewStatus.CORRECTED,
        "new_profile": ReviewStatus.CONFIRMED,
        "intruder": ReviewStatus.INTRUDER,
        "rejected": ReviewStatus.REJECTED,
    }
    item.status = status_map[body.action]
    item.labeled_profile_id = body.profile_id or item.suggested_profile_id
    item.labeled_at = datetime.utcnow()
    item.operator_id = str(user.id)
    if body.note:
        item.operator_note = body.note
    await db.commit()

    labeled = await _labeled_count(db)
    threshold = _threshold()
    labeled_mod = labeled % threshold if threshold else 0
    next_trigger = max(0, threshold - labeled_mod)

    triggered = False
    task_id = None
    if threshold > 0 and labeled > 0 and labeled % threshold == 0:
        triggered = True
        try:
            from workers.celery_app import celery_app
            task = celery_app.send_task("workers.tasks.fine_tune_model", queue="low")
            task_id = task.id
        except Exception:
            pass

    return {
        "review_id": review_id,
        "action": body.action,
        "status": item.status.value,
        "labeled_count": labeled,
        "next_trigger_in": next_trigger,
        "fine_tuning_triggered": triggered,
        "task_id": task_id,
    }


@router.post("/training/trigger")
async def trigger_training(_=Depends(require_role("admin"))):
    """Déclenche un fine-tuning manuel (admin uniquement)."""
    try:
        from workers.celery_app import celery_app
        task = celery_app.send_task("workers.tasks.fine_tune_model", queue="low")
        return {"status": "triggered", "task_id": task.id}
    except Exception as e:
        raise HTTPException(503, f"Worker Celery injoignable : {e}")


@router.get("/training/status")
async def training_status(_=Depends(require_role("operator"))):
    """Inspecte Celery pour savoir si un fine-tuning est en cours."""
    try:
        from workers.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=2.0)
        active = inspect.active() or {}
        running = [
            {"worker": w, "task_id": t.get("id"), "name": t.get("name")}
            for w, tasks in active.items()
            for t in tasks
            if "fine_tune" in t.get("name", "")
        ]
        return {"is_running": len(running) > 0, "running_tasks": running}
    except Exception as exc:
        return {"is_running": False, "running_tasks": [], "error": str(exc)}


@router.get("/training/config")
async def get_training_config(_=Depends(require_role("operator"))):
    """Retourne la configuration active de l'active learning."""
    return {
        "trigger_threshold": _threshold(),
        "confidence_min": float(os.getenv("ML_THRESHOLD_SUSPECT", "0.70")),
        "confidence_max": float(os.getenv("ML_THRESHOLD_AUTHORIZED", "0.85")),
        "auto_deploy": os.getenv("ML_AUTO_DEPLOY", "true").lower() == "true",
        "min_improvement_pct": float(os.getenv("ML_MIN_IMPROVEMENT_PCT", "1.0")),
    }


@router.put("/training/config")
async def update_training_config(
    body: TrainingConfigRequest,
    _=Depends(require_role("admin")),
):
    """Met à jour la configuration de l'active learning (admin)."""
    changes = {}
    if body.trigger_threshold is not None:
        os.environ["ML_ACTIVE_LEARNING_TRIGGER"] = str(body.trigger_threshold)
        changes["trigger_threshold"] = body.trigger_threshold
    if body.confidence_min is not None:
        os.environ["ML_THRESHOLD_SUSPECT"] = str(body.confidence_min)
        changes["confidence_min"] = body.confidence_min
    if body.confidence_max is not None:
        os.environ["ML_THRESHOLD_AUTHORIZED"] = str(body.confidence_max)
        changes["confidence_max"] = body.confidence_max
    if body.auto_deploy is not None:
        os.environ["ML_AUTO_DEPLOY"] = str(body.auto_deploy).lower()
        changes["auto_deploy"] = body.auto_deploy
    if body.min_improvement_pct is not None:
        os.environ["ML_MIN_IMPROVEMENT_PCT"] = str(body.min_improvement_pct)
        changes["min_improvement_pct"] = body.min_improvement_pct
    return {"status": "updated", "changes": changes,
            "warning": "En mémoire uniquement — redémarrer pour persister"}


@router.get("/training/history")
async def training_history(_=Depends(require_role("operator"))):
    """Historique des runs MLflow (fine-tunings passés)."""
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.post(
                f"{getattr(settings, 'mlflow_tracking_uri', 'http://mlflow:5000')}"
                "/api/2.0/mlflow/runs/search",
                json={"experiment_ids": ["1"], "max_results": 20, "order_by": ["start_time DESC"]},
            )
            runs_raw = resp.json().get("runs", [])
            return {
                "runs": [
                    {
                        "run_id": r["info"]["run_id"],
                        "run_name": r["info"].get("run_name", ""),
                        "status": r["info"]["status"],
                        "start_time": r["info"].get("start_time"),
                        "end_time": r["info"].get("end_time"),
                        "metrics": r.get("data", {}).get("metrics", {}),
                        "params": r.get("data", {}).get("params", {}),
                    }
                    for r in runs_raw
                ]
            }
        except Exception:
            return {"runs": [], "error": "MLflow indisponible"}


@router.post("/training/rollback/{run_id}")
async def rollback_model(run_id: str, _=Depends(require_role("admin"))):
    """Demande au service ML de revenir à la version du run spécifié (admin)."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(f"{ML_SERVICE_URL}/model/rollback", json={"run_id": run_id})
            return resp.json()
        except Exception as exc:
            raise HTTPException(503, f"Service ML injoignable : {exc}")
