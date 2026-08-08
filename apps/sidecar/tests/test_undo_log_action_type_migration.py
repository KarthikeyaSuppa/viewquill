"""Tests for the `9694678ecc85` migration — widening `undo_log.action_type`'s CHECK
constraint to allow `'create_edge'`/`'delete_edge'`/`'update_edge'` alongside the
pre-existing `'delete_scene'`/`'merge_scenes'` values (canvas edge undo/redo coverage).

Mirrors tests/test_continuity_flags_migration.py's shape exactly (same widen-a-CHECK
precedent, `d25598084db3`): proves the migration round-trips (`upgrade` -> `downgrade`
to the prior revision -> `upgrade` head) without error or data loss for the two
pre-existing action types, and that the CHECK constraint itself actually enforces the
right value set on each side of the migration.

No Ollama/Groq call happens here; nothing in this file touches a network or model.
"""

from __future__ import annotations

import os
import tempfile

# Per tests/conftest.py: `QUILLNIGHT_DATA_DIR` only "wins" for whichever test module the
# collector imports first, since `app.config.get_settings()` is `@lru_cache`-d and
# `app.db.base` builds its engine once at import time. This module doesn't need its own
# database for that reason — like tests/test_continuity_flags_migration.py, it just calls
# `run_migrations()` (idempotent — no-op once already at head) against whatever engine the
# session already has, and only touches the leaf `undo_log` table (nothing else in the
# schema has a foreign key into it besides `books`, which this test also creates fresh rows
# for), so it cannot disturb other modules' data.
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-undolog-actiontype-")
os.environ.setdefault("QUILLNIGHT_DATA_DIR", _TMP_DATA_DIR)
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.db.base import SessionLocal, engine  # noqa: E402
from app.db.migrate import make_alembic_config, run_migrations  # noqa: E402
from app.models.orm import Book, UndoLog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    run_migrations()


@pytest.fixture
def book_id() -> str:
    with SessionLocal() as db:
        book = Book(title="Undo Log Action Type Test Book", book_type="story_book")
        db.add(book)
        db.commit()
        return book.id


def _next_sequence(db) -> int:
    from app.services import undo_service

    return undo_service.next_sequence(db)


def _insert_undo_log(book_id: str, action_type: str) -> str:
    """Returns 'OK' or 'REJECTED' — never raises, mirrors the round-trip check style."""
    with SessionLocal() as db:
        try:
            db.add(
                UndoLog(
                    book_id=book_id,
                    action_type=action_type,
                    payload={"test": True},
                    sequence=_next_sequence(db),
                )
            )
            db.commit()
            return "OK"
        except IntegrityError:
            db.rollback()
            return "REJECTED"


def _current_action_type_check_sql() -> str:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='undo_log'")
        ).scalar_one()


# ── At head: the widened check accepts all five values ────────────────────────────────
def test_action_type_check_allows_all_five_values_at_head(book_id: str) -> None:
    assert _insert_undo_log(book_id, "delete_scene") == "OK"
    assert _insert_undo_log(book_id, "merge_scenes") == "OK"
    assert _insert_undo_log(book_id, "create_edge") == "OK"
    assert _insert_undo_log(book_id, "delete_edge") == "OK"
    assert _insert_undo_log(book_id, "update_edge") == "OK"


def test_action_type_check_still_rejects_bogus_values_at_head(book_id: str) -> None:
    assert _insert_undo_log(book_id, "bogus") == "REJECTED"


# ── Round-trip: downgrade to prior revision, then upgrade head, no error, no lost rows ──
def test_migration_round_trips_and_preserves_pre_existing_rows(book_id: str) -> None:
    cfg = make_alembic_config()

    assert _insert_undo_log(book_id, "create_edge") == "OK"
    assert _insert_undo_log(book_id, "merge_scenes") == "OK"

    with engine.connect() as conn:
        before_merge_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM undo_log "
                "WHERE book_id = :b AND action_type = 'merge_scenes'"
            ),
            {"b": book_id},
        ).scalar_one()

    # Target the explicit prior revision (this migration's own `down_revision`) rather than
    # the relative "-1", which would only mean "undo whichever migration is newest" once a
    # later phase stacks another migration on top — same fix already applied to
    # tests/test_auth_migration.py and tests/test_continuity_flags_migration.py.
    command.downgrade(cfg, "c4c1f0a29f3a")

    # Narrower check is back: 'create_edge' rows for this test are gone (documented in the
    # migration's downgrade — see its comment), 'merge_scenes' rows are untouched, and the
    # check itself now rejects 'create_edge' again.
    assert "IN ('delete_scene','merge_scenes')" in _current_action_type_check_sql()
    with engine.connect() as conn:
        remaining_create_edge = conn.execute(
            text(
                "SELECT COUNT(*) FROM undo_log "
                "WHERE book_id = :b AND action_type = 'create_edge'"
            ),
            {"b": book_id},
        ).scalar_one()
        after_merge_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM undo_log "
                "WHERE book_id = :b AND action_type = 'merge_scenes'"
            ),
            {"b": book_id},
        ).scalar_one()
    assert remaining_create_edge == 0
    assert after_merge_count == before_merge_count
    assert _insert_undo_log(book_id, "create_edge") == "REJECTED"

    command.upgrade(cfg, "head")

    # Widened check restored, cleanly, no error raised getting here.
    assert (
        "IN ('delete_scene','merge_scenes','create_edge','delete_edge','update_edge')"
        in _current_action_type_check_sql()
    )
    assert _insert_undo_log(book_id, "create_edge") == "OK"
    with engine.connect() as conn:
        final_merge_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM undo_log "
                "WHERE book_id = :b AND action_type = 'merge_scenes'"
            ),
            {"b": book_id},
        ).scalar_one()
    assert final_merge_count == before_merge_count
