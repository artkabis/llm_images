"""Configuration Celery — conforme AGENT_BACKEND.md §5."""
from celery import Celery
from core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "facerec",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "workers.tasks.enroll_profile":    {"queue": "high"},
        "workers.tasks.identify_image":    {"queue": "high"},
        "workers.tasks.fine_tune_model":   {"queue": "low"},
        "workers.tasks.generate_report":   {"queue": "low"},
        "workers.tasks.export_incidents":  {"queue": "low"},
        "workers.tasks.cleanup_frames":    {"queue": "low"},
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limits={
        "workers.tasks.enroll_profile":  30,
        "workers.tasks.identify_image":  5,
        "workers.tasks.fine_tune_model": None,   # sans limite
        "workers.tasks.generate_report": 120,
        "workers.tasks.export_incidents": 60,
        "workers.tasks.cleanup_frames":  300,
    },
    beat_schedule={
        "cleanup-old-frames-daily": {
            "task": "workers.tasks.cleanup_frames",
            "schedule": 86400,  # toutes les 24h
        },
        "generate-weekly-report": {
            "task": "workers.tasks.generate_report",
            "schedule": 604800,  # toutes les 7 jours
        },
    },
)
