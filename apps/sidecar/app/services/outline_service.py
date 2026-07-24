"""Outline/Timeline services (docs/03-DATA-MODEL.md `chapters` / `book_scene_order`,
docs/06 Phase 4 tasks BE-2/BE-3).

This module owns Chapter CRUD (task BE-2) plus ``book_scene_order`` (task BE-3) — the
single table that backs BOTH the Outline (beat-board) and Timeline views. There is exactly
ONE ``BookSceneOrder`` row per (book_id, scene_id) pair (``UniqueConstraint(book_id,
scene_id)``, see app/models/orm.py); it carries the Outline position (chapter_id,
structure_beat, outline_order_index) AND the Timeline position (timeline_order_index,
in_story_time_label, in_story_time_sort_key) side by side. Every write path here funnels
through :func:`get_or_create_order_row` so a second row for the same pair is never inserted.

DATA-SENSITIVE (read-only elsewhere): ``prompt_builder.build_codex_context`` reads
``outline_order_index`` off this same table for its anti-spoiler filter — this module is
the only writer of that column; it is never touched by prompt_builder itself.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import new_uuid
from app.models.orm import Book, BookSceneOrder, Chapter, Scene


def list_chapters(db: Session, book_id: str) -> list[Chapter]:
    return list(
        db.execute(
            select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.order_index)
        ).scalars()
    )


def get_chapter(db: Session, chapter_id: str) -> Chapter | None:
    return db.get(Chapter, chapter_id)


def _next_order_index(db: Session, book_id: str) -> int:
    max_index = db.execute(
        select(func.max(Chapter.order_index)).where(Chapter.book_id == book_id)
    ).scalar_one_or_none()
    return 0 if max_index is None else max_index + 1


def create_chapter(
    db: Session, book_id: str, title: str, order_index: int | None = None
) -> Chapter:
    """Create a Chapter under ``book_id``.

    Raises ``ValueError("BOOK_NOT_FOUND")`` if the Book doesn't exist. When
    ``order_index`` is omitted, the new Chapter is appended after the Book's current
    highest ``order_index`` (0 if it has none yet).
    """
    if db.get(Book, book_id) is None:
        raise ValueError("BOOK_NOT_FOUND")

    chapter = Chapter(
        id=new_uuid(),
        book_id=book_id,
        title=title,
        order_index=order_index if order_index is not None else _next_order_index(db, book_id),
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


def update_chapter(db: Session, chapter_id: str, values: dict[str, Any]) -> Chapter | None:
    """Partial update — only keys present in ``values`` are applied."""
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        return None
    for key, value in values.items():
        setattr(chapter, key, value)
    db.commit()
    db.refresh(chapter)
    return chapter


def delete_chapter(db: Session, chapter_id: str) -> bool:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        return False
    db.delete(chapter)
    db.commit()
    return True


# ── book_scene_order — the Outline/Timeline mediator (task BE-3) ───────────────────────


def get_or_create_order_row(db: Session, book_id: str, scene_id: str) -> BookSceneOrder:
    """Fetch the single ``book_scene_order`` row for (book_id, scene_id) or create one with
    all-null positions.

    Respects the table's ``UniqueConstraint(book_id, scene_id)`` — this is the ONLY place a
    ``BookSceneOrder`` row is inserted, so every assign/set/reorder path below reuses the
    same row for a given pair instead of ever creating a second one. Does not commit; the
    caller commits once after applying whichever fields it's setting.
    """
    row = db.execute(
        select(BookSceneOrder).where(
            BookSceneOrder.book_id == book_id, BookSceneOrder.scene_id == scene_id
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = BookSceneOrder(id=new_uuid(), book_id=book_id, scene_id=scene_id)
    db.add(row)
    db.flush()
    return row


def list_outline(db: Session, book_id: str) -> list[BookSceneOrder]:
    """Rows for ``book_id`` ordered by (outline_order_index NULLS LAST, id).

    Scenes not yet placed in the Outline carry a NULL ``outline_order_index`` — the
    ``.is_(None)`` term sorts those (True/1) after placed rows (False/0) portably on SQLite,
    so the UI can render an "unplaced" area after the ordered chapters/beats.
    """
    return list(
        db.execute(
            select(BookSceneOrder)
            .where(BookSceneOrder.book_id == book_id)
            .order_by(
                BookSceneOrder.outline_order_index.is_(None),
                BookSceneOrder.outline_order_index,
                BookSceneOrder.id,
            )
        ).scalars()
    )


def list_timeline(db: Session, book_id: str) -> list[BookSceneOrder]:
    """Rows for ``book_id`` ordered by (in_story_time_sort_key NULLS LAST,
    timeline_order_index NULLS LAST, id)."""
    return list(
        db.execute(
            select(BookSceneOrder)
            .where(BookSceneOrder.book_id == book_id)
            .order_by(
                BookSceneOrder.in_story_time_sort_key.is_(None),
                BookSceneOrder.in_story_time_sort_key,
                BookSceneOrder.timeline_order_index.is_(None),
                BookSceneOrder.timeline_order_index,
                BookSceneOrder.id,
            )
        ).scalars()
    )


def _require_book(db: Session, book_id: str) -> None:
    if db.get(Book, book_id) is None:
        raise ValueError("BOOK_NOT_FOUND")


def _require_book_and_scene(db: Session, book_id: str, scene_id: str) -> None:
    _require_book(db, book_id)
    if db.get(Scene, scene_id) is None:
        raise ValueError("SCENE_NOT_FOUND")


_ASSIGN_FIELDS = {"chapter_id", "structure_beat", "outline_order_index"}


def assign_scene(
    db: Session,
    book_id: str,
    scene_id: str,
    updates: dict[str, Any],
) -> BookSceneOrder:
    """Place (or re-place) a Scene in ``book_id``'s Outline.

    ``updates`` is a partial-update dict of ONLY the keys the caller actually wants to
    change (typically ``payload.model_dump(exclude_unset=True)``) — a key that is *absent*
    is left as-is, but a key that is *present with value ``None``* is applied and clears
    that column (e.g. ``{"structure_beat": None}`` moves a Scene back to "Unassigned" on
    the beat-board). This mirrors ``codex_service.update_entry``'s dict/setattr pattern and
    is what makes clearing possible — a plain ``if x is not None`` guard on a keyword arg
    can't distinguish "not provided" from "explicitly set to null".

    Any already-set Timeline fields on the same row are left untouched regardless. Raises
    ``ValueError("BOOK_NOT_FOUND")`` / ``ValueError("SCENE_NOT_FOUND")`` if either doesn't
    exist, or ``ValueError("CHAPTER_MISMATCH")`` if ``chapter_id`` is being set to a
    non-``None`` value that belongs to a different Book (or doesn't exist at all) — a
    ``chapter_id`` being cleared to ``None`` skips this check entirely.
    """
    _require_book_and_scene(db, book_id, scene_id)
    if updates.get("chapter_id") is not None:
        chapter = db.get(Chapter, updates["chapter_id"])
        if chapter is None or chapter.book_id != book_id:
            raise ValueError("CHAPTER_MISMATCH")

    row = get_or_create_order_row(db, book_id, scene_id)
    for key, value in updates.items():
        if key in _ASSIGN_FIELDS:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def reorder_outline(db: Session, book_id: str, ordered_scene_ids: list[str]) -> None:
    """Authoritative reindex: each id in ``ordered_scene_ids`` gets
    ``outline_order_index`` = its position (0..n), reusing (never duplicating) its
    ``book_scene_order`` row. Scenes belonging to the Book but omitted from the list are
    left with whatever ``outline_order_index`` they already had (or NULL if unplaced).

    Raises ``ValueError("BOOK_NOT_FOUND")`` / ``ValueError("SCENE_NOT_FOUND")`` — mirrors
    ``screenplay_service.reorder_elements``'s strictness about not silently dropping or
    orphaning rows for ids that don't resolve.
    """
    _require_book(db, book_id)
    for index, scene_id in enumerate(ordered_scene_ids):
        if db.get(Scene, scene_id) is None:
            raise ValueError("SCENE_NOT_FOUND")
        row = get_or_create_order_row(db, book_id, scene_id)
        row.outline_order_index = index
    db.commit()


_TIMELINE_FIELDS = {"timeline_order_index", "in_story_time_label", "in_story_time_sort_key"}


def set_timeline(
    db: Session,
    book_id: str,
    scene_id: str,
    updates: dict[str, Any],
) -> BookSceneOrder:
    """Place (or re-place) a Scene in ``book_id``'s Timeline.

    ``updates`` is a partial-update dict of ONLY the keys the caller actually wants to
    change (typically ``payload.model_dump(exclude_unset=True)``) — a key that is *absent*
    is left as-is, but a key that is *present with value ``None``* is applied and clears
    that column (e.g. ``{"in_story_time_label": None}`` clears a Scene's in-story date).
    Mirrors :func:`assign_scene`'s dict/setattr pattern for the same reason. Any
    already-set Outline fields on the same row are left untouched regardless. Raises
    ``ValueError("BOOK_NOT_FOUND")`` / ``ValueError("SCENE_NOT_FOUND")`` if either doesn't
    exist.
    """
    _require_book_and_scene(db, book_id, scene_id)
    row = get_or_create_order_row(db, book_id, scene_id)
    for key, value in updates.items():
        if key in _TIMELINE_FIELDS:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def reorder_timeline(db: Session, book_id: str, ordered_scene_ids: list[str]) -> None:
    """Authoritative reindex: each id in ``ordered_scene_ids`` gets
    ``timeline_order_index`` = its position (0..n). Mirrors :func:`reorder_outline`; does
    not touch ``in_story_time_label``/``in_story_time_sort_key`` (those are set separately
    via :func:`set_timeline`, since a drag-reorder is a distinct action from re-dating a
    scene)."""
    _require_book(db, book_id)
    for index, scene_id in enumerate(ordered_scene_ids):
        if db.get(Scene, scene_id) is None:
            raise ValueError("SCENE_NOT_FOUND")
        row = get_or_create_order_row(db, book_id, scene_id)
        row.timeline_order_index = index
    db.commit()
