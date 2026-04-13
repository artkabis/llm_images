"""
Camera Manager — Ingestion flux vidéo multi-caméras
Conforme à AGENT_VIDEO.md §3 Architecture multi-caméras

Cross-platform : Windows (CAP_DSHOW, device_id int) + Linux/macOS (V4L2, /dev/videoX)
Local mode     : publish_fn callback découple Redis du worker → supporte EventBus in-memory
"""
import ctypes
import io
import json
import platform
import threading
import time
from collections.abc import Callable
from typing import Optional

import cv2
import httpx
import numpy as np
import structlog
from PIL import Image

from metrics import (
    VIDEO_FPS_EFFECTIVE,
    VIDEO_FRAMES_DROPPED,
    VIDEO_RECONNECT_COUNT,
    VIDEO_STREAM_STATUS,
)

log = structlog.get_logger()

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

ML_SERVICE_URL = __import__("os").getenv("ML_SERVICE_URL", "http://localhost:8001")
BLUR_THRESHOLD = 50.0   # Variance Laplacien min
MIN_BRIGHTNESS = 20
MAX_BRIGHTNESS = 240
RECONNECT_DELAYS = [2, 4, 8, 8]  # Backoff exponentiel (s)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_source(config: dict):
    """
    Retourne la source correcte pour cv2.VideoCapture selon le type de caméra
    et l'OS courant.

    - RTSP  → str  URL (tous OS)
    - USB   → int  device_id  (Windows / Linux avec index numérique)
            → str  "/dev/videoX" (Linux avec chemin explicite)
    """
    cam_type = config.get("type", "usb").lower()

    if cam_type == "rtsp":
        url = config.get("url", "")
        if not url:
            raise ValueError(f"Camera {config.get('id')}: 'url' required for RTSP type")
        return url

    # USB / local device
    device_id = config.get("device_id", 0)

    if IS_WINDOWS:
        # Windows : OpenCV attend un entier pour CAP_DSHOW
        if isinstance(device_id, str):
            # Accepter "0", "1", etc. en entrée YAML
            try:
                return int(device_id)
            except ValueError:
                raise ValueError(
                    f"Camera {config.get('id')}: device_id must be an integer on Windows, got '{device_id}'"
                )
        return int(device_id)

    # Linux / macOS
    if isinstance(device_id, str) and device_id.startswith("/dev/"):
        return device_id  # chemin explicite V4L2
    return int(device_id)  # indice numérique


def _open_capture(source) -> cv2.VideoCapture:
    """Ouvre un VideoCapture avec le bon backend selon l'OS et la source."""
    if IS_WINDOWS and isinstance(source, int):
        cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(source)
    return cap


