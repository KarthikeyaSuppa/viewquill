"""Shared export orchestration — the module every per-format renderer (markdown/docx/pdf/
fountain/fdx) imports from (docs/03-DATA-MODEL.md `draft_versions`, docs/06 Phase 6 task
BE-2). This module builds the format-agnostic ``CompiledDocument`` a renderer walks, gates
which formats a Book's ``book_type`` is allowed to compile to, and owns ``draft_versions``
bookkeeping. It does NOT render any bytes to disk itself — that's BE-3 onward.

FULLY MATERIALIZED, NOT LAZY ORM: ``build_compiled_document`` returns plain dataclasses with
every field already read — no ``Scene``/``Chapter``/``ScreenplayElement`` ORM instance (and no
lazy relationship) is held past this function's return, so a renderer can safely run after the
request-scoped session that produced the ``CompiledDocument`` has closed (mirrors how
``images_service.to_image_read`` fully builds its Pydantic ``ImageRead`` before handing it
back, rather than returning a bound ORM ``Image``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.base import new_uuid
from app.models.orm import Book, BookSceneOrder, Chapter, DraftVersion, Scene
from app.models.schemas import DraftVersionRead
from app.services import screenplay_service

# Formats that are ALSO gated to script book types — every other allowed format
# (markdown/docx/pdf) is valid for every ``book_type`` the DB CHECK allows.
_SCRIPT_ONLY_FORMATS = {"fountain", "fdx"}
_SCRIPT_BOOK_TYPES = {"movie_script", "short_film_script"}
ALL_FORMATS = ("markdown", "docx", "pdf", "fountain", "fdx")


# ── Compiled document shape ──────────────────────────────────────────────────────


@dataclass
class ScreenplayElementLike:
    """Detached, plain copy of one ``ScreenplayElement`` row — never the live ORM object,
    per the module's "fully materialized" contract."""

    element_type: str
    text: str
    order_index: int


@dataclass
class CompiledScene:
    title: str
    description: str  # prose text; empty string if the scene has none
    elements: list[ScreenplayElementLike] = field(default_factory=list)


@dataclass
class CompiledChapter:
    title: str | None
    scenes: list[CompiledScene] = field(default_factory=list)


@dataclass
class CompiledDocument:
    book_id: str
    book_title: str
    book_type: str
    logline: str | None
    front_matter: dict | None
    cover_image_id: str | None
    chapters: list[CompiledChapter] = field(default_factory=list)


def _is_script_book_type(book_type: str) -> bool:
    return book_type in _SCRIPT_BOOK_TYPES


def build_compiled_document(db: Session, book: Book) -> CompiledDocument:
    """Walks ``book_scene_order`` (+ ``scenes`` + ``chapters``) for ``book.id``, grouped into
    ``CompiledChapter`` buckets in outline order, and returns a fully-materialized
    ``CompiledDocument`` — no lazy ORM access survives this call.

    Ordering matches ``outline_service.list_outline``'s convention exactly: (
    ``outline_order_index`` NULLS LAST, ``id``). Scenes with no ``chapter_id`` are grouped
    into ONE chapterless bucket (``CompiledChapter(title=None, ...)``), holding every such
    scene in outline order — not one bucket per chapterless scene. Since an unplaced/
    chapterless scene typically carries a NULL ``outline_order_index``, that bucket's
    position among the returned ``chapters`` list follows the same NULLS-LAST rule (it lands
    wherever its first member scene sorts — usually last, but not guaranteed if a chapterless
    scene has a non-NULL ``outline_order_index``).

    For script book types (``movie_script``/``short_film_script``) each scene's
    ``ScreenplayElement`` rows (via ``screenplay_service.list_elements``) are also attached to
    ``CompiledScene.elements``; ``single_scene`` is treated as prose (no elements attached) —
    see the task's note that the roadmap only ever pairs Fountain/FDX with the two script
    types, not ``single_scene``. ``CompiledScene.description`` is always populated regardless
    of book type — prose notes and structured elements coexist per the data model, neither is
    dropped.
    """
    rows = list(
        db.execute(
            select(BookSceneOrder, Scene, Chapter)
            .join(Scene, Scene.id == BookSceneOrder.scene_id)
            .outerjoin(Chapter, Chapter.id == BookSceneOrder.chapter_id)
            .where(BookSceneOrder.book_id == book.id)
            .order_by(
                BookSceneOrder.outline_order_index.is_(None),
                BookSceneOrder.outline_order_index,
                BookSceneOrder.id,
            )
        )
    )

    attach_elements = _is_script_book_type(book.book_type)

    chapterless = CompiledChapter(title=None, scenes=[])
    chapter_buckets: dict[str, CompiledChapter] = {}
    ordered_chapter_ids: list[str | None] = []  # None sentinel represents the chapterless bucket

    for _order_row, scene, chapter in rows:
        if attach_elements:
            elements = [
                ScreenplayElementLike(
                    element_type=el.element_type, text=el.text, order_index=el.order_index
                )
                for el in screenplay_service.list_elements(db, scene.id)
            ]
        else:
            elements = []

        compiled_scene = CompiledScene(
            title=scene.title,
            description=scene.description or "",
            elements=elements,
        )

        if chapter is None:
            if None not in ordered_chapter_ids:
                ordered_chapter_ids.append(None)
            chapterless.scenes.append(compiled_scene)
            continue

        bucket = chapter_buckets.get(chapter.id)
        if bucket is None:
            bucket = CompiledChapter(title=chapter.title, scenes=[])
            chapter_buckets[chapter.id] = bucket
            ordered_chapter_ids.append(chapter.id)
        bucket.scenes.append(compiled_scene)

    chapters: list[CompiledChapter] = []
    for chapter_id in ordered_chapter_ids:
        chapters.append(chapterless if chapter_id is None else chapter_buckets[chapter_id])

    return CompiledDocument(
        book_id=book.id,
        book_title=book.title,
        book_type=book.book_type,
        logline=book.logline,
        front_matter=book.front_matter,
        cover_image_id=book.cover_image_id,
        chapters=chapters,
    )


