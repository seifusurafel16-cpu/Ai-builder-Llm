"""Application configuration (env-driven, with sane dev defaults).

Defaults are chosen so the platform runs with zero external services:
SQLite file DB, local filesystem object storage, in-process + DB-polling worker.
Switch DATABASE_URL to a PostgreSQL DSN for production (Railway provides one).

Railway-specific behaviour:
- ``PORT`` is honoured for the HTTP listener (Railway injects it).
- The Railway-provided ``DATABASE_URL`` (``postgresql://``) is normalized to the
  SQLAlchemy ``postgresql+psycopg2://`` dialect automatically.
- Storage directories default to ``/data`` when a Railway volume is mounted there,
  but any path can be set via ``STORAGE_DIR`` etc.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _normalize_db_url(url: str) -> str:
    """Normalize a DATABASE_URL so SQLAlchemy can use it.

    Railway/Heroku-style ``postgresql://`` (and ``postgres://``) URLs are rewritten
    to ``postgresql+psycopg2://`` (the SQLAlchemy dialect for psycopg2). SQLite and
    already-qualified dialect URLs are returned unchanged.
    """
    if not url:
        return url
    if url.startswith("sqlite"):
        return url
    if "+" in url.split("://", 1)[0]:
        return url  # already qualified, e.g. postgresql+psycopg2://
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


class Settings:
    # --- HTTP (Railway injects PORT) ---
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")

    # --- Storage ---
    # Default to /data when present (Railway volume mount), else repo-local ./data.
    _default_data = "/data" if Path("/data").exists() else str(REPO_ROOT / "data")
    DATABASE_URL: str = _normalize_db_url(
        os.getenv("DATABASE_URL", f"sqlite:///{_default_data}/ai_platform.db")
    )
    STORAGE_DIR: Path = Path(os.getenv("STORAGE_DIR", _default_data + "/storage"))
    CHECKPOINT_DIR: Path = Path(os.getenv("CHECKPOINT_DIR", _default_data + "/checkpoints"))
    TOKENIZER_DIR: Path = Path(os.getenv("TOKENIZER_DIR", _default_data + "/tokenizers"))
    LOG_DIR: Path = Path(os.getenv("LOG_DIR", _default_data + "/logs"))

    # --- Security ---
    # Generate an ephemeral key if none is set, so the app still boots. In production
    # (Railway) you MUST set SECRET_KEY to a stable value or sessions invalidate on redeploy.
    SECRET_KEY: str = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "168"))
    # bcrypt handled by passlib if present, else sha256+salt fallback
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))  # 200MB
    RATE_LIMIT_PER_MIN: int = int(os.getenv("RATE_LIMIT_PER_MIN", "120"))

    # --- Training defaults ---
    DEFAULT_DEVICE: str = os.getenv("DEFAULT_DEVICE", "auto")  # auto|cpu|gpu
    WORKER_POLL_SECONDS: float = float(os.getenv("WORKER_POLL_SECONDS", "1.0"))
    SSE_HEARTBEAT_SECONDS: float = float(os.getenv("SSE_HEARTBEAT_SECONDS", "15"))

    # --- Worker ---
    # When true, the API process also runs the training worker in a background thread.
    # This enables a single-service Railway deployment. Set false to run a dedicated
    # worker process (see Procfile).
    RUN_INLINE_WORKER: bool = os.getenv("RUN_INLINE_WORKER", "true").lower() in ("1", "true", "yes")

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def is_production(self) -> bool:
        return not self.DATABASE_URL.startswith("sqlite")

    def ensure_dirs(self) -> None:
        # Ensure the base data directory exists (also used by the default SQLite path).
        for d in (Path(self.STORAGE_DIR).parent, self.STORAGE_DIR, self.CHECKPOINT_DIR,
                  self.TOKENIZER_DIR, self.LOG_DIR):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError:
                # Read-only filesystem or permission issue: skip (env misconfigured).
                pass


settings = Settings()
settings.ensure_dirs()
