"""Tests for `app/services/notes_service.py` (LAN Notes, last-write-wins).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app.db.base)
so a fresh SQLite DB is migrated to head for this test run only — never touches a real
app-data directory. Same pattern as tests/test_embedding_service.py: run_migrations() is
idempotent, so calling it here doesn't care whether some other test module already "won"
the module-level engine build (see tests/conftest.py's module docstring).
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-notesservice-")
os.environ.setdefault("QUILLNIGHT_DATA_DIR", _TMP_DATA_DIR)

import pytest  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.db.migrate import run_migrations  # noqa: E402
from app.models.schemas import NoteWrite  # noqa: E402
from app.services import notes_service  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    run_migrations()


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def test_get_note_auto_creates_empty_row(db) -> None:
    note = notes_service.get_note(db, "lan-test-a")
    assert note.channel == "lan-test-a"
    assert note.content == ""
    assert note.updated_at == 0
    assert note.updated_by == "desktop-local"
    assert note.rev == 0


def test_apply_note_with_newer_clock_updates_and_bumps_rev(db) -> None:
    channel = "lan-test-b"
    notes_service.get_note(db, channel)  # seed the empty row

    result = notes_service.apply_note(
        db,
        channel,
        NoteWrite(content="hello from device A", updated_at=1000, updated_by="device-a"),
    )
    assert result.content == "hello from device A"
    assert result.updated_at == 1000
    assert result.updated_by == "device-a"
    assert result.rev == 1

    # A strictly newer write applies again and bumps rev further.
    result2 = notes_service.apply_note(
        db,
        channel,
        NoteWrite(content="hello from device B", updated_at=2000, updated_by="device-b"),
    )
    assert result2.content == "hello from device B"
    assert result2.updated_at == 2000
    assert result2.updated_by == "device-b"
    assert result2.rev == 2


def test_apply_note_with_older_or_equal_clock_is_rejected(db) -> None:
    channel = "lan-test-c"
    notes_service.apply_note(
        db,
        channel,
        NoteWrite(content="current content", updated_at=5000, updated_by="device-a"),
    )

    # Older clock: rejected, row unchanged.
    older = notes_service.apply_note(
        db,
        channel,
        NoteWrite(content="stale write", updated_at=4000, updated_by="device-b"),
    )
    assert older.content == "current content"
    assert older.updated_at == 5000
    assert older.updated_by == "device-a"
    assert older.rev == 1

    # Equal clock: also rejected (strictly newer required), row unchanged.
    equal = notes_service.apply_note(
        db,
        channel,
        NoteWrite(content="tied write", updated_at=5000, updated_by="device-c"),
    )
    assert equal.content == "current content"
    assert equal.updated_at == 5000
    assert equal.updated_by == "device-a"
    assert equal.rev == 1
