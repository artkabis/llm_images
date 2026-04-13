# CLAUDE.md — Instructions prioritaires pour Claude Code

> Ce fichier est lu en priorité par Claude Code avant toute action sur ce dépôt.

## 1. Repo & branche

- **Repo unique** : `artkabis/llm_images` — ne jamais toucher `multi-vendor-pim`
- **Branche de dev** : `claude/facial-recognition-system-bLZRZ`
- Push toujours sur cette branche, PR vers `main` sur demande explicite

---

## 2. Sources de vérité — Lire AVANT tout code

| Fichier | Contenu |
|---|---|
| `docs/agents/AGENT_ML_IA.md` | ML, embeddings, fine-tuning, métriques FAR/FRR/EER/TAR |
| `docs/agents/AGENT_VIDEO.md` | Ingestion vidéo, multi-caméras, qualité frames |
| `docs/agents/AGENT_SECURITE.md` | Alertes 4 niveaux, RBAC, chiffrement AES-256, audit |
| `docs/agents/AGENT_BACKEND.md` | API REST, WebSocket, Celery, endpoints |
| `docs/agents/AGENT_INFRA.md` | Docker, monitoring, migration local→VPS |
| `docs/agents/AGENT_DATA.md` | Dataset, augmentation, GDPR |
| `docs/agents/AGENT_FRONTEND.md` | UI pages, RBAC frontend, dark mode |
| `CAHIER_DES_CHARGES.md` | Architecture globale, roadmap phases |

---

## 3. Règles GitHub MCP (critique — lire attentivement)

Le serveur MCP GitHub se déconnecte toutes les ~2-5 min.

### Stratégie anti-timeout
- **Toujours utiliser `push_files`** (pas de SHA requis, multi-fichiers)
- **Maximum 2 fichiers par appel `push_files`** pour éviter le stream idle timeout
- Charger le schéma via `ToolSearch` ET appeler le tool dans la **même réponse**
- Préparer tout le contenu des fichiers AVANT d'appeler les tools GitHub
- En cas de déconnexion : `ToolSearch` immédiatement à la reconnexion, sans texte inutile
- Ne jamais écrire de longs blocs de texte avant un appel tool (cause de timeout)

### Ordre d'exécution correct
```
1. ToolSearch (charge schéma) — même réponse que l'appel suivant si possible
2. push_files avec 1-2 fichiers max
3. Répéter pour chaque batch
```

---

## 4. Compatibilité cross-platform (obligatoire)

| OS | Mode | Démarrage |
|---|---|---|
| Windows | Local (no Docker) | `python run.py` ou `.\scripts\start-dev.ps1` |
| Linux/macOS | Local | `python run.py` ou `./scripts/start-dev.sh` |
| Linux/macOS | Docker | `docker compose up -d` |

### Variables d'environnement clés
```bash
LOCAL_MODE=true           # Sans Redis, sans Docker (EventBus in-memory)
INSIGHTFACE_CTX_ID=-1    # CPU (-1) ou GPU (0)
API_SERVICE_URL=http://localhost:8000
ML_SERVICE_URL=http://localhost:8001
```

### Pattern publish_fn (VideoService)
```python
# LOCAL_MODE → HTTP vers /internal/broadcast
# Docker     → redis.publish() direct
publish_fn = _build_publish_fn()  # services/video/main.py
worker = CameraWorker(config=cam_config, publish_fn=publish_fn)
```

---

## 5. Pipeline Active Learning & Fine-tuning (AGENT_ML_IA.md §5)

```
Frame incertaine (score 70-85%)
    │
    ▼
[ReviewItem en DB] ← camera_id, confidence, candidates, frame.jpg
    │
    ▼ (opérateur humain)
[Review.tsx] ← 5 actions : confirmed / corrected / new_profile / intruder / rejected
    │
    ▼
[POST /api/v1/review/{id}/label] ← compte labels, retourne task_id
    │ (si labeled_count % trigger_threshold == 0)
    ▼
[Celery: fine_tune_model] ← POST vers ML /fine_tune
    │
    ▼
[ML: mise à jour centroids FAISS + évaluation FAR/FRR/EER]
    ├─ improvement >= min_pct → deployed=True, version++
    └─ dégradation → rolled_back=True, anciens centroids conservés
    │
    ▼
[MLflow] ← far_before/after, frr_before/after, eer, improvement_pct, n_samples
```

