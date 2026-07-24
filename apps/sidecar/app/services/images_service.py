"""Image storage: attach/serve for the Codex + Canvas, both buckets, with real dimensions
and thumbnails (docs/03-DATA-MODEL.md `images`, docs/06 Phase 5 task BE-1). Supersedes the
Phase 3 BE-3 minimal version (single bucket, no thumbnails, no real dimensions).

DATA-SENSITIVE (flagged for a `reviewer` pass per CLAUDE.md): this module writes raw,
client-supplied bytes to disk, decodes them with Pillow, and later serves them back by ID.
Defenses that matter most:

1. **Content-type/size validation** — only a small allow-list of image MIME types, capped
   at ``MAX_IMAGE_BYTES``, is ever accepted (mirrors ``speech_stt.py``'s cap, scaled down —
   see ``app/api/voice.py``'s streamed 413 for the request-level half of this).
2. **No client-controlled filenames/paths** — ``save_image`` NEVER uses the client's
   ``original_filename`` (or any client value) to build the on-disk path. The filename is
   always ``f"{new_uuid()}{ext}"`` where ``ext`` comes from a fixed content-type -> extension
   table, never from user input. ``original_filename`` is stored as opaque metadata only.
   ``resolve_path``/``resolve_thumb_path`` additionally assert (belt-and-suspenders, since we
   control the name) that the resolved path never escapes ``media_dir``.
3. **Decompression-bomb guard** — ``PILImage.MAX_IMAGE_PIXELS`` is capped at module import so
   a maliciously crafted small file that decodes to an enormous bitmap raises
   ``Image.DecompressionBombError`` instead of exhausting memory. Any Pillow decode failure
   (unidentified format, truncated data, bomb, etc.) is caught and mapped to a plain
   ``ValueError("BAD_IMAGE")`` — never re-raised with internal detail.

Two buckets now: ``reference_pool`` (Codex moodboards) and ``finalized_scene`` (Canvas
node-attached art) — see the ``bucket`` CheckConstraint on the ``Image`` ORM model. A
thumbnail (longest side ~320px) is generated best-effort alongside the original; it's a
convenience only — the original file remains the source of truth and upload never fails
just because thumbnail generation did.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import new_uuid, utcnow_iso
from app.models.orm import Image, ImageTag
from app.models.schemas import ImageRead

logger = logging.getLogger(__name__)

# Bound decompression bombs: a small file that claims to decode to more than this many
# pixels raises PIL.Image.DecompressionBombError instead of allocating an enormous bitmap.
# Applies process-wide to every Pillow open call, which is what we want here.
PILImage.MAX_IMAGE_PIXELS = 64_000_000

# Small, explicit allow-list — never trust the client's declared content-type beyond
# matching it against this set (still not a substitute for real content sniffing; the
# Pillow decode step below is the actual content-sniffing backstop).
ALLOWED_CONTENT_TYPES: set[str] = {"image/png", "image/jpeg", "image/webp", "image/gif"}

# Smaller than /voice/transcribe's 100MB audio cap (app/api/voice.py) — a single image
# never needs to be that large.
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_BUCKETS: set[str] = {"reference_pool", "finalized_scene"}

# Longest side of a generated thumbnail, in pixels. Convenience only — never the source
# of truth for the image.
THUMB_MAX_SIDE = 320

_CONTENT_TYPE_EXT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _ext_for_content_type(content_type: str) -> str:
    """Only ever called with a content_type already validated against
    ``ALLOWED_CONTENT_TYPES`` by ``save_image`` — never falls through to a guess."""
    return _CONTENT_TYPE_EXT[content_type]


def _decode_dimensions(data: bytes) -> tuple[int, int]:
    """Decodes untrusted bytes with Pillow and returns the real ``(width, height)``.

    Raises ``ValueError("BAD_IMAGE")`` for anything Pillow can't safely decode — unidentified
    format, truncated/corrupt data, or a decompression bomb (``PILImage.MAX_IMAGE_PIXELS``
    above bounds this). Deliberately catches the broad ``Exception``: Pillow raises several
    distinct exception types for "this isn't a valid image"
    (``PIL.UnidentifiedImageError``, ``PIL.Image.DecompressionBombError``, ``OSError``,
    ``ValueError``) and the caller only needs "reject this upload", not which one fired.
    """
    try:
        with PILImage.open(io.BytesIO(data)) as img:
            img.verify()
    except Exception as exc:
        raise ValueError("BAD_IMAGE") from exc

    # img.verify() invalidates further use of that handle — reopen a fresh one from the
    # same bytes to actually read the size it decoded to.
    try:
        with PILImage.open(io.BytesIO(data)) as img:
            width, height = img.size
    except Exception as exc:
        raise ValueError("BAD_IMAGE") from exc
    return width, height


_THUMB_FORMAT_FOR_EXT: dict[str, str] = {
    "png": "PNG",
    "jpg": "JPEG",
    "webp": "WEBP",
    "gif": "GIF",
}


def _write_thumbnail(data: bytes, ext: str, thumb_path: Path) -> None:
    """Best-effort: writes a downscaled thumbnail (longest side ``THUMB_MAX_SIDE``px,
    aspect preserved) to ``thumb_path``. NEVER raises — logs and returns on any failure,
    since the thumbnail is a convenience only; the original file (already written by the
    caller before this runs) remains the source of truth and an upload must not fail just
    because thumbnailing did.

    Writes atomically: the downscaled image is saved to a temp file in the SAME directory
    as ``thumb_path``, then moved into place with ``os.replace`` (atomic on the same
    filesystem). This guarantees ``GET /images/{id}/thumb`` never observes a
    partially-written thumbnail (e.g. process killed / disk full mid-``save``) — it either
    sees no file (falls back to the full image, per that route's existing behavior) or a
    complete one, never a truncated one. Any exception (including during the temp-file
    write itself) cleans up the temp file, if created, and is swallowed here.
    """
    tmp_path: Path | None = None
    try:
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        with PILImage.open(io.BytesIO(data)) as img:
            img.thumbnail((THUMB_MAX_SIDE, THUMB_MAX_SIDE))
            fmt = _THUMB_FORMAT_FOR_EXT.get(ext, img.format or "PNG")
            if fmt == "JPEG" and img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            fd, tmp_name = tempfile.mkstemp(
                prefix=f"{thumb_path.name}.tmp-", dir=thumb_path.parent
            )
            tmp_path = Path(tmp_name)
            with os.fdopen(fd, "wb") as tmp_file:
                img.save(tmp_file, format=fmt)
        os.replace(tmp_path, thumb_path)
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        logger.warning(
            "Thumbnail generation failed for %s; original image was kept.",
            thumb_path,
            exc_info=True,
        )


def save_image(
    db: Session,
    *,
    data: bytes,
    content_type: str,
    original_filename: str | None,
    display_name: str | None = None,
    bucket: str = "reference_pool",
) -> Image:
    """Validates and persists one uploaded image to ``app-data/media/<bucket>/``, plus a
    best-effort thumbnail under ``app-data/media/<bucket>/thumb/``.

    Raises ``ValueError`` (mapped to HTTP status by the route) for:
    ``"UNSUPPORTED_BUCKET"``, ``"UNSUPPORTED_TYPE"``, ``"EMPTY"``, ``"TOO_LARGE"``,
    ``"BAD_IMAGE"`` (bytes passed the content-type/size checks but Pillow couldn't decode
    them as a real image of that type).

    The on-disk filename is ALWAYS server-generated (``{new_uuid()}{ext}``) — never derived
    from ``original_filename``, which is stored only as descriptive metadata. The thumbnail
    reuses the SAME uuid stem so it can be derived from ``storage_path`` alone.
    """
    if bucket not in ALLOWED_BUCKETS:
        raise ValueError("UNSUPPORTED_BUCKET")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("UNSUPPORTED_TYPE")
    if len(data) == 0:
        raise ValueError("EMPTY")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("TOO_LARGE")

    # Real content-sniffing backstop: reject anything the declared content-type allow-list
    # let through but that Pillow can't actually decode as an image (also catches
    # decompression bombs via PILImage.MAX_IMAGE_PIXELS, set at module import above).
    width, height = _decode_dimensions(data)

    checksum = hashlib.sha256(data).hexdigest()

    cfg = get_settings()
    cfg.ensure_dirs()
    ext = _ext_for_content_type(content_type)
    filename = f"{new_uuid()}.{ext}"
    storage_path = f"{bucket}/{filename}"

    full_path = cfg.media_dir / storage_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(data)

    thumb_path = cfg.media_dir / f"{bucket}/thumb/{filename}"
    _write_thumbnail(data, ext, thumb_path)

    resolved_display_name = display_name or original_filename or filename

    image = Image(
        id=new_uuid(),
        bucket=bucket,
        storage_path=storage_path,
        display_name=resolved_display_name,
        original_filename=original_filename,
        width=width,
        height=height,
        checksum_sha256=checksum,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def get_image(db: Session, image_id: str) -> Image | None:
    return db.get(Image, image_id)


def _escape_like(value: str) -> str:
    """Escapes SQL LIKE wildcards (``%``/``_``) in user-supplied search text so a query
    containing a literal ``%`` or ``_`` is matched literally rather than as a wildcard.
    Paired with ``.like(pattern, escape="\\\\")`` at every call site below."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_images(
    db: Session,
    *,
    bucket: str | None = None,
    tag: str | None = None,
    q: str | None = None,
) -> list[Image]:
    """Lists images, optionally filtered by ``bucket``, an exact ``tag``, and/or a
    case-insensitive substring ``q`` over ``display_name``, ``description``, or any tag.

    Raises ``ValueError("UNSUPPORTED_BUCKET")`` if ``bucket`` is provided but not one of
    ``ALLOWED_BUCKETS`` (mapped to HTTP 422 by the route, same as ``save_image``).

    Ordering is deterministic: ``created_at DESC, id DESC`` (never depends on tag-join
    duplication — the tag filter uses a sub-select, not a join, so each Image row still
    appears at most once).
    """
    if bucket is not None and bucket not in ALLOWED_BUCKETS:
        raise ValueError("UNSUPPORTED_BUCKET")

    stmt = select(Image)
    if bucket is not None:
        stmt = stmt.where(Image.bucket == bucket)
    if tag is not None:
        normalized_tag = tag.strip().lower()
        stmt = stmt.where(
            Image.id.in_(select(ImageTag.image_id).where(ImageTag.tag == normalized_tag))
        )
    if q is not None and q.strip():
        pattern = f"%{_escape_like(q.strip().lower())}%"
        tag_match = select(ImageTag.image_id).where(
            ImageTag.tag.ilike(pattern, escape="\\")
        )
        stmt = stmt.where(
            or_(
                Image.display_name.ilike(pattern, escape="\\"),
                Image.description.ilike(pattern, escape="\\"),
                Image.id.in_(tag_match),
            )
        )
    stmt = stmt.order_by(Image.created_at.desc(), Image.id.desc())
    return list(db.execute(stmt).scalars())


