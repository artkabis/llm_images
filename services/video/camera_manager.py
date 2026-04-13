"""
Camera Manager — Ingestion flux vidéo multi-caméras
Conforme à AGENT_VIDEO.md §3 Architecture multi-caméras
"""
import asyncio
import time
import threading
import cv2
import numpy as np
import structlog
import httpx
import redis
import io
from pathlib import Path
from PIL import Image

from metrics import (
    VIDEO_FPS_EFFECTIVE, VIDEO_STREAM_STATUS,
    VIDEO_FRAMES_DROPPED, VIDEO_RECONNECT_COUNT,
    VIDEO_QUEUE_SIZE,
)

log = structlog.get_logger()

REDIS_URL = __import__("os").getenv("REDIS_URL", "redis://redis:6379/0")
ML_SERVICE_URL = __import__("os").getenv("ML_SERVICE_URL", "http://ml:8001")
BLUR_THRESHOLD = 50.0        # Variance Laplacien min
MIN_BRIGHTNESS = 20
MAX_BRIGHTNESS = 240
RECONNECT_DELAYS = [2, 4, 8, 8]  # Backoff exponentiel (s)


class CameraWorker(threading.Thread):
    """Worker dédié à une caméra. Tourne dans son propre thread."""

    def __init__(self, config: dict, redis_client: redis.Redis):
        super().__init__(daemon=True)
        self.config = config
        self.camera_id: str = config["id"]
        self.source = config.get("url") or config.get("device_id", 0)
        self.fps_target: int = config.get("fps_target", 15)
        self.redis = redis_client
        self._stop_event = threading.Event()
        self._cap: cv2.VideoCapture | None = None
        self._status = 0  # 0=coupé, 1=actif, 2=dégradé
        self._frame_interval = 1.0 / self.fps_target

    def run(self):
        log.info("Worker caméra démarré", camera_id=self.camera_id)
        while not self._stop_event.is_set():
            self._connect_and_capture()

    def stop(self):
        self._stop_event.set()
        if self._cap:
            self._cap.release()

    def _connect_and_capture(self):
        """Connexion avec backoff exponentiel et boucle de capture."""
        for attempt, delay in enumerate(RECONNECT_DELAYS):
            if self._stop_event.is_set():
                return
            cap = cv2.VideoCapture(self.source)
            if cap.isOpened():
                self._cap = cap
                self._set_status(1)
                log.info("Caméra connectée", camera_id=self.camera_id, attempt=attempt)
                self._capture_loop()
                return
            log.warning("Connexion échouée", camera_id=self.camera_id, attempt=attempt, retry_in=delay)
            VIDEO_RECONNECT_COUNT.labels(camera_id=self.camera_id).inc()
            time.sleep(delay)

        # Après tous les essais → alerte critique
        self._set_status(0)
        self._publish_alert(level="CRITICAL", message=f"Caméra {self.camera_id} inaccessible après {len(RECONNECT_DELAYS)} tentatives")
        time.sleep(30)

    def _capture_loop(self):
        """Boucle de capture à la cadence cible."""
        last_frame_time = 0.0
        consecutive_failures = 0

        while not self._stop_event.is_set() and self._cap and self._cap.isOpened():
            now = time.time()
            if now - last_frame_time < self._frame_interval:
                time.sleep(0.005)
                continue

            ret, frame_bgr = self._cap.read()
            if not ret:
                consecutive_failures += 1
                if consecutive_failures >= 10:
                    log.error("Perte de flux", camera_id=self.camera_id)
                    self._set_status(0)
                    return
                continue

            consecutive_failures = 0
            last_frame_time = now

            # Contrôle qualité
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            if not self._quality_check(frame_rgb):
                VIDEO_FRAMES_DROPPED.labels(camera_id=self.camera_id).inc()
                continue

            # Envoi au service ML via Redis queue
            self._push_to_ml(frame_rgb)
            fps_actual = 1.0 / max(time.time() - last_frame_time, 0.001)
            VIDEO_FPS_EFFECTIVE.labels(camera_id=self.camera_id).set(fps_actual)

        self._set_status(0)

    def _quality_check(self, frame_rgb: np.ndarray) -> bool:
        """Rejette les frames floues, surexposées ou sous-exposées."""
        gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
        blur = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = gray.mean()

        if blur < BLUR_THRESHOLD:
            return False
        if not (MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS):
            return False
        return True

    def _push_to_ml(self, frame_rgb: np.ndarray):
        """Encode la frame en JPEG et l'envoie au service ML via HTTP."""
        try:
            pil_img = Image.fromarray(frame_rgb)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=85)
            frame_bytes = buf.getvalue()

            # Appel synchrone (dans le thread worker)
            with httpx.Client(timeout=5) as client:
                resp = client.post(
                    f"{ML_SERVICE_URL}/identify",
                    files={"file": ("frame.jpg", frame_bytes, "image/jpeg")},
                    data={"camera_id": self.camera_id},
                )
            if resp.status_code == 200:
                result = resp.json()
                # Publier les détections sur Redis pour le frontend WebSocket
                self.redis.publish("channel:detections", __import__("json").dumps({
                    "camera_id": self.camera_id,
                    "faces": result.get("faces", []),
                    "timestamp": time.time(),
                }))
        except Exception as exc:
            log.error("Erreur envoi frame au ML", camera_id=self.camera_id, error=str(exc))

    def _set_status(self, status: int):
        self._status = status
        VIDEO_STREAM_STATUS.labels(camera_id=self.camera_id).set(status)

    def _publish_alert(self, level: str, message: str):
        self.redis.publish("channel:alerts", __import__("json").dumps({
            "level": level,
            "camera_id": self.camera_id,
            "message": message,
            "timestamp": time.time(),
        }))
