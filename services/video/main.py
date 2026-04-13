"""Service Vidéo — Point d'entrée
Lance les workers caméra et expose un endpoint de santé.
Conforme à AGENT_VIDEO.md §3 Architecture multi-caméras

Cross-platform : Windows (LOCAL_MODE + HTTP publish) + Linux/Docker (Redis publish)
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

# Résolution chemin cameras.yml multi-plateforme
_DEFAULT_CAMERAS_PATH = (
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "cameras.yml")
    if IS_WINDOWS
    else "/config/cameras.yml"
)
CAMERAS_CONFIG_PATH = os.getenv("CAMERAS_CONFIG", _DEFAULT_CAMERAS_PATH)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
API_SERVICE_URL = os.getenv("API_SERVICE_URL", "http://localhost:8000")

workers: list[CameraWorker] = []


def _build_publish_fn():
    """
    Construit la fonction publish selon le mode d'exécution.

    - LOCAL_MODE : POST HTTP vers /internal/broadcast de l'API
                   (fonctionne sans Redis — Windows, dev local)
    - Docker mode : Redis pub/sub direct
    """
    if LOCAL_MODE:
        import httpx

        def publish_fn(channel: str, payload: dict):
            try:
                with httpx.Client(timeout=2.0) as client:
                    client.post(
                        f"{API_SERVICE_URL}/internal/broadcast",
                        json={"channel": channel, "data": payload},
                    )
            except Exception as exc:
                log.debug("publish HTTP ignoré (non critique)", error=str(exc))

        log.info("Mode local : publication via HTTP vers l'API", url=API_SERVICE_URL)
        return publish_fn

    else:
        import redis as _redis

        _redis_client = _redis.from_url(REDIS_URL)

        def publish_fn(channel: str, payload: dict):
            _redis_client.publish(channel, json.dumps(payload))

        log.info("Mode Docker : publication via Redis", url=REDIS_URL)
        return publish_fn


@asynccontextmanager
async def lifespan(app: FastAPI):
    config_path = os.path.normpath(CAMERAS_CONFIG_PATH)
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        cameras = config.get("cameras", [])
        log.info("Configuration caméras chargée", path=config_path, n=len(cameras))
    except FileNotFoundError:
        log.warning("cameras.yml introuvable — aucune caméra démarrée", path=config_path)
        cameras = []

    publish_fn = _build_publish_fn()

    for cam_config in cameras:
        cam_id = cam_config.get("id", "unknown")
        try:
            worker = CameraWorker(config=cam_config, publish_fn=publish_fn)
            worker.start()
            workers.append(worker)
            log.info("Worker caméra lancé", camera_id=cam_id)
        except Exception as exc:
            log.error("Impossible de démarrer la caméra", camera_id=cam_id, error=str(exc))

    log.info("Service vidéo démarré", n_cameras=len(workers), os=platform.system(), local_mode=LOCAL_MODE)
    yield

    for worker in workers:
        worker.stop()
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
