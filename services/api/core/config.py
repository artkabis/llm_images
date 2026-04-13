"""Configuration centralisée — chargée depuis les variables d'environnement."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_env: str = "development"
    app_secret_key: str = "changeme"
    app_debug: bool = False

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_v1_prefix: str = "/api/v1"
    api_cors_origins: str = "http://localhost:3000"

    # JWT
    jwt_secret_key: str = "changeme"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Database
    database_url: str = "sqlite+aiosqlite:////data/db/facerec.db"

    # Redis
    redis_url: str = "redis://redis:6379/0"
    redis_cache_ttl: int = 300

    # ML Service
    ml_service_url: str = "http://ml:8001"
    ml_threshold_authorized: float = 0.85
    ml_threshold_suspect: float = 0.70

    # Stockage
    data_raw_path: str = "/data/raw"
    data_processed_path: str = "/data/processed"
    data_active_learning_path: str = "/data/active_learning"
    secure_frames_path: str = "/data/secure_frames"
    audit_logs_path: str = "/data/audit_logs"

    # Notifications
    notify_min_level: str = "ALERT"
    notify_email_enabled: bool = False
    notify_webhook_enabled: bool = False
    notify_webhook_url: str = ""

    # Rate limiting
    rate_limit_per_minute: int = 100
    rate_limit_auth_failures: int = 10

    # Logging
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "case_sensitive": False}


@lru_cache
def get_settings() -> Settings:
    return Settings()
