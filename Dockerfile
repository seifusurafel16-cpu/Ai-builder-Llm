# =====================================================================
# AI Continual-Learning Platform — single-image Railway deployment
# =====================================================================
# Stage 1: build the React + Vite frontend SPA.
# Stage 2: Python runtime that installs CPU-only torch + deps, copies the
#          built SPA, and serves the API + inline worker on $PORT.
# =====================================================================

# ---------- Stage 1: frontend build ----------
FROM node:20-slim AS web-build
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci || npm install
COPY apps/web/ ./
RUN npm run build   # outputs to /web/dist

# ---------- Stage 2: Python runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    PORT=8000

WORKDIR /app

# System deps: build-essential for any source builds, libpq-dev for psycopg2,
# curl for the Railway healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first (small image, no CUDA), then the rest of deps.
COPY requirements.txt ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 \
    && pip install -r requirements.txt

# Copy the application code (monorepo layout).
COPY packages ./packages
COPY services ./services
COPY apps/api ./apps/api
COPY training ./training

# Copy the built frontend so the API can serve the SPA at /.
COPY --from=web-build /web/dist ./apps/web/dist

# Persistent data volume mount point (Railway volume -> /data).
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# Healthcheck hits the FastAPI health endpoint. Railway also uses this if configured.
HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/health" || exit 1

# Single process: API (which starts the inline worker thread by default).
# Shell form so uvicorn reads the Railway-injected PORT env var at runtime.
CMD sh -c "python -m uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"
