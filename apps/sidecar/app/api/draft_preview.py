"""GET /books/{book_id}/draft-preview — a read-only JSON preview of a Book's fully compiled
manuscript, for the frontend's "manuscript reader" (docs/06 Phase 8).

This is NOT part of the export pipeline: it writes no file to disk and creates no
``draft_versions`` row. It reuses ``export_service.build_compiled_document`` (the same pure,
fully-materialized compiler `api/export.py` calls before handing off to a renderer) purely
to read back the current compiled shape, then serializes it through its own Pydantic
response models (``DraftPreviewOut`` et al. in app/models/schemas.py) rather than returning
the export pipeline's internal dataclasses directly.

Mirrors ``api/export.py``'s book-lookup-then-404 pattern; does not import anything from
``export_docx``/``export_pdf``/``export_markdown``/``export_fountain`` since no rendering
happens here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import (
    CompiledChapterPreviewOut,
    CompiledScenePreviewOut,
    DraftPreviewOut,
    ScreenplayElementPreviewOut,
)
from app.services import book_service, export_service

router = APIRouter(prefix="/books", tags=["export"])


def _to_draft_preview_out(doc: export_service.CompiledDocument) -> DraftPreviewOut:
    return DraftPreviewOut(
        book_id=doc.book_id,
        book_title=doc.book_title,
        book_type=doc.book_type,
        logline=doc.logline,
        front_matter=doc.front_matter,
        cover_image_id=doc.cover_image_id,
        chapters=[
            CompiledChapterPreviewOut(
                title=chapter.title,
                scenes=[
                    CompiledScenePreviewOut(
                        title=scene.title,
                        description=scene.description,
                        elements=[
                            ScreenplayElementPreviewOut(
                                element_type=el.element_type,
                                text=el.text,
                                order_index=el.order_index,
                            )
                            for el in scene.elements
                        ],
                    )
                    for scene in chapter.scenes
                ],
            )
            for chapter in doc.chapters
        ],
    )


@router.get("/{book_id}/draft-preview", response_model=DraftPreviewOut)
def get_draft_preview(book_id: str, db: Session = Depends(get_db)) -> DraftPreviewOut:
    book = book_service.get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    doc = export_service.build_compiled_document(db, book)
    return _to_draft_preview_out(doc)
