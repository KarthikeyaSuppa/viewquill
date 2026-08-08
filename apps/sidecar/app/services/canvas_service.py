"""Node Canvas: per-Book scene membership/layout (``book_scene_links``) and graph edges
(``scene_connections``), plus cross-Book move/copy (docs/03-DATA-MODEL.md, docs/01
Node Canvas, docs/06 Phase 2 tasks A3/A4/A5).

DATA-SENSITIVE:
* Scenes are canonical and shared across Books (like Codex entries). Removing a Scene
  from a Book's canvas (``remove_from_canvas``) deletes ONLY that Book's ``BookSceneLink``
  row — the ``Scene`` row itself, and its ``ScreenplayElement`` rows, are never touched.
* ``move_scene`` (A5) re-links the SAME canonical Scene into a different Book's canvas —
  it creates zero new ``scenes`` rows. ``copy_scene`` (A5) is the only function here that
  creates a new Scene: it deep-copies the source Scene's fields and its
  ``screenplay_elements`` into brand-new rows (new UUIDs) and never modifies the source.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import new_uuid, utcnow_iso
from app.models.orm import BookSceneLink, Scene, SceneConnection, ScreenplayElement, UndoLog
from app.models.schemas import CanvasEdge, CanvasNode, CanvasResponse
from app.services import undo_service


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Plain JSON-safe dict of a row's own columns — no relationships, no lazy loads.

    Same pattern as ``scene_service._row_to_dict`` (Phase 11 delete_scene undo precedent) —
    reimplemented here rather than imported since that's a private helper local to its
    module.
    """
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def to_canvas_node(link: BookSceneLink, scene: Scene) -> CanvasNode:
    return CanvasNode(
        link_id=link.id,
        scene_id=scene.id,
        node_type=scene.node_type,
        title=scene.title,
        description=scene.description,
        status=scene.status,
        canvas_x=link.canvas_x,
        canvas_y=link.canvas_y,
        color=link.color,
    )


def get_canvas(db: Session, book_id: str) -> CanvasResponse:
    rows = db.execute(
        select(BookSceneLink, Scene)
        .join(Scene, BookSceneLink.scene_id == Scene.id)
        .where(BookSceneLink.book_id == book_id, BookSceneLink.archived_at.is_(None))
    ).all()
    nodes = [to_canvas_node(link, scene) for link, scene in rows]
    edges = [CanvasEdge.model_validate(edge) for edge in list_edges(db, book_id)]
    return CanvasResponse(nodes=nodes, edges=edges)


def _get_link(db: Session, book_id: str, scene_id: str) -> BookSceneLink | None:
    return db.execute(
        select(BookSceneLink).where(
            BookSceneLink.book_id == book_id,
            BookSceneLink.scene_id == scene_id,
            BookSceneLink.archived_at.is_(None),
        )
    ).scalar_one_or_none()


