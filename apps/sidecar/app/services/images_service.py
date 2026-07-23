"""Image storage: minimal single-image attach/serve for the Codex (docs/03-DATA-MODEL.md
`images`, docs/06 Phase 3 task BE-3).

DATA-SENSITIVE (flagged for a `reviewer` pass per CLAUDE.md): this module writes raw,
client-supplied bytes to disk and later serves them back by ID. Two defenses matter most:

1. **Content-type/size validation** — only a small allow-list of image MIME types, capped
   at ``MAX_IMAGE_BYTES``, is ever accepted (mirrors ``speech_stt.py``'s cap, scaled down —
   see ``app/api/voice.py``'s streamed 413 for the request-level half of this).
2. **No client-controlled filenames/paths** — ``save_image`` NEVER uses the client's
   ``original_filename`` (or any client value) to build the on-disk path. The filename is
   always ``f"{new_uuid()}{ext}"`` where ``ext`` comes from a fixed content-type -> extension
   table, never from user input. ``original_filename`` is stored as opaque metadata only.
   ``resolve_path`` additionally asserts (belt-and-suspenders, since we control the name)
   that the resolved path never escapes ``media_dir``.

Scope is deliberately minimal (Phase 3 BE-3): one bucket (`reference_pool`), no thumbnails,
no EXIF, no resizing, no multi-image galleries — those are Phase 5.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import new_uuid
from app.models.orm import Image

# Small, explicit allow-list — never trust the client's declared content-type beyond
# matching it against this set (still not a substitute for real content sniffing, but this
# is the minimal Phase 3 scope; full validation is a Phase 5+/reviewer concern).
ALLOWED_CONTENT_TYPES: set[str] = {"image/png", "image/jpeg", "image/webp", "image/gif"}

# Smaller than /voice/transcribe's 100MB audio cap (app/api/voice.py) — a single reference
# image never needs to be that large in the minimal Phase 3 scope.
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

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


def save_image(
    db: Session,
    *,
    data: bytes,
    content_type: str,
    original_filename: str | None,
    display_name: str | None = None,
) -> Image:
    """Validates and persists one uploaded image to ``app-data/media/reference_pool/``.

    Raises ``ValueError`` (mapped to HTTP status by the route) for:
    ``"UNSUPPORTED_TYPE"``, ``"EMPTY"``, ``"TOO_LARGE"``.

    The on-disk filename is ALWAYS server-generated (``{new_uuid()}{ext}``) — never derived
    from ``original_filename``, which is stored only as descriptive metadata.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("UNSUPPORTED_TYPE")
    if len(data) == 0:
        raise ValueError("EMPTY")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("TOO_LARGE")

    checksum = hashlib.sha256(data).hexdigest()

    cfg = get_settings()
    cfg.ensure_dirs()
    ext = _ext_for_content_type(content_type)
    filename = f"{new_uuid()}.{ext}"
    storage_path = f"reference_pool/{filename}"

    full_path = cfg.media_dir / storage_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(data)

    resolved_display_name = display_name or original_filename or filename

    image = Image(
        id=new_uuid(),
        bucket="reference_pool",
        storage_path=storage_path,
        display_name=resolved_display_name,
        original_filename=original_filename,
        checksum_sha256=checksum,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def get_image(db: Session, image_id: str) -> Image | None:
    return db.get(Image, image_id)


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
