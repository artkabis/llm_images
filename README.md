# Vision AI — Facial Recognition System

Système de reconnaissance faciale enterprise pour la vidéosurveillance.
Détection temps réel des personnes autorisées vs intrus, avec boucle d'apprentissage actif et supervision humaine.

---

## Fonctionnalités

- **Reconnaissance temps réel** — Flux RTSP / webcam USB, détection et identification par caméra
- **Pipeline active learning** — Les frames à faible confiance (70–85%) sont soumises à revue humaine ; le modèle se réentraîne automatiquement
- **Interface de revue humaine** — 5 actions (confirmer, corriger, nouveau profil, intrus, rejeter), top-k candidats, zoom, progression vers le prochain fine-tuning
- **Fine-tuning automatique** — Mise à jour des centroides FAISS, évaluation FAR/FRR/EER avant/après, déploiement ou rollback automatique
- **Monitoring complet** — Ressources système (CPU/RAM/GPU/disque), métriques ML, alertes Prometheus, dashboards Grafana, logs Loki
- **Sécurité** — RBAC (viewer/operator/admin), chiffrement AES-256 des embeddings, audit logs, zero endpoint sans authentification
- **Cross-platform** — Windows (sans Docker), Linux/macOS (Docker Compose ou natif), VPS

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Nginx (reverse proxy)                    │
└──────────┬──────────────────────┬──────────────────────────────┘
           │                      │
    ┌──────▼──────┐       ┌───────▼──────┐
    │  API (8000) │       │ Frontend     │
    │  FastAPI    │       │ React/Vite   │
    │  WebSocket  │       │ (5173/build) │
    └──────┬──────┘       └──────────────┘
           │ EventBus (Redis ou InMemory)
    ┌──────▼──────────────────────────────────┐
    │              Services internes          │
    │  ┌──────────┐  ┌────────┐  ┌────────┐  │
    │  │ ML (8001)│  │ Video  │  │ Celery │  │
    │  │InsightFace│  │OpenCV  │  │Workers │  │
    │  │FAISS     │  │FFmpeg  │  │Tasks   │  │
    │  └────┬─────┘  └───┬────┘  └───┬────┘  │
    └───────┼────────────┼───────────┼────────┘
            │            │           │
    ┌───────▼────┐  ┌────▼───┐  ┌───▼──────┐
    │  MLflow    │  │ Redis  │  │ SQLite / │
    │  (5050)    │  │ (6379) │  │ PostgreSQL│
    └────────────┘  └────────┘  └──────────┘

    ┌─────────────────────────────────────────┐
    │            Stack Monitoring             │
    │  Prometheus → Alertmanager → Loki       │
    │  node-exporter → Grafana (3001)         │
    └─────────────────────────────────────────┘
```

---

## Stack technologique

| Couche | Technologie | Usage |
|--------|------------|-------|
| **ML / IA** | InsightFace `buffalo_l`, ArcFace | Détection (RetinaFace) + embeddings 512-d |
| **Recherche vectorielle** | FAISS `IndexFlatIP` | Matching cosinus par centroide de profil |
| **Tracking expériences** | MLflow | FAR/FRR/EER/TAR, runs de fine-tuning, rollback |
| **API** | FastAPI + uvicorn | REST + WebSocket, RBAC JWT |
| **Workers async** | Celery + Redis | Fine-tuning, évaluation, alertes |
| **Event bus** | Redis Pub/Sub / InMemoryEventBus | Détections temps réel, LOCAL\_MODE sans Redis |
| **Vidéo** | OpenCV, FFmpeg | Ingestion RTSP / USB, extraction frames |
| **Frontend** | React 18, TypeScript, Vite, TailwindCSS, Recharts | Dashboard, revue humaine, monitoring |
| **Base de données** | SQLite → PostgreSQL | Profils, alertes, audit logs |
| **Monitoring** | Prometheus, Grafana, Alertmanager, Loki, Promtail, node-exporter | Métriques, alertes, logs |
| **Infra** | Docker Compose, Nginx, Let's Encrypt | Déploiement local et VPS |

---

## Démarrage rapide

### Windows (sans Docker)

```powershell
# Cloner le projet
git clone https://github.com/artkabis/llm_images.git
cd llm_images