def to_image_read(db: Session, image: Image) -> ImageRead:
    """Builds an ``ImageRead`` (row fields + sorted ``tags``) for one ``Image`` — the single
    helper list/detail/upload responses all go through so tags are assembled consistently
    everywhere an image is returned over the wire."""
    data = ImageRead.model_validate(image).model_dump()
    data["tags"] = list_tags(db, image.id)
    return ImageRead(**data)


def update_image(db: Session, image_id: str, values: dict[str, Any]) -> Image | None:
    """Partial update — only keys present in ``values`` are applied (mirrors
    ``codex_service.update_entry`` / ``book_service.update_book``). Returns ``None`` if the
    image doesn't exist."""
    image = db.get(Image, image_id)
    if image is None:
        return None
    for key, value in values.items():
        setattr(image, key, value)
    # `updated_at` has an `onupdate` default, but that only fires on a flush that detects a
    # change; touch it explicitly so a no-op-looking patch still bumps the timestamp.
    image.updated_at = utcnow_iso()
    db.commit()
    db.refresh(image)
    return image


def delete_image(db: Session, image_id: str) -> bool:
    """Deletes the ``Image`` row — ``image_tags`` and ``entity_images`` rows referencing it
    are removed via ``ondelete="CASCADE"`` (app/models/orm.py) — and best-effort unlinks the
    original file and its thumbnail from disk. A missing file on disk is never an error;
    only the DB row's existence determines this function's return value.
    """
    image = db.get(Image, image_id)
    if image is None:
        return False

    for resolver in (resolve_path, resolve_thumb_path):
        try:
            path = resolver(image)
        except ValueError:
            # PATH_ESCAPE should never happen (see resolve_path's docstring) — skip
            # unlinking that one path rather than raising; the DB delete below is unaffected.
            continue
        path.unlink(missing_ok=True)

    db.delete(image)
    db.commit()
    return True


