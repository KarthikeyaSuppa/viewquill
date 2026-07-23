"""/images — minimal single-image upload/serve/attach (docs/03-DATA-MODEL.md `images`,
docs/06 Phase 3 task BE-3).

DATA-SENSITIVE (flagged for a `reviewer` pass, per CLAUDE.md): `POST /images` reads and
persists raw client bytes to disk. See `app/services/images_service.py`'s module docstring
for the content-type/size validation and path-escape guard this route relies on.

Like `POST /voice/transcribe` (app/api/voice.py), the image bytes arrive as the RAW request
body, not a multipart form field — `python-multipart` is not among this sidecar's pinned
dependencies (pyproject.toml), so this mirrors voice.py's raw-body + streamed-size-cap
pattern rather than introducing `UploadFile`/`Form` and a new dependency. Metadata that
would otherwise ride along in multipart fields (the original filename, an optional display
name) is passed as query parameters instead — both are stored as opaque display metadata
only and never influence the on-disk path (see images_service.save_image).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import ImageRead
from app.services import images_service

router = APIRouter(prefix="/images", tags=["images"])

# Smaller than /voice/transcribe's 100MB audio cap — see images_service.MAX_IMAGE_BYTES.
MAX_IMAGE_BYTES = images_service.MAX_IMAGE_BYTES

_MEDIA_TYPE_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


@router.post("", response_model=ImageRead, status_code=status.HTTP_201_CREATED)
async def upload_image(
    request: Request,
    filename: str | None = Query(default=None, description="Original filename (metadata only)."),
    display_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ImageRead:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Image exceeds 10MB.",
            )

    # Read via the stream (rather than request.body()) so a missing/lying Content-Length
    # header can't bypass the cap — mirrors app/api/voice.py's transcribe_voice_note.
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Image exceeds 10MB.",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()

    try:
        image = images_service.save_image(
            db,
            data=data,
            content_type=content_type,
            original_filename=filename,
            display_name=display_name,
        )
    except ValueError as exc:
        if str(exc) == "UNSUPPORTED_TYPE":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported image type.",
            ) from exc
        if str(exc) == "EMPTY":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Empty file.",
            ) from exc
        if str(exc) == "TOO_LARGE":
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Image exceeds 10MB.",
            ) from exc
        raise
    return ImageRead.model_validate(image)


@router.get("/{image_id}")
def get_image(image_id: str, db: Session = Depends(get_db)) -> FileResponse:
    image = images_service.get_image(db, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        full_path = images_service.resolve_path(image)
    except ValueError as exc:
        # PATH_ESCAPE should never happen (the path is always server-generated) — treat it
        # as a 404 rather than leaking any detail about the failed resolution.
        raise HTTPException(status_code=404, detail="Image not found") from exc
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    ext = full_path.suffix.lstrip(".").lower()
    media_type = _MEDIA_TYPE_BY_EXT.get(ext, "application/octet-stream")
    return FileResponse(full_path, media_type=media_type)
