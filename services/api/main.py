"""
Service API - Point d'entree FastAPI
Conforme a AGENT_BACKEND.md
"""
import asyncio
import json
import os
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from prometheus_client import make_asgi_app

from core.config import get_settings
from core.database import init_db
from core.eventbus import bus
from core.metrics import (
    CAMERAS_ACTIVE, MODEL_FAR, MODEL_FRR, MODEL_EER, MODEL_TAR,
    MODEL_DRIFT, MODEL_PROFILES, MODEL_INFO,
)
from routers import profiles, identify, alerts, auth, monitoring, review
from routers.ml_proxy import router as ml_router

log = structlog.get_logger()
settings = get_settings()

LOCAL_MODE = os.getenv("LOCAL_MODE", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Demarrage du service API", env=settings.app_env, local_mode=LOCAL_MODE)
    await init_db()
    await bus.init(redis_url=None if LOCAL_MODE else settings.redis_url)
    app.state.ws_manager = ConnectionManager()
    # Initialisation des metriques statiques
    MODEL_INFO.info({"name": "buffalo_l", "version": "1.0"})
    CAMERAS_ACTIVE.set(0)
    log.info("Service API pret")
    yield
    log.info("Service API arrete")


app = FastAPI(
    title="Facial Recognition API",
    version="1.0.0",
    docs_url="/api/docs" if settings.app_debug else None,
    redoc_url=None,
    lifespan=lifespan,
)

# -- Middleware --
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Prometheus /metrics --
app.mount("/metrics", make_asgi_app())

# -- Routers --
PREFIX = settings.api_v1_prefix
app.include_router(auth.router,       prefix=f"{PREFIX}/auth",       tags=["Auth"])
app.include_router(profiles.router,   prefix=f"{PREFIX}/profiles",   tags=["Profiles"])
app.include_router(identify.router,   prefix=f"{PREFIX}/identify",   tags=["Identify"])
app.include_router(alerts.router,     prefix=f"{PREFIX}/alerts",     tags=["Alerts"])
app.include_router(review.router,     prefix=f"{PREFIX}/review",     tags=["Review"])
app.include_router(monitoring.router, prefix=f"{PREFIX}/monitoring", tags=["Monitoring"])
app.include_router(ml_router,         prefix=f"{PREFIX}/ml",         tags=["ML"])


# -- WebSocket Manager --

class ConnectionManager:
    """Gere les connexions WebSocket actives par canal."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, channel: str):
        await ws.accept()
        self._connections.setdefault(channel, []).append(ws)

    def disconnect(self, ws: WebSocket, channel: str):
        conns = self._connections.get(channel, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, channel: str, data: dict):
        dead = []
        for ws in self._connections.get(channel, []):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections[channel].remove(ws)


# -- WebSocket endpoints --

@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    manager: ConnectionManager = websocket.app.state.ws_manager
    await manager.connect(websocket, "alerts")
    try:
        async for raw in bus.subscribe("channel:alerts"):
            payload = raw if isinstance(raw, str) else json.dumps(raw)
            await websocket.send_text(payload)
    except WebSocketDisconnect:
        manager.disconnect(websocket, "alerts")


@app.websocket("/ws/metrics")
async def ws_metrics(websocket: WebSocket):
    """Stream metriques systeme toutes les 5 secondes."""
    manager: ConnectionManager = websocket.app.state.ws_manager
    await manager.connect(websocket, "metrics")
    try:
        while True:
            await asyncio.sleep(5)
            import psutil
            data = {
                "cpu_percent": psutil.cpu_percent(),
                "ram_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage("/").percent,
            }
            await websocket.send_json(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket, "metrics")


@app.websocket("/ws/cameras/{camera_id}")
async def ws_camera(websocket: WebSocket, camera_id: str):
    manager: ConnectionManager = websocket.app.state.ws_manager
    await manager.connect(websocket, f"camera_{camera_id}")
    try:
        async for raw in bus.subscribe("channel:detections"):
            payload = json.loads(raw) if isinstance(raw, str) else raw
            if payload.get("camera_id") == camera_id:
                await websocket.send_json(payload)
    except WebSocketDisconnect:
        manager.disconnect(websocket, f"camera_{camera_id}")


# -- Internal broadcast (video service -> EventBus en LOCAL_MODE) --

class BroadcastPayload(BaseModel):
    channel: str
    data: dict


@app.post("/internal/broadcast", include_in_schema=False)
async def internal_broadcast(payload: BroadcastPayload):
    await bus.publish(payload.channel, payload.data)
    return {"ok": True}


# -- Health --

@app.get(f"{PREFIX}/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "1.0.0", "env": settings.app_env}