def list_tags(db: Session, image_id: str) -> list[str]:
    """Sorted tags for one image. Does not check the image exists — callers that need a
    404-on-missing-image already resolved the ``Image`` row first."""
    rows = db.execute(
        select(ImageTag.tag).where(ImageTag.image_id == image_id).order_by(ImageTag.tag)
    ).scalars()
    return list(rows)


def add_tag(db: Session, image_id: str, tag: str) -> Image | None:
    """Adds ``tag`` to ``image_id``. Idempotent: adding a tag already present is a no-op,
    not an error (``ImageTag`` has a composite primary key on (image_id, tag), so this
    checks first rather than relying on a constraint violation).

    Normalizes ``tag`` by stripping whitespace and lowercasing. Raises
    ``ValueError("EMPTY_TAG")`` if that normalizes to an empty string (mapped to HTTP 422 by
    the route). Returns ``None`` if the image doesn't exist (mapped to 404 by the route).
    """
    image = db.get(Image, image_id)
    if image is None:
        return None
    normalized = tag.strip().lower()
    if not normalized:
        raise ValueError("EMPTY_TAG")
    existing = db.get(ImageTag, (image_id, normalized))
    if existing is None:
        db.add(ImageTag(image_id=image_id, tag=normalized))
        db.commit()
    return image


