# Railway Deployment Guide

This guide explains how to deploy the AI Continual-Learning Platform to Railway.

The platform deploys as a **single Docker image** that:
1. Builds the React + Vite frontend (Stage 1)
2. Installs CPU-only PyTorch + backend deps, serves the FastAPI API + built SPA, and runs
   the training worker in a background thread (Stage 2)

One Railway service handles everything. No separate worker or web containers required
(though you *can* split them — see [Advanced: dedicated worker](#advanced-dedicated-worker)).

---

## What gets deployed

```
Railway Service (single Docker image)
├── uvicorn FastAPI app  →  REST API + SSE on $PORT
│     ├── serves built SPA at /  (apps/web/dist)
│     └── inline training worker thread  (RUN_INLINE_WORKER=true)
└── PostgreSQL add-on  →  DATABASE_URL (auto-injected)
```

- **API**: FastAPI, 11 routers, 76 routes, SSE live updates, `/api/health` healthcheck.
- **Worker**: runs inside the API process by default, polls the DB for queued training jobs.
- **DB**: Railway PostgreSQL (the `DATABASE_URL` is auto-normalized to `postgresql+psycopg2://`).
- **Storage**: a Railway Volume mounted at `/data` holds datasets, tokenizers, checkpoints.

---

## Prerequisites

- A [Railway](https://railway.app) account.
- This GitHub repo connected to Railway.

---

## Step-by-step deploy

### 1. Create a new Railway project

1. Go to <https://railway.app> → **New Project** → **Deploy from GitHub repo**.
2. Select this repository (`Ai-builder-Llm`).
3. Railway detects the `Dockerfile` and builds it automatically.

### 2. Add PostgreSQL

1. In the project, click **New → Database → Add PostgreSQL**.
2. Railway provisions a Postgres instance and exposes a `DATABASE_URL` variable.
3. Go to your **web service → Variables** and add a reference variable:
   - `DATABASE_URL` = `${{ Postgres.DATABASE_URL }}`
   (Railway's variable reference syntax, or just pick it from the Postgres service.)

> The app accepts Railway's `postgresql://...` URL directly — it is rewritten to the
> SQLAlchemy `postgresql+psycopg2://` dialect automatically at startup.

### 3. Set required variables

In **web service → Variables**, set at minimum:

| Variable | Value | Why |
|----------|-------|-----|
| `SECRET_KEY` | a random 48+ char string | Signs JWTs. **Required** for stable sessions across redeploys. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` | Postgres connection (see step 2). |

Optional (defaults shown):

| Variable | Default | Notes |
|----------|---------|-------|
| `RUN_INLINE_WORKER` | `true` | Run the training worker inside the API process. |
| `DEFAULT_DEVICE` | `auto` | `auto` / `cpu` / `gpu` (Railway CPU plans → `auto` resolves to CPU). |
| `STORAGE_DIR` | `/data/storage` | Object storage root (mount a Volume, see step 4). |
| `CHECKPOINT_DIR` | `/data/checkpoints` | Model checkpoints. |
| `TOKENIZER_DIR` | `/data/tokenizers` | Trained tokenizers. |
| `JWT_EXPIRE_HOURS` | `168` | Token lifetime. |
| `MAX_UPLOAD_BYTES` | `209715200` | Max upload size (200 MB). |

Railway injects `PORT` automatically — do **not** set it manually.

### 4. Add a persistent Volume (IMPORTANT)

Railway's filesystem is **ephemeral** — files are lost on redeploy unless you attach a
Volume. Uploaded datasets, trained tokenizers, and model checkpoints must be persisted.

1. In the **web service → Settings → Volumes**, click **Add Volume**.
2. Mount path: `/data`
3. This persists everything under `/data` (storage, checkpoints, tokenizers, logs).

> Without a volume, training still works but datasets/checkpoints vanish on redeploy.

### 5. Deploy

1. Click **Deploy**. Railway builds the image (frontend + backend) and starts the service.
2. Watch the **Deploy Logs**. On success you'll see:
   ```
   [api] inline training worker started in background thread
   INFO: Uvicorn running on http://0.0.0.0:PORT
   ```
3. Railway runs the healthcheck against `/api/health`; once it returns `200`, the service
   is live.

### 6. Open the app

- In **Settings → Networking → Generate Domain** to get a public URL like
  `https://ai-builder-llm.up.railway.app`.
- Open it in your browser → **Register** → use the platform.

---

## Verify it works

```bash
# health
curl https://<your-app>.up.railway.app/api/health
# → {"status":"ok","service":"ai-platform-api"}

# API docs (Swagger)
open https://<your-app>.up.railway.app/docs
```

Then in the UI:
1. **Tokenizers** → train a BPE tokenizer from sample text.
2. **Datasets** → paste text → create a version.
3. **Training** → start a job → watch live progress (real loss/perplexity/tokens-per-sec).
4. **Evaluations** → run tests → check retention score.
5. **Models** → promote a candidate to production.
6. **Model Test Lab** → prompt your trained model.
7. **Chat** → chat with the production model (memory + RAG).

---

## Environment variables reference

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `PORT` | Railway sets it | `8000` | HTTP listen port. |
| `DATABASE_URL` | **Yes** (prod) | sqlite dev | Postgres DSN; normalized automatically. |
| `SECRET_KEY` | **Yes** (prod) | ephemeral | JWT signing secret. |
| `STORAGE_DIR` | no | `/data/storage` | Dataset/object storage root. |
| `CHECKPOINT_DIR` | no | `/data/checkpoints` | Model checkpoint storage. |
| `TOKENIZER_DIR` | no | `/data/tokenizers` | Tokenizer storage. |
| `LOG_DIR` | no | `/data/logs` | Log directory. |
| `RUN_INLINE_WORKER` | no | `true` | Run training worker in-process. |
| `DEFAULT_DEVICE` | no | `auto` | Compute device selection. |
| `WORKER_POLL_SECONDS` | no | `1.0` | Worker job poll interval. |
| `SSE_HEARTBEAT_SECONDS` | no | `15` | SSE keepalive interval. |
| `JWT_EXPIRE_HOURS` | no | `168` | JWT expiry. |
| `MAX_UPLOAD_BYTES` | no | `209715200` | Max upload size. |
| `CORS_ORIGINS` | no | `*` | Allowed CORS origins. |

---

## How Railway builds this repo

- **Build detection**: Railway finds `Dockerfile` at the repo root and uses it (not
  Nixpacks). The `railway.toml` configures the healthcheck + start command.
- **`Dockerfile` (multi-stage)**:
  - Stage 1 (`web-build`): `node:20-slim` → `npm run build` → `/web/dist`.
  - Stage 2 (`runtime`): `python:3.12-slim` → installs **CPU-only** torch from the PyTorch
    CPU wheel index (small image, no CUDA) + `requirements.txt`, copies the app + built SPA.
- **Start command**: `uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT`.
- **Healthcheck**: `GET /api/health` → `{"status":"ok"}`.

---

## Advanced: dedicated worker

For heavier training, split the worker into its own Railway service so training CPU
doesn't compete with API requests:

1. On the **web** service set `RUN_INLINE_WORKER=false`.
2. **New → Service → GitHub repo** (same repo, same image) → name it `worker`.
3. Set its start command to: `python -m apps.api.worker`
   (Railway: **Settings → Start command**, or use the `Procfile` `worker` entry).
4. Give it the same `DATABASE_URL` and Volume mount (`/data`) so it shares the job queue
   and can read/write checkpoints.

Both services share the same Postgres DB and `/data` volume, so the web service enqueues
jobs and the worker executes them.

---

## GPU on Railway

Railway offers GPU plans. To use one:

1. Provision a GPU service (Railway **New → GPU** if available on your plan).
2. The app auto-detects CUDA via `torch.cuda.is_available()` and uses AMP mixed precision.
3. The default `Dockerfile` installs CPU-only torch for size. For a GPU service, replace
   the torch install line in `Dockerfile` with a CUDA build, or use `Dockerfile.worker.gpu`.

> On standard CPU plans, `DEFAULT_DEVICE=auto` resolves to CPU and everything works —
> just slower. Training a small model for a demo is fine on CPU.

---

## Failure recovery on Railway

- **Redeploy / restart**: state is in Postgres + the `/data` volume — nothing is lost.
- **Worker crash**: the job is marked `failed` in the DB; re-queue or resume from the last
  checkpoint via the **Checkpoints** page.
- **Healthcheck failure**: Railway restarts the service automatically (up to
  `restartPolicyMaxRetries = 5`).

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `502 / connection refused` after deploy | Wait for the healthcheck to pass; check logs for boot errors. |
| Login works once then fails | `SECRET_KEY` not set → ephemeral key changes on redeploy. Set a stable `SECRET_KEY`. |
| Uploaded files disappear | No Volume mounted at `/data`. Add one (step 4). |
| DB errors / `relation does not exist` | `DATABASE_URL` not pointing at Postgres, or Postgres not provisioned. Tables auto-create on boot. |
| `psycopg2` import error | Should not happen — `psycopg2-binary` is in `requirements.txt`. Rebuild the image. |
| Training jobs stuck in `queued` | `RUN_INLINE_WORKER` is `false` and no dedicated worker is running. Set it to `true` or start a worker service. |
| Build OOM / slow | The torch CPU wheel is large; use a Railway plan with ≥ 1 GB build memory. First build caches afterward. |

---

## Local testing of the production image

```bash
# build & run the exact image Railway uses
docker build -t ai-platform .
docker run -p 8000:8000 -e PORT=8000 -e SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(48))") -v ai-platform-data:/data ai-platform
# open http://localhost:8000
```

---

## Reference links

- Railway docs: <https://docs.railway.app>
- Config-as-code (`railway.toml`): <https://docs.railway.app/deploy/config-as-code>
- Volumes: <https://docs.railway.app/deploy/volumes>
- PostgreSQL add-on: <https://docs.railway.app/deploy/databases#postgresql>
- Dockerfile deploys: <https://docs.railway.app/deploy/dockerfile>
