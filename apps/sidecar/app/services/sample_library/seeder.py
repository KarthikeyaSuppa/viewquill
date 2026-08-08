"""Sample library seeder: turns ``sample_library/content.py``'s pure-data spec into real
rows for a fresh Quillnight install (Phase 14, PHASE14.md).

## When this runs

Called once from ``app/main.py``'s startup lifespan, AFTER ``seed_structure_templates`` —
each demo Book resolves its ``structure_template_id`` by template name, so the templates
must already exist. Non-fatal at the call site: a failed seed must never block startup.

## The guard (idempotent, never resurrects deleted samples)

:func:`seed_sample_library` no-ops (returns ``0``) if EITHER:

* a global ``AppSetting`` row (``user_id IS NULL``) with ``key == "sample_library"`` already
  exists — this is the marker written at the end of a successful seed, and it stops the
  samples from resurrecting after the user deletes them; OR
* the ``books`` table is already non-empty — this protects a library restored from a backup
  that predates the marker (or otherwise lost it) from being seeded on top of real data; OR
* ``QUILLNIGHT_SKIP_SAMPLE_SEED=1`` is set in the environment — the test-suite opt-out, since
  the shared pytest database starts empty and would otherwise be seeded by any test that
  enters ``TestClient(app)``. See ``_SKIP_ENV_VAR`` below for the full rationale.

## Three subtle rules this module exists to get right

1. **Canvas edges are written directly via the ORM (``SceneConnection``), never through
   ``canvas_service.create_edge``.** That function also writes an ``UndoLog`` row (Workstream
   B scoped undo, ``canvas_service.py``) — if the seeder used it, a fresh install's canvas
   undo button would offer to delete sample content the user never touched. Every sample
   Book must end with ZERO ``UndoLog`` rows.
2. **Scene ``status`` is set directly on the ORM object, never through
   ``scene_service.update_scene``.** That function stamps a ``SceneRevision`` with
   ``change_source="manual_edit"`` on every status change (Workstream B history) — using it
   here would pollute the History feature with revisions the user never made.
3. **``SceneRevision`` rows are hand-built from ``content.REVISIONS``**, not produced by
   calling ``update_scene`` repeatedly, specifically so the seeder can exercise all four
   ``change_source`` values (``update_scene`` can only ever produce ``manual_edit``).
   ``parent_revision_id`` chains to the previous revision of the same scene, in ascending
   ``revision_number`` order, mirroring ``undo_service._restore_delete_scene``'s documented
   assumption that same-table self-referential inserts land in insertion order.

## Everything else goes through the ordinary services

Scenes go through ``scene_service.create_scene`` and Codex entries through
``codex_service.create_entry`` specifically so ``search_index_service.upsert_entity`` runs
for free (it never raises; without a real embedding backend on this machine the embedding
half fails and is silently swallowed, which is expected here). Fields those service
functions don't accept (e.g. a Scene's non-default ``status``, a CodexEntry's
``primary_image_id``) are set directly on the returned ORM object before the batching
``db.commit()`` that follows each step.

## Failure handling

``content.py``'s data is validated at import time (``content._validate()``), so a raised
exception here means something the seeder itself did was wrong, not bad input data. Because
several of the services this module calls (``scene_service.create_scene``,
``images_service.save_image``, ...) commit internally, a single atomic transaction/rollback
across the whole seed isn't achievable — instead, on any failure, this module rolls back
whatever's still pending, then best-effort deletes every Book/Scene/CodexEntry/Image it
already created (in that order — deleting a Book cascades its per-Book join/order/edge/
chapter/continuity-flag rows; deleting an Image cascades its ``entity_images`` rows;
Scenes/CodexEntries are canonical and are never cascade-deleted by a Book delete, so they're
cleaned up explicitly), logs loudly, and re-raises. The marker is only ever written after a
fully successful seed, so a failed/partial seed is retried (not skipped) on the next startup.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import new_uuid, utcnow_iso
from app.models.orm import (
    AppSetting,
    Book,
    BookSceneLink,
    ContinuityFlag,
    ImageTag,
    SceneConnection,
    SceneRevision,
    ScreenplayElement,
    StructureTemplate,
)
from app.services import (
    book_service,
    canvas_service,
    codex_service,
    entity_images_service,
    images_service,
    outline_service,
    scene_service,
)
from app.services.sample_library import content
from app.services.sample_library import images as placeholder_images

logger = logging.getLogger("quillnight")

_MARKER_KEY = "sample_library"

# Opt-out switch, read at CALL time (not import time) so a test can flip it per-case.
#
# Why this exists: the pytest suite shares ONE SQLite database across every test module
# (see tests/conftest.py's module docstring — `app.db.base` builds the engine once at
# import time, so whichever module is collected first wins). That database starts empty,
# which is exactly the condition `_already_seeded` treats as "fresh install, please seed".
# Without this flag, entering `TestClient(app)` anywhere in the suite runs the lifespan,
# seeds 4 demo Books into the shared DB, and breaks every test that assumes an empty
# library — `test_bundle_import_inspect.py::test_inspect_empty_db_everything_created` and
# the three migration round-trip tests were the concrete casualties.
#
# Same raw `os.environ.get(...) == "1"` convention as `QUILLNIGHT_LLM_STUB`
# (llm_orchestrator.py) and `QUILLNIGHT_STT_STUB` (speech_stt.py) rather than a third
# mechanism. tests/conftest.py sets it for the whole session; tests/test_sample_library.py
# unsets it around the calls that deliberately exercise the seeder.
_SKIP_ENV_VAR = "QUILLNIGHT_SKIP_SAMPLE_SEED"

_IMAGE_GENERATORS = {
    "cover": placeholder_images.generate_cover,
    "scene": placeholder_images.generate_scene_art,
    "portrait": placeholder_images.generate_portrait,
}


def _already_seeded(db: Session) -> bool:
    marker = db.execute(
        select(AppSetting).where(AppSetting.user_id.is_(None), AppSetting.key == _MARKER_KEY)
    ).scalar_one_or_none()
    if marker is not None:
        return True
    any_book = db.execute(select(Book.id).limit(1)).first()
    return any_book is not None


def _resolve_structure_template_id(db: Session, name: str | None) -> str | None:
    if name is None:
        return None
    template = db.execute(
        select(StructureTemplate).where(StructureTemplate.name == name)
    ).scalar_one_or_none()
    if template is None:
        logger.warning("sample_library: structure template %r not found; leaving FK unset.", name)
        return None
    return template.id


def _seed_books(db: Session, created: dict[str, list[str]]) -> dict[str, str]:
    book_key_to_id: dict[str, str] = {}
    for spec in content.BOOKS:
        book = book_service.create_book(
            db,
            title=spec.title,
            book_type=spec.book_type,
            logline=spec.logline,
            front_matter=spec.front_matter,
        )
        # book_service.create_book doesn't accept structure_template_id/cover_image_id —
        # set directly on the ORM object (cover_image_id is resolved later, once Images
        # exist; structure_template_id can be resolved now).
        book.structure_template_id = _resolve_structure_template_id(
            db, spec.structure_template_name
        )
        book_key_to_id[spec.key] = book.id
        created["books"].append(book.id)
    db.commit()
    return book_key_to_id


def _seed_chapters(db: Session, book_key_to_id: dict[str, str]) -> dict[str, str]:
    chapter_key_to_id: dict[str, str] = {}
    for book_spec in content.BOOKS:
        book_id = book_key_to_id[book_spec.key]
        for chapter_spec in book_spec.chapters:
            chapter = outline_service.create_chapter(
                db, book_id, chapter_spec.title, chapter_spec.order_index
            )
            chapter_key_to_id[chapter_spec.key] = chapter.id
    return chapter_key_to_id


def _seed_images(
    db: Session, book_key_to_id: dict[str, str], created: dict[str, list[str]]
) -> dict[str, str]:
    image_key_to_id: dict[str, str] = {}
    for spec in content.IMAGES:
        generator = _IMAGE_GENERATORS[spec.kind]
        data = generator(spec.seed, label=spec.display_name)
        image = images_service.save_image(
            db,
            data=data,
            content_type="image/png",
            original_filename=None,
            display_name=spec.display_name,
            bucket=spec.bucket,
        )
        if spec.description:
            image.description = spec.description
        for tag in spec.tags:
            db.add(ImageTag(image_id=image.id, tag=tag.strip().lower()))
        image_key_to_id[spec.key] = image.id
        created["images"].append(image.id)
    db.commit()

    # Now that Images exist, resolve each Book's cover_image_id (book_service.create_book
    # doesn't accept it — see _seed_books).
    for book_spec in content.BOOKS:
        if book_spec.cover_image_key is None:
            continue
        book = db.get(Book, book_key_to_id[book_spec.key])
        if book is not None:
            book.cover_image_id = image_key_to_id.get(book_spec.cover_image_key)
    db.commit()

    return image_key_to_id


def _seed_scenes(db: Session, created: dict[str, list[str]]) -> dict[str, str]:
    scene_key_to_id: dict[str, str] = {}
    for spec in content.SCENES:
        scene = scene_service.create_scene(
            db, node_type=spec.node_type, title=spec.title, description=spec.description
        )
        # RULE 2: set status directly — never scene_service.update_scene, which would stamp
        # a manual_edit SceneRevision on every one of these (see module docstring).
        if spec.status != scene.status:
            scene.status = spec.status
        scene_key_to_id[spec.key] = scene.id
        created["scenes"].append(scene.id)
    db.commit()
    return scene_key_to_id


def _seed_canvas_links(
    db: Session,
    book_key_to_id: dict[str, str],
    scene_key_to_id: dict[str, str],
) -> None:
    archived_links: list[BookSceneLink] = []
    for book_spec in content.BOOKS:
        book_id = book_key_to_id[book_spec.key]
        for node in book_spec.canvas:
            link = canvas_service.add_scene_to_canvas(
                db,
                book_id,
                scene_key_to_id[node.scene_key],
                canvas_x=node.x,
                canvas_y=node.y,
                color=node.color,
            )
            if node.archived:
                archived_links.append(link)
    for link in archived_links:
        link.archived_at = utcnow_iso()
    db.commit()


def _seed_order_rows(
    db: Session,
    book_key_to_id: dict[str, str],
    scene_key_to_id: dict[str, str],
    chapter_key_to_id: dict[str, str],
) -> None:
    for book_spec in content.BOOKS:
        book_id = book_key_to_id[book_spec.key]
        for order_spec in book_spec.order:
            row = outline_service.get_or_create_order_row(
                db, book_id, scene_key_to_id[order_spec.scene_key]
            )
            row.chapter_id = (
                chapter_key_to_id.get(order_spec.chapter_key) if order_spec.chapter_key else None
            )
            row.outline_order_index = order_spec.outline_order_index
            row.structure_beat = order_spec.structure_beat
            row.timeline_order_index = order_spec.timeline_order_index
            row.in_story_time_label = order_spec.in_story_time_label
            row.in_story_time_sort_key = order_spec.in_story_time_sort_key
    db.commit()


def _seed_codex_entries(
    db: Session, image_key_to_id: dict[str, str], created: dict[str, list[str]]
) -> dict[str, str]:
    codex_key_to_id: dict[str, str] = {}
    for spec in content.CODEX_ENTRIES:
        entry = codex_service.create_entry(
            db,
            entry_type=spec.entry_type,
            name=spec.name,
            summary=spec.summary,
            custom_fields=spec.custom_fields,
        )
        if spec.portrait_image_key:
            entry.primary_image_id = image_key_to_id.get(spec.portrait_image_key)
        codex_key_to_id[spec.key] = entry.id
        created["codex_entries"].append(entry.id)
    db.commit()
    return codex_key_to_id


def _seed_codex_links(
    db: Session,
    book_key_to_id: dict[str, str],
    scene_key_to_id: dict[str, str],
    codex_key_to_id: dict[str, str],
) -> None:
    for link_spec in content.CODEX_BOOK_LINKS:
        link = codex_service.link_book(
            db, codex_key_to_id[link_spec.codex_key], book_key_to_id[link_spec.book_key]
        )
        if link_spec.role_note:
            link.role_note = link_spec.role_note
    db.commit()

    for scene_link_spec in content.CODEX_SCENE_LINKS:
        link = codex_service.link_scene(
            db,
            codex_key_to_id[scene_link_spec.codex_key],
            scene_key_to_id[scene_link_spec.scene_key],
        )
        if scene_link_spec.note:
            link.note = scene_link_spec.note
    db.commit()


def _seed_entity_images(
    db: Session,
    book_key_to_id: dict[str, str],
    scene_key_to_id: dict[str, str],
    codex_key_to_id: dict[str, str],
    image_key_to_id: dict[str, str],
) -> None:
    """Attach Images to their Book/Scene/CodexEntry per ``content.ENTITY_IMAGES``.

    DEVIATION from the brief's literal step ordering: several ``EntityImageSpec`` rows
    target a ``scene`` or ``codex_entry`` key, so this can only run once BOTH Scenes and
    Codex entries exist — i.e. after those two steps, not immediately after Images (which
    only Book keys would be resolvable that early).
    """
    entity_key_maps = {
        "book": book_key_to_id,
        "scene": scene_key_to_id,
        "codex_entry": codex_key_to_id,
    }
    for entity_image_spec in content.ENTITY_IMAGES:
        entity_id = entity_key_maps[entity_image_spec.entity_type][entity_image_spec.entity_key]
        link = entity_images_service.attach(
            db,
            image_id=image_key_to_id[entity_image_spec.image_key],
            entity_type=entity_image_spec.entity_type,
            entity_id=entity_id,
            role=entity_image_spec.role,
        )
        if entity_image_spec.order_index is not None:
            link.order_index = entity_image_spec.order_index
    db.commit()


def _seed_relationships(db: Session, codex_key_to_id: dict[str, str]) -> None:
    for rel_spec in content.RELATIONSHIPS:
        codex_service.create_relationship(
            db,
            codex_key_to_id[rel_spec.from_key],
            codex_key_to_id[rel_spec.to_key],
            rel_spec.relationship_type,
            rel_spec.description,
        )


def _seed_arc_states(
    db: Session, book_key_to_id: dict[str, str], codex_key_to_id: dict[str, str]
) -> None:
    for arc_spec in content.ARC_STATES:
        codex_service.create_arc_state(
            db,
            codex_key_to_id[arc_spec.codex_key],
            book_key_to_id[arc_spec.book_key],
            arc_spec.as_of_outline_order_index,
            arc_spec.status_summary,
            arc_spec.traits_snapshot,
        )


def _seed_edges(
    db: Session, book_key_to_id: dict[str, str], scene_key_to_id: dict[str, str]
) -> None:
    # RULE 1: SceneConnection rows are written DIRECTLY via the ORM — never
    # canvas_service.create_edge, which also writes an UndoLog row that would arm the
    # canvas Undo button to delete sample content (see module docstring).
    for book_spec in content.BOOKS:
        book_id = book_key_to_id[book_spec.key]
        for edge_spec in book_spec.edges:
            db.add(
                SceneConnection(
                    id=new_uuid(),
                    book_id=book_id,
                    source_scene_id=scene_key_to_id[edge_spec.source_key],
                    target_scene_id=scene_key_to_id[edge_spec.target_key],
                    source_handle=None,
                    target_handle=None,
                    connection_type=edge_spec.connection_type,
                    label=edge_spec.label,
                    sequence_weight=edge_spec.sequence_weight,
                )
            )
    db.commit()


def _seed_screenplay_elements(db: Session, scene_key_to_id: dict[str, str]) -> None:
    for element_spec in content.SCREENPLAY_ELEMENTS:
        db.add(
            ScreenplayElement(
                id=new_uuid(),
                scene_id=scene_key_to_id[element_spec.scene_key],
                order_index=element_spec.order_index,
                element_type=element_spec.element_type,
                text=element_spec.text,
            )
        )
    db.commit()


def _seed_revisions(db: Session, scene_key_to_id: dict[str, str]) -> None:
    # RULE 3: SceneRevision rows are hand-built from content.REVISIONS (not produced by
    # calling scene_service.update_scene repeatedly) so all four change_source values are
    # exercised — see module docstring.
    revisions_by_scene: dict[str, list] = {}
    for revision_spec in content.REVISIONS:
        revisions_by_scene.setdefault(revision_spec.scene_key, []).append(revision_spec)

    for scene_key, revision_specs in revisions_by_scene.items():
        parent_id: str | None = None
        for revision_spec in sorted(revision_specs, key=lambda r: r.revision_number):
            revision_id = new_uuid()
            db.add(
                SceneRevision(
                    id=revision_id,
                    scene_id=scene_key_to_id[scene_key],
                    revision_number=revision_spec.revision_number,
                    title=revision_spec.title,
                    description=revision_spec.description,
                    status=revision_spec.status,
                    change_source=revision_spec.change_source,
                    parent_revision_id=parent_id,
                    note=revision_spec.note,
                )
            )
            # Flush so each revision's row exists before the next one in the chain
            # references it as parent_revision_id (self-referential FK on the same table).
            db.flush()
            parent_id = revision_id
    db.commit()


def _seed_continuity_flags(
    db: Session,
    book_key_to_id: dict[str, str],
    scene_key_to_id: dict[str, str],
    codex_key_to_id: dict[str, str],
) -> None:
    for flag_spec in content.CONTINUITY_FLAGS:
        db.add(
            ContinuityFlag(
                id=new_uuid(),
                book_id=book_key_to_id[flag_spec.book_key],
                scene_id=(
                    scene_key_to_id.get(flag_spec.scene_key) if flag_spec.scene_key else None
                ),
                codex_entry_id=(
                    codex_key_to_id.get(flag_spec.codex_key) if flag_spec.codex_key else None
                ),
                flag_type=flag_spec.flag_type,
                severity=flag_spec.severity,
                description=flag_spec.description,
                status=flag_spec.status,
                source=flag_spec.source,
            )
        )
    db.commit()


def _write_marker(db: Session, book_ids: list[str]) -> None:
    db.add(
        AppSetting(
            id=new_uuid(),
            user_id=None,
            key=_MARKER_KEY,
            value={"version": 1, "seeded_at": utcnow_iso(), "book_ids": book_ids},
        )
    )
    db.commit()


def _seed_all(db: Session, created: dict[str, list[str]]) -> list[str]:
    book_key_to_id = _seed_books(db, created)
    chapter_key_to_id = _seed_chapters(db, book_key_to_id)
    image_key_to_id = _seed_images(db, book_key_to_id, created)
    scene_key_to_id = _seed_scenes(db, created)
    _seed_canvas_links(db, book_key_to_id, scene_key_to_id)
    _seed_order_rows(db, book_key_to_id, scene_key_to_id, chapter_key_to_id)
    codex_key_to_id = _seed_codex_entries(db, image_key_to_id, created)
    _seed_codex_links(db, book_key_to_id, scene_key_to_id, codex_key_to_id)
    _seed_entity_images(db, book_key_to_id, scene_key_to_id, codex_key_to_id, image_key_to_id)
    _seed_relationships(db, codex_key_to_id)
    _seed_arc_states(db, book_key_to_id, codex_key_to_id)
    _seed_edges(db, book_key_to_id, scene_key_to_id)
    _seed_screenplay_elements(db, scene_key_to_id)
    _seed_revisions(db, scene_key_to_id)
    _seed_continuity_flags(db, book_key_to_id, scene_key_to_id, codex_key_to_id)
    return [book_key_to_id[book_spec.key] for book_spec in content.BOOKS]


def _best_effort_cleanup(db: Session, created: dict[str, list[str]]) -> None:
    """Defensive, simple cleanup after a failed seed — not guaranteed perfect, just
    determined not to leave a half-seeded library sitting there silently. Each delete is
    independently best-effort: one failure is logged and does not stop the rest.

    Order matters: Books first (cascades book_scene_links/book_scene_order/
    scene_connections/book_codex_links/codex_arc_states/chapters/continuity_flags/
    draft_versions — see book_service.py's module docstring), THEN the canonical
    Scenes/CodexEntries/Images those Books referenced but do NOT cascade-delete.
    """
    try:
        db.rollback()
    except Exception:  # noqa: BLE001 — best-effort, must not mask the original error
        logger.exception("sample_library cleanup: rollback failed")

    for book_id in created.get("books", []):
        try:
            book_service.delete_book(db, book_id)
        except Exception:  # noqa: BLE001
            logger.exception("sample_library cleanup: failed to delete book %s", book_id)
    for scene_id in created.get("scenes", []):
        try:
            scene_service.delete_scene(db, scene_id)
        except Exception:  # noqa: BLE001
            logger.exception("sample_library cleanup: failed to delete scene %s", scene_id)
    for codex_id in created.get("codex_entries", []):
        try:
            codex_service.delete_entry(db, codex_id)
        except Exception:  # noqa: BLE001
            logger.exception("sample_library cleanup: failed to delete codex entry %s", codex_id)
    for image_id in created.get("images", []):
        try:
            images_service.delete_image(db, image_id)
        except Exception:  # noqa: BLE001
            logger.exception("sample_library cleanup: failed to delete image %s", image_id)


def seed_sample_library(db: Session) -> int:
    """Seed the four demo Books from ``content.py`` into a fresh/empty library.

    Returns the number of Books seeded, or ``0`` if skipped (see the guard in the module
    docstring). Idempotent and non-destructive: never touches an existing library, never
    re-seeds after the marker is written, and on failure cleans up any partial rows it
    created rather than leaving them behind (see ``_best_effort_cleanup``) before
    re-raising.
    """
    if os.environ.get(_SKIP_ENV_VAR) == "1":
        return 0
    if _already_seeded(db):
        return 0

    created: dict[str, list[str]] = {
        "books": [],
        "scenes": [],
        "codex_entries": [],
        "images": [],
    }
    try:
        book_ids = _seed_all(db, created)
    except Exception:
        logger.exception(
            "Sample library seeding failed partway through; rolling back and cleaning up "
            "any partially-created rows so the library is left empty rather than half-seeded."
        )
        _best_effort_cleanup(db, created)
        raise

    _write_marker(db, book_ids)
    return len(book_ids)
