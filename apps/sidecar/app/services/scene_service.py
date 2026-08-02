"""Scene CRUD — the canonical node entity behind the Node Canvas (docs/01-PRODUCT-VISION.md,
docs/03-DATA-MODEL.md `scenes`, docs/06 Phase 2).

Scenes are canonical and shared across Books (like Codex entries) — this module only
manages the scene row itself; per-Book canvas placement/links are separate tables
(``book_scene_links``, ``book_scene_order``) added by later Phase 2 tasks.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.base import new_uuid, utcnow_iso
from app.models.orm import (
    BookSceneLink,
    Scene,
    SceneMerge,
    SceneRevision,
    ScreenplayElement,
    UndoLog,
)
from app.services import search_index_service, undo_service

_REVISIONED_FIELDS = ("title", "description", "status")


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Plain JSON-safe dict of a row's own columns — no relationships, no lazy loads.

    Same pattern as ``bundle_export._row_to_dict`` (Phase 7), reimplemented here rather
    than imported since that module is reviewer-gated and this is a two-line helper.
    """
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def _word_count(description: str | None) -> int:
    if not description:
        return 0
    return len(description.split())


def create_scene(
    db: Session,
    *,
    node_type: str,
    title: str,
    description: str | None = None,
) -> Scene:
    scene = Scene(
        id=new_uuid(),
        node_type=node_type,
        title=title,
        description=description,
        word_count=_word_count(description),
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)
    # Embed-on-save (Phase 10 task 3, PHASE10.md) — derived data, never blocks this save;
    # see search_index_service's module docstring.
    search_index_service.upsert_entity("scene", scene.id, scene.title, scene.description)
    return scene


def list_scenes(db: Session) -> list[Scene]:
    return list(db.execute(select(Scene).order_by(Scene.updated_at.desc())).scalars())


def get_scene(db: Session, scene_id: str) -> Scene | None:
    return db.get(Scene, scene_id)


def _record_revision_if_changed(db: Session, scene: Scene, values: dict[str, Any]) -> None:
    """Snapshot the scene's pre-update title/description/status into ``scene_revisions``
    (Workstream B history) — but only when this update actually changes at least one of
    those fields. A patch that only touches unrelated keys (or repeats the current values)
    must not produce a no-op revision row.
    """
    changed = any(
        field in values and values[field] != getattr(scene, field) for field in _REVISIONED_FIELDS
    )
    if not changed:
        return
    latest = db.execute(
        select(SceneRevision)
        .where(SceneRevision.scene_id == scene.id)
        .order_by(SceneRevision.revision_number.desc())
    ).scalars().first()
    revision = SceneRevision(
        id=new_uuid(),
        scene_id=scene.id,
        revision_number=(latest.revision_number if latest else 0) + 1,
        title=scene.title,
        description=scene.description,
        status=scene.status,
        change_source="manual_edit",
        parent_revision_id=latest.id if latest else None,
        created_at=utcnow_iso(),
    )
    db.add(revision)


def update_scene(db: Session, scene_id: str, values: dict[str, Any]) -> Scene | None:
    """Partial update — only keys present in ``values`` are applied.

    Recomputes ``word_count`` whenever ``description`` is one of the changed keys.
    Before applying, snapshots the scene's pre-update title/description/status into a
    ``SceneRevision`` row (Workstream B history) if any of those fields actually change.
    """
    scene = db.get(Scene, scene_id)
    if scene is None:
        return None
    _record_revision_if_changed(db, scene, values)
    for key, value in values.items():
        setattr(scene, key, value)
    if "description" in values:
        scene.word_count = _word_count(scene.description)
    # `updated_at` has an `onupdate` default, but that only fires on a flush that detects a
    # change; touch it explicitly so a no-op-looking patch still bumps the timestamp.
    scene.updated_at = utcnow_iso()
    db.commit()
    db.refresh(scene)
    # Embed-on-save (Phase 10 task 3) — re-index unconditionally so the search index never
    # drifts from the saved row, even on a patch that didn't touch title/description.
    search_index_service.upsert_entity("scene", scene.id, scene.title, scene.description)
    return scene


