"""/codex — the Codex (docs/01-PRODUCT-VISION.md, docs/03-DATA-MODEL.md `codex_entries` /
`codex_scene_links` / `book_codex_links`, docs/06 Phase 2 tasks B1/B2).

Codex entries are canonical and shared across Books (like Scenes) — this module owns the
entry row itself plus its links to Scenes and Books, including the scene-scoped
``GET /scenes/{scene_id}/codex`` list endpoint (kept here, not in app/api/scenes.py, since
it's a Codex-owned view).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import (
    CodexArcStateCreate,
    CodexArcStateRead,
    CodexEntryCreate,
    CodexEntryRead,
    CodexEntryUpdate,
    CodexRelationshipCreate,
    CodexRelationshipRead,
)
from app.services import book_service, codex_service, scene_service

router = APIRouter(tags=["codex"])


def _require_entry(db: Session, entry_id: str) -> None:
    if codex_service.get_entry(db, entry_id) is None:
        raise HTTPException(status_code=404, detail="Codex entry not found")


def _require_scene(db: Session, scene_id: str) -> None:
    if scene_service.get_scene(db, scene_id) is None:
        raise HTTPException(status_code=404, detail="Scene not found")


def _require_book(db: Session, book_id: str) -> None:
    if book_service.get_book(db, book_id) is None:
        raise HTTPException(status_code=404, detail="Book not found")


# ── Codex entry CRUD ───────────────────────────────────────────────────────────


@router.post("/codex", response_model=CodexEntryRead, status_code=status.HTTP_201_CREATED)
def create_entry(payload: CodexEntryCreate, db: Session = Depends(get_db)) -> CodexEntryRead:
    entry = codex_service.create_entry(
        db,
        entry_type=payload.entry_type,
        name=payload.name,
        summary=payload.summary,
        custom_fields=payload.custom_fields,
    )
    return CodexEntryRead.model_validate(entry)


@router.get("/codex", response_model=list[CodexEntryRead])
def list_entries(
    entry_type: str | None = Query(default=None), db: Session = Depends(get_db)
) -> list[CodexEntryRead]:
    return [
        CodexEntryRead.model_validate(entry)
        for entry in codex_service.list_entries(db, entry_type=entry_type)
    ]


@router.get("/codex/{entry_id}", response_model=CodexEntryRead)
def get_entry(entry_id: str, db: Session = Depends(get_db)) -> CodexEntryRead:
    entry = codex_service.get_entry(db, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Codex entry not found")
    return CodexEntryRead.model_validate(entry)


@router.patch("/codex/{entry_id}", response_model=CodexEntryRead)
def update_entry(
    entry_id: str, payload: CodexEntryUpdate, db: Session = Depends(get_db)
) -> CodexEntryRead:
    values = payload.model_dump(exclude_unset=True)
    entry = codex_service.update_entry(db, entry_id, values)
    if entry is None:
        raise HTTPException(status_code=404, detail="Codex entry not found")
    return CodexEntryRead.model_validate(entry)


@router.delete("/codex/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: str, db: Session = Depends(get_db)) -> None:
    if not codex_service.delete_entry(db, entry_id):
        raise HTTPException(status_code=404, detail="Codex entry not found")


# ── Scene links ────────────────────────────────────────────────────────────────


@router.post(
    "/codex/{entry_id}/scenes/{scene_id}",
    response_model=CodexEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def link_scene(entry_id: str, scene_id: str, db: Session = Depends(get_db)) -> CodexEntryRead:
    _require_entry(db, entry_id)
    _require_scene(db, scene_id)
    codex_service.link_scene(db, entry_id, scene_id)
    entry = codex_service.get_entry(db, entry_id)
    return CodexEntryRead.model_validate(entry)


@router.delete("/codex/{entry_id}/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_scene(entry_id: str, scene_id: str, db: Session = Depends(get_db)) -> None:
    if not codex_service.unlink_scene(db, entry_id, scene_id):
        raise HTTPException(status_code=404, detail="Codex entry is not linked to this Scene")


@router.get("/scenes/{scene_id}/codex", response_model=list[CodexEntryRead])
def list_codex_for_scene(scene_id: str, db: Session = Depends(get_db)) -> list[CodexEntryRead]:
    _require_scene(db, scene_id)
    return [
        CodexEntryRead.model_validate(entry)
        for entry in codex_service.list_entries_for_scene(db, scene_id)
    ]


# ── Book links ─────────────────────────────────────────────────────────────────


@router.post(
    "/codex/{entry_id}/books/{book_id}",
    response_model=CodexEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def link_book(entry_id: str, book_id: str, db: Session = Depends(get_db)) -> CodexEntryRead:
    _require_entry(db, entry_id)
    _require_book(db, book_id)
    codex_service.link_book(db, entry_id, book_id)
    entry = codex_service.get_entry(db, entry_id)
    return CodexEntryRead.model_validate(entry)


@router.delete("/codex/{entry_id}/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_book(entry_id: str, book_id: str, db: Session = Depends(get_db)) -> None:
    if not codex_service.unlink_book(db, entry_id, book_id):
        raise HTTPException(status_code=404, detail="Codex entry is not linked to this Book")


# ── Entity relationships (Codex entry <-> Codex entry) ─────────────────────────


@router.post(
    "/codex/{entry_id}/relationships",
    response_model=CodexRelationshipRead,
    status_code=status.HTTP_201_CREATED,
)
def create_relationship(
    entry_id: str, payload: CodexRelationshipCreate, db: Session = Depends(get_db)
) -> CodexRelationshipRead:
    _require_entry(db, entry_id)
    try:
        relationship = codex_service.create_relationship(
            db,
            entry_id,
            payload.to_entry_id,
            payload.relationship_type,
            payload.description,
        )
    except ValueError as exc:
        if str(exc) == "SELF_LINK":
            raise HTTPException(
                status_code=422, detail="An entry cannot link to itself."
            ) from exc
        if str(exc) == "ENTRY_NOT_FOUND":
            raise HTTPException(
                status_code=404, detail="Target codex entry not found."
            ) from exc
        if str(exc) == "DUPLICATE":
            raise HTTPException(
                status_code=409, detail="That relationship already exists."
            ) from exc
        raise
    return CodexRelationshipRead.model_validate(relationship)


@router.get("/codex/{entry_id}/relationships", response_model=list[CodexRelationshipRead])
def list_relationships(entry_id: str, db: Session = Depends(get_db)) -> list[CodexRelationshipRead]:
    _require_entry(db, entry_id)
    return [
        CodexRelationshipRead.model_validate(relationship)
        for relationship in codex_service.list_relationships(db, entry_id)
    ]


@router.delete("/codex/relationships/{rel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_relationship(rel_id: str, db: Session = Depends(get_db)) -> None:
    if not codex_service.delete_relationship(db, rel_id):
        raise HTTPException(status_code=404, detail="Relationship not found.")


# ── Arc states (point-in-time entity snapshots; feeds prompt_builder's anti-spoiler filter,
# which is NOT touched by this module) ──────────────────────────────────────────────────────


@router.post(
    "/codex/{entry_id}/arc-states",
    response_model=CodexArcStateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_arc_state(
    entry_id: str, payload: CodexArcStateCreate, db: Session = Depends(get_db)
) -> CodexArcStateRead:
    _require_entry(db, entry_id)
    try:
        arc_state = codex_service.create_arc_state(
            db,
            entry_id,
            payload.book_id,
            payload.as_of_outline_order_index,
            payload.status_summary,
            payload.traits_snapshot,
        )
    except ValueError as exc:
        if str(exc) == "ENTRY_NOT_FOUND":
            raise HTTPException(status_code=404, detail="Codex entry not found.") from exc
        if str(exc) == "BOOK_NOT_FOUND":
            raise HTTPException(status_code=404, detail="Book not found.") from exc
        raise
    return CodexArcStateRead.model_validate(arc_state)


@router.get("/codex/{entry_id}/arc-states", response_model=list[CodexArcStateRead])
def list_arc_states(
    entry_id: str, book_id: str | None = Query(default=None), db: Session = Depends(get_db)
) -> list[CodexArcStateRead]:
    _require_entry(db, entry_id)
    return [
        CodexArcStateRead.model_validate(arc_state)
        for arc_state in codex_service.list_arc_states(db, entry_id, book_id=book_id)
    ]


@router.delete("/codex/arc-states/{arc_state_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_arc_state(arc_state_id: str, db: Session = Depends(get_db)) -> None:
    if not codex_service.delete_arc_state(db, arc_state_id):
        raise HTTPException(status_code=404, detail="Arc state not found.")
