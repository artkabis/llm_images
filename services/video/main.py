"""
Service Vidéo — Point d'entrée
Lance les workers caméra et expose un endpoint de santé.
"""
import os
import yaml
import redis
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from camera_manager import CameraWorker

log = structlog.get_logger()
CAMERAS_CONFIG_PATH = os.getenv("CAMERAS_CONFIG", "/config/cameras.yml")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

workers: list[CameraWorker] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Chargement config caméras
    try:
        with open(CAMERAS_CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        cameras = config.get("cameras", [])
    except FileNotFoundError:
        log.warning("Fichier cameras.yml introuvable, aucune caméra démarrée")
        cameras = []

    redis_client = redis.from_url(REDIS_URL)

    # Démarrage des workers
    for cam_config in cameras:
        worker = CameraWorker(config=cam_config, redis_client=redis_client)
        worker.start()
        workers.append(worker)
        log.info("Worker caméra lancé", camera_id=cam_config["id"])

    log.info("Service vidéo démarré", n_cameras=len(workers))
    yield

    # Arrêt propre
    for worker in workers:
        worker.stop()
    log.info("Service vidéo arrêté")


app = FastAPI(title="Video Service", docs_url=None, lifespan=lifespan)
app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "cameras": [
            {"id": w.camera_id, "status": w._status}
            for w in workers
        ],
    }
