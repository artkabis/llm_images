# =============================================================
# FaceRec — Commandes de développement
# Usage : make <commande>
# =============================================================

.PHONY: help dev stop install test lint docker-up docker-down create-admin

help:
	@echo ""
	@echo "  Commandes disponibles :"
	@echo ""
	@echo "  ── Mode local (sans Docker) ──────────────────"
	@echo "  make dev           Démarrer tous les services localement"
	@echo "  make stop          Arrêter tous les services"
	@echo "  make install       Installer toutes les dépendances Python + Node"
	@echo "  make create-admin  Créer le premier utilisateur admin"
	@echo ""
	@echo "  ── Qualité ───────────────────────────────────"
	@echo "  make lint          Lint Python (ruff)"
	@echo "  make test          Tests unitaires (pytest)"
	@echo ""
	@echo "  ── Mode Docker ───────────────────────────────"
	@echo "  make docker-up     Démarrer avec Docker Compose"
	@echo "  make docker-down   Arrêter Docker Compose"
	@echo "  make docker-logs   Suivre les logs Docker"
	@echo ""

# ── Mode local ─────────────────────────────────────────────

dev:
	@cp -n .env.local .env 2>/dev/null || true
	@bash scripts/start-dev.sh

stop:
	@bash scripts/stop-dev.sh

install:
	@echo "Installation des dépendances ML..."
	cd services/ml  && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
	@echo "Installation des dépendances API..."
	cd services/api && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
	@echo "Installation des dépendances Vidéo..."
	cd services/video && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
	@echo "Installation des dépendances Frontend..."
	cd services/frontend && npm install
	@echo "Installation terminée."

create-admin:
	@echo "Création de l'utilisateur admin..."
	cd services/api && .venv/bin/python -c " \
import asyncio, sys; sys.path.insert(0, '.'); \
from core.database import init_db, AsyncSessionLocal, User; \
from core.security import hash_password; \
async def run(): \
    await init_db(); \
    async with AsyncSessionLocal() as db: \
        u = User(email='admin@facerec.local', hashed_password=hash_password('ChangeMe123!'), role='admin'); \
        db.add(u); await db.commit(); print('Admin créé : admin@facerec.local / ChangeMe123!'); \
asyncio.run(run())"

# ── Qualité ────────────────────────────────────────────────

lint:
	@echo "Lint ML..."
	cd services/ml  && .venv/bin/ruff check . || true
	@echo "Lint API..."
	cd services/api && .venv/bin/ruff check . || true
	@echo "Lint Vidéo..."
	cd services/video && .venv/bin/ruff check . || true

test:
	@echo "Tests API..."
	cd services/api && .venv/bin/pytest tests/ -v --tb=short 2>/dev/null || echo "Pas encore de tests (phase 1)"

# ── Docker ─────────────────────────────────────────────────

docker-up:
	@cp -n .env.dev .env 2>/dev/null || true
	docker compose up --build -d
	@echo "Services démarrés → http://localhost"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api ml video

redis-only:
	@echo "Démarrage Redis seul (pour mode local)..."
	docker run -d --name facerec-redis -p 6379:6379 redis:7-alpine 2>/dev/null || \
	docker start facerec-redis 2>/dev/null || echo "Redis déjà actif"
