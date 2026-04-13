"""Router /profiles — CRUD profils + appel ML pour enrôlement."""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
import httpx

from core.database import get_db, Profile
from core.security import require_role
from core.config import get_settings

router = APIRouter()
settings = get_settings()
ML_URL = settings.ml_service_url


# ── Schémas ─────────────────────────────────────────────────

class ProfileOut(BaseModel):
    id: str
    name: str
    role: str | None
    active: bool
    n_images: int
    created_at: datetime
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class ProfileList(BaseModel):
    items: list[ProfileOut]
    total: int
    page: int
    page_size: int


# ── Endpoints ────────────────────────────────────────────────

@router.post("/", response_model=ProfileOut, status_code=201)
async def create_profile(
    name: str = Form(...),
    role: str = Form(None),
    expires_at: datetime = Form(None),
    photos: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
):
    """Crée un profil et l'enrôle dans l'index FAISS via le service ML."""
    if len(photos) < 1:
        raise HTTPException(400, "Au moins 1 photo requise")

    profile_id = str(uuid.uuid4())

    # Enrôlement ML
    async with httpx.AsyncClient(timeout=30) as client:
        files = [("files", (p.filename, await p.read(), p.content_type)) for p in photos]
        resp = await client.post(f"{ML_URL}/enroll/{profile_id}", files=files)
        if resp.status_code == 422:
            raise HTTPException(422, "Aucun visage détecté dans les photos fournies")
        if resp.status_code != 200:
            raise HTTPException(503, "Service ML indisponible")
        ml_data = resp.json()

    # Persistance base de données
    profile = Profile(
        id=profile_id,
        name=name,
        role=role,
        n_images=ml_data["n_embeddings"],
        expires_at=expires_at,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/", response_model=ProfileList)
async def list_profiles(
    page: int = 1,
    page_size: int = 50,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("operator")),
):
    offset = (page - 1) * page_size
    q = select(Profile)
    if active_only:
        q = q.where(Profile.active == True)
    result = await db.execute(q.offset(offset).limit(page_size))
    items = result.scalars().all()

    count_result = await db.execute(select(Profile))
    total = len(count_result.scalars().all())
    return ProfileList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("operator")),
):
    result = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profil introuvable")
    return profile


@router.post("/{profile_id}/photos")
async def add_photos(
    profile_id: str,
    photos: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
):
    """Ajoute des photos à un profil existant et recalcule le centroïde."""
    result = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profil introuvable")

    async with httpx.AsyncClient(timeout=30) as client:
        files = [("files", (p.filename, await p.read(), p.content_type)) for p in photos]
        resp = await client.post(f"{ML_URL}/enroll/{profile_id}/update", files=files)
        if resp.status_code != 200:
            raise HTTPException(503, "Mise à jour ML échouée")

    profile.n_images += len(photos)
    profile.updated_at = datetime.utcnow()
    await db.commit()
    return {"profile_id": profile_id, "status": "updated", "n_new_photos": len(photos)}


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role("admin")),
):
    """Supprime un profil (RGPD — embedding + DB)."""
    async with httpx.AsyncClient(timeout=10) as client:
        await client.delete(f"{ML_URL}/enroll/{profile_id}")

    await db.execute(delete(Profile).where(Profile.id == profile_id))
    await db.commit()
