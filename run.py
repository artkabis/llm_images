#!/usr/bin/env python3
"""
=============================================================
FaceRec — Lanceur universel
Compatible : Windows 10/11, Ubuntu 20+, Debian 11+, macOS 12+
Zéro dépendance externe : pas de Redis, pas de Docker requis.
Usage : python run.py
=============================================================
"""
import os
import sys
import signal
import platform
import subprocess
import shutil
import time
import threading
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
IS_WINDOWS = platform.system() == "Windows"
IS_MAC     = platform.system() == "Darwin"
IS_LINUX   = platform.system() == "Linux"

VENV_PYTHON = "Scripts/python.exe" if IS_WINDOWS else "bin/python"
VENV_PIP    = "Scripts/pip.exe"    if IS_WINDOWS else "bin/pip"
VENV_UV     = "Scripts/uvicorn.exe" if IS_WINDOWS else "bin/uvicorn"

GREEN  = "\033[92m" if not IS_WINDOWS else ""
YELLOW = "\033[93m" if not IS_WINDOWS else ""
RED    = "\033[91m" if not IS_WINDOWS else ""
RESET  = "\033[0m"  if not IS_WINDOWS else ""

PROCESSES: list[subprocess.Popen] = []


# ── Affichage ────────────────────────────────────────────────

def info(msg):  print(f"{GREEN}[INFO]{RESET}  {msg}", flush=True)
def warn(msg):  print(f"{YELLOW}[WARN]{RESET}  {msg}", flush=True)
def error(msg): print(f"{RED}[ERR]{RESET}   {msg}", flush=True); sys.exit(1)


# ── Environnement virtuel ────────────────────────────────────

def setup_venv(name: str, service_dir: Path) -> Path:
    """Crée et installe un venv Python pour un service. Cross-platform."""
    venv_dir = service_dir / ".venv"
    python_bin = venv_dir / VENV_PYTHON
    reqs = service_dir / "requirements.txt"

    if not reqs.exists():
        warn(f"Pas de requirements.txt pour {name}, skip.")
        return venv_dir

    if not python_bin.exists():
        info(f"Création du venv {name}...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        pip = str(venv_dir / VENV_PIP)
        subprocess.run([pip, "install", "-q", "--upgrade", "pip"], check=True)
        subprocess.run([pip, "install", "-q", "-r", str(reqs)], check=True)
        info(f"Venv {name} installé.")
    else:
        info(f"Venv {name} déjà présent.")

    return venv_dir


# ── Lancement de service ─────────────────────────────────────

def start_service(name: str, cmd: list[str], cwd: Path, env: dict = None) -> subprocess.Popen:
    """Lance un service en subprocess. Les logs vont dans logs/<name>.log."""
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_file = open(logs_dir / f"{name}.log", "w", encoding="utf-8")

    merged_env = {**os.environ, **(env or {})}

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=merged_env,
        stdout=log_file,
        stderr=log_file,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0,
    )
    PROCESSES.append(proc)
    info(f"{name} démarré (PID {proc.pid}) → logs/{name}.log")
    return proc


# ── Arrêt propre ─────────────────────────────────────────────

def shutdown(sig=None, frame=None):
    print()
    info("Arrêt des services...")
    for proc in PROCESSES:
        try:
            if IS_WINDOWS:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
        except Exception:
            pass
    for proc in PROCESSES:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    info("Tous les services arrêtés.")
    sys.exit(0)


signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)


# ── Configuration .env ───────────────────────────────────────

def ensure_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        local = ROOT / ".env.local"
        dev   = ROOT / ".env.dev"
        src   = local if local.exists() else (dev if dev.exists() else None)
        if src:
            shutil.copy(src, env_file)
            info(f".env créé depuis {src.name}")
        else:
            warn(".env introuvable — utilisation des valeurs par défaut")

    # Forcer le mode local (pas de Redis, pas de Docker)
    _patch_env_for_local(env_file)


def _patch_env_for_local(env_file: Path):
    """S'assure que les URLs pointent vers localhost (mode local)."""
    if not env_file.exists():
        return
    content = env_file.read_text(encoding="utf-8")
    replacements = {
        "redis://redis:":   "redis://localhost:",
        "http://ml:":       "http://localhost:",
        "http://mlflow:":   "http://localhost:",
        "http://video:":    "http://localhost:",
        "INSIGHTFACE_CTX_ID=0": "INSIGHTFACE_CTX_ID=-1",   # CPU par défaut
    }
    for old, new in replacements.items():
        content = content.replace(old, new)
    env_file.write_text(content, encoding="utf-8")


def load_env() -> dict:
    env = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


# ── Dossiers de données ──────────────────────────────────────

def ensure_data_dirs():
    for d in [
        "data/db", "data/faiss", "data/raw", "data/processed",
        "data/active_learning/pending", "data/active_learning/labeled",
        "data/secure_frames", "data/audit_logs", "logs",
    ]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)


# ── Vérification Python ──────────────────────────────────────

def check_python():
    major, minor = sys.version_info[:2]
    if major < 3 or minor < 10:
        error(f"Python 3.10+ requis. Version actuelle : {major}.{minor}")
    info(f"Python {major}.{minor} ({platform.system()} {platform.machine()})")


