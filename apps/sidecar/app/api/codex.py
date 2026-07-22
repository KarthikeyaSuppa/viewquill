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
from app.models.schemas import CodexEntryCreate, CodexEntryRead, CodexEntryUpdate
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