# Copier et configurer les variables d'environnement
copy .env.example .env.local
# Editer .env.local : SECRET_KEY, INSIGHTFACE_CTX_ID=-1, LOCAL_MODE=true

# Lancer tous les services (crée les venvs, installe les deps)
.\scripts\start-dev.ps1

# Arrêter tous les services
.\scripts\start-dev.ps1 -Stop

# Créer le premier compte admin
.\scripts\start-dev.ps1 -CreateAdmin
```

### Linux / macOS (natif)

```bash
git clone https://github.com/artkabis/llm_images.git
cd llm_images
cp .env.example .env.local
# Editer .env.local
python run.py
```

### Docker Compose (Linux / macOS / VPS)

```bash
git clone https://github.com/artkabis/llm_images.git
cd llm_images
cp .env.example .env
# Editer .env : SECRET_KEY, GRAFANA_ADMIN_PASSWORD, etc.

# Webcam USB Linux uniquement
cp docker-compose.override.example.yml docker-compose.override.yml
# Editer docker-compose.override.yml : adapter /dev/videoX

docker compose up --build
```

---

## Services et ports

| Service | Port | Accès | Description |
|---------|------|-------|-------------|
| **Nginx** | 80 / 443 | Public | Reverse proxy, TLS (phase VPS) |
| **API** | 8000 | Interne | FastAPI REST + WebSocket |
| **ML** | 8001 | Interne | InsightFace, FAISS, fine-tuning |
| **Video** | 8002 | Interne | Ingestion caméras |
| **Frontend** | 5173 | Local dev | React/Vite (ou build statique Nginx) |
| **Redis** | 6379 | Interne | Broker Celery + EventBus (Docker uniquement) |
| **MLflow** | 5050 | Local | UI expériences ML |
| **Grafana** | 3001 | Local | Dashboards monitoring |
| **Prometheus** | 9090 | Interne | Collecte métriques |
| **Alertmanager** | 9093 | Interne | Routage alertes |
| **Loki** | 3100 | Interne | Agrégation logs |

---

## Configuration

Copier `.env.example` → `.env` (Docker) ou `.env.local` (LOCAL_MODE).

| Variable | Défaut | Description |
|----------|--------|-------------|
| `SECRET_KEY` | — | Clé JWT (obligatoire, générer avec `openssl rand -hex 32`) |
| `LOCAL_MODE` | `false` | `true` = sans Redis/Docker (Windows) |
| `INSIGHTFACE_CTX_ID` | `0` | `-1` pour CPU, `0` pour GPU CUDA |
| `ML_SERVICE_URL` | `http://ml:8001` | URL du service ML |
| `REDIS_URL` | `redis://redis:6379/0` | Broker Celery + EventBus |
| `FINE_TUNE_THRESHOLD` | `50` | Nombre de labels avant déclenchement fine-tuning |
| `CONFIDENCE_MIN` | `0.70` | Seuil bas active learning |
| `CONFIDENCE_MAX` | `0.85` | Seuil haut active learning |
| `AUTO_DEPLOY` | `true` | Déploiement auto si amélioration atteinte |
| `MIN_IMPROVEMENT_PCT` | `1.0` | Amélioration minimum (%) pour déployer |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Mot de passe Grafana |

---

## Pipeline Active Learning

