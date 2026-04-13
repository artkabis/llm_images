"""Métriques Prometheus du service vidéo — AGENT_VIDEO.md §6."""
from prometheus_client import Counter, Gauge

VIDEO_FPS_EFFECTIVE = Gauge(
    "video_fps_effective",
    "FPS réel par caméra",
    ["camera_id"],
)

VIDEO_FRAMES_DROPPED = Counter(
    "video_frames_dropped_total",
    "Frames rejetées (qualité insuffisante)",
    ["camera_id"],
)

VIDEO_STREAM_STATUS = Gauge(
    "video_stream_status",
    "Statut flux : 1=actif, 0=coupé, 2=dégradé",
    ["camera_id"],
)

VIDEO_QUEUE_SIZE = Gauge(
    "video_queue_size",
    "Taille queue Redis vers ML",
)

VIDEO_RECONNECT_COUNT = Counter(
    "video_reconnect_total",
    "Nombre de reconnexions par caméra",
    ["camera_id"],
)

VIDEO_BLUR_SCORE = Gauge(
    "video_blur_score",
    "Score de netteté moyen par caméra",
    ["camera_id"],
)
