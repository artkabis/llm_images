"""Router /review — Active learning : file de labellisation et fine-tuning."""
import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
import httpx

from core.database import get_db, ReviewItem, ReviewStatus
from core.security import require_role
from core.config import get_settings

router = APIRouter()
settings = get_settings()


class LabelRequest(BaseModel):
    action: str          # confirmed | corrected | new_profile | intruder | rejected
    profile_id: str | None = None   # obligatoire si action=corrected


@router.get("/queue")
async def get_review_queue(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("operator")),
):
    """Retourne les frames en attente de labellisation, triées par incertitude (score le plus bas en premier)."""
    q = (
        select(ReviewItem)
        .where(ReviewItem.status == ReviewStatus.PENDING)
        .order_by(ReviewItem.confidence.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(q)
    items = result.scalars().all()

    # Compter total pending
    count = await db.execute(select(func.count()).where(ReviewItem.status == ReviewStatus.PENDING))
    total_pending = count.scalar()

    return {
        "items": items,
        "total_pending": total_pending,
        "trigger_threshold": settings.ml_active_learning_trigger,
        "page": page,
    }


@router.post("/{review_id}/label")
async def submit_label(
    review_id: str,
    body: LabelRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("operator")),
):
    """Soumet un label pour une frame de review et déclenche le fine-tuning si seuil atteint."""
    result = await db.execute(select(ReviewItem).where(ReviewItem.id == review_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Élément de review introuvable")
    if item.status != ReviewStatus.PENDING:
        raise HTTPException(409, "Élément déjà labellisé")

    # Validation
    if body.action == "corrected" and not body.profile_id:
        raise HTTPException(400, "profile_id obligatoire pour action=corrected")

    # Mise à jour statut
    status_map = {
        "confirmed":   ReviewStatus.CONFIRMED,
        "corrected":   ReviewStatus.CORRECTED,
        "intruder":    ReviewStatus.INTRUDER,
        "rejected":    ReviewStatus.REJECTED,
        "new_profile": ReviewStatus.CONFIRMED,
    }
    item.status = status_map.get(body.action, ReviewStatus.REJECTED)
    item.labeled_profile_id = body.profile_id or item.suggested_profile_id
    item.labeled_at = datetime.utcnow()
    item.operator_id = user.id
    await db.commit()

    # Vérifier seuil de déclenchement
    count = await db.execute(
        select(func.count()).where(
            ReviewItem.status.in_([ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED])
        )
    )
    labeled_count = count.scalar()

    triggered = False
    if labeled_count >= settings.ml_active_learning_trigger:
        triggered = True
        # Déclencher fine-tuning via Celery (tâche asynchrone)
        try:
            from workers.celery_app import celery_app
            celery_app.send_task("workers.tasks.fine_tune_model", queue="low")
        except Exception:
            pass  # Le fine-tuning peut aussi être déclenché manuellement

    return {
        "review_id": review_id,
        "status": item.status,
        "labeled_count": labeled_count,
        "fine_tuning_triggered": triggered,
    }


@router.post("/training/trigger")
async def trigger_training(
    _=Depends(require_role("admin")),
):
    """Déclenche un fine-tuning manuel."""
    try:
        from workers.celery_app import celery_app
        task = celery_app.send_task("workers.tasks.fine_tune_model", queue="low")
        return {"status": "triggered", "task_id": task.id}
    except Exception as e:
        raise HTTPException(503, f"Impossible de déclencher le fine-tuning : {e}")


@router.get("/training/history")
async def training_history():
    """Retourne l'historique des entraînements depuis MLflow."""
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(
                f"{settings.mlflow_tracking_uri}/api/2.0/mlflow/runs/search",
                params={"experiment_ids": '["1"]', "max_results": 20},
            )
            return resp.json()
        except Exception:
            return {"runs": [], "message": "MLflow indisponible"}
