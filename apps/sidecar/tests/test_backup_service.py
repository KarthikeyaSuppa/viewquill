"""Tests for app/services/backup_service.py (Phase 7 task 8 — local DB backup rotation).

Each test gets its own throwaway ``QUILLNIGHT_DATA_DIR`` via ``tmp_path`` + a
``get_settings.cache_clear()`` around it, so this module never touches the shared
test-session database other modules rely on (see tests/conftest.py's module docstring for
why that matters). ``run_rotation``'s ``now`` param lets these tests use deterministic,
distinct timestamps instead of real sleeps.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config import get_settings
from app.services import backup_service
from app.services.backup_service import BackupError


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("QUILLNIGHT_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    cfg = get_settings()
    yield cfg
    get_settings.cache_clear()


def _init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO marker (value) VALUES ('original')")
        conn.commit()
    finally:
        conn.close()


def test_run_rotation_keeps_only_newest_seven(settings) -> None:
    _init_db(settings.db_path)
    base = datetime(2026, 1, 1, tzinfo=UTC)

    paths = [
        backup_service.run_rotation(keep=7, now=base + timedelta(minutes=i)) for i in range(9)
    ]

    backups_dir = settings.data_dir / "backups"
    files = sorted(backups_dir.glob("quillnight-*.sqlite"))
    assert len(files) == 7
    # The newest snapshot (last call) must be among the retained files.
    assert files[-1].name == Path(paths[-1]).name


def test_list_backups_returns_newest_first(settings) -> None:
    _init_db(settings.db_path)
    base = datetime(2026, 2, 1, tzinfo=UTC)

    for i in range(3):
        backup_service.run_rotation(keep=10, now=base + timedelta(minutes=i))

    items = backup_service.list_backups()
    assert len(items) == 3
    names = [item["name"] for item in items]
    assert names == sorted(names, reverse=True)
    for item in items:
        assert item["size_bytes"] > 0
        assert "created_at" in item


@pytest.mark.parametrize("bad_name", ["../evil.sqlite", "sub/evil.sqlite", "..\\evil.sqlite", ""])
def test_restore_backup_rejects_path_traversal(settings, bad_name: str) -> None:
    _init_db(settings.db_path)
    with pytest.raises(BackupError):
        backup_service.restore_backup(bad_name)


def test_restore_backup_rejects_missing_file(settings) -> None:
    _init_db(settings.db_path)
    with pytest.raises(BackupError):
        backup_service.restore_backup("quillnight-2026-01-01T00-00-00+00-00.sqlite")


def test_restore_backup_replaces_db_and_it_still_opens(settings) -> None:
    _init_db(settings.db_path)
    snapshot_path = backup_service.run_rotation(
        keep=10, now=datetime(2026, 3, 1, tzinfo=UTC)
    )

    # Mutate the live db after the snapshot was taken.
    conn = sqlite3.connect(settings.db_path)
    try:
        conn.execute("INSERT INTO marker (value) VALUES ('changed')")
        conn.commit()
    finally:
        conn.close()

    name = Path(snapshot_path).name
    backup_service.restore_backup(name)

    conn = sqlite3.connect(settings.db_path)
    try:
        rows = conn.execute("SELECT value FROM marker ORDER BY id").fetchall()
    finally:
        conn.close()
    assert rows == [("original",)]

    # restore_backup must also have taken its own pre-restore safety snapshot.
    backups_dir = settings.data_dir / "backups"
    assert len(list(backups_dir.glob("quillnight-*.sqlite"))) >= 2


def test_restore_backup_removes_stale_wal_shm_sidecars(settings) -> None:
    """The app runs SQLite in WAL mode (app/db/base.py). Stale `-wal`/`-shm` sidecars left
    over from the live db must never survive a restore -- otherwise SQLite could replay
    old WAL frames against the freshly-restored main file and corrupt it."""
    _init_db(settings.db_path)
    snapshot_path = backup_service.run_rotation(
        keep=10, now=datetime(2026, 4, 1, tzinfo=UTC)
    )

    wal_path = Path(str(settings.db_path) + "-wal")
    shm_path = Path(str(settings.db_path) + "-shm")
    wal_path.write_bytes(b"stale-wal-frames")
    shm_path.write_bytes(b"stale-shm-index")
    assert wal_path.exists()
    assert shm_path.exists()

    backup_service.restore_backup(Path(snapshot_path).name)

    assert not wal_path.exists()
    assert not shm_path.exists()
