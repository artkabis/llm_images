"""
Service Vidéo — Point d'entrée cross-platform (Windows/Linux/macOS)
LOCAL_MODE : publish via HTTP vers API (pas de Redis)
Docker mode : publish via Redis directement
"""
import json
import os
import platform
import structlog
import yaml
from contextlib import asynccontextmanager
from fastapi import FastAPI
from prometheus_client import make_asgi_app
from camera_manager import CameraWorker

log = structlog.get_logger()

IS_WINDOWS = platform.system() == "Windows"
LOCAL_MODE = os.getenv("LOCAL_MODE", "false").lower() == "true"

_default_cameras = (
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "cameras.yml")
    if IS_WINDOWS
    else "/config/cameras.yml"
)
CAMERAS_CONFIG_PATH = os.getenv("CAMERAS_CONFIG", _default_cameras)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
API_SERVICE_URL = os.getenv("API_SERVICE_URL", "http://localhost:8000")

workers: list[CameraWorker] = []


def _build_publish_fn():
    """
    LOCAL_MODE : POST HTTP vers /internal/broadcast de l'API (EventBus in-memory)
    Docker mode: Redis pub/sub direct
    """
    if LOCAL_MODE:
        import httpx

        def publish_fn(channel: str, payload: dict):
            try:
                with httpx.Client(timeout=2.0) as c:
                    c.post(
                        f"{API_SERVICE_URL}/internal/broadcast",
                        json={"channel": channel, "data": payload},
                    )
            except Exception as exc:
                log.debug("publish http non-critique", error=str(exc))

        log.info("Mode local : publish via HTTP", url=API_SERVICE_URL)
        return publish_fn
    else:
        import redis as _redis

        _rc = _redis.from_url(REDIS_URL)

        def publish_fn(channel: str, payload: dict):
            _rc.publish(channel, json.dumps(payload))

        log.info("Mode Docker : publish via Redis", url=REDIS_URL)
        return publish_fn


@asynccontextmanager
async def lifespan(app: FastAPI):
    config_path = os.path.normpath(CAMERAS_CONFIG_PATH)
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        cameras = config.get("cameras", [])
        log.info("Caméras chargées", path=config_path, n=len(cameras))
    except FileNotFoundError:
        log.warning("cameras.yml introuvable — aucune caméra démarrée", path=config_path)
        cameras = []

    publish_fn = _build_publish_fn()

    for cam in cameras:
        cam_id = cam.get("id", "?")
        try:
            w = CameraWorker(config=cam, publish_fn=publish_fn)
            w.start()
            workers.append(w)
            log.info("Worker caméra lancé", camera_id=cam_id)
        except Exception as exc:
            log.error("Impossible de démarrer la caméra", camera_id=cam_id, error=str(exc))

    log.info("Service vidéo démarré", n_cameras=len(workers), os=platform.system())
    yield

    for w in workers:
        w.stop()
    log.info("Service vidéo arrêté")


app = FastAPI(title="Video Service", docs_url=None, lifespan=lifespan)
app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "cameras": [{"id": w.camera_id, "status": w._status} for w in workers],
        "os": platform.system(),
        "local_mode": LOCAL_MODE,
    }
