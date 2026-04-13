"""Router /alerts — Gestion des alertes et incidents."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
import io, csv

from core.database import get_db, Alert, AlertLevel, AlertStatus
from core.security import require_role

router = APIRouter()


class AlertOut(BaseModel):
    id: str
    camera_id: str
    level: AlertLevel
    status: AlertStatus
    confidence: float
    profile_id: str | None
    frame_path: str | None
    operator_note: str | None
    created_at: datetime
    acknowledged_at: datetime | None

    model_config = {"from_attributes": True}


class AcknowledgeRequest(BaseModel):
    note: str


@router.get("/", response_model=list[AlertOut])
async def list_alerts(
    level: AlertLevel | None = None,
    status: AlertStatus | None = None,
    camera_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("operator")),
):
    q = select(Alert).order_by(desc(Alert.created_at))
    if level:
        q = q.where(Alert.level == level)
    if status:
        q = q.where(Alert.status == status)
    if camera_id:
        q = q.where(Alert.camera_id == camera_id)

    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("operator")),
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alerte introuvable")
    return alert


@router.post("/{alert_id}/ack")
async def acknowledge_alert(
    alert_id: str,
    body: AcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("operator")),
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alerte introuvable")
    if alert.status == AlertStatus.ACKNOWLEDGED:
        raise HTTPException(409, "Alerte déjà acquittée")

    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_at = datetime.utcnow()
    alert.operator_note = body.note
    await db.commit()
    return {"alert_id": alert_id, "status": "acknowledged"}


@router.get("/export/csv")
async def export_csv(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("operator")),
):
    """Export CSV des alertes."""
    result = await db.execute(select(Alert).order_by(desc(Alert.created_at)).limit(10000))
    alerts = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "camera_id", "level", "status", "confidence", "profile_id", "created_at", "acknowledged_at", "note"])
    for a in alerts:
        writer.writerow([a.id, a.camera_id, a.level, a.status, a.confidence, a.profile_id, a.created_at, a.acknowledged_at, a.operator_note])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=alerts_export.csv"},
    )
