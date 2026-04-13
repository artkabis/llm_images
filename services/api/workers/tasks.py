"""
Tâches Celery — conforme AGENT_BACKEND.md §5 et AGENT_ML_IA.md §5.3
fine_tune_model : délègue au service ML, logge dans MLflow, auto-deploy/rollback
"""
import os
import structlog
from datetime import datetime, timedelta
from pathlib import Path

from workers.celery_app import celery_app

log = structlog.get_logger()

SECURE_FRAMES_PATH = os.getenv("SECURE_FRAMES_PATH", "/data/secure_frames")
ACTIVE_LEARNING_PATH = os.getenv("DATA_ACTIVE_LEARNING_PATH", "/data/active_learning")
ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://ml:8001")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
AUTO_DEPLOY = os.getenv("ML_AUTO_DEPLOY", "true").lower() == "true"
MIN_IMPROVEMENT_PCT = float(os.getenv("ML_MIN_IMPROVEMENT_PCT", "1.0"))


@celery_app.task(name="workers.tasks.fine_tune_model", bind=True, max_retries=3, time_limit=3600)
def fine_tune_model(self):
    """
    Fine-tuning ArcFace sur données labelliées.
    1. Démarre un run MLflow
    2. POST ML /fine_tune → mise à jour centroids FAISS + évaluation FAR/FRR/EER
    3. Log métriques : far_before/after, frr_before/after, eer, improvement_pct, n_samples
    4. outcome : deployed | rolled_back | unchanged
    5. Retry sur erreur (backoff 60s, 120s, 180s)
    """
    import httpx
    import mlflow

    log.info("Démarrage fine-tuning", task_id=self.request.id)
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("facial-recognition")

    run_name = f"fine_tune_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    with mlflow.start_run(run_name=run_name) as run:
        run_id = run.info.run_id
        mlflow.log_params({
            "auto_deploy": AUTO_DEPLOY,
            "min_improvement_pct": MIN_IMPROVEMENT_PCT,
            "labeled_path": str(Path(ACTIVE_LEARNING_PATH) / "labeled"),
            "task_id": self.request.id,
        })

        try:
            with httpx.Client(timeout=3000.0) as client:
                resp = client.post(
                    f"{ML_SERVICE_URL}/fine_tune",
                    json={
                        "run_id": run_id,
                        "labeled_path": str(Path(ACTIVE_LEARNING_PATH) / "labeled"),
                        "auto_deploy": AUTO_DEPLOY,
                        "min_improvement_pct": MIN_IMPROVEMENT_PCT,
                    },
                )
            resp.raise_for_status()
            result = resp.json()
        except Exception as exc:
            log.error("Erreur appel ML /fine_tune", error=str(exc))
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))

        metrics = result.get("metrics", {})
        loggable = {
            k: float(v)
            for k in ["far_before", "far_after", "frr_before", "frr_after",
                      "eer_before", "eer_after", "improvement_pct", "n_samples", "tar"]
            if k in metrics and metrics[k] is not None
        }
        if loggable:
            mlflow.log_metrics(loggable)

        deployed = result.get("deployed", False)
        rolled_back = result.get("rolled_back", False)
        outcome = "deployed" if deployed else ("rolled_back" if rolled_back else "unchanged")
        mlflow.log_param("outcome", outcome)

        log.info("Fine-tuning terminé", outcome=outcome,
                 improvement=metrics.get("improvement_pct"), n_samples=metrics.get("n_samples"))
        return {"run_id": run_id, "outcome": outcome, "metrics": metrics}


@celery_app.task(name="workers.tasks.evaluate_model", bind=True, max_retries=2, time_limit=600)
def evaluate_model(self):
    """Evalue le modèle actif sur le jeu de test, logge dans MLflow."""
    import httpx
    import mlflow

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("facial-recognition")
    with mlflow.start_run(run_name=f"eval_{datetime.utcnow().strftime('%Y%m%d_%H%M')}") as run:
        mlflow.log_param("type", "evaluation")
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(f"{ML_SERVICE_URL}/model/evaluate")
            resp.raise_for_status()
            metrics = resp.json().get("metrics", {})
            loggable = {k: float(v) for k, v in metrics.items()
                        if isinstance(v, (int, float)) and v is not None}
            if loggable:
                mlflow.log_metrics(loggable)
            log.info("Evaluation terminée", **{k: round(v, 4) for k, v in loggable.items()})
            return {"run_id": run.info.run_id, "metrics": metrics}
        except Exception as exc:
            raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


@celery_app.task(name="workers.tasks.generate_report")
def generate_report():
    """Génère le rapport hebdomadaire (FAR/FRR, incidents, drift)."""
    log.info("Génération rapport hebdomadaire")
    # Phase 3 : génération PDF avec reportlab


@celery_app.task(name="workers.tasks.export_incidents")
def export_incidents(format: str = "csv"):
    """Export des incidents en CSV ou PDF."""
    log.info("Export incidents", format=format)


@celery_app.task(name="workers.tasks.cleanup_frames")
def cleanup_frames(retention_days: int = 30):
    """Supprime les frames sécurisées plus anciennes que retention_days."""
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    frames_dir = Path(SECURE_FRAMES_PATH)
    deleted = 0
    if not frames_dir.exists():
        return
    for day_dir in frames_dir.iterdir():
        try:
            day_date = datetime.strptime(day_dir.name, "%Y-%m-%d")
            if day_date < cutoff:
                for f in day_dir.glob("*.jpg"):
                    f.unlink()
                    deleted += 1
                if not any(day_dir.iterdir()):
                    day_dir.rmdir()
        except (ValueError, OSError):
            continue
    log.info("Nettoyage frames", deleted=deleted, retention_days=retention_days)
