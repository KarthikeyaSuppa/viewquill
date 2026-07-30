"""semantic search: fts5 + vec0 virtual tables

Phase 10 (semantic layer, docs/11-AI-INTELLIGENCE.md §2) adds two virtual tables for
hybrid (keyword + vector) search over Scene and CodexEntry text:

* ``search_fts`` — an FTS5 full-text index. One row per (entity_type, entity_id),
  ``title``/``body`` indexed. Scene rows are ``title``/``description``; CodexEntry rows
  are ``name``/``summary`` — the two free-text fields on each entity, per §2's
  "embed per entity (title + body), no arbitrary splitting" rule (the same rule applies
  here to keyword indexing, not just embeddings).
* ``embeddings`` — a ``sqlite-vec`` ``vec0`` table holding one 1024-dim
  ``qwen3-embedding:0.6b`` embedding per (entity_type, entity_id) pair (stub embeddings
  behind ``QUILLNIGHT_LLM_STUB`` until Phase 10's embedding service lands — see PHASE10.md).

Both tables are polymorphic over ``entity_type IN ('scene', 'codex_entry')`` +
``entity_id``, the same shape convention as ``EntityImage`` in app/models/orm.py.
Neither is modeled in app/models/orm.py (see that file's module docstring) — SQLAlchemy
Core has no ORM mapping for FTS5/vec0 virtual tables, so they're managed here via raw
``op.execute()`` SQL, the standard Alembic pattern for virtual tables.

Both are additive-only, derived/rebuildable infrastructure with no existing data to
migrate (empty on every current database): the FTS5 table is populated by an
embed-on-save trigger added in a later Phase 10 task, and embeddings are explicitly
never included in `.quillproj` export bundles (docs/05, docs/11 §2) — they can be
regenerated from ``search_fts``'s source rows (``scenes``/``codex_entries``) at any time
via a bulk backfill. downgrade() simply drops both tables.

``vec0`` is a loadable SQLite extension (``sqlite-vec``), not built into SQLite the way
FTS5 is — Alembic's migration runner opens its own engine (app/db/migrations/env.py),
separate from app/db/base.py's, so this migration loads the extension onto its own
connection before touching ``embeddings``. (app/db/base.py loads it on every
application connection via a ``connect`` event listener, so runtime queries work too.)

Revision ID: e51867fcdc66
Revises: d25598084db3
Create Date: 2026-07-30
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlite_vec
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e51867fcdc66'
down_revision: str | None = 'd25598084db3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 1024-dim per docs/11-AI-INTELLIGENCE.md §2 (`qwen3-embedding:0.6b`, MRL-truncatable but
# stored at full width here — truncation, if ever adopted, is a later migration).
EMBEDDING_DIM = 1024


def _load_vec_extension() -> None:
    """Loads sqlite-vec onto *this migration's* raw DBAPI connection so the ``vec0``
    module is registered before CREATE/DROP VIRTUAL TABLE statements run against it."""
    raw_conn = op.get_bind().connection
    raw_conn.enable_load_extension(True)
    try:
        sqlite_vec.load(raw_conn)
    finally:
        raw_conn.enable_load_extension(False)


def upgrade() -> None:
    # FTS5 is built into SQLite itself — no extension load needed.
    op.execute(
        sa.text(
            "CREATE VIRTUAL TABLE search_fts USING fts5("
            "entity_type UNINDEXED, "
            "entity_id UNINDEXED, "
            "title, "
            "body"
            ")"
        )
    )

    _load_vec_extension()
    op.execute(
        sa.text(
            "CREATE VIRTUAL TABLE embeddings USING vec0("
            "entity_type text, "
            "entity_id text, "
            f"embedding float[{EMBEDDING_DIM}]"
            ")"
        )
    )


def downgrade() -> None:
    _load_vec_extension()
    op.execute(sa.text("DROP TABLE IF EXISTS embeddings"))
    op.execute(sa.text("DROP TABLE IF EXISTS search_fts"))
