"""/books/{book_id}/export, /books/{book_id}/draft-versions, /draft-versions/{id}/download —
the Final Draft export pipeline's HTTP surface (docs/03-DATA-MODEL.md `draft_versions`,
docs/06 Phase 6 task BE-7).

This router is the ONLY place ``export_service.build_compiled_document`` is called from an
HTTP handler and the ONLY place any renderer's output bytes are written to disk — every
service module it imports (``export_service``/``export_markdown``/``export_docx``/
``export_pdf``/``export_fountain``) is otherwise a pure transform with zero disk/DB side
effects of its own (see each module's docstring). Mirrors ``app/api/images.py``'s
"resolve -> guard missing file -> FileResponse" pattern for the download route, and
``app/api/continuity.py``'s ``_handle_value_error``-style ``ValueError`` -> HTTP mapping.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import get_db, new_uuid
from app.models.orm import Image
from app.models.schemas import DraftVersionRead, ExportFormat
from app.services import (
    book_service,
    export_docx,
    export_fountain,
    export_markdown,
    export_pdf,
    export_service,
    images_service,
)

router = APIRouter(prefix="/books", tags=["export"])

# Separate router (no `/books` prefix) for the download-by-id route — a DraftVersion is
# addressed by its own id, not scoped under a book path, mirroring how images.py splits
# `/images/...` from the entity-scoped `/entities/...` routes into two routers.
draft_versions_router = APIRouter(prefix="/draft-versions", tags=["export"])

_MEDIA_TYPE_BY_FORMAT = {
    "markdown": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "fountain": "text/plain",
    "fdx": "application/xml",
}

_EXT_BY_FORMAT = {
    "markdown": "md",
    "docx": "docx",
    "pdf": "pdf",
    "fountain": "fountain",
    "fdx": "fdx",
}

# Strips anything that isn't safe inside a Content-Disposition filename value (also keeps
# the header itself from being corrupted by a title containing quotes/control characters).
_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n]')


def _handle_value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code == "FORMAT_NOT_SUPPORTED_FOR_BOOK_TYPE":
        return HTTPException(status_code=422, detail=code)
    raise exc


def _resolve_cover_image_path(db: Session, cover_image_id: str | None):
    """Best-effort: a broken/missing cover reference degrades to no cover image rather than
    failing the whole export — see this task's brief."""
    if cover_image_id is None:
        return None
    image = db.get(Image, cover_image_id)
    if image is None:
        return None
    try:
        return images_service.resolve_path(image)
    except ValueError:
        return None


def _to_relative_file_path(path) -> str:
    """Stores ``draft_versions.file_path`` RELATIVE to the data dir (posix separators), the
    same portable-across-data-dir-moves convention ``speech_stt.save_audio`` uses for
    ``voice_notes.audio_path``."""
    data_dir = get_settings().data_dir
    return path.resolve().relative_to(data_dir.resolve()).as_posix()


@router.post("/{book_id}/export/{format}", response_model=DraftVersionRead)
def export_book(
    book_id: str, format: ExportFormat, db: Session = Depends(get_db)
) -> DraftVersionRead:
    book = book_service.get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    try:
        export_service.ensure_format_allowed(format, book.book_type)
    except ValueError as exc:
        raise _handle_value_error(exc) from exc

    doc = export_service.build_compiled_document(db, book)
    cover_image_path = _resolve_cover_image_path(db, book.cover_image_id)

    cfg = get_settings()
    cfg.ensure_dirs()

    if format == "markdown":
        file_path = export_markdown.write_markdown_file(doc, cfg.drafts_dir)
    else:
        book_dir = cfg.drafts_dir / book.id
        book_dir.mkdir(parents=True, exist_ok=True)
        ext = _EXT_BY_FORMAT[format]
        file_path = book_dir / f"{new_uuid()}.{ext}"
        if format == "docx":
            file_path.write_bytes(export_docx.render_docx(doc, cover_image_path))
        elif format == "pdf":
            file_path.write_bytes(export_pdf.render_pdf(doc, cover_image_path))
        elif format == "fountain":
            file_path.write_text(export_fountain.render_fountain(doc), encoding="utf-8")
        elif format == "fdx":
            file_path.write_text(export_fountain.render_fdx(doc), encoding="utf-8")

    draft_version = export_service.create_draft_version(
        db,
        book.id,
        format,
        file_path=_to_relative_file_path(file_path),
        format_settings={"format": format},
    )
    return export_service.to_draft_version_read(draft_version)


@router.get("/{book_id}/draft-versions", response_model=list[DraftVersionRead])
def list_book_draft_versions(book_id: str, db: Session = Depends(get_db)) -> list[DraftVersionRead]:
    if book_service.get_book(db, book_id) is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return [
        export_service.to_draft_version_read(row)
        for row in export_service.list_draft_versions(db, book_id)
    ]


@draft_versions_router.get("/{draft_version_id}/download")
def download_draft_version(draft_version_id: str, db: Session = Depends(get_db)) -> FileResponse:
    draft_version = export_service.get_draft_version(db, draft_version_id)
    if draft_version is None:
        raise HTTPException(status_code=404, detail="Draft version not found")

    full_path = get_settings().data_dir / draft_version.file_path
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="Draft version not found")

    fmt = (draft_version.format_settings or {}).get("format", "markdown")
    media_type = _MEDIA_TYPE_BY_FORMAT.get(fmt, "application/octet-stream")
    ext = _EXT_BY_FORMAT.get(fmt, full_path.suffix.lstrip("."))

    book = book_service.get_book(db, draft_version.book_id)
    title = book.title if book is not None else "draft"
    safe_title = _UNSAFE_FILENAME_CHARS.sub("_", title).strip() or "draft"
    filename = f"{safe_title}.{ext}"

    return FileResponse(full_path, media_type=media_type, filename=filename)
