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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import new_uuid, utcnow_iso
from app.models.orm import BookCodexLink, CodexEntry, CodexSceneLink


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
    return entry


def delete_entry(db: Session, entry_id: str) -> bool:
    entry = db.get(CodexEntry, entry_id)
    if entry is None:
        return False
    db.delete(entry)
    db.commit()
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
