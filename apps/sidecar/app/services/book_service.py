"""Book CRUD — the Story Library (docs/01-PRODUCT-VISION.md, docs/06 Phase 1).

A Book is the per-project container (title, type, structure template, cover). Scenes and
Codex entries are canonical and shared across Books (docs/03-DATA-MODEL.md); deleting a Book
cascades only its per-book link/order/connection rows (FK ``ondelete="CASCADE"`` in
``app/models/orm.py`` on ``book_scene_links``, ``book_scene_order``, ``scene_connections``,
``book_codex_links``, ``codex_arc_states``, ``chapters``, ``continuity_flags``,
``draft_versions``) — it must NEVER remove the shared ``scenes`` or ``codex_entries`` rows
themselves, and it does not.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import new_uuid, utcnow_iso
from app.models.orm import Book


def create_book(
    db: Session,
    *,
    title: str,
    book_type: str,
    logline: str | None = None,
    front_matter: dict[str, Any] | None = None,
) -> Book:
    book = Book(
        id=new_uuid(),
        title=title,
        book_type=book_type,
        logline=logline,
        front_matter=front_matter,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def list_books(db: Session) -> list[Book]:
    return list(db.execute(select(Book).order_by(Book.updated_at.desc())).scalars())


def get_book(db: Session, book_id: str) -> Book | None:
    return db.get(Book, book_id)


def update_book(db: Session, book_id: str, values: dict[str, Any]) -> Book | None:
    """Partial update — only keys present in ``values`` are applied."""
    book = db.get(Book, book_id)
    if book is None:
        return None
    for key, value in values.items():
        setattr(book, key, value)
    # `updated_at` has an `onupdate` default, but that only fires on a flush that detects a
    # change; touch it explicitly so a no-op-looking patch still bumps the timestamp.
    book.updated_at = utcnow_iso()
    db.commit()
    db.refresh(book)
    return book


def convert_book_type(db: Session, book_id: str, book_type: str) -> Book | None:
    """Change a Book's ``book_type`` only.

    This is intentionally non-destructive and additive-by-design: it does not touch
    ``scenes``, ``screenplay_elements``, or any other content. The AI-assisted transform
    that would populate/rewrite ``screenplay_elements`` (or ``Scene.description``) to match
    the new type is Phase 2+ work — out of scope here.
    """
    return update_book(db, book_id, {"book_type": book_type})


def delete_book(db: Session, book_id: str) -> bool:
    book = db.get(Book, book_id)
    if book is None:
        return False
    db.delete(book)
    db.commit()
    return True
