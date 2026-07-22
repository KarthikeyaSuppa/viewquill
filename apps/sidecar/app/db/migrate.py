"""Programmatic Alembic upgrade, run at sidecar startup.

Building the Alembic Config in code (rather than relying on CWD + alembic.ini discovery)
means migrations run correctly whether launched via `uvicorn`, pytest, or the packaged
PyInstaller binary — where there is no shell CWD to depend on.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import get_settings

_SIDECAR_ROOT = Path(__file__).resolve().parents[2]  # apps/sidecar
_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def make_alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def run_migrations() -> None:
    """Bring the database up to head. No-op if already current."""
    get_settings().ensure_dirs()
    command.upgrade(make_alembic_config(), "head")