# ── Format gating ────────────────────────────────────────────────────────────────


def format_allowed_for_book_type(fmt: str, book_type: str) -> bool:
    """``fountain``/``fdx`` are allowed only for ``movie_script``/``short_film_script``;
    every other known format (``markdown``/``docx``/``pdf``) is allowed for every book type
    (including ``single_scene``)."""
    if fmt in _SCRIPT_ONLY_FORMATS:
        return book_type in _SCRIPT_BOOK_TYPES
    return fmt in ALL_FORMATS


def ensure_format_allowed(fmt: str, book_type: str) -> None:
    """Raises ``ValueError("FORMAT_NOT_SUPPORTED_FOR_BOOK_TYPE")`` if ``fmt`` isn't allowed
    for ``book_type`` — see :func:`format_allowed_for_book_type`."""
    if not format_allowed_for_book_type(fmt, book_type):
        raise ValueError("FORMAT_NOT_SUPPORTED_FOR_BOOK_TYPE")


# ── draft_versions bookkeeping ───────────────────────────────────────────────────


def create_draft_version(
    db: Session,
    book_id: str,
    fmt: str,
    file_path: str,
    format_settings: dict | None = None,
    notes: str | None = None,
) -> DraftVersion:
    """Records one compiled export snapshot for ``book_id``.

    ``is_current`` is scoped per (``book_id``, format), where format lives inside
    ``format_settings["format"]`` (there is no real ``format`` column) — every existing
    ``DraftVersion`` row for this ``book_id`` whose ``format_settings["format"] == fmt`` is
    flipped to ``is_current=0`` in one bulk ``UPDATE`` (verified against SQLite's JSON1
    extension via SQLAlchemy 2.0's ``Column["key"].as_string()`` item-access operator — see
    this task's manual check; NULL ``format_settings`` rows are correctly left untouched, no
    error), then the new row is inserted with ``is_current=1``.

    ``version_number`` is a GLOBAL per-book counter across every format — ``max`` existing
    ``version_number`` for ``book_id`` (0 if none) + 1.

    The caller-supplied ``format_settings`` is merged with ``{"format": fmt}`` (added only if
    not already present as exactly ``fmt``) so ``format_settings["format"]`` is always
    recoverable later — the only way format is stored at all.
    """
    db.execute(
        update(DraftVersion)
        .where(
            DraftVersion.book_id == book_id,
            DraftVersion.format_settings["format"].as_string() == fmt,
        )
        .values(is_current=0)
    )

    max_version = db.execute(
        select(func.max(DraftVersion.version_number)).where(DraftVersion.book_id == book_id)
    ).scalar_one_or_none()
    version_number = (max_version or 0) + 1

    merged_settings = dict(format_settings) if format_settings else {}
    merged_settings.setdefault("format", fmt)
    merged_settings["format"] = fmt  # authoritative — always matches the caller's `fmt`

    draft_version = DraftVersion(
        id=new_uuid(),
        book_id=book_id,
        version_number=version_number,
        file_path=file_path,
        format_settings=merged_settings,
        is_current=1,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        notes=notes,
    )
    db.add(draft_version)
    db.commit()
    db.refresh(draft_version)
    return draft_version


def list_draft_versions(db: Session, book_id: str) -> list[DraftVersion]:
    """``DraftVersion`` rows for ``book_id``, ordered ``version_number DESC``."""
    return list(
        db.execute(
            select(DraftVersion)
            .where(DraftVersion.book_id == book_id)
            .order_by(DraftVersion.version_number.desc())
        ).scalars()
    )


def get_draft_version(db: Session, draft_version_id: str) -> DraftVersion | None:
    return db.get(DraftVersion, draft_version_id)


def to_draft_version_read(row: DraftVersion) -> DraftVersionRead:
    """Builds a ``DraftVersionRead`` from one ``DraftVersion`` row — mirrors
    ``images_service.to_image_read``'s pattern of a small conversion helper living next to the
    data functions it serves. Unpacks ``format_settings["format"]`` (defaulting to
    ``"unknown"`` if somehow absent) since there is no real ``format`` column to pull from via
    ``from_attributes``."""
    settings = row.format_settings or {}
    return DraftVersionRead(
        id=row.id,
        book_id=row.book_id,
        version_number=row.version_number,
        format=settings.get("format", "unknown"),
        format_settings=row.format_settings,
        is_current=bool(row.is_current),
        generated_at=row.generated_at,
        notes=row.notes,
    )
