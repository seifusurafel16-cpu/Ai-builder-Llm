"""Database engine + session (SQLAlchemy 2.0 style).

Defaults to SQLite for zero-dependency dev. To run on PostgreSQL set
DATABASE_URL=postgresql+psycopg://user:pass@host/db (install psycopg). pgvector
optional for vector embeddings — schema degrades gracefully if not installed.

Railway: the DATABASE_URL is normalized in config.py; the pgvector extension is
created on startup when running on PostgreSQL (no-op if already present / unsupported).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from .config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# pool_pre_ping avoids stale connections after a Postgres connection is reaped.
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    future=True,
    pool_pre_ping=not settings.DATABASE_URL.startswith("sqlite"),
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _record):  # noqa: D401
    if settings.DATABASE_URL.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def _ensure_pgvector() -> None:
    """Create the pgvector extension on PostgreSQL if available.

    No-op on SQLite or if the extension is not installed on the server. Vector
    search falls back to exact cosine over stored arrays when pgvector is absent.
    """
    if settings.DATABASE_URL.startswith("sqlite"):
        return
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    except Exception:
        # Extension not available or no permission — schema degrades gracefully.
        pass


def init_db() -> None:
    """Create all tables (idempotent). Called on app + worker startup."""
    from . import models  # noqa: F401  ensure models imported
    _ensure_pgvector()
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
