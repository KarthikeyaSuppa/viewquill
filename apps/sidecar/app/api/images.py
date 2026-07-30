"""/images — image upload/serve/attach, both buckets, with Pillow-verified dimensions and
thumbnails (docs/03-DATA-MODEL.md `images`, docs/06 Phase 5 task BE-1). Supersedes the
Phase 3 BE-3 minimal version (single bucket, no thumbnails, no real dimensions).

DATA-SENSITIVE (flagged for a `reviewer` pass, per CLAUDE.md): `POST /images` reads and
persists raw client bytes to disk, and Pillow decodes those untrusted bytes to get real
dimensions + a thumbnail. See `app/services/images_service.py`'s module docstring for the
content-type/size validation, decompression-bomb guard, and path-escape guards this route
relies on.

Like `POST /voice/transcribe` (app/api/voice.py), the image bytes arrive as the RAW request
body, not a multipart form field — `python-multipart` is not among this sidecar's pinned
dependencies (pyproject.toml), so this mirrors voice.py's raw-body + streamed-size-cap
pattern rather than introducing `UploadFile`/`Form` and a new dependency. Metadata that
would otherwise ride along in multipart fields (the original filename, an optional display
name, the target bucket) is passed as query parameters instead — the filename/display name
are stored as opaque display metadata only and never influence the on-disk path (see
images_service.save_image).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import (
    EntityImageLinkCreate,
    EntityImageRead,
    EntityImageReorderRequest,
    ImageRead,
    ImageTagAdd,
    ImageUpdate,
)
from app.services import entity_images_service, images_service

router = APIRouter(prefix="/images", tags=["images"])

# Separate router (no `/images` prefix) for the entity-scoped read of attached images —
# `GET /entities/{entity_type}/{entity_id}/images` deliberately lives outside `/images/...`
# so it never collides with real per-book/scene/codex-entry routes elsewhere
# (docs/06 Phase 5 task BE-3). Registered alongside `router` in app/main.py.
entities_router = APIRouter(prefix="/entities", tags=["images"])

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
    bucket: str = Query(
        default="reference_pool", description="'reference_pool' or 'finalized_scene'."
    ),
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
            bucket=bucket,
        )
    except ValueError as exc:
        if str(exc) == "UNSUPPORTED_BUCKET":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported bucket.",
            ) from exc
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
        if str(exc) == "BAD_IMAGE":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Not a valid image.",
            ) from exc
        raise
    return images_service.to_image_read(db, image)


@router.get("", response_model=list[ImageRead])
def list_images(
    bucket: str | None = Query(default=None, description="'reference_pool' or 'finalized_scene'."),
    tag: str | None = Query(default=None, description="Exact tag match."),
    q: str | None = Query(
        default=None, description="Case-insensitive substring match over name/description/tags."
    ),
    db: Session = Depends(get_db),
) -> list[ImageRead]:
    try:
        images = images_service.list_images(db, bucket=bucket, tag=tag, q=q)
    except ValueError as exc:
        if str(exc) == "UNSUPPORTED_BUCKET":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported bucket.",
            ) from exc
        raise
    return [images_service.to_image_read(db, image) for image in images]


@router.get("/{image_id}/meta", response_model=ImageRead)
def get_image_meta(image_id: str, db: Session = Depends(get_db)) -> ImageRead:
    """Metadata (including tags) for one image — distinct from ``GET /{image_id}``, which
    serves the raw image bytes."""
    image = images_service.get_image(db, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return images_service.to_image_read(db, image)


@router.patch("/{image_id}", response_model=ImageRead)
def update_image(
    image_id: str, payload: ImageUpdate, db: Session = Depends(get_db)
) -> ImageRead:
    values = payload.model_dump(exclude_unset=True)
    image = images_service.update_image(db, image_id, values)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return images_service.to_image_read(db, image)


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(image_id: str, db: Session = Depends(get_db)) -> None:
    if not images_service.delete_image(db, image_id):
        raise HTTPException(status_code=404, detail="Image not found")


@router.post("/{image_id}/tags", response_model=ImageRead, status_code=status.HTTP_201_CREATED)
def add_image_tag(
    image_id: str, payload: ImageTagAdd, db: Session = Depends(get_db)
) -> ImageRead:
    try:
        image = images_service.add_tag(db, image_id, payload.tag)
    except ValueError as exc:
        if str(exc) == "EMPTY_TAG":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Tag must not be empty.",
            ) from exc
        raise
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return images_service.to_image_read(db, image)


@router.delete("/{image_id}/tags/{tag}", status_code=status.HTTP_204_NO_CONTENT)
def remove_image_tag(image_id: str, tag: str, db: Session = Depends(get_db)) -> None:
    image = images_service.remove_tag(db, image_id, tag)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")


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


@router.get("/{image_id}/thumb")
def get_image_thumb(image_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """Serves the thumbnail. Thumbnails are best-effort (see images_service._write_thumbnail)
    — if one is missing on disk (generation failed, or the row predates this feature), falls
    back to serving the full image so the UI never 404s a thumb request for a real image.
    """
    image = images_service.get_image(db, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        thumb_path = images_service.resolve_thumb_path(image)
        full_path = images_service.resolve_path(image)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Image not found") from exc

    serve_path = thumb_path if thumb_path.is_file() else full_path
    if not serve_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    ext = serve_path.suffix.lstrip(".").lower()
    media_type = _MEDIA_TYPE_BY_EXT.get(ext, "application/octet-stream")
    return FileResponse(serve_path, media_type=media_type)


# ── Polymorphic entity attach/detach (docs/03-DATA-MODEL.md `entity_images`; docs/06
# Phase 5 task BE-3) — see app/services/entity_images_service.py for the idempotency and
# role-matching semantics these routes rely on. ─────────────────────────────────────────


@router.post(
    "/{image_id}/links", response_model=EntityImageRead, status_code=status.HTTP_201_CREATED
)
def create_entity_image_link(
    image_id: str, payload: EntityImageLinkCreate, db: Session = Depends(get_db)
) -> EntityImageRead:
    try:
        link = entity_images_service.attach(
            db,
            image_id=image_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            role=payload.role,
        )
    except ValueError as exc:
        if str(exc) == "BAD_ENTITY_TYPE":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported entity_type.",
            ) from exc
        if str(exc) == "IMAGE_NOT_FOUND":
            raise HTTPException(status_code=404, detail="Image not found") from exc
        raise
    return EntityImageRead.model_validate(link)


@router.delete("/{image_id}/links", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity_image_link(
    image_id: str,
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    role: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> None:
    """204 either way — deleting a link that doesn't (or no longer) exists is a no-op, not
    an error (mirrors ``DELETE /images/{image_id}/tags/{tag}``)."""
    try:
        entity_images_service.detach(
            db, image_id=image_id, entity_type=entity_type, entity_id=entity_id, role=role
        )
    except ValueError as exc:
        if str(exc) == "BAD_ENTITY_TYPE":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported entity_type.",
            ) from exc
        raise


@entities_router.get("/{entity_type}/{entity_id}/images", response_model=list[ImageRead])
def list_entity_images(
    entity_type: str, entity_id: str, db: Session = Depends(get_db)
) -> list[ImageRead]:
    try:
        images = entity_images_service.list_for_entity(
            db, entity_type=entity_type, entity_id=entity_id
        )
    except ValueError as exc:
        if str(exc) == "BAD_ENTITY_TYPE":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported entity_type.",
            ) from exc
        raise
    return [images_service.to_image_read(db, image) for image in images]


@entities_router.post(
    "/{entity_type}/{entity_id}/images/reorder", response_model=list[ImageRead]
)
def reorder_entity_images(
    entity_type: str,
    entity_id: str,
    payload: EntityImageReorderRequest,
    db: Session = Depends(get_db),
) -> list[ImageRead]:
    """Sets the display order of images attached to (``entity_type``, ``entity_id``) —
    ``payload.image_ids`` is the full desired order; any currently-attached image left out
    of that list has its order reset to the recency-based fallback (see
    ``entity_images_service.reorder_for_entity``). Returns the updated list, same shape as
    ``GET /entities/{entity_type}/{entity_id}/images``, so the frontend can just replace its
    local list with the response rather than re-fetching separately."""
    try:
        entity_images_service.reorder_for_entity(
            db, entity_type=entity_type, entity_id=entity_id, image_ids=payload.image_ids
        )
        images = entity_images_service.list_for_entity(
            db, entity_type=entity_type, entity_id=entity_id
        )
    except ValueError as exc:
        if str(exc) == "BAD_ENTITY_TYPE":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported entity_type.",
            ) from exc
        raise
    return [images_service.to_image_read(db, image) for image in images]
