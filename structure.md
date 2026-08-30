# Project Structure

A complete overview of the file structure of the AI Continual-Learning Platform.

The project is a **monorepo**: a Python backend (FastAPI + PyTorch), a React + Vite +
TypeScript frontend, shared ML packages (model, tokenizer), and service modules
(trainer, inference, evaluator, memory, scheduler). One Docker image builds the frontend
and serves the backend + built SPA together for Railway deployment.

---

## Top-level layout

```
Ai-builder-Llm/
├── apps/                  # Application entrypoints
│   ├── api/               # FastAPI backend (routers, auth, worker, schemas)
│   └── web/               # React + Vite + TypeScript frontend
├── packages/              # Shared libraries (importable by all services)
│   ├── model/             # Real decoder-only Transformer (PyTorch)
│   ├── tokenizer/         # Trainable versioned byte-level BPE tokenizer
│   └── shared/            # Config, DB models, hardware, security, dataset, metrics
├── services/              # Backend service modules
│   ├── trainer/           # Training loop, checkpoints, replay, continual learning
│   ├── inference/         # KV-cache generation, streaming, comparison
│   ├── evaluator/         # Benchmarks, custom tests, retention scoring
│   ├── memory/            # Explicit memory + vector embeddings + RAG retrieval
│   └── retrieval/         # Vector search helpers
├── training/              # Training configs / recipes by stage
│   ├── pretraining/
│   ├── finetuning/
│   └── continual_learning/
├── tests/                 # Pytest suite (51 tests)
├── scripts/               # E2E test harness
├── docs/                  # Architecture & feature docs
├── infrastructure/        # Deployment notes
│
├── Dockerfile             # ★ Primary image (multi-stage) for Railway
├── railway.toml           # Railway config-as-code (healthcheck, startCommand)
├── Procfile               # Optional web/worker process split
├── docker-compose.yml     # Local multi-service (db/redis/api/worker/web)
├── Dockerfile.api         # API-only image (compose)
├── Dockerfile.web         # Frontend image (compose)
├── Dockerfile.worker.gpu  # GPU worker image
├── requirements.txt       # ★ Canonical Python deps (used by Dockerfile)
├── .env.example           # Environment variable template
├── .dockerignore          # Docker build context exclusions
├── .gitignore
├── README.md
├── railway.md             # ★ Railway deployment guide
├── structure.md           # ★ This file
└── AGENTS.md              # Repo memory / dev notes
```

★ = the files that matter most for Railway deployment.

---

## `apps/api/` — FastAPI backend

```
apps/api/
├── __init__.py
├── main.py            # App factory: mounts routers, init_db, serves SPA, inline worker
├── auth.py            # JWT auth dependency (get current user)
├── model_manager.py   # Load & cache trained models for inference
├── worker.py          # Training worker: polls DB, runs real training, checkpoints
├── schemas.py         # Pydantic request/response schemas
├── requirements.txt   # Backend-specific deps (superset of root requirements.txt)
└── routers/
    ├── __init__.py
    ├── auth.py            # /auth — register, login, me
    ├── datasets.py        # /datasets — CRUD, versions, upload, paste, preview
    ├── tokenizers.py      # /tokenizers — train, list, activate
    ├── training.py        # /training — hardware, plan, jobs, SSE stream, control
    ├── models.py          # /models — registry, versions, promote, rollback
    ├── evaluations.py     # /evaluations — suites, custom tests, results
    ├── memory.py          # /memory — documents, memories, retrieve, corrections
    ├── inference.py       # /inference — generate, stream, compare (Test Lab)
    ├── chat.py            # /chat — streaming chat with RAG + memory
    ├── dashboard.py       # /dashboard — status, growth, charts, knowledge, vocab, ...
    └── schedules.py       # /schedules — scheduled + auto learning
```

Key points:
- `main.py` calls `init_db()` (idempotent table creation) on startup, serves the built SPA
  from `apps/web/dist` when present, and (when `RUN_INLINE_WORKER=true`) starts the worker
  in a daemon thread so one process handles API + training.
- `worker.py` exposes `run_worker_loop()` used both standalone and inline.

---

## `apps/web/` — Frontend (React + Vite + TS)

```
apps/web/
├── index.html
├── package.json
├── package-lock.json
├── tsconfig.json
├── vite.config.ts        # Dev proxy of all API routes → :8000
├── dist/                 # (build output — gitignored, produced by Dockerfile Stage 1)
└── src/
    ├── main.tsx          # React entry
    ├── App.tsx           # Router + layout + nav
    ├── api.ts            # Central API client (JWT in localStorage, relative URLs)
    ├── auth.tsx          # Auth context / hooks
    ├── ui.tsx            # Shared UI primitives (cards, badges, charts)
    ├── styles.css        # Global styles
    └── pages/
        ├── Login.tsx
        ├── Dashboard.tsx
        ├── AIGrowth.tsx
        ├── Training.tsx
        ├── TrainingQueue.tsx
        ├── Datasets.tsx
        ├── Knowledge.tsx
        ├── Vocabulary.tsx
        ├── Memory.tsx
        ├── Evaluations.tsx
        ├── Models.tsx
        ├── Checkpoints.tsx
        ├── Workers.tsx
        ├── Performance.tsx
        ├── Settings.tsx
        └── TestLab.tsx
```

The frontend uses **relative URLs** (`BASE = ''`), so when served by the API at `/` it
calls the same origin — no CORS configuration needed in production.

---

## `packages/` — Shared ML libraries

