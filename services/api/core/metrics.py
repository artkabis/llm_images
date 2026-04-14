"""
Metriques Prometheus metier pour le service API.
Expose des compteurs/histogrammes sur la reconnaissance faciale,
l'active learning, le modele ML et les cameras.

Utilisation :
    from core.metrics import RECOGNITION_TOTAL, AL_QUEUE_SIZE, ...
    RECOGNITION_TOTAL.labels(camera_id="cam1", result="authorized").inc()
    AL_QUEUE_SIZE.set(42)
"""
from prometheus_client import Counter, Gauge, Histogram, Info

# -- Reconnaissance faciale --
RECOGNITION_TOTAL = Counter(
    "facial_recognition_total",
    "Nombre total d identifications",
    ["camera_id", "result"],  # result: authorized | intruder | unknown
)

RECOGNITION_CONFIDENCE = Histogram(
    "facial_recognition_confidence",
    "Distribution des scores de confiance",
    buckets=[0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.99, 1.0],
)

RECOGNITION_LATENCY = Histogram(
    "facial_recognition_latency_seconds",
    "Latence d identification (embedding + matching)",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

# -- Active learning --
AL_QUEUE_SIZE = Gauge(
    "facial_recognition_al_queue_size",
    "Frames en attente de revue humaine",
)

AL_LABELED_TOTAL = Counter(
    "facial_recognition_al_labeled_total",
    "Total de frames labelisees",
    ["action"],  # confirmed | corrected | new_profile | intruder | rejected
)

# -- Modele ML --
MODEL_FAR = Gauge("facial_recognition_far", "False Acceptance Rate actuel")
MODEL_FRR = Gauge("facial_recognition_frr", "False Rejection Rate actuel")
MODEL_EER = Gauge("facial_recognition_eer", "Equal Error Rate actuel")
MODEL_TAR = Gauge("facial_recognition_tar", "True Acceptance Rate actuel")
MODEL_DRIFT = Gauge("facial_recognition_drift_score", "Score de derive du modele")
MODEL_PROFILES = Gauge("facial_recognition_profiles_total", "Profils enroles")

# -- Fine-tuning --
FINETUNING_TOTAL = Counter(
    "facial_recognition_finetuning_total",
    "Cycles de fine-tuning executes",
    ["outcome"],  # deployed | rolled_back | unchanged
)

FINETUNING_DURATION = Histogram(
    "facial_recognition_finetuning_duration_seconds",
    "Duree d un cycle de fine-tuning",
    buckets=[60, 120, 300, 600, 900, 1800, 3600],
)

# -- Alertes securite --
SECURITY_ALERTS_TOTAL = Counter(
    "facial_recognition_security_alerts_total",
    "Alertes de securite emises",
    ["severity", "camera_id"],
)

# -- Cameras --
CAMERAS_ACTIVE = Gauge("facial_recognition_cameras_active", "Cameras actives")
CAMERA_FPS = Gauge(
    "facial_recognition_camera_fps",
    "FPS effectif par camera",
    ["camera_id"],
)

MODEL_INFO = Info("facial_recognition_model", "Informations sur le modele actif")
