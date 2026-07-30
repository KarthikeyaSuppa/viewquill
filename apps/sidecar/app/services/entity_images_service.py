"""Polymorphic image<->entity attach/detach (docs/03-DATA-MODEL.md `entity_images`,
docs/06 Phase 5 task BE-3). Builds on BE-1/BE-2's `images_service` — this module never
touches image bytes on disk, only the `entity_images` link table.

``entity_images`` has ``ON DELETE CASCADE`` on ``image_id`` (app/models/orm.py) — deleting
an ``Image`` row already clears every link that pointed at it, so this module doesn't need
its own cleanup hook for that case.

Deliberately does NOT validate that ``entity_id`` points to a real ``books`` / ``scenes`` /
``codex_entries`` row: those tables have no FK to ``entity_images`` (it's polymorphic, so a
single FK column can't target three different tables), and entities may legitimately be
created in any order (e.g. attaching a reference image to a Scene before the Scene is saved
elsewhere, or a Book/Scene/Codex entry being deleted independently of its image links). Only
the image side (``image_id`` -> ``images.id``) is ever checked.
"""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.base import new_uuid
from app.models.orm import Book, BookCodexLink, BookSceneLink, EntityImage, Image

ALLOWED_ENTITY_TYPES: set[str] = {"book", "scene", "codex_entry"}


