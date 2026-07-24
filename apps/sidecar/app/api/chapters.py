"""/books/{book_id}/chapters and /chapters/{chapter_id} — Outline chapter groupings
(docs/03-DATA-MODEL.md `chapters`, docs/06 Phase 4 task BE-2).

Chapters are per-Book (not canonical/shared like Scenes/Codex) — creating one requires an
existing Book; deleting a Book cascades its Chapters (FK ``ondelete="CASCADE"``, see
app/models/orm.py). This module never touches Scene or Book rows themselves.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import ChapterCreate, ChapterRead, ChapterUpdate
from app.services import outline_service

router = APIRouter(tags=["chapters"])


@router.post(
    "/books/{book_id}/chapters", response_model=ChapterRead, status_code=status.HTTP_201_CREATED
)
def create_chapter(
    book_id: str, payload: ChapterCreate, db: Session = Depends(get_db)
) -> ChapterRead:
    try:
        chapter = outline_service.create_chapter(
            db, book_id, payload.title, payload.order_index
        )
    except ValueError as exc:
        if str(exc) == "BOOK_NOT_FOUND":
            raise HTTPException(status_code=404, detail="Book not found") from exc
        raise
    return ChapterRead.model_validate(chapter)


@router.get("/books/{book_id}/chapters", response_model=list[ChapterRead])
def list_chapters(book_id: str, db: Session = Depends(get_db)) -> list[ChapterRead]:
    return [
        ChapterRead.model_validate(chapter)
        for chapter in outline_service.list_chapters(db, book_id)
    ]


@router.patch("/chapters/{chapter_id}", response_model=ChapterRead)
def update_chapter(
    chapter_id: str, payload: ChapterUpdate, db: Session = Depends(get_db)
) -> ChapterRead:
    values = payload.model_dump(exclude_unset=True)
    chapter = outline_service.update_chapter(db, chapter_id, values)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return ChapterRead.model_validate(chapter)


@router.delete("/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chapter(chapter_id: str, db: Session = Depends(get_db)) -> None:
    if not outline_service.delete_chapter(db, chapter_id):
        raise HTTPException(status_code=404, detail="Chapter not found")
