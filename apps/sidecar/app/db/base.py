"""SQLAlchemy engine, session, and declarative base.

SQLite specifics that matter here:
* ``PRAGMA foreign_keys=ON`` is set on every connection — SQLite ignores ``ON DELETE
  CASCADE`` otherwise, and the whole schema (docs/03) leans on cascade deletes.
* A fixed constraint-naming convention is attached to the metadata so Alembic
  autogenerate produces stable, human-readable names across revisions.
* The ``sqlite-vec`` extension (``vec0`` virtual tables, Phase 10 semantic layer —
  docs/11-AI-INTELLIGENCE.md §2) is a loadable SQLite extension, not a Python
  driver feature — every connection has to load it explicitly via
  ``enable_load_extension``/``load_extension`` before it can see ``vec0`` tables,
  or queries against ``embeddings`` silently fail with "no such module: vec0".
  Alembic's own migration runner (``app/db/migrations/env.py``) opens a separate
  engine, so its virtual-table migration also loads the extension itself.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlite_vec
from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

# Stable names for indexes/constraints so migrations stay clean and reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def new_uuid() -> str:
    """Primary-key default. UUIDs (not autoincrement) let `.quillproj` import merge by
    stable ID without collisions — see docs/03-DATA-MODEL.md and docs/05."""
    return str(uuid.uuid4())


def utcnow_iso() -> str:
    """Timestamps are stored as ISO-8601 UTC text (the schema uses TEXT columns)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


_settings = get_settings()
_settings.ensure_dirs()

engine: Engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False},  # FastAPI uses a threadpool for sync routes
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(engine, "connect")
def _enable_sqlite_fks(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")  # better concurrency for the local single-user app
    cursor.close()


@event.listens_for(engine, "connect")
def _load_sqlite_vec(dbapi_connection, _connection_record) -> None:
    """Loads the ``sqlite-vec`` extension so ``vec0`` virtual tables (the ``embeddings``
    table, Phase 10) are queryable on this connection. ``enable_load_extension`` is
    flipped back off immediately after — loading is a one-time per-connection setup
    step, not something arbitrary query text should ever be able to trigger again."""
    dbapi_connection.enable_load_extension(True)
    try:
        sqlite_vec.load(dbapi_connection)
    finally:
        dbapi_connection.enable_load_extension(False)


def get_db() -> Session:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
