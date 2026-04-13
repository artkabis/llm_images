# Facial Recognition System — Vidéosurveillance d'Entreprise

Système de reconnaissance faciale temps réel pour la sécurité des accès en entreprise.
Détecte les personnes autorisées et les intrus sur des flux vidéo multi-caméras,
avec alertes temps réel et tableau de bord de monitoring avancé.

## Démarrage rapide

### Mode local — Windows / Linux / macOS (sans Docker, sans Redis)

```bash
# Toutes plateformes — une seule commande
python run.py

# Windows PowerShell (alternative)
.\scripts\start-dev.ps1

# Premier lancement — créer le compte admin
python run.py --create-admin
# ou
.\scripts\start-dev.ps1 -CreateAdmin
```

**Services démarrés automatiquement :**

| Service | URL | Rôle |
|---|---|---|
| API REST + WebSocket | http://localhost:8000/api/docs | Backend principal |
| Service ML | http://localhost:8001/health | InsightFace / ArcFace |
| Service Vidéo | http://localhost:8002/health | Ingestion caméras |
| Interface React | http://localhost:3000 | Dashboard |

### Mode Docker — Linux / macOS / Windows (avec WSL2)

```bash
# Copier et adapter l'environnement
cp .env.example .env

# Linux + webcam USB : activer l'override
cp docker-compose.override.example.yml docker-compose.override.yml

# Démarrer tous les services
docker compose up -d

# Créer l'administrateur
docker compose exec api python -m scripts.create_admin
```

> **Windows + Docker Desktop** : les webcams USB ne peuvent pas être passées
> au conteneur. Utiliser `python run.py` ou `start-dev.ps1` pour les caméras
> USB locales. Les caméras IP/RTSP fonctionnent dans tous les modes.

---

## Compatibilité multi-plateforme

| Fonctionnalité | Windows (local) | Linux (local) | Docker |
|---|---|---|---|
| Caméras RTSP / IP | ✅ | ✅ | ✅ |
| Webcam USB | ✅ CAP\_DSHOW | ✅ V4L2 | ✅ Linux seulement |
| Sans Redis / Docker | ✅ EventBus | ✅ EventBus | ❌ Redis requis |
| GPU NVIDIA | ⚠️ CPU fallback | ✅ CUDA | ✅ nvidia-docker |
| Commande unique | `python run.py` | `python run.py` | `docker compose up` |
| PowerShell | ✅ start-dev.ps1 | — | — |

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Nginx / API Gateway                     │
└──────────┬──────────────────┬──────────────────┬──────────┘
           │                  │                  │
      ┌────▼────┐        ┌────▼────┐       ┌────▼────┐
      │  API    │        │   ML    │       │  Video  │
      │FastAPI  │◄──────►│InsightFace     │OpenCV   │
      │:8000    │        │ArcFace  │       │:8002    │
      └────┬────┘        │:8001    │       └────┬────┘
           │             └─────────┘            │
    ┌──────▼──────┐   ┌──────────────────┐      │
    │  EventBus   │   │  Vector Store    │      │
    │ Redis (prod)│   │ FAISS → Qdrant   │◄─────┘
    │ In-mem(dev) │   └──────────────────┘
    └──────┬──────┘
           │ WebSocket
    ┌──────▼──────┐
    │  Frontend   │
    │React :3000  │
    └─────────────┘
```

**Pipeline de reconnaissance :**
```
Caméra → Frame → Qualité OK ? → InsightFace (RetinaFace) → ArcFace 512d
  → FAISS cosine search → Score → Autorisé / Suspect / Inconnu
  → Alerte (si suspect) → EventBus → WebSocket → Dashboard
```

---

## Documentation

| Document | Description |
|---|---|
| [Cahier des charges](CAHIER_DES_CHARGES.md) | Spécification complète |
| [Guide de démarrage](DEMARRAGE.md) | Installation, exemples curl |
| [Agent ML/IA](docs/agents/AGENT_ML_IA.md) | Entraînement, embeddings, active learning |
| [Agent Vidéo](docs/agents/AGENT_VIDEO.md) | Ingestion flux, multi-caméras |
| [Agent Sécurité](docs/agents/AGENT_SECURITE.md) | Alertes, RBAC, audit |
| [Agent Backend](docs/agents/AGENT_BACKEND.md) | API REST, WebSocket, Celery |
| [Agent Infra](docs/agents/AGENT_INFRA.md) | Docker, CI/CD, VPS migration |
| [Agent Data](docs/agents/AGENT_DATA.md) | Dataset, annotation, DVC |
| [Agent Frontend](docs/agents/AGENT_FRONTEND.md) | Dashboard React, monitoring |

---

## Stack technique

| Couche | Local (dev) | Production |
|---|---|---|
| **ML** | InsightFace buffalo\_l · ArcFace 512d · CPU | + CUDA GPU |
| **API** | FastAPI · Celery (memory://) · EventBus in-mem | + Redis · PostgreSQL |
| **Vidéo** | OpenCV · CAP\_DSHOW (Win) · V4L2 (Linux) | + FFmpeg · GStreamer |
| **Stockage** | SQLite · FAISS | PostgreSQL · Qdrant |
| **Monitoring** | MLflow local | + Prometheus · Grafana · Loki |
| **Infra** | `python run.py` | Docker Compose · GitHub Actions |
| **UI** | React 18 · TailwindCSS · Recharts · Zustand | Nginx |

---

## Variables d'environnement clés

| Variable | Défaut | Description |
|---|---|---|
| `LOCAL_MODE` | `false` | Active EventBus in-memory (sans Redis) |
| `INSIGHTFACE_CTX_ID` | `0` | `-1` = CPU forcé |
| `CAMERAS_CONFIG` | `/config/cameras.yml` | Chemin config caméras |
| `API_SERVICE_URL` | `http://localhost:8000` | URL API (pour service vidéo) |
| `ML_SERVICE_URL` | `http://localhost:8001` | URL service ML |

Copier `.env.local` pour le mode local, `.env.example` pour Docker.