```
Flux vidéo (RTSP / USB)
       │
       ▼
Extraction frames (OpenCV/FFmpeg)
       │
       ▼
Détection visages (RetinaFace)
       │
       ▼
Embedding 512-d (ArcFace buffalo_l)
       │
       ▼
Matching FAISS (cosinus)
       │
   ┌───┴───────────────────────┐
   │                           │
Score ≥ 0.85              Score 0.70–0.85
(Résultat direct)         (Incertitude → AL)
   │                           │
Authorisé/Intrus          ReviewItem → /review/queue
                               │
                    Revue humaine (5 actions)
                    confirmed / corrected /
                    new_profile / intrus / rejected
                               │
                    N labels atteints (FINE_TUNE_THRESHOLD)
                               │
                    Celery: fine_tune_model
                               │
                    ML: update centroides FAISS
                    Eval FAR/FRR/EER avant→après
                               │
               ┌───────────────┴───────────────┐
         amélioration ≥ seuil            amélioration < seuil
               │                               │
           Déployer                        Rollback
           MLflow log                      MLflow log
```

---

## Monitoring

### Dashboards Grafana (`http://localhost:3001`)

| Dashboard | Contenu |
|-----------|--------|
| **System Resources** | CPU %, RAM %, disque %, réseau I/O, latence API p50/p99, état des services |
| **ML Model Monitoring** | FAR, FRR, EER, TAR, drift score, file AL, identifications/min, fine-tuning history |

### Alertes Prometheus (seuils)

| Métrique | Warning | Critical |
|----------|---------|----------|
| CPU | > 75% / 5 min | > 85% / 5 min |
| RAM | > 70% / 5 min | > 80% / 5 min |
| Disque | > 70% / 10 min | > 85% / 5 min |
| Réseau | > 80 Mo/s | — |
| Latence API p99 | > 300 ms | > 500 ms |
| FAR | — | > 0.5% / 10 min |
| FRR | > 2% / 10 min | — |
| Drift score | > 0.05 / 10 min | — |
| File AL | > 500 frames | — |
| Service down | — | > 1 min |

### Logs (Loki + Promtail)

Tous les services loguent en JSON structuré (stdout → Promtail → Loki). Consultables dans Grafana via l'explorateur Loki.

### LOCAL_MODE (sans Docker)

En mode local, les métriques système sont accessibles via :
- `GET /api/v1/monitoring/system/resources` — CPU/RAM/disque/GPU (psutil + nvidia-smi)
- `GET /api/v1/monitoring/health` — Santé consolidée de tous les services
- `WS /ws/metrics` — Push temps réel toutes les 5 secondes

---

## Métriques ML

