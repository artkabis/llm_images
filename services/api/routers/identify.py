"""Router /identify — Identification d'une image + création d'alerte."""
from datetime import datetime
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import redis.asyncio as aioredis
import json, uuid
from pathlib import Path

from core.database import get_db, Alert, AlertLevel, AlertStatus
from core.security import require_role
from core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.post("/")
async def identify_image(
    file: UploadFile = File(...),
    camera_id: str = "manual",
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("operator")),
):
    """Identifie les visages dans une image et crée les alertes nécessaires."""
    contents = await file.read()

    # Validation format
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(400, "Format accepté : JPEG, PNG, WEBP")
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(400, "Image trop grande (max 10 Mo)")

    # Appel service ML
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{settings.ml_service_url}/identify",
            files={"file": (file.filename, contents, file.content_type)},
            data={"camera_id": camera_id},
        )
    if resp.status_code != 200:
        raise HTTPException(503, "Service ML indisponible")

    result = resp.json()
    faces = result.get("faces", [])

    # Création alertes pour suspects et intrus
    alerts_created = []
    for face in faces:
        if face["status"] in ("suspect", "unknown"):
            level = AlertLevel.WARNING if face["status"] == "suspect" else AlertLevel.ALERT

            # Sauvegarde frame
            frame_path = _save_frame(contents, camera_id)

            alert = Alert(
                id=str(uuid.uuid4()),
                camera_id=camera_id,
                level=level,
                status=AlertStatus.OPEN,
                confidence=face["confidence"] / 100,
                profile_id=face.get("profile_id"),
                frame_path=str(frame_path),
            )
            db.add(alert)
            alerts_created.append(alert.id)

    if alerts_created:
        await db.commit()

    return {
        "faces": faces,
        "camera_id": camera_id,
        "alerts_created": len(alerts_created),
    }


@router.get("/history")
async def identification_history(
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("operator")),
):
    q = select(Alert).order_by(desc(Alert.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    return result.scalars().all()


def _save_frame(contents: bytes, camera_id: str) -> Path:
    """Sauvegarde la frame capturée dans le répertoire sécurisé."""
    frame_dir = Path(settings.secure_frames_path) / datetime.utcnow().strftime("%Y-%m-%d")
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_path = frame_dir / f"{uuid.uuid4()}.jpg"
    frame_path.write_bytes(contents)
    return frame_path
