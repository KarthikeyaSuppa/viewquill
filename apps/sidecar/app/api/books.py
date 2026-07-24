"""/books — the Story Library (docs/01-PRODUCT-VISION.md, docs/06 Phase 1).

CRUD for the per-project Book container plus a type-conversion endpoint. Scenes/Codex are
canonical and shared across Books, so deleting a Book only removes its own row and per-book
link/order rows via FK cascade (see app/services/book_service.py docstring).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import BookConvert, BookCreate, BookRead, BookUpdate, ImageRead
from app.services import book_service, entity_images_service, images_service

router = APIRouter(prefix="/books", tags=["books"])


@router.post("", response_model=BookRead, status_code=status.HTTP_201_CREATED)
def create_book(payload: BookCreate, db: Session = Depends(get_db)) -> BookRead:
    book = book_service.create_book(
        db,
        title=payload.title,
        book_type=payload.book_type,
        logline=payload.logline,
        front_matter=payload.front_matter,
    )
    return BookRead.model_validate(book)


@router.get("", response_model=list[BookRead])
def list_books(db: Session = Depends(get_db)) -> list[BookRead]:
    return [BookRead.model_validate(book) for book in book_service.list_books(db)]


@router.get("/{book_id}", response_model=BookRead)
def get_book(book_id: str, db: Session = Depends(get_db)) -> BookRead:
    book = book_service.get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return BookRead.model_validate(book)


@router.patch("/{book_id}", response_model=BookRead)
def update_book(book_id: str, payload: BookUpdate, db: Session = Depends(get_db)) -> BookRead:
    values = payload.model_dump(exclude_unset=True)
    book = book_service.update_book(db, book_id, values)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return BookRead.model_validate(book)


@router.post("/{book_id}/convert", response_model=BookRead)
def convert_book_type(
    book_id: str, payload: BookConvert, db: Session = Depends(get_db)
) -> BookRead:
    book = book_service.convert_book_type(db, book_id, payload.book_type)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return BookRead.model_validate(book)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: str, db: Session = Depends(get_db)) -> None:
    if not book_service.delete_book(db, book_id):
        raise HTTPException(status_code=404, detail="Book not found")


@router.get("/{book_id}/images", response_model=list[ImageRead])
def get_book_images(book_id: str, db: Session = Depends(get_db)) -> list[ImageRead]:
    """Every image that "belongs to" this Book for `.quillproj` export purposes — the union
    of images attached directly to the Book, to any Scene on its canvas, to any Codex entry
    linked to it, plus its cover image (docs/06 Phase 5 task BE-4). See
    ``entity_images_service.gather_book_images`` for the exact scoping rules — this route
    exists to 404 on an unknown Book before delegating to that service."""
    if book_service.get_book(db, book_id) is None:
        raise HTTPException(status_code=404, detail="Book not found")
    images = entity_images_service.gather_book_images(db, book_id)
    return [images_service.to_image_read(db, image) for image in images]
