"""
Proxy router: exposes ML-service endpoints under /ml so the frontend
does not need to call the ML service directly.

Routes:
  GET /ml/model/info   -> ML /model/info
  GET /ml/drift        -> ML /drift

Mount in services/api/main.py:
  from routers.ml_proxy import router as ml_router
  app.include_router(ml_router, prefix="/ml", tags=["ml"])
"""

import asyncio
import os
from fastapi import APIRouter, Depends, HTTPException
import httpx

from core.auth import require_role

router = APIRouter()

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://ml:8001")
_TIMEOUT = 5.0


async def _ml_get(path: str) -> dict:
    """Forward a GET request to the ML service and return parsed JSON."""
    url = f"{ML_SERVICE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"ML service timeout on {path}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ML service unavailable: {exc}")


@router.get("/model/info")
async def ml_model_info(current_user=Depends(require_role("viewer"))):
    """
    Current model metadata: version, n_profiles, model_name, FAR, FRR, EER, TAR.
    Proxied from the ML service.
    """
    return await _ml_get("/model/info")


@router.get("/drift")
async def ml_drift(current_user=Depends(require_role("viewer"))):
    """
    Distribution drift indicator.
    Returns drift_score, baseline_score, recent_mean, alert (bool).
    Proxied from the ML service.
    """
    return await _ml_get("/drift")
