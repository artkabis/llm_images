"""Tâches Celery asynchrones — conforme AGENT_BACKEND.md §5."""
import os, structlog
from datetime import datetime, timedelta
from pathlib import Path
from workers.celery_app import celery_app

log = structlog.get_logger()
SECURE_FRAMES_PATH = os.getenv("SECURE_FRAMES_PATH", "/data/secure_frames")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")


@celery_app.task(name="workers.tasks.fine_tune_model", bind=True, max_retries=3)
def fine_tune_model(self):
    """
    Fine-tuning du modèle ArcFace sur les nouvelles données labellisées.
    Déclenché automatiquement par l'active learning ou manuellement.
    """
    log.info("Démarrage du fine-tuning")
    try:
        import mlflow
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment("facial-recognition")

        with mlflow.start_run(run_name=f"fine_tune_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"):
            # TODO Phase 3 : implémenter le fine-tuning ArcFace complet
            # 1. Charger le dataset de review labellisé
            # 2. Augmenter les données (Albumentations)
            # 3. Fine-tuner les dernières couches du modèle
            # 4. Valider sur le jeu de test (FAR/FRR)
            # 5. Si amélioration → déployer, sinon → rollback
            mlflow.log_param("status", "placeholder_phase3")
            log.info("Fine-tuning terminé (placeholder phase 3)")

    except Exception as exc:
        log.error("Erreur fine-tuning", error=str(exc))
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="workers.tasks.generate_report")
def generate_report():
    """Génère le rapport hebdomadaire de santé du modèle en PDF."""
    log.info("Génération du rapport hebdomadaire")
    # TODO Phase 3 : générer PDF avec reportlab (FAR/FRR, incidents, drift)


@celery_app.task(name="workers.tasks.export_incidents")
def export_incidents(format: str = "csv"):
    """Export des incidents en CSV ou PDF à la demande."""
    log.info("Export des incidents", format=format)


@celery_app.task(name="workers.tasks.cleanup_frames")
def cleanup_frames(retention_days: int = 30):
    """Supprime les frames sécurisées plus anciennes que retention_days."""
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    frames_dir = Path(SECURE_FRAMES_PATH)
    deleted = 0
    for day_dir in frames_dir.iterdir():
        try:
            day_date = datetime.strptime(day_dir.name, "%Y-%m-%d")
            if day_date < cutoff:
                for f in day_dir.glob("*.jpg"):
                    f.unlink()
                    deleted += 1
                if not any(day_dir.iterdir()):
                    day_dir.rmdir()
        except ValueError:
            continue
    log.info("Nettoyage frames terminé", deleted=deleted, retention_days=retention_days)
