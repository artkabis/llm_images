---
paths:
  - services/ml/**
---
# ML Service — Path Rules

## Model & inference
- Use `insightface.app.FaceAnalysis(name="buffalo_l")` exclusively
- `ctx_id=-1` (CPU) when `LOCAL_MODE=true`; `ctx_id=0` for GPU in Docker
- Always L2-normalize embeddings before FAISS: `faiss.normalize_L2(embedding)`
- Return 512-d `float32` vectors; never truncate or cast to float16 for storage

## FAISS index
- Index type: `faiss.IndexFlatIP` (inner product ≈ cosine after L2 normalization)
- Centroid update: weighted mean `(old_centroid * n + new_embedding) / (n + 1)`
- Rebuild index after bulk profile updates, never per individual frame
- Persist FAISS index to `/data/models/faiss.index` after every update

## Active learning thresholds
- Uncertainty window: `CONFIDENCE_MIN (default 0.70) ≤ score ≤ CONFIDENCE_MAX (default 0.85)`
- Save pending frame JPEG: `/data/active_learning/pending/{review_id}.jpg`
- Save metadata JSON:      `/data/active_learning/pending/{review_id}.json`
- Confirmed samples moved to: `/data/active_learning/confirmed/`

## Fine-tuning protocol (POST /fine_tune)
1. Load labeled samples from JSON + JPEG pairs in `/data/active_learning/confirmed/`
2. Extract embeddings with `_extract_embedding(image)` (insightface pipeline)
3. Update FAISS centroids per profile (weighted mean, then re-normalize)
4. Evaluate FAR / FRR / EER on held-out pairs **before and after** update
5. Deploy if `improvement_pct ≥ MIN_IMPROVEMENT_PCT`; else restore previous index
6. Save checkpoint JSON to `/data/models/checkpoints/{version}.json`
7. Log all 8 metrics to MLflow: `far_before`, `far_after`, `frr_before`, `frr_after`,
   `eer_before`, `eer_after`, `improvement_pct`, `n_samples` + param `outcome`

## Drift detection
- Maintain `_recent_scores: deque(maxlen=100)` — last N recognition confidences
- Compute on every `GET /drift`: `drift_score = abs(mean(_recent_scores) - _baseline_score)`
- Set `alert=True` when `drift_score > 0.05`
- Update `_baseline_score` after each successful fine-tune deploy

## Endpoints (ML service, port 8001)
- `POST /embed`          — extract embedding from uploaded image
- `POST /recognize`      — 1-N matching, returns top-k with confidence
- `GET  /model/info`     — version, n_profiles, model_name, FAR/FRR/EER/TAR
- `GET  /model/versions` — list checkpoint JSON files
- `POST /model/rollback` — restore checkpoint by version id
- `POST /model/evaluate` — synthetic evaluation, updates global metrics
- `POST /fine_tune`      — full fine-tuning cycle (called by Celery worker)
- `GET  /drift`          — drift score + alert flag
- `GET  /health`         — liveness probe
