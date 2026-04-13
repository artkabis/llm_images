#!/usr/bin/env bash
# =============================================================
# Démarrage du projet en mode dev LOCAL (sans Docker)
# Usage : bash scripts/start-dev.sh
# =============================================================
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
mkdir -p "$ROOT/data/db" "$ROOT/data/faiss" "$ROOT/data/secure_frames" \
         "$ROOT/data/active_learning/pending" "$ROOT/data/active_learning/labeled" \
         "$ROOT/data/raw" "$ROOT/data/processed" "$ROOT/data/audit_logs"

# Couleurs
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Charger .env.local si .env absent
if [ ! -f "$ROOT/.env" ]; then
  if [ -f "$ROOT/.env.local" ]; then
    cp "$ROOT/.env.local" "$ROOT/.env"
    info ".env créé depuis .env.local"
  else
    error ".env introuvable — copier .env.local ou .env.dev"
  fi
fi

# ── Vérifications préalables ───────────────────────────────
info "Vérification des prérequis..."

command -v python3 >/dev/null 2>&1 || error "Python 3.11+ requis"
command -v node >/dev/null 2>&1    || warn  "Node.js non trouvé — le frontend ne démarrera pas"
command -v redis-cli >/dev/null 2>&1 || warn "redis-cli non trouvé — Redis doit tourner sur le port 6379"

# Vérifier Redis
if ! redis-cli ping >/dev/null 2>&1; then
  warn "Redis non détecté. Tentative de démarrage via Docker..."
  if command -v docker >/dev/null 2>&1; then
    docker run -d --name facerec-redis -p 6379:6379 redis:7-alpine >/dev/null 2>&1 || true
    sleep 1
    redis-cli ping >/dev/null 2>&1 && info "Redis démarré via Docker" \
      || error "Impossible de démarrer Redis. Installer : sudo apt install redis / brew install redis"
  else
    error "Redis requis. Installer : sudo apt install redis-server && redis-server"
  fi
else
  info "Redis OK"
fi

# ── Environnements virtuels Python ─────────────────────────

setup_venv() {
  local name=$1 path=$2 reqs=$3
  if [ ! -d "$path/.venv" ]; then
    info "Création venv $name..."
    python3 -m venv "$path/.venv"
    "$path/.venv/bin/pip" install -q --upgrade pip
    "$path/.venv/bin/pip" install -q -r "$reqs"
    info "Venv $name installé"
  else
    info "Venv $name déjà existant"
  fi
}

setup_venv "ML"  "$ROOT/services/ml"  "$ROOT/services/ml/requirements.txt"
setup_venv "API" "$ROOT/services/api" "$ROOT/services/api/requirements.txt"
setup_venv "VIDEO" "$ROOT/services/video" "$ROOT/services/video/requirements.txt"

# ── Démarrage des services ─────────────────────────────────
PIDS=()

start_service() {
  local name=$1 cmd=$2 dir=$3 port=$4
  info "Démarrage $name sur le port $port..."
  cd "$dir"
  eval "$cmd" > "$LOG_DIR/$name.log" 2>&1 &
  PIDS+=($!)
  cd "$ROOT"
  sleep 1
  if kill -0 "${PIDS[-1]}" 2>/dev/null; then
    info "$name démarré (PID ${PIDS[-1]}) → log: logs/$name.log"
  else
    warn "$name a échoué — vérifier logs/$name.log"
  fi
}

# Service ML (port 8001)
start_service "ml" \
  ".venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001 --reload" \
  "$ROOT/services/ml" 8001

# Service API (port 8000)
start_service "api" \
  ".venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload" \
  "$ROOT/services/api" 8000

# Worker Celery
start_service "worker" \
  ".venv/bin/celery -A workers.celery_app worker -Q high,low -c 2 --loglevel=info" \
  "$ROOT/services/api" 9999

# Service Vidéo (port 8002)
start_service "video" \
  ".venv/bin/uvicorn main:app --host 0.0.0.0 --port 8002 --reload" \
  "$ROOT/services/video" 8002

# MLflow (port 5000)
if "$ROOT/services/api/.venv/bin/mlflow" --version >/dev/null 2>&1; then
  start_service "mlflow" \
    ".venv/bin/mlflow server --host 0.0.0.0 --port 5000 \
     --backend-store-uri ./mlruns --default-artifact-root ./mlartifacts" \
    "$ROOT/services/api" 5000
fi

# Frontend React (port 3000)
if command -v node >/dev/null 2>&1 && [ -d "$ROOT/services/frontend/node_modules" ]; then
  start_service "frontend" "npm run dev" "$ROOT/services/frontend" 3000
elif command -v node >/dev/null 2>&1; then
  info "Installation des dépendances frontend..."
  cd "$ROOT/services/frontend" && npm install -q && cd "$ROOT"
  start_service "frontend" "npm run dev" "$ROOT/services/frontend" 3000
fi

# ── Récapitulatif ──────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Système démarré — Mode dev local${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "  API        → http://localhost:8000"
echo -e "  API docs   → http://localhost:8000/api/docs"
echo -e "  ML service → http://localhost:8001"
echo -e "  Frontend   → http://localhost:3000"
echo -e "  MLflow     → http://localhost:5000"
echo -e "  Logs       → $LOG_DIR/"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo "  Arrêter : bash scripts/stop-dev.sh"
echo "  Ou : Ctrl+C puis kill \$(cat logs/pids.txt)"
echo ""

# Sauvegarder les PIDs
printf '%s\n' "${PIDS[@]}" > "$LOG_DIR/pids.txt"

# Attendre signal d'arrêt
trap 'info "Arrêt..."; kill "${PIDS[@]}" 2>/dev/null; exit 0' SIGINT SIGTERM
wait
