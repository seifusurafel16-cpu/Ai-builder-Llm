"""apps.api.main — FastAPI application entrypoint.

Mounts all routers, initializes DB, serves the built frontend SPA, and exposes
a root health endpoint.

Railway deployment:
- Listens on ``PORT`` (injected by Railway) via ``settings.PORT``.
- Optionally starts the training worker in a background thread within the same
  process (``RUN_INLINE_WORKER=true``) so a single service handles both API + jobs.
- Serves the built SPA from ``apps/web/dist`` when present (built in the Docker image).
"""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from packages.shared import init_db, settings
from apps.api.routers import (
    auth as auth_router,
    datasets as datasets_router,
    tokenizers as tokenizers_router,
    training as training_router,
    models as models_router,
    evaluations as evaluations_router,
    memory as memory_router,
    inference as inference_router,
    chat as chat_router,
    dashboard as dashboard_router,
    schedules as schedules_router,
)


def _maybe_start_inline_worker() -> None:
    """Start the training worker in a daemon thread if enabled.

    This lets a single Railway service run both the API and the training loop.
    For heavier setups, set RUN_INLINE_WORKER=false and run a dedicated worker
    service via the Procfile ``worker`` process type.
    """
    if not settings.RUN_INLINE_WORKER:
        return
    try:
        from apps.api.worker import run_worker_loop
        t = threading.Thread(target=run_worker_loop, name="inline-worker", daemon=True)
        t.start()
        print("[api] inline training worker started in background thread")
    except Exception as e:  # never let worker failure block API startup
        print(f"[api] inline worker failed to start: {e}")


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="AI Continual-Learning Platform",
                  description="Real trainable Transformer LM platform with continual "
                              "learning, model versioning, evaluation, and RAG.",
                  version="1.0.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(auth_router.router)
    app.include_router(datasets_router.router)
    app.include_router(tokenizers_router.router)
    app.include_router(training_router.router)
    app.include_router(models_router.router)
    app.include_router(evaluations_router.router)
    app.include_router(memory_router.router)
    app.include_router(inference_router.router)
    app.include_router(chat_router.router)
    app.include_router(dashboard_router.router)
    app.include_router(schedules_router.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "ai-platform-api"}

    # Serve built frontend (SPA) if present
    web_dist = settings.repo_root / "apps" / "web" / "dist"
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")
    else:
        @app.get("/")
        def root():
            return {"name": "AI Continual-Learning Platform",
                    "docs": "/docs",
                    "frontend": "not built (run: cd apps/web && npm install && npm run build)"}

    _maybe_start_inline_worker()
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.api.main:app", host=settings.HOST, port=settings.PORT, reload=False)
