"""
Service API — Point d'entrée FastAPI
Conforme à AGENT_BACKEND.md
"""
import asyncio
import json
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_client import make_asgi_app
import redis.asyncio as aioredis

from core.config import get_settings
from core.database import init_db
from core.security import require_role
from routers import profiles, identify, alerts, auth, monitoring, review

log = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log.info("Démarrage du service API", env=settings.app_env)
    await init_db()
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    app.state.ws_manager = ConnectionManager()
    log.info("Service API prêt")
    yield
    # Shutdown
    await app.state.redis.aclose()
    log.info("Service API arrêté")


app = FastAPI(
    title="Facial Recognition API",
    version="1.0.0",
    docs_url="/api/docs" if settings.app_debug else None,
    redoc_url=None,
    lifespan=lifespan,
)

# ── Middleware ───────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Métriques Prometheus ─────────────────────────────────────
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ── Routers ──────────────────────────────────────────────────
PREFIX = settings.api_v1_prefix
app.include_router(auth.router,       prefix=f"{PREFIX}/auth",       tags=["Auth"])
app.include_router(profiles.router,   prefix=f"{PREFIX}/profiles",   tags=["Profiles"])
app.include_router(identify.router,   prefix=f"{PREFIX}/identify",   tags=["Identify"])
app.include_router(alerts.router,     prefix=f"{PREFIX}/alerts",     tags=["Alerts"])
app.include_router(review.router,     prefix=f"{PREFIX}/review",     tags=["Review"])
app.include_router(monitoring.router, prefix=f"{PREFIX}/monitoring", tags=["Monitoring"])


# ── WebSocket Manager ────────────────────────────────────────

class ConnectionManager:
    """Gère les connexions WebSocket actives par canal."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, channel: str):
        await ws.accept()
        self._connections.setdefault(channel, []).append(ws)
        log.info("WS connecté", channel=channel, total=len(self._connections.get(channel, [])))

    def disconnect(self, ws: WebSocket, channel: str):
        self._connections.get(channel, []).remove(ws)

    async def broadcast(self, channel: str, data: dict):
        dead = []
        for ws in self._connections.get(channel, []):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.get(channel, []).remove(ws)


# ── WebSocket endpoints ──────────────────────────────────────

@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    """Stream des alertes temps réel (toutes caméras)."""
    manager: ConnectionManager = websocket.app.state.ws_manager
    await manager.connect(websocket, "alerts")
    redis: aioredis.Redis = websocket.app.state.redis
    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe("channel:alerts")
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        manager.disconnect(websocket, "alerts")


@app.websocket("/ws/metrics")
async def ws_metrics(websocket: WebSocket):
    """Stream métriques système toutes les 5 secondes."""
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


@app.get(f"{PREFIX}/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "1.0.0", "env": settings.app_env}
