"""``.quillproj`` encrypted bundle export/import HTTP surface (docs/05-EXPORT-IMPORT-
SECURITY.md; docs/06 Phase 7 task 4 onward).

Exposes the export endpoint (``POST /books/{book_id}/export/bundle``, task 4) plus the two
import endpoints (``POST /import/quillproj/inspect`` and ``POST /import/quillproj/apply``,
task 7). Mirrors ``app/api/export.py``'s style (router setup, DB session dependency,
error-to-HTTPException conventions) since a bundle export/import is a sibling of the plain
-format exports there.

No ``python-multipart`` here, same as ``app/api/voice.py``/``app/api/images.py`` (not among
this sidecar's pinned dependencies — CLAUDE.md: "only official packages... Do NOT install
anything" for this task): the encrypted bundle bytes arrive as the RAW request body, capped
and streamed exactly like those two routes. The passphrase is deliberately carried in a
custom request HEADER (``X-Quillnight-Passphrase``), never a query parameter — ASGI access
logs and any intermediary proxy commonly log the request path+query string, never headers,
so this keeps the passphrase out of logs (CLAUDE.md / docs/01: never log the passphrase).
``resolutions`` (apply only) is NOT secret, so it travels as an ordinary JSON-encoded query
parameter.

Hard rule (CLAUDE.md / docs/01-PRODUCT-VISION.md): never log the passphrase.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import BundleExportRequest
from app.services import book_service
from app.services.bundle_crypto import BundlePassphraseError, encrypt_bundle
from app.services.bundle_export import BundleExportError, export_book_to_zip_bytes
from app.services.bundle_import import BundleImportError, apply_import, inspect_bundle
from app.services.bundle_schema import BundleSchemaError

router = APIRouter(tags=["import-export"])

# Same order of magnitude as a whole-book export bundle (images/voice notes/drafts included)
# — generous but not unbounded, per the task's "sane limit" instruction.
MAX_BUNDLE_BYTES = 500 * 1024 * 1024  # 500 MB

_PASSPHRASE_HEADER = "x-quillnight-passphrase"  # noqa: S105 -- header NAME, not a secret value

# Collapses any run of non-alphanumeric characters into a single hyphen, then the caller
# strips leading/trailing hyphens — same intent as export.py's filename sanitizing, but
# producing a slug (lowercase, hyphenated) rather than an arbitrary safe filename.
_SLUG_UNSAFE_CHARS = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    slug = _SLUG_UNSAFE_CHARS.sub("-", title.lower()).strip("-")
    return slug or "book"


@router.post("/books/{book_id}/export/bundle")
def export_book_bundle(
    book_id: str, body: BundleExportRequest, db: Session = Depends(get_db)
) -> Response:
    book = book_service.get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    exported_at = datetime.now(UTC).isoformat()

    try:
        zip_bytes, _manifest = export_book_to_zip_bytes(db, book_id, exported_at=exported_at)
    except BundleExportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    encrypted = encrypt_bundle(zip_bytes, body.passphrase)

    slug = _slugify(book.title)
    date_part = exported_at.split("T", 1)[0]
    filename = f"{slug}-{date_part}.quillproj"

    return Response(
        content=encrypted,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _require_passphrase(request: Request) -> str:
    passphrase = request.headers.get(_PASSPHRASE_HEADER)
    if not passphrase:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing {_PASSPHRASE_HEADER} header",
        )
    return passphrase


async def _read_capped_bundle_body(request: Request) -> bytes:
    """Reads the raw request body, capped at `MAX_BUNDLE_BYTES` — mirrors
    `app/api/voice.py`'s `transcribe_voice_note` / `app/api/images.py`'s `upload_image`:
    fast-path reject via `Content-Length` when present, always enforced via a streamed
    read too (so a missing/lying `Content-Length` can't bypass the cap)."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > MAX_BUNDLE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Bundle exceeds max size of {MAX_BUNDLE_BYTES} bytes",
            )

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BUNDLE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Bundle exceeds max size of {MAX_BUNDLE_BYTES} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/import/quillproj/inspect")
async def inspect_quillproj_bundle(
    request: Request, db: Session = Depends(get_db)
) -> dict:
    """Read-only dry-run: reports what importing the posted `.quillproj` bundle WOULD do.
    Never writes anything (see `bundle_import.inspect_bundle`'s docstring)."""
    passphrase = _require_passphrase(request)
    data = await _read_capped_bundle_body(request)

    try:
        report = inspect_bundle(db, data, passphrase)
    except BundlePassphraseError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wrong passphrase or corrupted bundle",
        ) from None
    except BundleSchemaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BundleImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return report.model_dump()


@router.post("/import/quillproj/apply")
async def apply_quillproj_bundle(
    request: Request,
    resolutions: str = Query(
        default="{}",
        description="JSON-encoded object mapping a conflicting row's id to "
        "'keep_local' | 'take_imported' | 'merge'.",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Applies the posted `.quillproj` bundle to the local database (merge-by-UUID, never a
    silent overwrite — see `bundle_import.apply_import`'s docstring). Runs in one
    transaction: any error below leaves the database exactly as it was."""
    passphrase = _require_passphrase(request)
    data = await _read_capped_bundle_body(request)

    try:
        parsed_resolutions = json.loads(resolutions)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="resolutions must be a JSON-encoded object",
        ) from exc
    if not isinstance(parsed_resolutions, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in parsed_resolutions.items()
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="resolutions must be a JSON object of string -> string",
        )

    try:
        report = apply_import(db, data, passphrase, parsed_resolutions)
    except BundlePassphraseError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wrong passphrase or corrupted bundle",
        ) from None
    except BundleSchemaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BundleImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return report.model_dump()
