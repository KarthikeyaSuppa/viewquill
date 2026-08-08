"""Scoped undo/redo for the last reversible destructive action per Book (Workstream B
task 7, PHASE11.md). Builds on the ``UndoLog`` tombstone rows ``scene_service.delete_scene``
already writes (task 6) — this module is what actually reads them back.

``delete_scene`` (task 6) and ``merge_scenes`` (``merge_service.accept_merge``, task
WS-B10) both produce ``UndoLog`` rows this module reverses. The ``merge_scenes`` case is
deliberately "soft": undo/redo only ever toggle ``BookSceneLink.archived_at`` on the
merged scene's link and each source's link — the merged ``Scene`` row and its
``SceneRevision``/``SceneMerge`` history rows are never deleted by either direction, since
that history must survive even after an undo (see ``_restore_merge_scenes``).

``create_edge``/``delete_edge``/``update_edge`` (written by ``canvas_service.py``'s edge
CRUD, a separate task) round out the set: ``create_edge``/``delete_edge`` are hard
create/destroy pairs following ``delete_scene``'s snapshot-based shape (undo/redo either
re-insert or re-delete a full ``SceneConnection`` row from ``payload["edge"]``), while
``update_edge`` follows ``merge_scenes``'s before/after toggle shape for the
``connection_type``/``sequence_weight`` edit case (``payload["before"]``/``payload["after"]``
dicts of just the changed columns).

``undo_last_action`` and ``redo_last_action`` toggle the SAME ``UndoLog`` row's ``undone_at``
back and forth — undo sets it, redo clears it — rather than ever writing a second row. Redo
never creates a new ``UndoLog`` entry (it would be recursive: redoing a delete is itself a
delete, which must NOT be undo-loggable, or "undo" would become an infinite chain).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow_iso
from app.models.orm import (
    BookSceneLink,
    Scene,
    SceneConnection,
    SceneMerge,
    SceneRevision,
    ScreenplayElement,
    UndoLog,
)
from app.services import search_index_service

# Sentinel raised when an undo/redo expects to find a specific row (a BookSceneLink or a
# Scene from a prior action's payload) and it's gone — e.g. hard-deleted or otherwise
# removed via an ordinary (non-undo) path in the meantime. Must never be swallowed: the
# alternative (silently skipping that piece of the restoration) would let the API return
# 200 for an undo/redo that only partially applied.
UNDO_TARGET_ROW_MISSING = "UNDO_TARGET_ROW_MISSING"


def next_sequence(db: Session) -> int:
    """Next value for ``UndoLog.sequence`` — a plain incrementing counter computed in
    Python (compute-max-then-add-one), the same pattern ``scene_service.py`` already uses
    for ``SceneRevision.revision_number``, rather than SQLite `AUTOINCREMENT` (which only
    applies to an `INTEGER PRIMARY KEY` rowid alias, not available here since ``id`` is a
    text uuid). Exists to break ties when two ``UndoLog`` rows share the same
    ``created_at`` second (``utcnow_iso`` only has 1-second resolution).
    """
    current_max = db.execute(select(func.max(UndoLog.sequence))).scalar()
    return (current_max or 0) + 1


def _latest_active_undo_log(db: Session, book_id: str) -> UndoLog | None:
    """Most recent not-yet-undone ``UndoLog`` row for this Book (``undone_at IS NULL``).

    Ordered by ``created_at`` DESC with ``sequence`` DESC as a tiebreaker — see
    ``UndoLog.sequence``'s docstring in ``app/models/orm.py``.
    """
    return db.execute(
        select(UndoLog)
        .where(UndoLog.book_id == book_id, UndoLog.undone_at.is_(None))
        .order_by(UndoLog.created_at.desc(), UndoLog.sequence.desc())
    ).scalars().first()


def _latest_undone_undo_log(db: Session, book_id: str) -> UndoLog | None:
    """Most recently-undone ``UndoLog`` row for this Book (``undone_at IS NOT NULL``).

    Ordered by ``undone_at`` DESC with ``sequence`` DESC as a tiebreaker, same rationale as
    ``_latest_active_undo_log``.
    """
    return db.execute(
        select(UndoLog)
        .where(UndoLog.book_id == book_id, UndoLog.undone_at.is_not(None))
        .order_by(UndoLog.undone_at.desc(), UndoLog.sequence.desc())
    ).scalars().first()


def get_undo_status(db: Session, book_id: str) -> dict[str, bool]:
    """Whether ``undo``/``redo`` currently have anything to do for this Book, WITHOUT
    performing either — the read-only counterpart to ``undo_last_action``/
    ``redo_last_action``, meant to back a status endpoint the frontend can poll instead of
    inferring "nothing available" from a 404 error toast.

    ``can_undo`` mirrors ``undo_last_action``'s own not-found check exactly: true iff
    ``_latest_active_undo_log`` finds a row.

    ``can_redo`` is NOT simply "``_latest_undone_undo_log`` finds a row" — that row can be
    stale. If a newer destructive action happened for this Book after the undo (i.e. some
    other ``UndoLog`` row for this Book now has a higher ``sequence``), that undone row is
    no longer the most recent action overall, and ``redo_last_action`` re-applying it would
    silently resurrect something the user has since moved past. So ``can_redo`` also
    requires that no other row for this Book has a higher ``sequence`` than the undone row.
    """
    can_undo = _latest_active_undo_log(db, book_id) is not None

    undone = _latest_undone_undo_log(db, book_id)
    can_redo = False
    if undone is not None:
        newer_row_exists = db.execute(
            select(UndoLog.id).where(
                UndoLog.book_id == book_id, UndoLog.sequence > undone.sequence
            )
        ).first()
        can_redo = newer_row_exists is None

    return {"can_undo": can_undo, "can_redo": can_redo}


def _restore_delete_scene(db: Session, payload: dict[str, Any]) -> None:
    """Reverse of ``scene_service._build_delete_undo_payload`` — re-insert the Scene row,
    then each ``BookSceneLink``, ``ScreenplayElement``, and ``SceneRevision`` (parent-before-
    children, since all three FK onto the scene), from their plain JSON-safe dicts. All
    columns on these tables are stored as plain strings/numbers/JSON (UUID text ids,
    ISO-8601 text timestamps) — no datetime/enum coercion is needed to round-trip a dict
    back into the ORM constructor.

    ``SceneMerge`` rows are handled differently: unlike the other three, they were never
    deleted (``ON DELETE SET NULL``, not CASCADE — see ``SceneMerge``'s docstring in
    ``app/models/orm.py``) — only their ``merged_scene_id``/``source_scene_id`` column
    pointing at this scene was nulled out. So instead of reinserting, restore those two
    columns on the still-existing row to their captured pre-delete values.
    """
    scene_values = payload["scene"]
    scene = Scene(**scene_values)
    db.add(scene)
    # Flush the Scene insert first — book_scene_links/screenplay_elements/scene_revisions FK
    # onto it, and SQLite enforces FKs immediately (PRAGMA foreign_keys=ON, app/db/base.py),
    # so the parent row must exist before the children are inserted.
    db.flush()

    for link_values in payload["book_scene_links"]:
        db.add(BookSceneLink(**link_values))

    for element_values in payload["screenplay_elements"]:
        db.add(ScreenplayElement(**element_values))

    # Ascending revision_number order (how scene_service captured them) so a revision's
    # parent_revision_id always points at an already-inserted row.
    for revision_values in payload.get("scene_revisions", []):
        db.add(SceneRevision(**revision_values))

    for merge_values in payload.get("scene_merges", []):
        merge = db.get(SceneMerge, merge_values["id"])
        if merge is not None:
            merge.merged_scene_id = merge_values["merged_scene_id"]
            merge.source_scene_id = merge_values["source_scene_id"]

    db.commit()
    # Embed-on-save (Phase 10 task 3) — a restored Scene must reappear in search just like a
    # freshly-created one; scene_service.delete_scene removed its index row on delete.
    search_index_service.upsert_entity("scene", scene.id, scene.title, scene.description)


def _redo_delete_scene(db: Session, payload: dict[str, Any]) -> None:
    """Re-apply the original delete: remove the same Scene row (and, via each table's
    ``ondelete=CASCADE`` + this app's ``PRAGMA foreign_keys=ON``, its ``BookSceneLink``/
    ``ScreenplayElement`` rows go with it) without writing a new ``UndoLog`` row.

    Raises ``UNDO_TARGET_ROW_MISSING`` if the Scene ``_restore_delete_scene`` re-inserted is
    already gone (e.g. hard-deleted again via the ordinary delete path since the undo) —
    silently no-op'ing here would make redo report success without actually reversing
    anything.
    """
    scene_id = payload["scene"]["id"]
    scene = db.get(Scene, scene_id)
    if scene is None:
        raise ValueError(UNDO_TARGET_ROW_MISSING)
    db.delete(scene)
    db.commit()
    search_index_service.delete_entity("scene", scene_id)


def _restore_merge_scenes(db: Session, book_id: str, payload: dict[str, Any]) -> None:
    """Reverse of ``merge_service.accept_merge`` (WS-B10).

    Deliberately "soft": undo archives the merged scene's own ``BookSceneLink`` (pulls the
    merged node off the canvas) and un-archives each source's ``BookSceneLink``, restoring
    its EXACT pre-merge column values (position, color, ``added_at``) from the frozen
    snapshot ``accept_merge`` took before archiving. The merged ``Scene`` row itself, and
    its ``SceneRevision``/``SceneMerge`` history rows, are NEVER deleted here — per
    PHASE11.md's "sources are soft-archived, never hard-deleted, so a merge is always
    reversible" design, the merge's history is a permanent record even once undone; only
    its *canvas presence* is what undo toggles, exactly like ``_restore_delete_scene`` vs.
    ``_redo_delete_scene`` toggle a Scene's *existence* for the delete_scene case.

    Raises ``UNDO_TARGET_ROW_MISSING`` if the merged scene's link, or any source's link, is
    no longer present (e.g. hard-deleted or unlinked via the ordinary canvas-remove path
    since the merge) — validated up front (before any write) so a missing row aborts the
    whole undo instead of silently applying a partial one.
    """
    merged_scene_id = payload["merged_scene_id"]
    merged_link = db.execute(
        select(BookSceneLink).where(
            BookSceneLink.book_id == book_id, BookSceneLink.scene_id == merged_scene_id
        )
    ).scalar_one_or_none()
    if merged_link is None:
        raise ValueError(UNDO_TARGET_ROW_MISSING)

    source_links: list[tuple[BookSceneLink, dict[str, Any]]] = []
    for source in payload["sources"]:
        link_values = source["book_scene_link"]
        link = db.get(BookSceneLink, link_values["id"])
        if link is None:
            raise ValueError(UNDO_TARGET_ROW_MISSING)
        source_links.append((link, link_values))

    merged_link.archived_at = utcnow_iso()
    for link, link_values in source_links:
        for key, value in link_values.items():
            setattr(link, key, value)

    db.commit()


def _redo_merge_scenes(db: Session, book_id: str, payload: dict[str, Any]) -> None:
    """Re-apply a previously-undone merge: re-archive each source's ``BookSceneLink`` and
    un-archive the merged scene's link again — the exact mirror of
    ``_restore_merge_scenes``. Writes no new ``UndoLog`` row (same rule as
    ``_redo_delete_scene``).

    Raises ``UNDO_TARGET_ROW_MISSING`` under the same conditions as ``_restore_merge_scenes``
    — validated up front so a missing row aborts the whole redo instead of silently applying
    a partial one.
    """
    merged_scene_id = payload["merged_scene_id"]
    merged_link = db.execute(
        select(BookSceneLink).where(
            BookSceneLink.book_id == book_id, BookSceneLink.scene_id == merged_scene_id
        )
    ).scalar_one_or_none()
    if merged_link is None:
        raise ValueError(UNDO_TARGET_ROW_MISSING)

    source_links: list[BookSceneLink] = []
    for source in payload["sources"]:
        link_values = source["book_scene_link"]
        link = db.get(BookSceneLink, link_values["id"])
        if link is None:
            raise ValueError(UNDO_TARGET_ROW_MISSING)
        source_links.append(link)

    merged_link.archived_at = None
    archive_ts = utcnow_iso()
    for link in source_links:
        link.archived_at = archive_ts

    db.commit()


def _restore_create_edge(db: Session, payload: dict[str, Any]) -> None:
    """Reverse of creating a ``SceneConnection`` (canvas edge): the edge didn't exist
    before, so undo just removes it again — the create/destroy mirror of
    ``_restore_delete_scene``/``_redo_delete_scene``, but for the opposite direction (undo
    destroys here instead of re-inserting).

    Raises ``UNDO_TARGET_ROW_MISSING`` if the edge ``canvas_service`` created is already
    gone (e.g. deleted via the ordinary canvas-remove path since the create) — silently
    no-op'ing would make undo report success without actually reversing anything.
    """
    edge_id = payload["edge"]["id"]
    edge = db.get(SceneConnection, edge_id)
    if edge is None:
        raise ValueError(UNDO_TARGET_ROW_MISSING)
    db.delete(edge)
    db.commit()


def _redo_create_edge(db: Session, payload: dict[str, Any]) -> None:
    """Re-apply a previously-undone edge creation: re-insert the exact same
    ``SceneConnection`` row (verbatim ``payload["edge"]`` dict — including ``id`` and
    ``sequence_weight`` — never recomputed) rather than calling back into
    ``canvas_service.create_connection``, mirroring ``_redo_delete_scene``'s "replay the
    captured snapshot" shape.

    Raises ``UNDO_TARGET_ROW_MISSING`` if either Scene the edge points at (``source_scene_id``/
    ``target_scene_id``) has been deleted since the edge was undone — without this guard,
    re-inserting the row would trip SQLite's FK enforcement (``PRAGMA foreign_keys=ON``,
    ``app/db/base.py``) and raise a raw, unhandled ``IntegrityError`` instead of this
    module's clean 409 convention.
    """
    edge_values = payload["edge"]
    if (
        db.get(Scene, edge_values["source_scene_id"]) is None
        or db.get(Scene, edge_values["target_scene_id"]) is None
    ):
        raise ValueError(UNDO_TARGET_ROW_MISSING)
    db.add(SceneConnection(**edge_values))
    db.commit()


def _restore_delete_edge(db: Session, payload: dict[str, Any]) -> None:
    """Reverse of deleting a ``SceneConnection``: re-insert the exact pre-delete row from
    its captured snapshot — the edge equivalent of ``_restore_delete_scene``, but simpler
    since no other table has a ``ForeignKey`` onto ``scene_connections.id`` (confirmed
    against ``app/models/orm.py``), so there are no cascading children to reattach.

    Raises ``UNDO_TARGET_ROW_MISSING`` under the same condition as ``_redo_create_edge`` —
    either endpoint Scene may have been deleted (via the ordinary scene-delete path) since
    the edge was deleted, which would otherwise trip the same raw FK ``IntegrityError``.
    """
    edge_values = payload["edge"]
    if (
        db.get(Scene, edge_values["source_scene_id"]) is None
        or db.get(Scene, edge_values["target_scene_id"]) is None
    ):
        raise ValueError(UNDO_TARGET_ROW_MISSING)
    db.add(SceneConnection(**edge_values))
    db.commit()


def _redo_delete_edge(db: Session, payload: dict[str, Any]) -> None:
    """Re-apply a previously-undone edge deletion: remove the same ``SceneConnection`` row
    again — direct mirror of ``_redo_delete_scene``'s shape.

    Raises ``UNDO_TARGET_ROW_MISSING`` if the edge ``_restore_delete_edge`` re-inserted is
    already gone (e.g. deleted again via the ordinary canvas-remove path since the undo).
    """
    edge_id = payload["edge"]["id"]
    edge = db.get(SceneConnection, edge_id)
    if edge is None:
        raise ValueError(UNDO_TARGET_ROW_MISSING)
    db.delete(edge)
    db.commit()


def _restore_update_edge(db: Session, payload: dict[str, Any]) -> None:
    """Reverse of an in-place edge edit (e.g. the directional/undirected
    ``connection_type`` toggle): apply the captured ``before`` values — the before/after
    toggle shape ``_restore_merge_scenes``/``_redo_merge_scenes`` use, but for a single row's
    changed columns instead of a set of ``BookSceneLink`` rows.

    Raises ``UNDO_TARGET_ROW_MISSING`` if the edge is gone (e.g. deleted via the ordinary
    canvas-remove path since the update).
    """
    edge = db.get(SceneConnection, payload["edge_id"])
    if edge is None:
        raise ValueError(UNDO_TARGET_ROW_MISSING)
    for key, value in payload["before"].items():
        setattr(edge, key, value)
    db.commit()


def _redo_update_edge(db: Session, payload: dict[str, Any]) -> None:
    """Re-apply a previously-undone edge edit: apply the captured ``after`` values — the
    exact mirror of ``_restore_update_edge``.

    Raises ``UNDO_TARGET_ROW_MISSING`` under the same condition as ``_restore_update_edge``.
    """
    edge = db.get(SceneConnection, payload["edge_id"])
    if edge is None:
        raise ValueError(UNDO_TARGET_ROW_MISSING)
    for key, value in payload["after"].items():
        setattr(edge, key, value)
    db.commit()


def undo_last_action(db: Session, book_id: str) -> UndoLog | None:
    """Reverse the most recent not-yet-undone action for this Book, marking it undone.

    Returns ``None`` (caller 404s) if there's nothing left to undo for this Book.
    """
    undo_log = _latest_active_undo_log(db, book_id)
    if undo_log is None:
        return None

    if undo_log.action_type == "delete_scene":
        _restore_delete_scene(db, undo_log.payload)
    elif undo_log.action_type == "merge_scenes":
        _restore_merge_scenes(db, book_id, undo_log.payload)
    elif undo_log.action_type == "create_edge":
        _restore_create_edge(db, undo_log.payload)
    elif undo_log.action_type == "delete_edge":
        _restore_delete_edge(db, undo_log.payload)
    elif undo_log.action_type == "update_edge":
        _restore_update_edge(db, undo_log.payload)

    undo_log.undone_at = utcnow_iso()
    db.commit()
    db.refresh(undo_log)
    return undo_log


def redo_last_action(db: Session, book_id: str) -> UndoLog | None:
    """Re-apply the most recently-undone action for this Book, marking it active again.

    Returns ``None`` (caller 404s) if there's nothing undone left to redo for this Book —
    including when the most-recently-undone row is STALE (a newer destructive action has
    happened for this Book since the undo). This mirrors ``get_undo_status``'s own
    ``can_redo`` staleness check exactly (see its docstring): if some other ``UndoLog`` row
    for this Book now has a higher ``sequence`` than the undone row, that row is no longer
    the most recent action overall, and re-applying it would silently resurrect something
    the user has since moved past — treated the same as "nothing to redo" rather than
    attempted and left to fail (e.g. hitting the FK guards in
    ``_redo_create_edge``/``_restore_delete_edge`` above).
    """
    undo_log = _latest_undone_undo_log(db, book_id)
    if undo_log is None:
        return None

    newer_row_exists = db.execute(
        select(UndoLog.id).where(
            UndoLog.book_id == book_id, UndoLog.sequence > undo_log.sequence
        )
    ).first()
    if newer_row_exists is not None:
        return None

    if undo_log.action_type == "delete_scene":
        _redo_delete_scene(db, undo_log.payload)
    elif undo_log.action_type == "merge_scenes":
        _redo_merge_scenes(db, book_id, undo_log.payload)
    elif undo_log.action_type == "create_edge":
        _redo_create_edge(db, undo_log.payload)
    elif undo_log.action_type == "delete_edge":
        _redo_delete_edge(db, undo_log.payload)
    elif undo_log.action_type == "update_edge":
        _redo_update_edge(db, undo_log.payload)

    undo_log.undone_at = None
    db.commit()
    db.refresh(undo_log)
    return undo_log
