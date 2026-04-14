# CLAUDE.md — Vision AI · Facial Recognition System

## Project
Enterprise facial recognition for video surveillance: real-time detection, authorized vs.
intruder classification, active learning loop with human-in-the-loop fine-tuning.
Stack: InsightFace (ArcFace 512-d) + FAISS + FastAPI + Celery + React + MLflow + Docker.

---

## Repository (non-negotiable)
- **Repo**: `artkabis/llm_images` — **never** touch `multi-vendor-pim`
- **Branch**: `claude/facial-recognition-system-bLZRZ` — push here, never to `main`
- **MCP push strategy**: max 2 files per `push_files` call; load schema + call in same turn

## Agent docs — source of truth
@docs/agents/AGENT_ML_IA.md
@docs/agents/AGENT_VIDEO.md
@docs/agents/AGENT_SECURITE.md
@docs/agents/AGENT_BACKEND.md
@docs/agents/AGENT_INFRA.md
@docs/agents/AGENT_DATA.md
@docs/agents/AGENT_FRONTEND.md

---

## Services & ports
| Service  | Port | Notes |
|----------|------|-------|
| api      | 8000 | FastAPI + WebSocket + /internal/broadcast |
| ml       | 8001 | InsightFace inference, FAISS, fine-tuning |
| celery   | —    | Worker: fine_tune_model, evaluate_model |
| video    | —    | Camera ingestion (RTSP / USB) |
| frontend | 5173 | React + Vite |
| redis    | 6379 | Docker only — absent in LOCAL_MODE |
| mlflow   | 5050 | Experiment tracking |

## Quick start
```bash
# Linux / macOS — Docker Compose
docker compose up --build

# Windows — no Docker required
.\scripts\start-dev.ps1

# Single entry point (any platform)
python run.py
```

---

## Cross-platform rules
```python
IS_WINDOWS = sys.platform == "win32"
LOCAL_MODE = os.getenv("LOCAL_MODE", "false").lower() == "true"
```
- USB camera: Windows → `int` + `cv2.CAP_DSHOW`; Linux → `/dev/videoX` or `int` + V4L2
- LOCAL_MODE: no Redis → `InMemoryEventBus`; Celery broker = `memory://`
- `pathlib.Path` for all filesystem paths — no hardcoded POSIX strings
- `publish_fn` callback injected into `CameraWorker`; never import Redis directly in video

---

## Active learning pipeline
```
Frame scored 0.70–0.85  →  ReviewItem(status=pending)  →  /review/queue
Human labels one of 5 actions:
  confirmed | corrected | new_profile | intruder | rejected
Every FINE_TUNE_THRESHOLD labels → Celery `fine_tune_model` task
  └─ ML /fine_tune: extract embeddings, update FAISS centroids per profile
  └─ Evaluate FAR/FRR/EER before & after
  └─ improvement ≥ MIN_IMPROVEMENT_PCT → deploy; else rollback
  └─ MLflow logs: far_before/after, frr_before/after, eer_before/after,
               improvement_pct, n_samples, tar, outcome
```

## ML evaluation targets
| Metric | Target | Alert threshold |
|--------|--------|-----------------|
| FAR    | < 0.1% | > 0.5%          |
| FRR    | < 1%   | > 2%            |
| EER    | < 0.5% | > 1%            |
| TAR    | > 99%  | < 98%           |
| Drift  | < 0.05 | > 0.05          |

---

## Critical code patterns

### Event bus (never bypass)
```python
# Always use EventBusAdapter — never import redis directly
from core.eventbus import EventBusAdapter
bus = EventBusAdapter()          # auto-selects Redis or InMemoryEventBus
await bus.publish(channel, data) # async
bus.publish_sync(channel, data)  # thread-safe (video workers)
```

### RBAC on every route
```python
@router.get("/resource")
async def endpoint(user=Depends(require_role("viewer"))):
    ...
# Hierarchy: viewer < operator < admin
# GET → viewer | POST/PATCH → operator | DELETE/rollback/config-write → admin
```

### InsightFace inference
```python
app = FaceAnalysis(name="buffalo_l")
app.prepare(ctx_id=-1 if LOCAL_MODE else 0)  # -1 = CPU
embedding = app.get(img)[0].embedding        # 512-d float32
# Always L2-normalize before FAISS IndexFlatIP (= cosine similarity)
```

---

## Security non-negotiables
- Credentials in env vars only — never in code or committed files
- AES-256 encryption for stored embeddings
- Full audit log on every recognition event and label action
- RBAC enforced on **every** API route — zero unauthenticated endpoints
- No credentials in logs; mask tokens in error messages

---

## Path-specific rules
@.claude/rules/ml-inference.md
@.claude/rules/api-design.md
@.claude/rules/frontend.md

---

## Commit & push checklist
- [ ] Branch: `claude/facial-recognition-system-bLZRZ` only
- [ ] README.md updated for every new user-visible feature
- [ ] Cross-platform: `pathlib.Path`, no hardcoded `/dev/video*`, no bare Redis in LOCAL_MODE
- [ ] `require_role()` dependency on every new API route
- [ ] No credentials, tokens, or secrets in committed files
- [ ] MLflow metrics logged for any training/evaluation change
- [ ] Drift detection deque updated after each recognition batch