# ── Point d'entrée ───────────────────────────────────────────

def main():
    print()
    print(f"{'='*50}")
    print(f"  FaceRec — Mode local ({platform.system()})")
    print(f"{'='*50}")
    print()

    check_python()
    ensure_env()
    ensure_data_dirs()

    env = load_env()
    env["PYTHONPATH"] = str(ROOT)

    # ── Installation des venvs ────────────────────────────────
    ml_venv    = setup_venv("ML",    ROOT / "services/ml")
    api_venv   = setup_venv("API",   ROOT / "services/api")
    video_venv = setup_venv("Video", ROOT / "services/video")

    # ── Service ML (port 8001) ────────────────────────────────
    ml_python = str(ml_venv / VENV_PYTHON)
    start_service(
        "ml",
        [ml_python, "-m", "uvicorn", "main:app",
         "--host", "0.0.0.0", "--port", "8001", "--reload"],
        cwd=ROOT / "services/ml",
        env={**env, "INSIGHTFACE_CTX_ID": "-1"},
    )
    time.sleep(3)  # Laisser InsightFace charger les modèles

    # ── Service API (port 8000) ───────────────────────────────
    api_python = str(api_venv / VENV_PYTHON)
    start_service(
        "api",
        [api_python, "-m", "uvicorn", "main:app",
         "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=ROOT / "services/api",
        env={**env, "LOCAL_MODE": "true"},  # Active le mode sans Redis
    )
    time.sleep(2)

    # ── Worker Celery (mémoire, sans Redis) ───────────────────
    start_service(
        "worker",
        [api_python, "-m", "celery", "-A", "workers.celery_app",
         "worker", "-Q", "high,low", "-c", "2",
         "--loglevel=warning", "--without-heartbeat"],
        cwd=ROOT / "services/api",
        env={**env, "CELERY_BROKER_URL": "memory://", "LOCAL_MODE": "true"},
    )

    # ── Service Vidéo (port 8002) ─────────────────────────────
    video_python = str(video_venv / VENV_PYTHON)
    start_service(
        "video",
        [video_python, "-m", "uvicorn", "main:app",
         "--host", "0.0.0.0", "--port", "8002", "--reload"],
        cwd=ROOT / "services/video",
        env=env,
    )

    # ── Frontend React (port 3000) ────────────────────────────
    node_available = shutil.which("node") is not None
    npm_available  = shutil.which("npm") is not None
    frontend_dir   = ROOT / "services/frontend"

    if node_available and npm_available:
        if not (frontend_dir / "node_modules").exists():
            info("Installation des dépendances frontend (npm install)...")
            subprocess.run(["npm", "install", "--silent"],
                           cwd=str(frontend_dir), check=True)
        start_service(
            "frontend",
            ["npm", "run", "dev"],
            cwd=frontend_dir,
            env=env,
        )
    else:
        warn("Node.js non trouvé — frontend non démarré.")
        warn("Installer Node.js 20+ : https://nodejs.org")

    # ── Récapitulatif ─────────────────────────────────────────
    print()
    print(f"{GREEN}{'='*50}{RESET}")
    print(f"{GREEN}  Système opérationnel{RESET}")
    print(f"{GREEN}{'='*50}{RESET}")
    print(f"  API          →  http://localhost:8000")
    print(f"  API docs     →  http://localhost:8000/api/docs")
    print(f"  ML service   →  http://localhost:8001/health")
    print(f"  Vidéo        →  http://localhost:8002/health")
    if node_available:
        print(f"  Frontend     →  http://localhost:3000")
    print(f"  Logs         →  {ROOT / 'logs'}/")
    print()
    print(f"  Créer un admin : python run.py --create-admin")
    print(f"  Arrêter       : Ctrl+C")
    print(f"{GREEN}{'='*50}{RESET}")
    print()

    # ── Attente + admin à la demande ──────────────────────────
    if "--create-admin" in sys.argv:
        time.sleep(3)
        _create_admin(api_python)

    # Monitoring léger : relancer un service crashé
    while True:
        for proc in list(PROCESSES):
            if proc.poll() is not None:
                warn(f"Un service (PID {proc.pid}) s'est arrêté — vérifier les logs.")
        time.sleep(10)


def _create_admin(python_bin: str):
    """Crée le premier utilisateur admin directement."""
    info("Création de l'utilisateur admin...")
    script = (
        "import asyncio, sys; sys.path.insert(0,'.');"
        "from core.database import init_db, AsyncSessionLocal, User;"
        "from core.security import hash_password;"
        "async def run():"
        "  await init_db();"
        "  async with AsyncSessionLocal() as db:"
        "    u=User(email='admin@facerec.local',"
        "           hashed_password=hash_password('ChangeMe123!'),"
        "           role='admin');"
        "    db.add(u); await db.commit();"
        "    print('Admin créé : admin@facerec.local / ChangeMe123!')"
        "asyncio.run(run())"
    )
    subprocess.run(
        [python_bin, "-c", script],
        cwd=str(ROOT / "services/api"),
        env={**os.environ, "PYTHONPATH": str(ROOT / "services/api")},
    )


if __name__ == "__main__":
    main()