def list_revisions(db: Session, scene_id: str) -> list[SceneRevision]:
    """Revision history for one scene, newest-first (Workstream B history)."""
    return list(
        db.execute(
            select(SceneRevision)
            .where(SceneRevision.scene_id == scene_id)
            .order_by(SceneRevision.revision_number.desc())
        ).scalars()
    )


def _build_delete_undo_payload(db: Session, scene: Scene) -> dict[str, Any] | None:
    """Reconstruction snapshot for a permanent-delete tombstone (Workstream B undo).

    Captures the ``Scene`` row itself, every ``BookSceneLink`` referencing it (a Scene
    is canonical and CAN be linked onto more than one Book's canvas — see
    ``canvas_service`` module docstring — so this is a list, not a single link), its
    ``ScreenplayElement`` rows, its ``SceneRevision`` history rows, and any ``SceneMerge``
    rows that reference it, all as plain JSON-safe dicts (``_row_to_dict``). Returns
    ``None`` if the scene has no ``BookSceneLink`` at all — there's no ``book_id`` to
    file the ``UndoLog`` row under, so nothing is written in that (currently only
    reachable via a direct service call, never via the API which always creates a link
    on add-to-canvas) edge case.

    ``SceneRevision`` rows are ``ON DELETE CASCADE`` (they're gone once the Scene is
    deleted, same as links/elements) so they're captured for full reinsertion. ``SceneMerge``
    rows are ``ON DELETE SET NULL`` instead — the row itself survives the delete, only its
    ``merged_scene_id``/``source_scene_id`` column pointing at this scene goes ``NULL`` — so
    they're captured here to let undo restore those two columns' original values rather than
    reinsert a row.
    """
    links = list(
        db.execute(
            select(BookSceneLink).where(BookSceneLink.scene_id == scene.id)
        ).scalars()
    )
    if not links:
        return None
    elements = list(
        db.execute(
            select(ScreenplayElement)
            .where(ScreenplayElement.scene_id == scene.id)
            .order_by(ScreenplayElement.order_index)
        ).scalars()
    )
    revisions = list(
        db.execute(
            select(SceneRevision)
            .where(SceneRevision.scene_id == scene.id)
            .order_by(SceneRevision.revision_number.asc())
        ).scalars()
    )
    merges = list(
        db.execute(
            select(SceneMerge).where(
                or_(SceneMerge.merged_scene_id == scene.id, SceneMerge.source_scene_id == scene.id)
            )
        ).scalars()
    )
    return {
        "scene": _row_to_dict(scene),
        "book_scene_links": [_row_to_dict(link) for link in links],
        "screenplay_elements": [_row_to_dict(element) for element in elements],
        "scene_revisions": [_row_to_dict(revision) for revision in revisions],
        "scene_merges": [_row_to_dict(merge) for merge in merges],
    }


def delete_scene(db: Session, scene_id: str) -> bool:
    scene = db.get(Scene, scene_id)
    if scene is None:
        return False
    # Workstream B undo (task 6): snapshot enough to reconstruct this Scene BEFORE the
    # delete, in the same transaction, so a failed commit rolls back both the tombstone
    # and the delete together. Nothing reads this row back yet (task 7 builds /undo).
    payload = _build_delete_undo_payload(db, scene)
    if payload is not None:
        db.add(
            UndoLog(
                id=new_uuid(),
                book_id=payload["book_scene_links"][0]["book_id"],
                action_type="delete_scene",
                payload=payload,
                created_at=utcnow_iso(),
                sequence=undo_service.next_sequence(db),
            )
        )
    db.delete(scene)
    db.commit()
    # Virtual tables (search_fts/embeddings) aren't real FK targets, so there's no DB-level
    # cascade delete for them — clean up the index row explicitly (Phase 10 task 3).
    search_index_service.delete_entity("scene", scene_id)
    return True