| Métrique | Cible | Alerte |
|----------|-------|--------|
| **FAR** (faux positifs) | < 0.1% | > 0.5% |
| **FRR** (faux rejets) | < 1% | > 2% |
| **EER** (point d'équilibre) | < 0.5% | > 1% |
| **TAR** (vrais positifs) | > 99% | < 98% |
| **Drift score** | < 0.05 | > 0.05 |

---

## Sécurité

- **RBAC** : viewer < operator < admin sur tous les endpoints
- **JWT** : tokens Bearer, expiration configurable
- **Embeddings chiffrés** : AES-256 au repos
- **Audit logs** : chaque identification, label et action admin est tracé (append-only, rétention 90 jours)
- **Zero endpoint public** : toutes les routes exigent authentification

---

## API

Documentation Swagger disponible en mode debug : `http://localhost:8000/api/docs`

Principaux endpoints :

```
POST /api/v1/auth/login          — Obtenir un token JWT
GET  /api/v1/profiles            — Lister les profils autorisés
POST /api/v1/profiles            — Enrôler un nouveau profil (images multi-angles)
POST /api/v1/identify            — Identifier un visage depuis une image
GET  /api/v1/review/queue        — File de revue humaine (active learning)
POST /api/v1/review/{id}/label   — Labelliser une frame
GET  /api/v1/review/stats        — Statistiques file + progression fine-tuning
POST /api/v1/review/training/trigger  — Déclencher un fine-tuning manuellement (admin)
GET  /api/v1/review/training/history  — Historique MLflow
GET  /api/v1/monitoring/system/resources  — CPU/RAM/disque/GPU
GET  /api/v1/monitoring/health            — Santé des services
GET  /api/v1/ml/model/info               — Version modèle + FAR/FRR/EER/TAR
GET  /api/v1/ml/drift                    — Drift score
WS   /ws/cameras/{camera_id}             — Stream détections temps réel
WS   /ws/alerts                          — Stream alertes sécurité
WS   /ws/metrics                         — Stream métriques système
```

---

## Compatibilité

| Fonctionnalité | Windows (LOCAL_MODE) | Linux/macOS natif | Docker Compose |
|---------------|---------------------|-------------------|----------------|
| API + ML + Celery | ✓ | ✓ | ✓ |
| Caméra RTSP | ✓ | ✓ | ✓ |
| Webcam USB | ✓ (CAP_DSHOW) | ✓ (V4L2) | ✓ (override.yml) |
| Redis / EventBus | InMemory (auto) | InMemory ou Redis | Redis |
| GPU CUDA | ✓ (drivers NVIDIA) | ✓ | ✓ (nvidia-toolkit) |
| Prometheus / Grafana | Manuel | Manuel | ✓ (services Docker) |
| node-exporter | N/A (psutil) | N/A (psutil) | ✓ |

---

## Structure du projet

```
llm_images/
├── services/
│   ├── api/          # FastAPI — REST, WebSocket, RBAC, Celery tasks
│   ├── ml/           # InsightFace, FAISS, fine-tuning, drift
│   ├── video/        # Ingestion caméras RTSP/USB
│   └── frontend/     # React 18, TypeScript, TailwindCSS
├── monitoring/
│   ├── prometheus/   # prometheus.yml + alerts.rules.yml
│   ├── alertmanager/ # alertmanager.yml
│   ├── grafana/      # Datasources + dashboards JSON
│   ├── loki/         # loki.yml
│   └── promtail/     # promtail.yml
├── docs/agents/      # Instructions par agent (source de vérité)
├── config/           # cameras.yml (configuration caméras)
├── nginx/            # nginx.conf
├── scripts/
│   └── start-dev.ps1 # Lanceur Windows sans Docker
├── docker-compose.yml
├── docker-compose.override.example.yml  # Webcam USB Linux
├── run.py            # Point d'entrée unique cross-platform
├── CLAUDE.md         # Instructions pour Claude Code
└── CAHIER_DES_CHARGES.md
```

---

## Documentation agents

Chaque agent du projet dispose de ses instructions dans `docs/agents/` :

| Agent | Fichier | Rôle |
|-------|---------|------|
| ML/IA | `AGENT_ML_IA.md` | Entraînement, embeddings, active learning, MLflow |
| Vidéo | `AGENT_VIDEO.md` | Ingestion flux, extraction frames, multi-caméras |
| Sécurité | `AGENT_SECURITE.md` | Détection intrus, alertes, RBAC, audit |
| Backend | `AGENT_BACKEND.md` | API REST, WebSocket, orchestration |
| Infra | `AGENT_INFRA.md` | Docker, Prometheus, Grafana, migration VPS |
| Data | `AGENT_DATA.md` | Dataset, annotation, augmentation, DVC |
| Frontend | `AGENT_FRONTEND.md` | Dashboard, revue humaine, monitoring UI |

---

## Migration locale → VPS

1. Provisionner un VPS (8 vCPU, 32 Go RAM, 500 Go SSD, GPU optionnel)
2. Exporter SQLite → PostgreSQL
3. Exporter index FAISS → Qdrant
4. Configurer Nginx + Let's Encrypt
5. Déployer avec `docker compose up -d`
6. Valider les smoke tests, pointer le DNS

Détails complets dans `docs/agents/AGENT_INFRA.md`.