def add_scene_to_canvas(
    db: Session,
    book_id: str,
    scene_id: str,
    *,
    canvas_x: float | None = None,
    canvas_y: float | None = None,
    color: str | None = None,
) -> BookSceneLink:
    """Add an existing Scene to a Book's canvas.

    ``BookSceneLink`` has a UNIQUE(book_id, scene_id) constraint — if the Scene is
    already on this Book's canvas, the existing link is returned unchanged rather than
    creating a duplicate row.
    """
    existing = _get_link(db, book_id, scene_id)
    if existing is not None:
        return existing
    link = BookSceneLink(
        id=new_uuid(),
        book_id=book_id,
        scene_id=scene_id,
        canvas_x=canvas_x,
        canvas_y=canvas_y,
        color=color,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def update_link(
    db: Session, book_id: str, scene_id: str, values: dict[str, Any]
) -> BookSceneLink | None:
    """Partial update of a link's position/color — only keys present in ``values`` change."""
    link = _get_link(db, book_id, scene_id)
    if link is None:
        return None
    for key, value in values.items():
        setattr(link, key, value)
    db.commit()
    db.refresh(link)
    return link


def remove_from_canvas(db: Session, book_id: str, scene_id: str) -> bool:
    """Unlink a Scene from a Book's canvas.

    DATA-SENSITIVE: deletes ONLY the ``BookSceneLink`` row. The canonical ``Scene`` row
    (and its ``screenplay_elements``) MUST survive — it may still be linked to other
    Books, and this function never touches ``scenes`` at all.
    """
    link = _get_link(db, book_id, scene_id)
    if link is None:
        return False
    db.delete(link)
    db.commit()
    return True


# ── Graph edges — scoped per Book ─────────────────────────────────────────────


def list_edges(db: Session, book_id: str) -> list[SceneConnection]:
    return list(
        db.execute(select(SceneConnection).where(SceneConnection.book_id == book_id)).scalars()
    )


def get_edge(db: Session, edge_id: str) -> SceneConnection | None:
    return db.get(SceneConnection, edge_id)


def _next_sequence_weight(db: Session, book_id: str) -> int:
    """Monotonic-with-gaps counter, scoped per Book. sequence_weight is intentionally
    independent of BookSceneOrder's chronological ordering (Phase 11 decision) — this
    is purely a canvas edge-directionality marker. Gap of 10 leaves room to splice a
    directional edge between two existing ones later without a full renumber."""
    current_max = db.execute(
        select(func.max(SceneConnection.sequence_weight)).where(SceneConnection.book_id == book_id)
    ).scalar()
    return (current_max or 0) + 10


def create_edge(
    db: Session,
    book_id: str,
    *,
    source_scene_id: str,
    target_scene_id: str,
    source_handle: str | None = None,
    target_handle: str | None = None,
    connection_type: str | None = None,
    label: str | None = None,
    sequence_weight: int | None = None,
) -> SceneConnection:
    if connection_type == "sequence":
        resolved_weight = (
            sequence_weight if sequence_weight is not None else _next_sequence_weight(db, book_id)
        )
    else:
        resolved_weight = None
    edge_values = {
        "id": new_uuid(),
        "book_id": book_id,
        "source_scene_id": source_scene_id,
        "target_scene_id": target_scene_id,
        "source_handle": source_handle,
        "target_handle": target_handle,
        "connection_type": connection_type,
        "label": label,
        "sequence_weight": resolved_weight,
    }
    edge = SceneConnection(**edge_values)
    db.add(edge)
    # Workstream B undo (Phase 11 follow-up): every column above is already known in
    # Python before any commit (no server-generated column requires a round-trip first),
    # so the UndoLog snapshot is built from `edge_values` directly and both rows commit
    # together in the single db.commit() below — matching delete_edge's single-commit
    # shape (a two-commit version left a crash window between the mutation landing and its
    # undo record landing).
    db.add(
        UndoLog(
            id=new_uuid(),
            book_id=book_id,
            action_type="create_edge",
            payload={"edge": edge_values},
            created_at=utcnow_iso(),
            sequence=undo_service.next_sequence(db),
        )
    )
    db.commit()
    db.refresh(edge)
    return edge


def update_edge(db: Session, edge_id: str, values: dict[str, Any]) -> SceneConnection | None:
    """Partial update — only keys present in ``values`` are applied."""
    edge = db.get(SceneConnection, edge_id)
    if edge is None:
        return None
    if "connection_type" in values:
        if values["connection_type"] == "sequence":
            values.setdefault("sequence_weight", _next_sequence_weight(db, edge.book_id))
        else:
            values["sequence_weight"] = None
    # Workstream B undo: capture pre-update values for exactly the keys about to change.
    # `values` may already contain `sequence_weight` here even if the caller only passed
    # `connection_type` — it's set/cleared as a side effect just above — so this dict
    # captures that silent change too, not just the caller's literal keys.
    before = {key: getattr(edge, key) for key in values}
    for key, value in values.items():
        setattr(edge, key, value)
    # `after` is exactly what was just applied above — no re-query needed, unlike `before`
    # which had to be read off the row prior to mutation.
    after = dict(values)
    # A no-op update (every changed key round-tripped to its own current value) must not
    # create undo noise. Both the mutation and its UndoLog row commit together below —
    # a two-commit version left a crash window between the mutation landing and its undo
    # record landing (same fix as create_edge above).
    if before != after:
        db.add(
            UndoLog(
                id=new_uuid(),
                book_id=edge.book_id,
                action_type="update_edge",
                payload={"edge_id": edge.id, "before": before, "after": after},
                created_at=utcnow_iso(),
                sequence=undo_service.next_sequence(db),
            )
        )
    db.commit()
    db.refresh(edge)
    return edge


def delete_edge(db: Session, edge_id: str) -> bool:
    edge = db.get(SceneConnection, edge_id)
    if edge is None:
        return False
    # Workstream B undo: snapshot the full row BEFORE deleting — same technique as
    # create_edge/scene_service._build_delete_undo_payload — then delete; both writes
    # commit together in the single db.commit() below, matching delete_scene's precedent.
    db.add(
        UndoLog(
            id=new_uuid(),
            book_id=edge.book_id,
            action_type="delete_edge",
            payload={"edge": _row_to_dict(edge)},
            created_at=utcnow_iso(),
            sequence=undo_service.next_sequence(db),
        )
    )
    db.delete(edge)
    db.commit()
    return True


# ── Cross-Book move/copy (docs/06 Phase 2 task A5) ────────────────────────────


def move_scene(
    db: Session, scene_id: str, dest_book_id: str, src_book_id: str | None = None
) -> BookSceneLink | None:
    """Move a canonical Scene onto ``dest_book_id``'s canvas.

    DATA-SENSITIVE (A5, no-duplication): links the SAME Scene id into the destination
    Book (creating zero new ``scenes`` rows, reusing an existing link if one is already
    there) and, only if ``src_book_id`` is given AND differs from ``dest_book_id``,
    removes ONLY that source Book's link. A same-book "move" (``src_book_id ==
    dest_book_id``) is a no-op beyond returning the existing link — it must NOT delete the
    link it just returned (that would wipe the Scene off the canvas and hand back a
    deleted/expired ORM object). Returns ``None`` if the Scene doesn't exist.
    """
    scene = db.get(Scene, scene_id)
    if scene is None:
        return None
    dest_link = add_scene_to_canvas(db, dest_book_id, scene_id)
    if src_book_id is not None and src_book_id != dest_book_id:
        remove_from_canvas(db, src_book_id, scene_id)
    return dest_link


def copy_scene(db: Session, scene_id: str, dest_book_id: str) -> Scene | None:
    """Duplicate a Scene into a brand-new Scene row and link it onto ``dest_book_id``'s canvas.

    DATA-SENSITIVE (A5, no-duplication of the ORIGINAL): creates exactly one new ``Scene``
    row (new UUID) copying node_type/title/description/status/word_count, deep-copies its
    ``screenplay_elements`` into new rows tied to the new scene id, then adds a
    ``BookSceneLink`` for the new scene on ``dest_book_id``. The source Scene and its
    elements are left completely untouched. Returns ``None`` if the source doesn't exist.
    """
    source = db.get(Scene, scene_id)
    if source is None:
        return None

    new_scene = Scene(
        id=new_uuid(),
        node_type=source.node_type,
        title=source.title,
        description=source.description,
        status=source.status,
        word_count=source.word_count,
    )
    db.add(new_scene)

    source_elements = db.execute(
        select(ScreenplayElement)
        .where(ScreenplayElement.scene_id == scene_id)
        .order_by(ScreenplayElement.order_index)
    ).scalars()
    for element in source_elements:
        db.add(
            ScreenplayElement(
                id=new_uuid(),
                scene_id=new_scene.id,
                order_index=element.order_index,
                element_type=element.element_type,
                text=element.text,
            )
        )

    db.commit()
    db.refresh(new_scene)

    add_scene_to_canvas(db, dest_book_id, new_scene.id)
    return new_scene