### `packages/model/` — Real Transformer
```
packages/model/
├── __init__.py        # Exports ModelConfig, TransformerLM
├── config.py          # ModelConfig dataclass (layers, heads, KV heads, RoPE, dtype...)
├── transformer.py     # TransformerLM: embeddings, RoPE, RMSNorm, GQA, SwiGLU, LM head
└── kv_cache.py        # KV cache: prefill + decode for fast autoregressive generation
```

### `packages/tokenizer/` — Versioned BPE
```
packages/tokenizer/
├── __init__.py        # Exports BPETokenizer
└── tokenizer.py       # Byte-level BPE: train, encode, decode, save/load (versioned)
```

### `packages/shared/` — Cross-cutting concerns
```
packages/shared/
├── __init__.py        # Exports settings, Base, engine, SessionLocal, get_db, init_db
├── config.py          # Settings (env-driven, Railway-aware: PORT, DB URL normalization)
├── database.py        # SQLAlchemy engine/session, init_db, pgvector setup
├── models.py          # Full ORM schema (all DB tables)
├── dataset.py         # Parse/clean/dedup/analyze/tokenize/split TXT/JSON/JSONL/CSV/MD
├── hardware.py        # Real CPU/GPU detection + live utilization (psutil/torch.cuda)
├── security.py        # Password hashing (bcrypt/PBKDF2), JWT, file-type allowlist
└── metrics.py         # Perplexity, retention score, AI growth score, word estimates
```

---

## `services/` — Backend service modules

```
services/
├── trainer/
│   ├── __init__.py
│   └── core.py        # Hyperparams, optimizer, LR schedule, batches, checkpoints, eval
├── inference/
│   ├── __init__.py
│   └── generate.py    # KV-cache sampling generation (temp/top-p/top-k/rep penalty)
├── evaluator/
│   ├── __init__.py
│   └── evaluator.py   # run_tests, EvalTest, benchmark Q/A generation, retention
├── memory/
│   ├── __init__.py
│   └── memory.py      # embed_text, cosine, document store, RAG retrieve
└── retrieval/
    └── __init__.py    # Vector search helpers
```

> Note: `services/scheduler/` logic is implemented inside `apps/api/routers/schedules.py`
> and `packages/shared/` (scheduled + auto-learning cycles).

---

## `training/` — Recipes by stage

```
training/
├── pretraining/
├── finetuning/
└── continual_learning/
```
Empty placeholder directories for future recipe/config files. The actual continual-learning
logic lives in `apps/api/worker.py` + `services/trainer/core.py` + `services/evaluator/`.

---

## `tests/` — Pytest suite (51 tests)

```
tests/
├── conftest.py        # Shared fixtures (temp DB, tokenizer, model, tokens)
├── test_tokenizer.py  # BPE train/encode/decode + Amharic/Ethiopic Unicode
├── test_model.py      # Transformer forward/backward, KV cache, shapes
├── test_training.py   # Loss decrease, checkpoint save/load/resume
├── test_evaluation.py # Retention score, benchmark tests
├── test_dataset.py    # Parse/clean/dedup/split/tokenize
├── test_memory.py     # Embeddings + cosine vector search (RAG)
└── test_api.py        # FastAPI endpoints (auth, datasets, training, models, ...)
```

Run: `python -m pytest tests/ -q`

---

## `scripts/`

```
scripts/
└── e2e_test.py        # Full HTTP e2e: register → tokenizer → dataset → train → promote → generate
```

Run: `python scripts/e2e_test.py` (starts against a running API on :8000).

---

## `docs/`

```
docs/
├── ARCHITECTURE.md
├── TRAINING.md
├── CONTINUAL_LEARNING.md
├── MODEL_REGISTRY.md
├── DATASETS.md
├── DEPLOYMENT.md
├── API.md
└── SECURITY.md
```

---

## Deployment files (Railway-relevant)

| File | Purpose |
|------|---------|
| `Dockerfile` | **Primary** multi-stage image: builds frontend → Python runtime with CPU torch → serves API + SPA + inline worker. |
| `railway.toml` | Railway config-as-code: healthcheck (`/api/health`), startCommand, restart policy. |
| `Procfile` | Optional `web`/`worker` process split. |
| `requirements.txt` | Canonical Python deps (includes psutil, psycopg2-binary, torch). |
| `.env.example` | All env vars with defaults + Railway notes. |
| `.dockerignore` | Keeps build context lean (excludes node_modules, dist, data, tests, docs). |
| `docker-compose.yml` | Local multi-service alternative (Postgres + Redis + API + worker + web). |
| `Dockerfile.api` / `Dockerfile.web` / `Dockerfile.worker.gpu` | Used by docker-compose / GPU worker; the Railway deploy uses the root `Dockerfile`. |

---

## Data flow at runtime

```
Browser (SPA at /)
   │  REST + SSE (same origin)
   ▼
FastAPI (apps/api/main.py)  ──►  PostgreSQL (DATABASE_URL)
   │  inline worker thread            └─ tables auto-created by init_db()
   ▼
worker.run_worker_loop()
   │  polls training_jobs (status=queued)
   ▼
services/trainer/core.py  ──►  packages/model TransformerLM  ──►  /data/checkpoints
   │  real forward/backward, replay, eval
   ▼
services/evaluator  ──►  retention score  ──►  candidate model version
   │  (promotion gated by quality thresholds)
   ▼
apps/api/model_manager  ──►  load checkpoint  ──►  inference / chat / test lab
```

All persistent state (datasets, jobs, models, checkpoints metadata, conversations,
memories, evaluations) lives in Postgres + the `/data` volume, so redeploys and restarts
never lose data.
