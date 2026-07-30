"""Codex CRUD plus its links to Scenes and Books (docs/01-PRODUCT-VISION.md,
docs/03-DATA-MODEL.md `codex_entries` / `codex_scene_links` / `book_codex_links`,
docs/06 Phase 2 tasks B1/B2).

Codex entries are canonical and shared across Books (like Scenes) — this module manages
the entry row itself plus its link tables. It never creates/deletes Scene or Book rows.

DATA-SENSITIVE: ``unlink_scene``/``unlink_book`` delete ONLY the join row — the Codex entry
and the Scene/Book it was linked to both survive untouched.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.base import new_uuid, utcnow_iso
from app.models.orm import (
    Book,
    BookCodexLink,
    CodexArcState,
    CodexEntry,
    CodexRelationship,
    CodexSceneLink,
)
from app.services import search_index_service


def create_entry(
    db: Session,
    *,
    entry_type: str,
    name: str,
    summary: str | None = None,
    custom_fields: dict[str, Any] | None = None,
) -> CodexEntry:
    entry = CodexEntry(
        id=new_uuid(),
        entry_type=entry_type,
        name=name,
        summary=summary,
        custom_fields=custom_fields,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    # Embed-on-save (Phase 10 task 3, PHASE10.md) — derived data, never blocks this save;
    # see search_index_service's module docstring.
    search_index_service.upsert_entity("codex_entry", entry.id, entry.name, entry.summary)
    return entry


def list_entries(db: Session, entry_type: str | None = None) -> list[CodexEntry]:
    stmt = select(CodexEntry).order_by(CodexEntry.updated_at.desc())
    if entry_type is not None:
        stmt = stmt.where(CodexEntry.entry_type == entry_type)
    return list(db.execute(stmt).scalars())


def get_entry(db: Session, entry_id: str) -> CodexEntry | None:
    return db.get(CodexEntry, entry_id)


def update_entry(db: Session, entry_id: str, values: dict[str, Any]) -> CodexEntry | None:
    """Partial update — only keys present in ``values`` are applied."""
    entry = db.get(CodexEntry, entry_id)
    if entry is None:
        return None
    for key, value in values.items():
        setattr(entry, key, value)
    # `updated_at` has an `onupdate` default, but that only fires on a flush that detects a
    # change; touch it explicitly so a no-op-looking patch still bumps the timestamp.
    entry.updated_at = utcnow_iso()
    db.commit()
    db.refresh(entry)
    # Embed-on-save (Phase 10 task 3) — re-index unconditionally so the search index never
    # drifts from the saved row, even on a patch that didn't touch name/summary.
    search_index_service.upsert_entity("codex_entry", entry.id, entry.name, entry.summary)
    return entry


def delete_entry(db: Session, entry_id: str) -> bool:
    entry = db.get(CodexEntry, entry_id)
    if entry is None:
        return False
    db.delete(entry)
    db.commit()
    # Virtual tables (search_fts/embeddings) aren't real FK targets, so there's no DB-level
    # cascade delete for them — clean up the index row explicitly (Phase 10 task 3).
    search_index_service.delete_entity("codex_entry", entry_id)
    return True


# ── Scene links ────────────────────────────────────────────────────────────────


def _get_scene_link(db: Session, entry_id: str, scene_id: str) -> CodexSceneLink | None:
    return db.execute(
        select(CodexSceneLink).where(
            CodexSceneLink.codex_entry_id == entry_id, CodexSceneLink.scene_id == scene_id
        )
    ).scalar_one_or_none()


def link_scene(db: Session, entry_id: str, scene_id: str) -> CodexSceneLink:
    """Link an existing Codex entry to an existing Scene.

    ``CodexSceneLink`` has a UNIQUE(codex_entry_id, scene_id) constraint — if the link
    already exists, it's returned unchanged rather than creating a duplicate row.
    """
    existing = _get_scene_link(db, entry_id, scene_id)
    if existing is not None:
        return existing
    link = CodexSceneLink(id=new_uuid(), codex_entry_id=entry_id, scene_id=scene_id)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def unlink_scene(db: Session, entry_id: str, scene_id: str) -> bool:
    """Unlink a Codex entry from a Scene.

    DATA-SENSITIVE: deletes ONLY the ``CodexSceneLink`` row. The Codex entry and the
    Scene row both survive untouched — either may still be linked elsewhere.
    """
    link = _get_scene_link(db, entry_id, scene_id)
    if link is None:
        return False
    db.delete(link)
    db.commit()
    return True


def list_entries_for_scene(db: Session, scene_id: str) -> list[CodexEntry]:
    return list(
        db.execute(
            select(CodexEntry)
            .join(CodexSceneLink, CodexSceneLink.codex_entry_id == CodexEntry.id)
            .where(CodexSceneLink.scene_id == scene_id)
        ).scalars()
    )


# ── Book links ─────────────────────────────────────────────────────────────────


def _get_book_link(db: Session, entry_id: str, book_id: str) -> BookCodexLink | None:
    return db.execute(
        select(BookCodexLink).where(
            BookCodexLink.codex_entry_id == entry_id, BookCodexLink.book_id == book_id
        )
    ).scalar_one_or_none()


def link_book(db: Session, entry_id: str, book_id: str) -> BookCodexLink:
    """Link an existing Codex entry to an existing Book.

    ``BookCodexLink`` has a UNIQUE(book_id, codex_entry_id) constraint — if the link
    already exists, it's returned unchanged rather than creating a duplicate row.
    """
    existing = _get_book_link(db, entry_id, book_id)
    if existing is not None:
        return existing
    link = BookCodexLink(id=new_uuid(), book_id=book_id, codex_entry_id=entry_id)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def unlink_book(db: Session, entry_id: str, book_id: str) -> bool:
    """Unlink a Codex entry from a Book.

    DATA-SENSITIVE: deletes ONLY the ``BookCodexLink`` row. The Codex entry and the Book
    row both survive untouched.
    """
    link = _get_book_link(db, entry_id, book_id)
    if link is None:
        return False
    db.delete(link)
    db.commit()
    return True


# ── Entity relationships (Codex entry <-> Codex entry; docs/03-DATA-MODEL.md
# `codex_relationships`; docs/06 Phase 3 task BE-1) ─────────────────────────────


def create_relationship(
    db: Session,
    from_entry_id: str,
    to_entry_id: str,
    relationship_type: str,
    description: str | None = None,
) -> CodexRelationship:
    """Create a directed relationship between two Codex entries.

    Raises ``ValueError`` (caught by the route and mapped to an HTTP status) for:
    ``"SELF_LINK"`` (an entry linked to itself), ``"ENTRY_NOT_FOUND"`` (either side
    doesn't exist), or ``"DUPLICATE"`` (the same (from, to, type) triple already exists).
    """
    if from_entry_id == to_entry_id:
        raise ValueError("SELF_LINK")
    if get_entry(db, from_entry_id) is None or get_entry(db, to_entry_id) is None:
        raise ValueError("ENTRY_NOT_FOUND")

    existing = db.execute(
        select(CodexRelationship).where(
            CodexRelationship.from_entry_id == from_entry_id,
            CodexRelationship.to_entry_id == to_entry_id,
            CodexRelationship.relationship_type == relationship_type,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("DUPLICATE")

    relationship = CodexRelationship(
        id=new_uuid(),
        from_entry_id=from_entry_id,
        to_entry_id=to_entry_id,
        relationship_type=relationship_type,
        description=description,
    )
    db.add(relationship)
    db.commit()
    db.refresh(relationship)
    return relationship


def list_relationships(db: Session, entry_id: str) -> list[CodexRelationship]:
    """All relationships touching ``entry_id`` in either direction (from or to)."""
    return list(
        db.execute(
            select(CodexRelationship)
            .where(
                or_(
                    CodexRelationship.from_entry_id == entry_id,
                    CodexRelationship.to_entry_id == entry_id,
                )
            )
            .order_by(CodexRelationship.relationship_type, CodexRelationship.id)
        ).scalars()
    )


def delete_relationship(db: Session, rel_id: str) -> bool:
    relationship = db.get(CodexRelationship, rel_id)
    if relationship is None:
        return False
    db.delete(relationship)
    db.commit()
    return True


# ── Arc states (docs/03-DATA-MODEL.md `codex_arc_states`; docs/06 Phase 3 task BE-2) —
# point-in-time entity snapshots. This is the WRITE side only; the anti-spoiler read/filter
# contract lives entirely in app/services/prompt_builder.py's `build_codex_context` and must
# not be duplicated or reinterpreted here. ──────────────────────────────────────────────────


def create_arc_state(
    db: Session,
    codex_entry_id: str,
    book_id: str,
    as_of_outline_order_index: int,
    status_summary: str | None = None,
    traits_snapshot: dict[str, Any] | None = None,
) -> CodexArcState:
    """Create a new point-in-time arc-state for ``codex_entry_id`` within ``book_id``.

    Raises ``ValueError("ENTRY_NOT_FOUND")`` if the Codex entry doesn't exist, or
    ``ValueError("BOOK_NOT_FOUND")`` if the Book doesn't exist. No dedupe: multiple
    arc-states per entry/book at different indices is the whole point, and two at the SAME
    index are also allowed (both created; the read path picks the latest applicable one).
    """
    if get_entry(db, codex_entry_id) is None:
        raise ValueError("ENTRY_NOT_FOUND")
    if db.get(Book, book_id) is None:
        raise ValueError("BOOK_NOT_FOUND")

    arc_state = CodexArcState(
        id=new_uuid(),
        codex_entry_id=codex_entry_id,
        book_id=book_id,
        as_of_outline_order_index=as_of_outline_order_index,
        status_summary=status_summary,
        traits_snapshot=traits_snapshot,
    )
    db.add(arc_state)
    db.commit()
    db.refresh(arc_state)
    return arc_state


def list_arc_states(
    db: Session, codex_entry_id: str, book_id: str | None = None
) -> list[CodexArcState]:
    """Arc-states for ``codex_entry_id``, optionally scoped to a single Book, in stable
    ascending order by outline position (then creation order, then id) for display purposes.
    (The anti-spoiler "latest applicable" resolution used by prompt_builder is separate and
    unaffected by this ordering.)"""
    stmt = select(CodexArcState).where(CodexArcState.codex_entry_id == codex_entry_id)
    if book_id is not None:
        stmt = stmt.where(CodexArcState.book_id == book_id)
    stmt = stmt.order_by(
        CodexArcState.as_of_outline_order_index.asc(),
        CodexArcState.created_at.asc(),
        CodexArcState.id.asc(),
    )
    return list(db.execute(stmt).scalars())


def delete_arc_state(db: Session, arc_state_id: str) -> bool:
    arc_state = db.get(CodexArcState, arc_state_id)
    if arc_state is None:
        return False
    db.delete(arc_state)
    db.commit()
    return True
