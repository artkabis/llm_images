# Facial Recognition System — Vidéosurveillance d'Entreprise

Système de reconnaissance faciale temps réel pour la sécurité des accès en entreprise.  
Détection personnes autorisées / intrus · Multi-caméras · Active learning · Monitoring avancé

---

## Démarrage rapide

### Mode local — Sans Docker (Windows / Linux / macOS)

> Aucune dépendance externe requise (pas de Redis, pas de Docker).

```bash
# Tous OS — un seul prérequis : Python >= 3.10
python run.py

# Premier lancement : créer un compte administrateur
python run.py --create-admin
```

**Windows PowerShell :**
```powershell
.\scripts\start-dev.ps1
.\scripts\start-dev.ps1 -CreateAdmin
.\scripts\start-dev.ps1 -Stop
```

**Linux / macOS :**
```bash
./scripts/start-dev.sh
```

**Services démarrés :**

| Service | URL |
|---|---|
| API REST + WebSocket | http://localhost:8000/api/docs |
| Service ML (InsightFace) | http://localhost:8001/health |
| Service Vidéo | http://localhost:8002/health |
| Interface React | http://localhost:3000 |

---

### Mode Docker (Linux / macOS / Windows + WSL2)

```bash
# Copier et adapter les variables d'environnement
cp .env.example .env

# Linux uniquement — activer les webcams USB :
cp docker-compose.override.example.yml docker-compose.override.yml

# Démarrer tous les services
docker compose up -d

# Créer un administrateur
docker compose exec api python -m scripts.create_admin
```

> **Windows + Docker Desktop** : les webcams USB ne peuvent pas être passées au conteneur vidéo.  
> Utiliser `python run.py` (LOCAL\_MODE) pour les caméras USB locales, ou des caméras IP/RTSP pour Docker.

---

## Compatibilité cross-platform

| Fonctionnalité | Windows (local) | Linux (local) | Docker |
|---|---|---|---|
| Caméras RTSP / IP | ✅ | ✅ | ✅ |
| Webcam USB | ✅ CAP\_DSHOW | ✅ V4L2 | ✅ Linux seulement |
| Sans Redis/Docker | ✅ EventBus | ✅ EventBus | ❌ |
| GPU NVIDIA | ❌ CPU fallback | ✅ CUDA | ✅ nvidia-docker |
| Lancement | `python run.py` | `python run.py` | `docker compose up` |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Nginx / API Gateway (prod)             │
└────────┬────────────────┬────────────────┬────────┘
         │                │                │
    ┌────┴────┐      ┌────┴────┐     ┌────┴────┐
    │  API    │      │   ML    │     │ Vidéo  │
    │FastAPI  │◄───►│InsightFace    OpenCV   │
    │:8000    │      │ArcFace  │     │:8002    │
    └────┬───┘      │:8001    │     └────────┘
         │           └────────┘
    ┌────┴────────────────────┐    ┌────────────┐
    │ EventBus (Redis/in-memory) │    │ FAISS/Qdrant │
    │ WebSocket → Frontend     │    │ Embeddings  │
    └────────────────────────┘    └────────────┘
```

---

## Pipeline Active Learning

```
Frame incertaine (score 70–85%)
    │
    ▼
[Review.tsx] ← 5 actions humaines :
    confirmed / corrected / new_profile / intruder / rejected
    │
    ▼ (seuil atteint : 50 labels)
[Celery: fine_tune_model]
    │
    ▼
[ML service: /fine_tune]
    ├─ Meilleur EER → deployed, version++
    └─ Dégradé     → rolled_back
    │
    ▼
[MLflow] FAR/FRR/EER avant→après
```

---

## Documentation

| Document | Description |
|---|---|
| [Cahier des charges](CAHIER_DES_CHARGES.md) | Spécification complète |
| [Guide de démarrage](DEMARRAGE.md) | Installation + exemples curl |
| [CLAUDE.md](CLAUDE.md) | Instructions prioritaires pour Claude Code |
| [Agent ML/IA](docs/agents/AGENT_ML_IA.md) | Entraînement & embeddings |
| [Agent Vidéo](docs/agents/AGENT_VIDEO.md) | Flux vidéo multi-caméras |
| [Agent Sécurité](docs/agents/AGENT_SECURITE.md) | Détection & alertes |
| [Agent Backend](docs/agents/AGENT_BACKEND.md) | API & orchestration |
| [Agent Infra](docs/agents/AGENT_INFRA.md) | Infrastructure & déploiement |
| [Agent Data](docs/agents/AGENT_DATA.md) | Dataset & annotation |
| [Agent Frontend](docs/agents/AGENT_FRONTEND.md) | Dashboard & UI |

---

## Stack

- **ML** : Python · PyTorch · InsightFace (buffalo\_l) · ArcFace 512d
- **API** : FastAPI · Celery · Redis (prod) / EventBus in-memory (local)
- **Vidéo** : OpenCV · FFmpeg · CAP\_DSHOW (Windows) · V4L2 (Linux)
- **Stockage** : SQLite → PostgreSQL · FAISS → Qdrant
- **Monitoring** : MLflow · Prometheus · Grafana · Loki
- **Infra** : Docker Compose → VPS · GitHub Actions CI/CD
- **UI** : React 18 · TailwindCSS · Recharts · Zustand

---

## Métriques ML cibles

| Métrique | Objectif |
|---|---|
| FAR (False Acceptance Rate) | < 0.1% |
| FRR (False Rejection Rate) | < 1% |
| TAR (True Acceptance Rate) | > 99% |
| EER (Equal Error Rate) | minimiser |
| Drift score | < 0.05 |
