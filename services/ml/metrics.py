"""
Métriques Prometheus du service ML
Conforme à AGENT_ML_IA.md §7 Métriques exposées
"""
from prometheus_client import Counter, Gauge, Histogram, Summary

ML_INFERENCE_LATENCY = Histogram(
    "ml_inference_latency_seconds",
    "Temps d'extraction d'embedding par frame",
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5],
)

ML_CONFIDENCE_SCORE = Gauge(
    "ml_confidence_score",
    "Score de confiance moyen sur fenêtre glissante",
)

ML_FAR = Gauge("ml_far", "False Acceptance Rate courant")
ML_FRR = Gauge("ml_frr", "False Rejection Rate courant")

ML_ACTIVE_LEARNING_QUEUE = Gauge(
    "ml_active_learning_queue",
    "Nombre de frames en attente de review",
)

ML_MODEL_VERSION = Gauge("ml_model_version", "Version du modèle actif")

ML_DRIFT_SCORE = Gauge(
    "ml_drift_score",
    "Score de dérive de distribution des embeddings",
)

ML_FACES_DETECTED = Counter(
    "ml_faces_detected_total",
    "Total de visages détectés",
    ["status"],  # authorized | suspect | unknown
)

ML_ENROLLMENT_TOTAL = Counter(
    "ml_enrollment_total",
    "Total de profils enrôlés",
)

ML_INFERENCE_ERRORS = Counter(
    "ml_inference_errors_total",
    "Erreurs d'inférence",
    ["type"],
)