### Seuils configurables (PUT /api/v1/review/training/config)
```
ML_THRESHOLD_SUSPECT=0.70     # En dessous → inconnu
ML_THRESHOLD_AUTHORIZED=0.85  # Au-dessus → autorisé
ML_ACTIVE_LEARNING_TRIGGER=50 # Labels pour déclencher fine-tuning
ML_AUTO_DEPLOY=true
ML_MIN_IMPROVEMENT_PCT=1.0
```

---

## 6. Structure du projet

```
llm_images/
├── CLAUDE.md                    ← CE FICHIER
├── CAHIER_DES_CHARGES.md
├── README.md
├── DEMARRAGE.md
├── run.py                       ← Launcher cross-platform (python run.py)
├── docker-compose.yml
├── docker-compose.override.example.yml  ← Webcam Linux
├── .env.example / .env.local
├── config/cameras.yml
├── services/
│   ├── api/                     ← FastAPI :8000
│   │   ├── core/                ← config, database, security, eventbus
│   │   ├── routers/             ← profiles, identify, alerts, review, auth, monitoring
│   │   └── workers/             ← celery_app, tasks
│   ├── ml/                      ← ML FastAPI :8001
│   │   ├── face_engine.py       ← RetinaFace + ArcFace 512d
│   │   ├── embedding_store.py   ← FAISS wrapper
│   │   ├── metrics.py           ← Prometheus
│   │   └── main.py              ← /identify /enroll /fine_tune /model/*
│   ├── video/                   ← Video FastAPI :8002
│   │   ├── camera_manager.py    ← CameraWorker cross-platform
│   │   └── main.py              ← publish_fn LOCAL/Docker
│   └── frontend/                ← React :3000
│       └── src/pages/           ← Dashboard, Alerts, Profiles, Review,
│                                   MonitoringML, MonitoringSystem, Login
├── docs/agents/                 ← Instructions agents IA par domaine
├── monitoring/                  ← Prometheus, Grafana, Loki, Promtail
└── scripts/
    ├── start-dev.sh             ← Bash (Linux/macOS)
    └── start-dev.ps1            ← PowerShell (Windows)
```

---

## 7. Patterns de code

### Router FastAPI
```python
from core.database import get_db, ReviewItem, ReviewStatus
from core.security import require_role
from core.config import get_settings

router = APIRouter()

@router.get("/endpoint")
async def my_endpoint(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("operator")),  # admin | operator | viewer
):
    ...
```

### EventBus
```python
# Publication
await bus.publish("channel:alerts", {"level": "CRITICAL", ...})
# Souscription WebSocket
async for raw in bus.subscribe("channel:alerts"):
    await websocket.send_text(raw)
```

---

## 8. Sécurité

- **JWT** : mémoire uniquement, jamais localStorage
- **RBAC** : viewer < operator < admin — `require_role("min_role")`
- **Embeddings** : chiffrés AES-256, ne jamais loguer les vecteurs bruts
- **GDPR** : DELETE /enroll/{id} supprime FAISS + images + logs

---

## 9. Métriques ML cibles (AGENT_ML_IA.md §7)

| Métrique | Objectif | Description |
|---|---|---|
| FAR | < 0.1% | False Acceptance Rate |
| FRR | < 1% | False Rejection Rate |
| EER | minimiser | Equal Error Rate |
| TAR | > 99% | True Acceptance Rate @ FAR=0.1% |
| Drift | < 0.05 | Dérive distribution embeddings |

---

## 10. Checklist avant chaque push

- [ ] Code testé cross-platform (Windows path + Linux path)
- [ ] Imports cohérents avec le style du projet (`from core.xxx` pas `from ..xxx`)
- [ ] Pas de dépendance Redis en LOCAL_MODE
- [ ] Métriques Prometheus exposées pour chaque nouveau service
- [ ] RBAC respecté sur tous les endpoints sensibles
- [ ] CLAUDE.md à jour si nouveau feature ajouté
