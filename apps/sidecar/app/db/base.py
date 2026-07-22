"""SQLAlchemy engine, session, and declarative base.

SQLite specifics that matter here:
* ``PRAGMA foreign_keys=ON`` is set on every connection — SQLite ignores ``ON DELETE
  CASCADE`` otherwise, and the whole schema (docs/03) leans on cascade deletes.
* A fixed constraint-naming convention is attached to the metadata so Alembic
  autogenerate produces stable, human-readable names across revisions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def get_db() -> Session:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