def remove_tag(db: Session, image_id: str, tag: str) -> Image | None:
    """Removes ``tag`` from ``image_id``. No-op (not an error) if that tag isn't present on
    this image. Returns ``None`` if the image doesn't exist — distinct from "tag wasn't
    present", which is still a successful no-op."""
    image = db.get(Image, image_id)
    if image is None:
        return None
    normalized = tag.strip().lower()
    existing = db.get(ImageTag, (image_id, normalized))
    if existing is not None:
        db.delete(existing)
        db.commit()
    return image


def resolve_path(image: Image) -> Path:
    """Resolves an ``Image`` row to its absolute on-disk path.

    Defensive check (belt-and-suspenders — ``save_image`` never lets client input reach the
    path, but this guards against any future regression): raises ``ValueError("PATH_ESCAPE")``
    if the resolved path is not inside ``media_dir``.
    """
    media_dir = get_settings().media_dir
    full_path = (media_dir / image.storage_path).resolve()
    if not full_path.is_relative_to(media_dir.resolve()):
        raise ValueError("PATH_ESCAPE")
    return full_path


def resolve_thumb_path(image: Image) -> Path:
    """Resolves an ``Image`` row to its thumbnail's absolute on-disk path.

    Derived deterministically from ``storage_path`` (``<bucket>/<file>`` ->
    ``<bucket>/thumb/<file>``) rather than a second stored column — there's only ever one
    place on disk a given image's thumbnail can be. Same escape guard as ``resolve_path``.
    """
    media_dir = get_settings().media_dir
    original = Path(image.storage_path)
    thumb_relative = original.parent / "thumb" / original.name
    full_path = (media_dir / thumb_relative).resolve()
    if not full_path.is_relative_to(media_dir.resolve()):
        raise ValueError("PATH_ESCAPE")
    return full_path