def attach(
    db: Session,
    *,
    image_id: str,
    entity_type: str,
    entity_id: str,
    role: str | None = None,
) -> EntityImage:
    """Links ``image_id`` to (``entity_type``, ``entity_id``), optionally tagged with a
    ``role`` (e.g. 'cover', 'moodboard').

    Raises ``ValueError`` (mapped to HTTP status by the route) for:
    ``"BAD_ENTITY_TYPE"`` (not one of ``ALLOWED_ENTITY_TYPES``),
    ``"IMAGE_NOT_FOUND"`` (``image_id`` doesn't exist).

    Idempotent: an existing link with the exact same (image_id, entity_type, entity_id,
    role) is returned as-is rather than inserting a duplicate row. ``role=None`` and
    ``role="x"`` are distinct links — a caller can attach the same image to the same
    entity twice under different roles, but not create two identical rows for the same
    role (including two rows both with ``role IS NULL``).
    """
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise ValueError("BAD_ENTITY_TYPE")
    if db.get(Image, image_id) is None:
        raise ValueError("IMAGE_NOT_FOUND")

    existing = db.execute(
        select(EntityImage).where(
            EntityImage.image_id == image_id,
            EntityImage.entity_type == entity_type,
            EntityImage.entity_id == entity_id,
            EntityImage.role.is_(role) if role is None else EntityImage.role == role,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    link = EntityImage(
        id=new_uuid(),
        image_id=image_id,
        entity_type=entity_type,
        entity_id=entity_id,
        role=role,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def detach(
    db: Session,
    *,
    image_id: str,
    entity_type: str,
    entity_id: str,
    role: str | None = None,
) -> bool:
    """Deletes the link(s) matching (``image_id``, ``entity_type``, ``entity_id``, ``role``).

    Raises ``ValueError("BAD_ENTITY_TYPE")`` if ``entity_type`` isn't one of
    ``ALLOWED_ENTITY_TYPES`` (mapped to HTTP 422 by the route).

    ``role`` semantics: this parameter is never "omitted" at this layer (the route always
    passes it explicitly, defaulting to ``None``) — ``role=None`` means "match the link with
    no role" (``role IS NULL``), matching ``attach``'s treatment of ``role=None`` as its own
    distinct link, not a wildcard that matches every role. To detach a specific role, pass it
    explicitly.

    Returns ``True`` if at least one row was deleted, ``False`` otherwise (including when the
    image itself doesn't exist — there's nothing to detach either way, so this is a no-op,
    not an error). Idempotent: calling it again after a successful detach returns ``False``.
    """
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise ValueError("BAD_ENTITY_TYPE")

    matches = list(
        db.execute(
            select(EntityImage).where(
                EntityImage.image_id == image_id,
                EntityImage.entity_type == entity_type,
                EntityImage.entity_id == entity_id,
                EntityImage.role.is_(role) if role is None else EntityImage.role == role,
            )
        ).scalars()
    )
    if not matches:
        return False
    for link in matches:
        db.delete(link)
    db.commit()
    return True


def list_for_entity(db: Session, *, entity_type: str, entity_id: str) -> list[Image]:
    """All ``Image`` rows linked to (``entity_type``, ``entity_id``), deterministically
    ordered: rows with an explicit ``EntityImage.order_index`` (user-reordered / "cover"
    picked, PHASE-UI-EFFECTS-2.md §4 B2) come first, lowest ``order_index`` first; rows
    with ``order_index IS NULL`` (every row until a user explicitly reorders) come after,
    falling back to ``created_at DESC, id DESC`` — the original ordering, preserved exactly
    for that fallback group — same tie-break ordering as ``images_service.list_images``.

    SQLite's own ``ORDER BY x ASC`` default already sorts NULL before non-NULL, which is
    the opposite of what's wanted here, so the ``EntityImage.order_index.is_(None)``
    boolean key is listed explicitly first (False/0 sorts before True/1) rather than
    relying on any driver's default NULL placement.

    Raises ``ValueError("BAD_ENTITY_TYPE")`` if ``entity_type`` isn't one of
    ``ALLOWED_ENTITY_TYPES`` (mapped to HTTP 422 by the route).
    """
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise ValueError("BAD_ENTITY_TYPE")

    stmt = (
        select(Image)
        .join(EntityImage, EntityImage.image_id == Image.id)
        .where(
            EntityImage.entity_type == entity_type,
            EntityImage.entity_id == entity_id,
        )
        .order_by(
            EntityImage.order_index.is_(None),
            EntityImage.order_index.asc(),
            Image.created_at.desc(),
            Image.id.desc(),
        )
    )
    return list(db.execute(stmt).scalars())


def reorder_for_entity(
    db: Session, *, entity_type: str, entity_id: str, image_ids: list[str]
) -> None:
    """Sets ``EntityImage.order_index`` for every link currently attached to
    (``entity_type``, ``entity_id``) so that ``list_for_entity`` returns images in exactly
    the order given by ``image_ids`` (PHASE-UI-EFFECTS-2.md §4 B2 / §5 task 3).

    For each ``image_id`` in the given ORDERED list, every ``EntityImage`` row matching
    (``entity_type``, ``entity_id``, ``image_id``) — there can be more than one if the same
    image is attached under multiple ``role``s, see ``attach``'s role semantics — has its
    ``order_index`` set to that image's 0-based position in the list.

    Links currently attached to this entity but NOT present in ``image_ids`` have their
    ``order_index`` reset to ``NULL`` — this is deliberate, not an oversight: without it, a
    previous reorder's stale ``order_index`` values would linger and interleave with the
    new ordering (a row explicitly ranked "3" from a prior call would keep sorting ahead of
    the NULL-fallback group even though the caller no longer mentions it). Resetting to
    ``NULL`` puts omitted images back into the recency-based fallback group
    (``created_at DESC, id DESC``, see ``list_for_entity``), i.e. they fall to the end of
    whatever's explicitly ordered, not to some arbitrary stale position.

    ``image_id`` values in the list that aren't actually attached to this entity are a
    no-op for that id — this never creates a phantom ``EntityImage`` row (that's `attach`'s
    job, and requires a real ``Image`` to exist); reordering is attach-list maintenance, not
    an attach operation.

    Idempotent: calling this again with the same ``image_ids`` list re-derives the same
    ``order_index`` values and re-resets the same omitted set to ``NULL`` — no duplicate
    rows, no drift.

    Raises ``ValueError("BAD_ENTITY_TYPE")`` if ``entity_type`` isn't one of
    ``ALLOWED_ENTITY_TYPES`` (mapped to HTTP 422 by the route).
    """
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise ValueError("BAD_ENTITY_TYPE")

    links = list(
        db.execute(
            select(EntityImage).where(
                EntityImage.entity_type == entity_type,
                EntityImage.entity_id == entity_id,
            )
        ).scalars()
    )

    position_by_image_id = {image_id: index for index, image_id in enumerate(image_ids)}
    for link in links:
        link.order_index = position_by_image_id.get(link.image_id)
    db.commit()


def gather_book_images(db: Session, book_id: str) -> list[Image]:
    """Every DISTINCT ``Image`` that "belongs to" ``book_id`` for `.quillproj` export
    purposes (docs/06 Phase 5 task BE-4) — the union of:

    (a) images linked via ``entity_images`` with ``entity_type='book'``,
        ``entity_id=book_id``;
    (b) images linked via ``entity_images`` with ``entity_type='scene'`` where the scene is
        on THIS Book's canvas — scoped via ``book_scene_links`` (``BookSceneLink``), NOT a
        ``Scene.book_id`` column, because ``Scene`` rows are canonical/shared across Books
        (app/models/orm.py) and per-Book membership is exactly what that link table encodes;
    (c) images linked via ``entity_images`` with ``entity_type='codex_entry'`` where the
        codex entry is linked to THIS Book — scoped via ``book_codex_links``
        (``BookCodexLink``), for the same "canonical/shared entity" reason as (b);
    (d) the Book's cover image (``books.cover_image_id``), if set.

    Deliberately does NOT check that ``book_id`` refers to a real ``Book`` row — callers
    (the route) are expected to 404 first; a nonexistent ``book_id`` here simply yields no
    scene/codex membership and no cover, i.e. an empty list, never an error.

    Ordered deterministically (``created_at DESC, id DESC``), same as
    ``images_service.list_images`` / ``list_for_entity``. Each Image appears at most once
    even when reachable through more than one of (a)-(d) above (e.g. attached to the Book
    directly AND to one of its scenes, or set as both a scene-linked image and the cover).
    """
    book_scene_ids = select(BookSceneLink.scene_id).where(BookSceneLink.book_id == book_id)
    book_codex_ids = select(BookCodexLink.codex_entry_id).where(BookCodexLink.book_id == book_id)

    linked_image_ids = select(EntityImage.image_id).where(
        or_(
            and_(EntityImage.entity_type == "book", EntityImage.entity_id == book_id),
            and_(
                EntityImage.entity_type == "scene",
                EntityImage.entity_id.in_(book_scene_ids),
            ),
            and_(
                EntityImage.entity_type == "codex_entry",
                EntityImage.entity_id.in_(book_codex_ids),
            ),
        )
    )

    cover_image_ids = select(Book.cover_image_id).where(
        Book.id == book_id, Book.cover_image_id.is_not(None)
    )

    stmt = (
        select(Image)
        .where(or_(Image.id.in_(linked_image_ids), Image.id.in_(cover_image_ids)))
        .distinct()
        .order_by(Image.created_at.desc(), Image.id.desc())
    )
    return list(db.execute(stmt).scalars())
