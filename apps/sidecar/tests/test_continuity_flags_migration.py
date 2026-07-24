"""Tests for the `d25598084db3` migration — widening `continuity_flags.source`'s CHECK
constraint to allow `'deterministic'` (docs/11-AI-INTELLIGENCE.md §4: Tier-1 deterministic
continuity checks) alongside the pre-existing `'ai'`/`'manual'` values.

[SECURITY-REVIEW + MIGRATION]: this is the schema/constraint-change piece flagged for a
`reviewer` pass. It proves the migration round-trips (`upgrade` -> `downgrade -1` ->
`upgrade`) without error or data loss for `'ai'`/`'manual'` rows, and that the CHECK
constraint itself actually enforces the right value set on each side of the migration.

No Ollama/Groq call happens here; nothing in this file touches a network or model.
"""

from __future__ import annotations

import os
import tempfile

# Per tests/conftest.py: `QUILLNIGHT_DATA_DIR` only "wins" for whichever test module the
# collector imports first, since `app.config.get_settings()` is `@lru_cache`-d and
# `app.db.base` builds its engine once at import time. This module doesn't need its own
# database for that reason — like tests/test_prompt_builder.py, it just calls
# `run_migrations()` (idempotent — no-op once already at head) against whatever engine the
# session already has, and only touches the leaf `continuity_flags` table (nothing else in
# the schema has a foreign key into it), so it cannot disturb other modules' data.
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-continuityflags-")
os.environ.setdefault("QUILLNIGHT_DATA_DIR", _TMP_DATA_DIR)
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.db.base import SessionLocal, engine  # noqa: E402
from app.db.migrate import make_alembic_config, run_migrations  # noqa: E402
from app.models.orm import Book, ContinuityFlag  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    run_migrations()


@pytest.fixture
def book_id() -> str:
    with SessionLocal() as db:
        book = Book(title="Continuity Flags Test Book", book_type="story_book")
        db.add(book)
        db.commit()
        return book.id


def _insert_flag(book_id: str, source: str) -> str:
    """Returns 'OK' or 'REJECTED' — never raises, mirrors the round-trip check style."""
    with SessionLocal() as db:
        try:
            db.add(ContinuityFlag(book_id=book_id, description="test flag", source=source))
            db.commit()
            return "OK"
        except IntegrityError:
            db.rollback()
            return "REJECTED"


def _current_source_check_sql() -> str:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='continuity_flags'")
        ).scalar_one()


# ── At head: the widened check accepts all three values ───────────────────────
def test_source_check_allows_deterministic_ai_and_manual_at_head(book_id: str) -> None:
    assert _insert_flag(book_id, "deterministic") == "OK"
    assert _insert_flag(book_id, "ai") == "OK"
    assert _insert_flag(book_id, "manual") == "OK"


def test_source_check_still_rejects_bogus_values_at_head(book_id: str) -> None:
    assert _insert_flag(book_id, "bogus") == "REJECTED"


def test_other_continuity_flag_checks_survive_the_rebuild(book_id: str) -> None:
    """The batch rebuild must not have silently dropped flag_type/severity/status checks."""
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.add(
                ContinuityFlag(
                    book_id=book_id, description="x", source="ai", severity="not-a-real-severity"
                )
            )
            db.commit()


# ── Round-trip: downgrade -1, then upgrade head, no error, no lost 'ai'/'manual' rows ──
def test_migration_round_trips_and_preserves_non_deterministic_rows(book_id: str) -> None:
    cfg = make_alembic_config()

    assert _insert_flag(book_id, "deterministic") == "OK"
    assert _insert_flag(book_id, "manual") == "OK"

    with engine.connect() as conn:
        before_manual_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM continuity_flags "
                "WHERE book_id = :b AND source = 'manual'"
            ),
            {"b": book_id},
        ).scalar_one()

    # Target the explicit prior revision `21b2ddd10525` (this module's subject
    # `d25598084db3`'s down_revision) rather than the relative "-1", which only meant "undo
    # d25598084db3" while it was still head. Once a later phase stacks a new migration on
    # top, "-1" would instead undo whichever migration is newest — not what this test checks
    # (same fix already applied to tests/test_auth_migration.py).
    command.downgrade(cfg, "21b2ddd10525")

    # Narrower check is back: 'deterministic' rows for this test are gone (documented in the
    # migration's downgrade — see its comment), 'manual' rows are untouched, and the check
    # itself now rejects 'deterministic' again.
    assert "IN ('ai','manual')" in _current_source_check_sql()
    with engine.connect() as conn:
        remaining_deterministic = conn.execute(
            text(
                "SELECT COUNT(*) FROM continuity_flags "
                "WHERE book_id = :b AND source = 'deterministic'"
            ),
            {"b": book_id},
        ).scalar_one()
        after_manual_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM continuity_flags "
                "WHERE book_id = :b AND source = 'manual'"
            ),
            {"b": book_id},
        ).scalar_one()
    assert remaining_deterministic == 0
    assert after_manual_count == before_manual_count
    assert _insert_flag(book_id, "deterministic") == "REJECTED"

    command.upgrade(cfg, "head")

    # Widened check restored, cleanly, no error raised getting here.
    assert "IN ('deterministic','ai','manual')" in _current_source_check_sql()
    assert _insert_flag(book_id, "deterministic") == "OK"
    with engine.connect() as conn:
        final_manual_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM continuity_flags "
                "WHERE book_id = :b AND source = 'manual'"
            ),
            {"b": book_id},
        ).scalar_one()
    assert final_manual_count == before_manual_count
