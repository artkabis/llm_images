#!/usr/bin/env bash
# Arrêt propre de tous les services dev
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDS_FILE="$ROOT/logs/pids.txt"

if [ -f "$PIDS_FILE" ]; then
  while read -r pid; do
    kill "$pid" 2>/dev/null && echo "Arrêté PID $pid" || true
  done < "$PIDS_FILE"
  rm "$PIDS_FILE"
else
  # Fallback : tuer par nom de processus
  pkill -f "uvicorn main:app" 2>/dev/null || true
  pkill -f "celery.*facerec" 2>/dev/null || true
  pkill -f "mlflow server" 2>/dev/null || true
  pkill -f "vite" 2>/dev/null || true
fi

echo "Tous les services arrêtés."
