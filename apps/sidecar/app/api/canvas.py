"""Node Canvas endpoints: per-Book scene membership/layout, graph edges, and cross-Book
move/copy (docs/01-PRODUCT-VISION.md, docs/03-DATA-MODEL.md `book_scene_links` /
`scene_connections`, docs/06 Phase 2 tasks A3/A4/A5).

Scenes stay canonical and shared across Books (docs/03) — every endpoint here manages a
Book's *link* to a Scene (or a graph edge), never the canonical Scene row itself, except
``copy`` which deliberately creates a brand-new Scene (see app/services/canvas_service.py
docstring for the data-sensitive rules this module relies on).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import (
    ApplyCanvasTemplateRequest,
    CanvasEdge,
    CanvasNode,
    CanvasResponse,
    EdgeCreate,
    EdgeUpdate,
    LinkCreate,
    LinkUpdate,
    SceneRead,
    UndoActionRead,
    UndoStatusRead,
)
from app.services import (
    book_service,
    canvas_service,
    canvas_template_service,
    scene_service,
    undo_service,
)

router = APIRouter(tags=["canvas"])


def _require_book(db: Session, book_id: str) -> None:
    if book_service.get_book(db, book_id) is None:
        raise HTTPException(status_code=404, detail="Book not found")


def _require_scene(db: Session, scene_id: str) -> None:
    if scene_service.get_scene(db, scene_id) is None:
        raise HTTPException(status_code=404, detail="Scene not found")


# ── Canvas membership + layout ────────────────────────────────────────────────


@router.get("/books/{book_id}/canvas", response_model=CanvasResponse)
def get_canvas(book_id: str, db: Session = Depends(get_db)) -> CanvasResponse:
    _require_book(db, book_id)
    return canvas_service.get_canvas(db, book_id)


@router.post("/books/{book_id}/canvas/apply-template", response_model=CanvasResponse)
def apply_canvas_template(
    book_id: str, payload: ApplyCanvasTemplateRequest, db: Session = Depends(get_db)
) -> CanvasResponse:
    _require_book(db, book_id)
    try:
        return canvas_template_service.apply_template(db, book_id, payload.template_key)
    except canvas_template_service.UnknownCanvasTemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except canvas_template_service.TemplateAlreadyAppliedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/books/{book_id}/scenes/{scene_id}",
    response_model=CanvasNode,
    status_code=status.HTTP_201_CREATED,
)
def add_scene_to_canvas(
    book_id: str,
    scene_id: str,
    payload: LinkCreate = LinkCreate(),
    db: Session = Depends(get_db),
) -> CanvasNode:
    _require_book(db, book_id)
    _require_scene(db, scene_id)
    scene = scene_service.get_scene(db, scene_id)
    link = canvas_service.add_scene_to_canvas(
        db,
        book_id,
        scene_id,
        canvas_x=payload.canvas_x,
        canvas_y=payload.canvas_y,
        color=payload.color,
    )
    return canvas_service.to_canvas_node(link, scene)


@router.patch("/books/{book_id}/scenes/{scene_id}", response_model=CanvasNode)
def update_canvas_link(
    book_id: str, scene_id: str, payload: LinkUpdate, db: Session = Depends(get_db)
) -> CanvasNode:
    _require_book(db, book_id)
    _require_scene(db, scene_id)
    values = payload.model_dump(exclude_unset=True)
    link = canvas_service.update_link(db, book_id, scene_id, values)
    if link is None:
        raise HTTPException(status_code=404, detail="Scene is not on this Book's canvas")
    scene = scene_service.get_scene(db, scene_id)
    return canvas_service.to_canvas_node(link, scene)


@router.delete("/books/{book_id}/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_scene_from_canvas(book_id: str, scene_id: str, db: Session = Depends(get_db)) -> None:
    if not canvas_service.remove_from_canvas(db, book_id, scene_id):
        raise HTTPException(status_code=404, detail="Scene is not on this Book's canvas")


# ── Graph edges — scoped per Book ─────────────────────────────────────────────


@router.get("/books/{book_id}/edges", response_model=list[CanvasEdge])
def list_edges(book_id: str, db: Session = Depends(get_db)) -> list[CanvasEdge]:
    _require_book(db, book_id)
    return [CanvasEdge.model_validate(edge) for edge in canvas_service.list_edges(db, book_id)]


@router.post(
    "/books/{book_id}/edges", response_model=CanvasEdge, status_code=status.HTTP_201_CREATED
)
def create_edge(book_id: str, payload: EdgeCreate, db: Session = Depends(get_db)) -> CanvasEdge:
    _require_book(db, book_id)
    _require_scene(db, payload.source_scene_id)
    _require_scene(db, payload.target_scene_id)
    edge = canvas_service.create_edge(
        db,
        book_id,
        source_scene_id=payload.source_scene_id,
        target_scene_id=payload.target_scene_id,
        source_handle=payload.source_handle,
        target_handle=payload.target_handle,
        connection_type=payload.connection_type,
        label=payload.label,
        sequence_weight=payload.sequence_weight,
    )
    return CanvasEdge.model_validate(edge)


@router.patch("/edges/{edge_id}", response_model=CanvasEdge)
def update_edge(edge_id: str, payload: EdgeUpdate, db: Session = Depends(get_db)) -> CanvasEdge:
    values = payload.model_dump(exclude_unset=True)
    edge = canvas_service.update_edge(db, edge_id, values)
    if edge is None:
        raise HTTPException(status_code=404, detail="Edge not found")
    return CanvasEdge.model_validate(edge)


@router.delete("/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_edge(edge_id: str, db: Session = Depends(get_db)) -> None:
    if not canvas_service.delete_edge(db, edge_id):
        raise HTTPException(status_code=404, detail="Edge not found")


# ── Cross-Book move/copy (docs/06 Phase 2 task A5) ────────────────────────────


@router.post("/books/{dest_book_id}/scenes/{scene_id}/move", response_model=CanvasNode)
def move_scene(
    dest_book_id: str,
    scene_id: str,
    from_book_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CanvasNode:
    _require_book(db, dest_book_id)
    _require_scene(db, scene_id)
    if from_book_id is not None:
        _require_book(db, from_book_id)
        if from_book_id == dest_book_id:
            raise HTTPException(
                status_code=400,
                detail="from_book_id and dest_book_id are the same Book — a no-op move",
            )
    link = canvas_service.move_scene(db, scene_id, dest_book_id, src_book_id=from_book_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    scene = scene_service.get_scene(db, scene_id)
    return canvas_service.to_canvas_node(link, scene)


@router.post(
    "/books/{dest_book_id}/scenes/{scene_id}/copy",
    response_model=SceneRead,
    status_code=status.HTTP_201_CREATED,
)
def copy_scene(dest_book_id: str, scene_id: str, db: Session = Depends(get_db)) -> SceneRead:
    _require_book(db, dest_book_id)
    _require_scene(db, scene_id)
    new_scene = canvas_service.copy_scene(db, scene_id, dest_book_id)
    if new_scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return SceneRead.model_validate(new_scene)


# ── Scoped undo/redo (Workstream B task 7, PHASE11.md) ────────────────────────


def _to_undo_action_read(undo_log) -> UndoActionRead:
    scene_id = None
    scene_payload = undo_log.payload.get("scene") if undo_log.payload else None
    if scene_payload:
        scene_id = scene_payload.get("id")
    edge_id = None
    if undo_log.payload:
        if undo_log.action_type in ("create_edge", "delete_edge"):
            edge_payload = undo_log.payload.get("edge")
            if edge_payload:
                edge_id = edge_payload.get("id")
        elif undo_log.action_type == "update_edge":
            edge_id = undo_log.payload.get("edge_id")
    return UndoActionRead(
        id=undo_log.id,
        action_type=undo_log.action_type,
        scene_id=scene_id,
        edge_id=edge_id,
        undone_at=undo_log.undone_at,
        created_at=undo_log.created_at,
    )


@router.get("/books/{book_id}/undo-status", response_model=UndoStatusRead)
def get_undo_status(book_id: str, db: Session = Depends(get_db)) -> UndoStatusRead:
    _require_book(db, book_id)
    status_dict = undo_service.get_undo_status(db, book_id)
    return UndoStatusRead(**status_dict)


@router.post("/books/{book_id}/undo", response_model=UndoActionRead)
def undo_last_action(book_id: str, db: Session = Depends(get_db)) -> UndoActionRead:
    _require_book(db, book_id)
    try:
        undo_log = undo_service.undo_last_action(db, book_id)
    except ValueError as exc:
        # e.g. UNDO_TARGET_ROW_MISSING — the recorded row to restore is gone (hard-deleted
        # or otherwise removed via an ordinary, non-undo path since the action being
        # undone). A conflict with the current DB state, not a bad request — 409, not 400.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if undo_log is None:
        raise HTTPException(status_code=404, detail="Nothing to undo for this Book")
    return _to_undo_action_read(undo_log)


@router.post("/books/{book_id}/redo", response_model=UndoActionRead)
def redo_last_action(book_id: str, db: Session = Depends(get_db)) -> UndoActionRead:
    _require_book(db, book_id)
    try:
        undo_log = undo_service.redo_last_action(db, book_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if undo_log is None:
        raise HTTPException(status_code=404, detail="Nothing to redo for this Book")
    return _to_undo_action_read(undo_log)
