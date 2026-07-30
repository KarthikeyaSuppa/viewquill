"""Search index maintenance — keeps `search_fts`/`embeddings` in sync with Scene/CodexEntry
rows (Phase 10 task 3, PHASE10.md, docs/11-AI-INTELLIGENCE.md §2).

This is the ONLY module that writes to `search_fts`/`embeddings` — scene_service.py and
codex_service.py both call `upsert_entity`/`delete_entity` here from their create/update/
delete paths rather than embedding the raw SQL themselves, so both entity types share one
upsert/delete dialect for the polymorphic `entity_type`/`entity_id` shape established by
the `e51867fcdc66` migration (same convention as `EntityImage` in app/models/orm.py).

Neither virtual table is modeled in app/models/orm.py (FTS5/vec0 have no SQLAlchemy ORM
support — see that migration's docstring), so every read/write here goes through raw
``sqlalchemy.text()`` SQL against app.db.base's shared engine (already wired to load the
``sqlite-vec`` extension on connect, see app/db/base.py's ``_load_sqlite_vec`` listener).

## Derived, rebuildable data — never blocks the real save

Embeddings/search-index rows are explicitly derived/rebuildable data (never included in
`.quillproj` export bundles, per docs/05/docs/11 §2), not source-of-truth like the Scene/
CodexEntry rows they're indexing. `upsert_entity`/`delete_entity` therefore never raise —
any failure (a bad embed call, a locked db, etc.) is logged and swallowed so it can never
roll back or block the Scene/CodexEntry save/delete that triggered it. Worst case a row is
temporarily missing/stale in search until the next successful save or a
``POST /search/backfill`` run (`backfill_all` below), which re-derives every row from
`scenes`/`codex_entries` from scratch.

## DELETE-then-INSERT, not UPDATE

FTS5 tables support UPDATE in general, but only when the table has an explicit rowid/unique
key to target — this schema's `search_fts` (entity_type/entity_id UNINDEXED, no declared
key) doesn't give us one to UPDATE against cleanly. `vec0` tables are more restrictive still:
sqlite-vec's vec0 module only supports INSERT/DELETE, not UPDATE, at all. So both tables are
kept in sync the same way, matched on (entity_type, entity_id): delete any existing row for
that entity, then insert the fresh one. This also naturally guarantees at most one row per
entity ever exists in either table — no duplicate/stale rows after repeated updates.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.base import engine
from app.services.embedding_service import embed, pack_embedding

logger = logging.getLogger("quillnight.search_index")


def upsert_entity(entity_type: str, entity_id: str, title: str, body: str | None) -> None:
    """Re-index one (entity_type, entity_id) row in both `search_fts` and `embeddings`.

    ``title``/``body`` are the entity's two free-text fields (Scene: title/description;
    CodexEntry: name/summary) — per docs/11 §2's "embed per entity (title + body), no
    arbitrary splitting" rule, they're joined into a single unit for the embedding call,
    while `search_fts` keeps them in its own title/body columns for keyword search.

    Never raises — see module docstring.
    """
    body = body or ""
    try:
        joined_text = f"{title}\n\n{body}" if body else title
        packed = pack_embedding(embed(joined_text))

        with engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM search_fts WHERE entity_type = :entity_type "
                    "AND entity_id = :entity_id"
                ),
                {"entity_type": entity_type, "entity_id": entity_id},
            )
            conn.execute(
                text(
                    "INSERT INTO search_fts(entity_type, entity_id, title, body) "
                    "VALUES (:entity_type, :entity_id, :title, :body)"
                ),
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "title": title,
                    "body": body,
                },
            )
            conn.execute(
                text(
                    "DELETE FROM embeddings WHERE entity_type = :entity_type "
                    "AND entity_id = :entity_id"
                ),
                {"entity_type": entity_type, "entity_id": entity_id},
            )
            conn.execute(
                text(
                    "INSERT INTO embeddings(entity_type, entity_id, embedding) "
                    "VALUES (:entity_type, :entity_id, :embedding)"
                ),
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "embedding": packed,
                },
            )
    except Exception:  # noqa: BLE001 — derived data, must never block the caller's save
        logger.exception(
            "search index upsert failed for %s/%s; continuing without it (rebuildable via "
            "POST /search/backfill)",
            entity_type,
            entity_id,
        )


def delete_entity(entity_type: str, entity_id: str) -> None:
    """Remove one (entity_type, entity_id) row from both `search_fts` and `embeddings`.

    Never raises — same reasoning as `upsert_entity`: index cleanup must never block the
    actual Scene/CodexEntry deletion that triggered it.
    """
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM search_fts WHERE entity_type = :entity_type "
                    "AND entity_id = :entity_id"
                ),
                {"entity_type": entity_type, "entity_id": entity_id},
            )
            conn.execute(
                text(
                    "DELETE FROM embeddings WHERE entity_type = :entity_type "
                    "AND entity_id = :entity_id"
                ),
                {"entity_type": entity_type, "entity_id": entity_id},
            )
    except Exception:  # noqa: BLE001 — derived data, must never block the caller's delete
        logger.exception("search index delete failed for %s/%s", entity_type, entity_id)


def backfill_all(db: Session) -> dict[str, int]:
    """Re-index every existing Scene and CodexEntry row (PHASE10.md task 3's bulk backfill —
    the one-time catch-up for rows that predate the embed-on-save hooks in scene_service.py/
    codex_service.py, e.g. rows created before this phase landed, or after a future model
    swap). Safe to re-run any time: `upsert_entity` is idempotent (delete-then-insert), so
    backfilling an already-indexed row just re-derives the same embedding.

    Returns ``{"scenes_indexed": N, "codex_entries_indexed": M}``.
    """
    from app.models.orm import CodexEntry, Scene

    scenes = list(db.execute(select(Scene)).scalars())
    for scene in scenes:
        upsert_entity("scene", scene.id, scene.title, scene.description)

    entries = list(db.execute(select(CodexEntry)).scalars())
    for entry in entries:
        upsert_entity("codex_entry", entry.id, entry.name, entry.summary)

    return {"scenes_indexed": len(scenes), "codex_entries_indexed": len(entries)}
