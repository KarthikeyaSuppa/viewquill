"""/books/{book_id}/outline and /books/{book_id}/timeline — the mediator that backs BOTH
the Outline (beat-board) and Timeline views (docs/03-DATA-MODEL.md `book_scene_order`,
docs/06 Phase 4 task BE-3).

There is exactly ONE ``book_scene_order`` row per (book_id, scene_id) pair, carrying the
Outline position (chapter/beat/order_index) AND the Timeline position (order_index/
label/sort_key) side by side — see app/services/outline_service.py module docstring. Every
route below funnels through ``outline_service.get_or_create_order_row`` (directly or via
assign/set/reorder) so a scene's row for a Book is reused, never duplicated.

DATA-SENSITIVE (read-only elsewhere): ``prompt_builder.build_codex_context`` reads
``outline_order_index`` off this same table for its anti-spoiler filter — this module (via
``outline_service``) is the only writer of that column.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import (
    AssignSceneRequest,
    BookSceneOrderRead,
    ReorderRequest,
    TimelineSetRequest,
)
from app.services import outline_service

router = APIRouter(tags=["outline"])


def _handle_value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code == "BOOK_NOT_FOUND":
        return HTTPException(status_code=404, detail="Book not found")
    if code == "SCENE_NOT_FOUND":
        return HTTPException(status_code=404, detail="Scene not found")
    if code == "CHAPTER_MISMATCH":
        return HTTPException(
            status_code=422, detail="Chapter does not belong to this Book"
        )
    raise exc


@router.get("/books/{book_id}/outline", response_model=list[BookSceneOrderRead])
def get_outline(book_id: str, db: Session = Depends(get_db)) -> list[BookSceneOrderRead]:
    return [
        BookSceneOrderRead.model_validate(row)
        for row in outline_service.list_outline(db, book_id)
    ]


@router.get("/books/{book_id}/timeline", response_model=list[BookSceneOrderRead])
def get_timeline(book_id: str, db: Session = Depends(get_db)) -> list[BookSceneOrderRead]:
    return [
        BookSceneOrderRead.model_validate(row)
        for row in outline_service.list_timeline(db, book_id)
    ]


@router.post(
    "/books/{book_id}/scenes/{scene_id}/assign",
    response_model=BookSceneOrderRead,
    status_code=status.HTTP_200_OK,
)
def assign_scene(
    book_id: str, scene_id: str, payload: AssignSceneRequest, db: Session = Depends(get_db)
) -> BookSceneOrderRead:
    try:
        row = outline_service.assign_scene(
            db, book_id, scene_id, payload.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise _handle_value_error(exc) from exc
    return BookSceneOrderRead.model_validate(row)


@router.post("/books/{book_id}/outline/reorder", response_model=list[BookSceneOrderRead])
def reorder_outline(
    book_id: str, payload: ReorderRequest, db: Session = Depends(get_db)
) -> list[BookSceneOrderRead]:
    try:
        outline_service.reorder_outline(db, book_id, payload.scene_ids)
    except ValueError as exc:
        raise _handle_value_error(exc) from exc
    return [
        BookSceneOrderRead.model_validate(row)
        for row in outline_service.list_outline(db, book_id)
    ]


@router.post(
    "/books/{book_id}/scenes/{scene_id}/timeline",
    response_model=BookSceneOrderRead,
    status_code=status.HTTP_200_OK,
)
def set_timeline(
    book_id: str, scene_id: str, payload: TimelineSetRequest, db: Session = Depends(get_db)
) -> BookSceneOrderRead:
    try:
        row = outline_service.set_timeline(
            db, book_id, scene_id, payload.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise _handle_value_error(exc) from exc
    return BookSceneOrderRead.model_validate(row)


@router.post("/books/{book_id}/timeline/reorder", response_model=list[BookSceneOrderRead])
def reorder_timeline(
    book_id: str, payload: ReorderRequest, db: Session = Depends(get_db)
) -> list[BookSceneOrderRead]:
    try:
        outline_service.reorder_timeline(db, book_id, payload.scene_ids)
    except ValueError as exc:
        raise _handle_value_error(exc) from exc
    return [
        BookSceneOrderRead.model_validate(row)
        for row in outline_service.list_timeline(db, book_id)
    ]