def _set_thread_name(name: str):
    """Nomme le thread courant (Linux/macOS uniquement, best-effort)."""
    if IS_LINUX:
        try:
            # prctl(PR_SET_NAME, …)
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            libc.prctl(15, name[:15].encode(), 0, 0, 0)
        except Exception:
            pass
    elif platform.system() == "Darwin":
        try:
            libc = ctypes.CDLL("libc.dylib", use_errno=True)
            libc.pthread_setname_np(name[:63].encode())
        except Exception:
            pass
    # Windows : pas d'API standard, on ignore


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class CameraWorker(threading.Thread):
    """
    Worker dédié à une caméra. Tourne dans son propre thread daemon.

    Args:
        config      : dict de configuration caméra (id, type, url/device_id, fps_target, …)
        publish_fn  : callable(channel: str, payload: dict) — abstraction pub/sub.
                      Peut être Redis.publish ou EventBus.publish_sync selon le mode.
    """

    def __init__(self, config: dict, publish_fn: Callable[[str, dict], None]):
        super().__init__(daemon=True, name=f"cam-{config.get('id', 'unknown')}")
        self.config = config
        self.camera_id: str = config["id"]
        self.source = _resolve_source(config)
        self.fps_target: int = config.get("fps_target", 15)
        self._publish = publish_fn
        self._stop_event = threading.Event()
        self._cap: Optional[cv2.VideoCapture] = None
        self._status = 0  # 0=coupé, 1=actif, 2=dégradé
        self._frame_interval = 1.0 / max(self.fps_target, 1)

    # ------------------------------------------------------------------
    # Thread lifecycle
    # ------------------------------------------------------------------

    def run(self):
        _set_thread_name(self.name)
        log.info("Worker caméra démarré", camera_id=self.camera_id, source=str(self.source))
        while not self._stop_event.is_set():
            self._connect_and_capture()

    def stop(self):
        self._stop_event.set()
        if self._cap and self._cap.isOpened():
            self._cap.release()
            self._cap = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect_and_capture(self):
        """Connexion avec backoff exponentiel puis boucle de capture."""
        for attempt, delay in enumerate(RECONNECT_DELAYS):
            if self._stop_event.is_set():
                return

            cap = _open_capture(self.source)
            if cap.isOpened():
                self._cap = cap
                self._set_status(1)
                log.info("Caméra connectée", camera_id=self.camera_id, attempt=attempt)
                self._capture_loop()
                cap.release()
                self._cap = None
                return

            log.warning(
                "Connexion caméra échouée",
                camera_id=self.camera_id,
                attempt=attempt,
                retry_in=delay,
            )
            VIDEO_RECONNECT_COUNT.labels(camera_id=self.camera_id).inc()
            self._stop_event.wait(delay)  # interruptible

        # Échec définitif → alerte critique
        self._set_status(0)
        self._publish_event(
            "channel:alerts",
            {
                "level": "CRITICAL",
                "camera_id": self.camera_id,
                "message": f"Caméra {self.camera_id} inaccessible après {len(RECONNECT_DELAYS)} tentatives",
                "timestamp": time.time(),
            },
        )
        # Attente avant nouvelle tentative globale
        self._stop_event.wait(30)

    # ------------------------------------------------------------------
    # Capture loop
    # ------------------------------------------------------------------

    def _capture_loop(self):
        """Boucle de capture à la cadence cible."""
        last_frame_time = 0.0
        consecutive_failures = 0

        while not self._stop_event.is_set() and self._cap and self._cap.isOpened():
            now = time.time()
            elapsed = now - last_frame_time
            if elapsed < self._frame_interval:
                # Pause courte non-bloquante
                time.sleep(max(0.001, self._frame_interval - elapsed - 0.001))
                continue

            ret, frame_bgr = self._cap.read()
            if not ret:
                consecutive_failures += 1
                VIDEO_FRAMES_DROPPED.labels(camera_id=self.camera_id).inc()
                if consecutive_failures >= 10:
                    log.error("Perte de flux répétée", camera_id=self.camera_id)
                    self._set_status(0)
                    return
                continue

            consecutive_failures = 0
            last_frame_time = time.time()

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            if not self._quality_check(frame_rgb):
                VIDEO_FRAMES_DROPPED.labels(camera_id=self.camera_id).inc()
                continue

            self._push_to_ml(frame_rgb)

            actual_fps = 1.0 / max(time.time() - last_frame_time, 1e-6)
            VIDEO_FPS_EFFECTIVE.labels(camera_id=self.camera_id).set(actual_fps)

        self._set_status(0)

    # ------------------------------------------------------------------
    # Quality control
    # ------------------------------------------------------------------

    def _quality_check(self, frame_rgb: np.ndarray) -> bool:
        """Rejette les frames floues, sous/surexposées."""
        gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
        blur = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = float(gray.mean())
        return blur >= BLUR_THRESHOLD and MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS

    # ------------------------------------------------------------------
    # ML call
    # ------------------------------------------------------------------

    def _push_to_ml(self, frame_rgb: np.ndarray):
        """Encode la frame JPEG et l'envoie au service ML via HTTP."""
        try:
            buf = io.BytesIO()
            Image.fromarray(frame_rgb).save(buf, format="JPEG", quality=85)
            frame_bytes = buf.getvalue()

            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{ML_SERVICE_URL}/identify",
                    files={"file": ("frame.jpg", frame_bytes, "image/jpeg")},
                    data={"camera_id": self.camera_id},
                )

            if resp.status_code == 200:
                result = resp.json()
                self._publish_event(
                    "channel:detections",
                    {
                        "camera_id": self.camera_id,
                        "faces": result.get("faces", []),
                        "timestamp": time.time(),
                    },
                )
        except httpx.TimeoutException:
            log.warning("ML timeout", camera_id=self.camera_id)
        except Exception as exc:
            log.error("Erreur envoi frame ML", camera_id=self.camera_id, error=str(exc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_status(self, status: int):
        self._status = status
        VIDEO_STREAM_STATUS.labels(camera_id=self.camera_id).set(status)

    def _publish_event(self, channel: str, payload: dict):
        """Délègue à la fonction publish injectée (Redis ou EventBus)."""
        try:
            self._publish(channel, payload)
        except Exception as exc:
            log.error("Erreur publish event", channel=channel, error=str(exc))
