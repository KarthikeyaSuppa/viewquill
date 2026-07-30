"""Tests for the `e51867fcdc66` migration — the Phase 10 semantic-layer schema
(docs/11-AI-INTELLIGENCE.md §2): the `search_fts` FTS5 virtual table and the `embeddings`
`sqlite-vec` `vec0` virtual table, both scoped polymorphically over
`entity_type IN ('scene', 'codex_entry')` + `entity_id` (same shape convention as
`EntityImage` in app/models/orm.py).

No Ollama/Groq call happens here; nothing in this file touches a network or model — rows
are inserted directly with synthetic text/embeddings, proving the schema itself (and the
`sqlite-vec` extension-loading wiring in app/db/base.py + app/db/migrations/env.py) works,
independent of the not-yet-built embedding service.
"""

from __future__ import annotations

import os
import struct
import tempfile

# Per tests/conftest.py: `QUILLNIGHT_DATA_DIR` only "wins" for whichever test module the
# collector imports first. This module doesn't need its own database for that reason —
# like tests/test_continuity_flags_migration.py, it just calls `run_migrations()`
# (idempotent) against whatever engine the session already has, and only touches the two
# new virtual tables (nothing else in the schema references them), so it cannot disturb
# other modules' data.
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-semanticsearch-")
os.environ.setdefault("QUILLNIGHT_DATA_DIR", _TMP_DATA_DIR)
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import engine  # noqa: E402
from app.db.migrate import make_alembic_config, run_migrations  # noqa: E402

EMBEDDING_DIM = 1024


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    run_migrations()


def _fake_embedding(seed: float) -> bytes:
    """A deterministic synthetic 1024-dim vector — no model involved, just proves the
    vec0 column round-trips float32 blobs and KNN search works against them."""
    values = [seed] + [0.0] * (EMBEDDING_DIM - 1)
    return struct.pack(f"<{EMBEDDING_DIM}f", *values)


def _table_names() -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    return {row[0] for row in rows}


# ── Both virtual tables exist after migrating to head ─────────────────────────
def test_both_virtual_tables_exist_at_head() -> None:
    names = _table_names()
    assert "search_fts" in names
    assert "embeddings" in names


# ── search_fts: insert + keyword search round-trip, scoped by entity ──────────
def test_search_fts_insert_and_match_round_trips_scoped_by_entity() -> None:
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO search_fts(entity_type, entity_id, title, body) "
                "VALUES ('scene', 'scene-1', 'The Ashgate Betrayal', "
                "'Elyndra confronts the traitor at the Ashgate.')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO search_fts(entity_type, entity_id, title, body) "
                "VALUES ('codex_entry', 'codex-1', 'Elyndra', "
                "'A former knight of the Ashgate order, now exiled.')"
            )
        )
        conn.commit()

        rows = conn.execute(
            text(
                "SELECT entity_type, entity_id FROM search_fts "
                "WHERE search_fts MATCH 'Ashgate' ORDER BY entity_id"
            )
        ).fetchall()

    assert {(r.entity_type, r.entity_id) for r in rows} == {
        ("scene", "scene-1"),
        ("codex_entry", "codex-1"),
    }

    with engine.connect() as conn:
        codex_only = conn.execute(
            text(
                "SELECT entity_id FROM search_fts "
                "WHERE search_fts MATCH 'knight' AND entity_type = 'codex_entry'"
            )
        ).fetchall()
    assert [r.entity_id for r in codex_only] == ["codex-1"]


# ── embeddings (vec0): insert 1024-dim vectors + KNN round-trip, scoped by entity ──
def test_embeddings_insert_and_knn_search_round_trips_scoped_by_entity() -> None:
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO embeddings(entity_type, entity_id, embedding) "
                "VALUES ('scene', 'scene-1', :emb)"
            ),
            {"emb": _fake_embedding(1.0)},
        )
        conn.execute(
            text(
                "INSERT INTO embeddings(entity_type, entity_id, embedding) "
                "VALUES ('codex_entry', 'codex-1', :emb)"
            ),
            {"emb": _fake_embedding(0.0)},
        )
        conn.commit()

        # KNN: nearest neighbor to a query vector identical to scene-1's embedding.
        rows = conn.execute(
            text(
                "SELECT entity_type, entity_id, distance FROM embeddings "
                "WHERE embedding MATCH :q AND k = 2 ORDER BY distance"
            ),
            {"q": _fake_embedding(1.0)},
        ).fetchall()

    assert len(rows) == 2
    assert rows[0].entity_type == "scene"
    assert rows[0].entity_id == "scene-1"
    assert rows[0].distance == pytest.approx(0.0, abs=1e-6)
    # The mismatched codex embedding is farther away, not equally close.
    assert rows[1].distance > rows[0].distance


# ── Round-trip: downgrade below this revision, then upgrade head, no error ─────
def test_migration_round_trips_downgrade_then_upgrade() -> None:
    cfg = make_alembic_config()

    # Alembic's migration runner (app/db/migrations/env.py) opens its own engine, separate
    # from this module's `engine` (app.db.base) — `engine.dispose()` after each alembic
    # command drops this module's pooled connections so the next read opens a fresh one
    # rather than a stale pre-migration snapshot from a connection checked out before the
    # DDL committed. Same known cross-module shared-database order-sensitivity as
    # tests/test_continuity_flags_migration.py's round-trip test (see tests/conftest.py's
    # module docstring) — not unique to this migration.
    command.downgrade(cfg, "d25598084db3")
    engine.dispose()
    names = _table_names()
    assert "search_fts" not in names
    assert "embeddings" not in names

    command.upgrade(cfg, "head")
    engine.dispose()
    names = _table_names()
    assert "search_fts" in names
    assert "embeddings" in names

    # Fresh (post-round-trip) tables are queryable, not left in some half-registered state.
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO search_fts(entity_type, entity_id, title, body) "
                "VALUES ('scene', 'post-roundtrip', 'Title', 'Body text')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO embeddings(entity_type, entity_id, embedding) "
                "VALUES ('scene', 'post-roundtrip', :emb)"
            ),
            {"emb": _fake_embedding(2.0)},
        )
        conn.commit()
        assert conn.execute(
            text("SELECT COUNT(*) FROM search_fts WHERE search_fts MATCH 'Title'")
        ).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM embeddings")).scalar_one() == 1
