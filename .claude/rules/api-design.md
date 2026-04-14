---
paths:
  - services/api/**
---
# API Service — Path Rules

## Auth & RBAC (mandatory on every route)
```python
from core.auth import require_role
# viewer  → GET read-only endpoints
# operator → POST label / trigger actions
# admin   → DELETE, rollback, config write, user management
@router.get("/resource")
async def read(user=Depends(require_role("viewer"))):
    ...
```
- JWT Bearer tokens; **never** log tokens or full Authorization headers
- Return 401 for missing/expired token; 403 for insufficient role

## Inter-service calls
```python
# Always async + httpx; never requests (blocks event loop)
async with httpx.AsyncClient(timeout=5.0) as client:
    resp = await client.get(f"{ML_SERVICE_URL}/model/info")
# Parallel calls via asyncio.gather()
info_r, drift_r = await asyncio.gather(
    client.get(f"{ML_SERVICE_URL}/model/info"),
    client.get(f"{ML_SERVICE_URL}/drift"),
    return_exceptions=True,
)
# Timeouts: 5 s for info/health; 3000 s for /fine_tune proxy
```

## Event bus (never bypass)
```python
from core.eventbus import EventBusAdapter
bus = EventBusAdapter()           # auto: Redis (Docker) or InMemory (LOCAL_MODE)
await bus.publish(channel, data)  # async coroutines
bus.publish_sync(channel, data)   # thread-safe (used by video workers)
```
- `POST /internal/broadcast {channel, data}` → LOCAL_MODE entry point from video service
- WebSocket channels: `cameras/{camera_id}`

## Review router conventions
- `GET  /review/queue`                   paginated, filterable by camera_id / confidence
- `GET  /review/{id}/frame`              FileResponse JPEG from `/data/active_learning/pending/`
- `POST /review/{id}/label`              5 actions; returns `{task_id, next_trigger_in}`
- `GET  /review/stats`                   counts by status + progress_pct + next_trigger_in
- `POST /review/training/trigger`        admin only — manual fine-tune
- `GET  /review/training/status`         Celery inspect (running tasks)
- `GET  /review/training/config`         returns env var dict
- `PUT  /review/training/config`         updates `os.environ`; admin only
- `GET  /review/training/history`        MLflow runs enriched with typed metrics
- `POST /review/training/rollback/{id}`  delegates to ML service; admin only

## ML proxy router (services/api/routers/ml_proxy.py)
- `GET /ml/model/info` and `GET /ml/drift` proxy to ML service
- Return 503 if ML service unreachable; 504 on timeout
- Include router in `main.py`: `app.include_router(ml_router, prefix="/ml", tags=["ml"])`

## Error handling
- 422 automatic via Pydantic (never catch ValidationError silently)
- 503 when ML service is unreachable
- 504 on upstream timeout
- 400 for invalid business logic (e.g., duplicate profile name)
- Never return 500 with raw traceback to the client
