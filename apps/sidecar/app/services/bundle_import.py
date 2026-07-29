"""`.quillproj` bundle import — DRY-RUN inspection half (docs/05-EXPORT-IMPORT-SECURITY.md;
Phase 7 task 5).

Hard rule (CLAUDE.md / docs/01-PRODUCT-VISION.md, "never lose data, never silently
overwrite"): `inspect_bundle` below NEVER writes anything — no INSERT, no UPDATE, no
`session.add`, no `session.flush`. It only reads the bundle and the existing database and
reports what an import WOULD do. Import is merge-by-UUID, never a silent overwrite: every
row in the bundle is looked up by its own primary key against the local database, and
classified as newly-`created`, already-`matched` (identical), or in `conflicts` (same UUID,
different content) for a human to resolve. `apply_import` (Phase 7 task 6) is the ONLY
writer in this module, reuses the `_TABLE_REGISTRY` below as its single source of truth for
table -> (ORM model, PK columns), and shares its row-classification logic with
`inspect_bundle` via `_classify_row` so the dry-run report and the real apply can never
disagree about created/matched/conflict.

`apply_import` runs the ENTIRE merge inside one transaction (`session.begin()`, or
`session.begin_nested()` if the caller already has an open transaction) — any exception
anywhere rolls back every write made so far, so a bundle either applies completely or not
at all. For a same-PK conflict, the caller's `resolutions` dict decides the outcome
(`keep_local` — the default when a PK is absent from `resolutions`, `take_imported`, or
`merge` — imported values only fill LOCAL gaps, never overwrite non-empty local content).
Join/association tables (`book_scene_links`, `book_codex_links`, `codex_scene_links`,
`entity_images`) are the one place PK-based logic is NOT enough: they are deduplicated by
their NATURAL key (e.g. `(book_id, scene_id)`), never their surrogate `id`, so a re-import
with a fresh `id` but the same natural key never creates a duplicate link row — see
`_apply_join_row`'s docstring for the invariant in full.

`read_bundle` is the shared open-and-validate step both `inspect_bundle` (this task) and
`apply_bundle` (task 6) build on: decrypt -> unzip -> parse `manifest.json` -> validate its
schema_version BEFORE any `data/*.json` is read (an unsupported/future schema version must
never be partially processed) -> parse each `data/<field>.json` into a `BundlePayload`.
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.orm import (
    Book,
    BookCodexLink,
    BookSceneLink,
    BookSceneOrder,
    Chapter,
    CodexArcState,
    CodexEntry,
    CodexRelationship,
    CodexSceneLink,
    ContinuityFlag,
    DraftVersion,
    EntityImage,
    Image,
    ImageTag,
    Scene,
    SceneConnection,
    ScreenplayElement,
    VoiceNote,
)
from app.services.bundle_crypto import decrypt_bundle
from app.services.bundle_schema import (
    BundleManifest,
    BundlePayload,
    BundleSchemaError,
    validate_manifest_version,
)

logger = logging.getLogger(__name__)

__all__ = [
    "BundleImportError",
    "EntityChange",
    "EntityConflict",
    "MergeReport",
    "apply_import",
    "inspect_bundle",
    "read_bundle",
]


class BundleImportError(Exception):
    """Raised for a structurally invalid bundle (corrupt zip, missing manifest.json,
    malformed manifest) — distinct from `BundlePassphraseError` (wrong key/tampered
    ciphertext) and `BundleSchemaError` (well-formed but unsupported schema_version)."""


# ── Table registry — single source of truth for table name -> (ORM model, PK columns).
# `apply_bundle` (Phase 7 task 6) reuses this exact dict; keep it in sync with
# `BundlePayload`'s field list (app/services/bundle_schema.py) and `gather_bundle`'s
# serialization order (app/services/bundle_export.py). Every table has an `id` PK except
# `image_tags`, whose PK is the composite `(image_id, tag)` — see app/models/orm.py. ──
_TABLE_REGISTRY: dict[str, tuple[type, tuple[str, ...]]] = {
    "books": (Book, ("id",)),
    "scenes": (Scene, ("id",)),
    "screenplay_elements": (ScreenplayElement, ("id",)),
    "book_scene_links": (BookSceneLink, ("id",)),
    "scene_connections": (SceneConnection, ("id",)),
    "chapters": (Chapter, ("id",)),
    "book_scene_order": (BookSceneOrder, ("id",)),
    "codex_entries": (CodexEntry, ("id",)),
    "codex_relationships": (CodexRelationship, ("id",)),
    "codex_arc_states": (CodexArcState, ("id",)),
    "book_codex_links": (BookCodexLink, ("id",)),
    "codex_scene_links": (CodexSceneLink, ("id",)),
    "images": (Image, ("id",)),
    "image_tags": (ImageTag, ("image_id", "tag")),
    "entity_images": (EntityImage, ("id",)),
    "continuity_flags": (ContinuityFlag, ("id",)),
    "draft_versions": (DraftVersion, ("id",)),
    "voice_notes": (VoiceNote, ("id",)),
}

# Join/association tables: dedup key is the NATURAL key, not the surrogate `id` PK — see
# `_apply_join_row`'s docstring for why. `image_tags` is deliberately absent: its PK
# (image_id, tag) already IS its natural key, so ordinary PK-based dedup is sufficient.
# `book_scene_order` also has a surrogate `id` PK but a UNIQUE(book_id, scene_id) natural
# key (see orm.py) — treated the same as the other join tables so a re-import after a local
# delete+recreate (same natural key, new id) never trips the unique constraint on insert.
_JOIN_TABLE_NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "book_scene_links": ("book_id", "scene_id"),
    "book_codex_links": ("book_id", "codex_entry_id"),
    "codex_scene_links": ("codex_entry_id", "scene_id"),
    "entity_images": ("image_id", "entity_type", "entity_id"),
    "book_scene_order": ("book_id", "scene_id"),
}

# Timestamp-ish columns that drift harmlessly across export/import round-trips — never
# counted as a "meaningful" difference when deciding matched vs. conflict.
_IGNORED_FIELDS = frozenset({"created_at", "updated_at", "added_at", "generated_at"})

# Preferred order to pick a human-readable label for a row, if it has one at all.
_LABEL_FIELDS = ("name", "title", "display_name")


class EntityChange(BaseModel):
    """One row that is either brand-new (`created`) or identical to what's already in the
    database (`matched`)."""

    table: str
    id: str
    name: str | None = None


class EntityConflict(BaseModel):
    """One row whose UUID already exists locally but whose content differs."""

    table: str
    id: str
    name: str | None = None
    differing_fields: list[str] = Field(default_factory=list)


class MergeReport(BaseModel):
    """Dry-run result of `inspect_bundle` — what an import WOULD do, nothing more."""

    schema_version: int
    book_id: str
    created: list[EntityChange] = Field(default_factory=list)
    matched: list[EntityChange] = Field(default_factory=list)
    conflicts: list[EntityConflict] = Field(default_factory=list)
    asset_warnings: list[str] = Field(default_factory=list)


def read_bundle(
    blob: bytes, passphrase: str
) -> tuple[BundleManifest, BundlePayload, zipfile.ZipFile]:
    """Decrypts, unzips, and parses a `.quillproj` bundle.

    Order matters: the manifest's `schema_version` is validated BEFORE any `data/*.json`
    is read, so an unsupported future schema version is rejected without ever attempting to
    interpret its (potentially incompatible) row shapes.

    Raises `BundlePassphraseError` for a wrong passphrase or corrupted/tampered ciphertext
    (propagated from `decrypt_bundle`, unchanged). Raises `BundleImportError` for a
    correctly-decrypted but structurally invalid bundle (not a zip, missing/malformed
    `manifest.json`). Raises `BundleSchemaError` for a well-formed manifest whose
    `schema_version` this app doesn't support.

    Returns the open `zipfile.ZipFile` so a caller that needs the asset files too (the
    future `apply_bundle`) doesn't have to re-decrypt/re-unzip. `inspect_bundle` below only
    needs the manifest + payload and closes the zip itself before returning.
    """
    plaintext = decrypt_bundle(blob, passphrase)  # BundlePassphraseError propagates as-is

    try:
        zf = zipfile.ZipFile(io.BytesIO(plaintext))
    except zipfile.BadZipFile as exc:
        raise BundleImportError("Corrupt or invalid .quillproj bundle") from exc

    try:
        manifest_raw = zf.read("manifest.json")
    except KeyError as exc:
        zf.close()
        raise BundleImportError("Bundle is missing manifest.json") from exc

    try:
        manifest = BundleManifest.model_validate_json(manifest_raw)
    except ValidationError as exc:
        zf.close()
        raise BundleImportError("Bundle manifest.json is malformed") from exc

    try:
        validate_manifest_version(manifest)
    except BundleSchemaError:
        zf.close()
        raise

    payload_kwargs: dict[str, list[dict]] = {}
    for field_name in BundlePayload.model_fields:
        arcname = f"data/{field_name}.json"
        if arcname in zf.namelist():
            try:
                payload_kwargs[field_name] = json.loads(zf.read(arcname))
            except (KeyError, json.JSONDecodeError) as exc:
                zf.close()
                raise BundleImportError(f"Bundle data/{field_name}.json is malformed") from exc

    try:
        payload = BundlePayload(**payload_kwargs)
    except ValidationError as exc:
        zf.close()
        raise BundleImportError("Bundle payload data is malformed") from exc

    return manifest, payload, zf


def _row_label(row: dict) -> str | None:
    for key in _LABEL_FIELDS:
        value = row.get(key)
        if value is not None:
            return str(value)
    return None


def _pk_identity(pk_columns: tuple[str, ...], row: dict) -> tuple[str, object]:
    """Returns (a display string for the row's id, the value to pass to `session.get`)."""
    pk_values = tuple(row[col] for col in pk_columns)
    display = "|".join(str(v) for v in pk_values)
    identity = pk_values if len(pk_values) > 1 else pk_values[0]
    return display, identity


def _existing_row_dict(existing) -> dict:
    return {c.name: getattr(existing, c.name) for c in existing.__table__.columns}


def _differing_fields(incoming: dict, existing: dict, pk_columns: tuple[str, ...]) -> list[str]:
    differing: list[str] = []
    for key, incoming_value in incoming.items():
        if key in _IGNORED_FIELDS or key in pk_columns:
            continue
        if existing.get(key) != incoming_value:
            differing.append(key)
    return sorted(differing)


class _RowClassification(NamedTuple):
    """One bundle row's classification against the local database — the single source of
    truth shared by `inspect_bundle` (read-only report) and `apply_import` (the writer), so
    the two can never disagree about what a row is."""

    row: dict
    display_id: str
    identity: object
    label: str | None
    existing: object | None
    status: str  # "created" | "matched" | "conflict"
    differing_fields: list[str]


def _classify_row(
    session: Session, model: type, pk_columns: tuple[str, ...], row: dict
) -> _RowClassification:
    """Looks up `row` by its own primary key against the local database and classifies it
    as `created` (no existing row), `matched` (existing row, no meaningful field differs —
    see `_IGNORED_FIELDS`), or `conflict` (existing row, at least one field differs). Read
    -only: only issues a `session.get` lookup, never writes."""
    display_id, identity = _pk_identity(pk_columns, row)
    label = _row_label(row)
    existing = session.get(model, identity)

    if existing is None:
        return _RowClassification(row, display_id, identity, label, None, "created", [])

    existing_dict = _existing_row_dict(existing)
    differing = _differing_fields(row, existing_dict, pk_columns)
    if differing:
        return _RowClassification(row, display_id, identity, label, existing, "conflict", differing)
    return _RowClassification(row, display_id, identity, label, existing, "matched", [])


def inspect_bundle(session: Session, blob: bytes, passphrase: str) -> MergeReport:
    """Read-only dry-run: reports what importing `blob` WOULD do, without writing anything.

    For every row in every table of the bundle's payload, classifies it via `_classify_row`
    as newly-`created`, already-`matched`, or in `conflicts`. Never calls
    `session.add`/`session.flush`/`session.commit` — the only reads here are `session.get`
    lookups against rows already committed by prior work.
    """
    manifest, payload, zf = read_bundle(blob, passphrase)
    zf.close()  # dry-run inspection never needs the bundle's asset files

    created: list[EntityChange] = []
    matched: list[EntityChange] = []
    conflicts: list[EntityConflict] = []

    for table_name, (model, pk_columns) in _TABLE_REGISTRY.items():
        rows = getattr(payload, table_name)
        for row in rows:
            c = _classify_row(session, model, pk_columns, row)
            if c.status == "created":
                created.append(EntityChange(table=table_name, id=c.display_id, name=c.label))
            elif c.status == "matched":
                matched.append(EntityChange(table=table_name, id=c.display_id, name=c.label))
            else:
                conflicts.append(
                    EntityConflict(
                        table=table_name,
                        id=c.display_id,
                        name=c.label,
                        differing_fields=c.differing_fields,
                    )
                )

    return MergeReport(
        schema_version=manifest.schema_version,
        book_id=manifest.book_id,
        created=created,
        matched=matched,
        conflicts=conflicts,
        asset_warnings=list(manifest.asset_warnings),
    )


# ── apply_import — the ONLY writer in this module ─────────────────────────────


def _apply_take_imported(existing: object, incoming: dict, pk_columns: tuple[str, ...]) -> None:
    """`take_imported` resolution: overwrite every local scalar column with the bundle's
    value, except the PK (never rewritten) and `created_at` (local creation time is
    preserved even when the rest of the row is replaced)."""
    for key, value in incoming.items():
        if key in pk_columns or key == "created_at":
            continue
        setattr(existing, key, value)


def _apply_merge_fill(existing: object, incoming: dict, pk_columns: tuple[str, ...]) -> None:
    """`merge` resolution: imported values fill LOCAL gaps only — a column is only ever
    taken from the bundle if the local value is NULL/empty-string AND the imported value is
    non-empty. Never clobbers existing local content (the "never lose data, never silently
    overwrite" rule applies to imports too, not just AI transforms)."""
    for key, value in incoming.items():
        if key in pk_columns or key in _IGNORED_FIELDS:
            continue
        current = getattr(existing, key)
        if (current is None or current == "") and value not in (None, ""):
            setattr(existing, key, value)


def _resolve_conflict(
    table_name: str,
    c: _RowClassification,
    resolutions: dict[str, str],
    pk_columns: tuple[str, ...],
) -> str:
    """Applies the caller's chosen resolution for one same-PK conflict and returns which
    action was actually taken. Absent from `resolutions` -> `keep_local` (the safe
    default — never silently take the imported value)."""
    action = resolutions.get(c.display_id, "keep_local")
    if action == "keep_local":
        return "keep_local"
    if action == "take_imported":
        _apply_take_imported(c.existing, c.row, pk_columns)
        return "take_imported"
    if action == "merge":
        _apply_merge_fill(c.existing, c.row, pk_columns)
        return "merge"
    raise BundleImportError(
        f"Unknown resolution '{action}' for {table_name}:{c.display_id} "
        "(expected keep_local, take_imported, or merge)"
    )


def _apply_canonical_row(
    session: Session,
    model: type,
    table_name: str,
    pk_columns: tuple[str, ...],
    row: dict,
    resolutions: dict[str, str],
    created: list[EntityChange],
    matched: list[EntityChange],
    conflicts: list[EntityConflict],
) -> str:
    """Applies one row of a CANONICAL table (every table except the join/association
    tables in `_JOIN_TABLE_NATURAL_KEYS`). Returns the action actually taken (`"created"`,
    `"matched"`, `"keep_local"`, `"take_imported"`, or `"merge"`) so callers that extract
    on-disk assets (images/voice_notes/draft_versions) know whether a fresh/updated asset
    file needs extracting."""
    c = _classify_row(session, model, pk_columns, row)
    if c.status == "created":
        session.add(model(**row))
        session.flush()
        created.append(EntityChange(table=table_name, id=c.display_id, name=c.label))
        return "created"
    if c.status == "matched":
        matched.append(EntityChange(table=table_name, id=c.display_id, name=c.label))
        return "matched"

    action = _resolve_conflict(table_name, c, resolutions, pk_columns)
    conflicts.append(
        EntityConflict(
            table=table_name, id=c.display_id, name=c.label, differing_fields=c.differing_fields
        )
    )
    return action


def _apply_join_row(
    session: Session,
    model: type,
    table_name: str,
    pk_columns: tuple[str, ...],
    natural_key_cols: tuple[str, ...],
    row: dict,
    resolutions: dict[str, str],
    created: list[EntityChange],
    matched: list[EntityChange],
    conflicts: list[EntityConflict],
) -> None:
    """Applies one row of a JOIN/ASSOCIATION table (`book_scene_links`, `book_codex_links`,
    `codex_scene_links`, `entity_images`).

    THE ANTI-DUPLICATION INVARIANT: these tables have their own surrogate `id` PK, but a
    UNIQUE natural key (e.g. `book_scene_links` -> `(book_id, scene_id)`). Inserting by
    `id` blindly would let a re-import bring in a fresh `id` for a link that already exists
    locally under the SAME natural key but a DIFFERENT `id` -> a duplicate link row. So this
    function ALWAYS checks the natural key first, before ever deciding to insert:
      * natural key absent locally -> fall through to ordinary PK-based created/matched/
        conflict handling (the surrogate id is new too, in the overwhelming common case).
      * natural key present locally under the SAME surrogate id -> ordinary matched/conflict
        resolution (nothing about the dedup logic changes here).
      * natural key present locally under a DIFFERENT surrogate id -> NEVER insert; treat as
        already satisfied, at most gap-filling non-key fields (role/note/color) from the
        bundle — this is the case that would otherwise duplicate the link.
    """
    nat_conditions = [getattr(model, col) == row[col] for col in natural_key_cols]
    existing_by_natural = session.execute(select(model).where(*nat_conditions)).scalars().first()
    display_id, _identity = _pk_identity(pk_columns, row)
    label = _row_label(row)

    if existing_by_natural is None:
        c = _classify_row(session, model, pk_columns, row)
        if c.status == "created":
            session.add(model(**row))
            session.flush()
            created.append(EntityChange(table=table_name, id=c.display_id, name=c.label))
            return
        if c.status == "matched":
            matched.append(EntityChange(table=table_name, id=c.display_id, name=c.label))
            return
        _resolve_conflict(table_name, c, resolutions, pk_columns)
        conflicts.append(
            EntityConflict(
                table=table_name, id=c.display_id, name=c.label, differing_fields=c.differing_fields
            )
        )
        return

    existing_dict = _existing_row_dict(existing_by_natural)
    local_pk_value = existing_dict[pk_columns[0]]
    if str(local_pk_value) == str(row[pk_columns[0]]):
        # Same surrogate id AND same natural key -> ordinary matched/conflict resolution.
        differing = _differing_fields(row, existing_dict, pk_columns)
        if not differing:
            matched.append(EntityChange(table=table_name, id=display_id, name=label))
            return
        classification = _RowClassification(
            row, display_id, local_pk_value, label, existing_by_natural, "conflict", differing
        )
        _resolve_conflict(table_name, classification, resolutions, pk_columns)
        conflicts.append(
            EntityConflict(table=table_name, id=display_id, name=label, differing_fields=differing)
        )
        return

    # Natural key already satisfied locally under a DIFFERENT surrogate id -- inserting this
    # row would create a duplicate link. Never insert; at most gap-fill non-key fields.
    _apply_merge_fill(existing_by_natural, row, pk_columns)
    matched.append(EntityChange(table=table_name, id=display_id, name=label))


def _safe_extract_asset(
    zf: zipfile.ZipFile, arcname: str, base_dir: Path, relative_path: Path
) -> None:
    """Extracts `arcname` from `zf` to `base_dir / relative_path`, guarding against zip-slip
    (a malicious/tampered bundle whose stored path tries to escape `base_dir`) — same guard
    pattern as `images_service.resolve_path`: resolve, then assert the result is still inside
    `base_dir`. Silently no-ops if the asset simply isn't in the bundle (already recorded as
    a warning at export time, per `gather_bundle`) — the row still imports; only the file is
    missing. Raises `BundleImportError` (aborting/rolling back the whole import) if the
    stored path would escape `base_dir` — this is a security violation, not a missing file.
    """
    if arcname not in zf.namelist():
        return
    full = (base_dir / relative_path).resolve()
    if not full.is_relative_to(base_dir.resolve()):
        raise BundleImportError(
            f"Refusing to extract asset outside target directory: {relative_path}"
        )
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(zf.read(arcname))


def _extract_image_asset(zf: zipfile.ZipFile, settings, row: dict) -> None:
    storage_path = row.get("storage_path")
    if not storage_path:
        return
    _safe_extract_asset(zf, f"media/{storage_path}", settings.media_dir, Path(storage_path))


def _extract_voice_note_asset(zf: zipfile.ZipFile, settings, row: dict) -> None:
    audio_path = row.get("audio_path")
    if not audio_path:
        return
    _safe_extract_asset(zf, f"audio/{audio_path}", settings.audio_dir, Path(audio_path))


def _extract_draft_asset(zf: zipfile.ZipFile, settings, row: dict) -> None:
    """`draft_versions.file_path` is stored relative to `settings.data_dir` and already
    includes its own `drafts/...` prefix (mirrors `gather_bundle`'s comment on the export
    side) — but the zip arcname `gather_bundle` writes is just `drafts/<basename>` (it never
    nests the full relative structure). An absolute `file_path` can't be safely relocated
    under `data_dir`, so it's skipped (the row still imports; only the file is absent)."""
    file_path = row.get("file_path")
    if not file_path:
        return
    stored_path = Path(file_path)
    if stored_path.is_absolute():
        return
    _safe_extract_asset(zf, f"drafts/{stored_path.name}", settings.data_dir, stored_path)


def _apply_all_tables(
    session: Session,
    payload: BundlePayload,
    resolutions: dict[str, str],
    zf: zipfile.ZipFile,
    settings,
) -> tuple[list[EntityChange], list[EntityChange], list[EntityConflict]]:
    created: list[EntityChange] = []
    matched: list[EntityChange] = []
    conflicts: list[EntityConflict] = []

    # Iteration order matters here even though every column is a plain UUID string: rows
    # are inserted in `_TABLE_REGISTRY`'s declared order, which is FK-dependency-safe
    # (e.g. `scenes` before `screenplay_elements`, `images` before `image_tags`) — see the
    # module-level comment above `_TABLE_REGISTRY`.
    for table_name, (model, pk_columns) in _TABLE_REGISTRY.items():
        rows = getattr(payload, table_name)
        natural_key_cols = _JOIN_TABLE_NATURAL_KEYS.get(table_name)

        for row in rows:
            if natural_key_cols:
                _apply_join_row(
                    session, model, table_name, pk_columns, natural_key_cols, row,
                    resolutions, created, matched, conflicts,
                )
                continue

            action = _apply_canonical_row(
                session, model, table_name, pk_columns, row,
                resolutions, created, matched, conflicts,
            )
            if action in ("created", "take_imported"):
                if table_name == "images":
                    _extract_image_asset(zf, settings, row)
                elif table_name == "voice_notes":
                    _extract_voice_note_asset(zf, settings, row)
                elif table_name == "draft_versions":
                    _extract_draft_asset(zf, settings, row)

    return created, matched, conflicts


def apply_import(
    session: Session,
    blob: bytes,
    passphrase: str,
    resolutions: dict[str, str],
) -> MergeReport:
    """Applies a `.quillproj` bundle to the local database — the ONLY writer in this
    module. `resolutions` maps a conflicting entity's PK-string (the same `id` string
    `inspect_bundle`/`MergeReport` report — for composite-PK tables, i.e. `image_tags`,
    the format is `"<image_id>|<tag>"`) to one of `"keep_local"` | `"take_imported"` |
    `"merge"`. A PK absent from `resolutions` defaults to `"keep_local"` — the safe default,
    since silently taking the imported value would be exactly the kind of silent overwrite
    `CLAUDE.md`/`docs/01-PRODUCT-VISION.md` forbid.

    Runs the ENTIRE merge inside one transaction: `session.begin()`, or
    `session.begin_nested()` (a SAVEPOINT) if the session already has an open transaction
    (detected via `session.in_transaction()` BEFORE this function touches the session at
    all — SQLAlchemy 2.0 sessions auto-begin on first use, so this check must happen first).
    ANY exception — a malformed bundle, an unknown resolution value, a zip-slip asset path,
    a database constraint violation — rolls back every write made so far; the bundle either
    applies completely or not at all, never partially.

    Re-runs `read_bundle` itself (schema_version is validated before any row is touched,
    exactly as in `inspect_bundle`) rather than trusting a caller-supplied dry-run report,
    so `apply_import` is safe to call standalone.
    """
    resolutions = dict(resolutions) if resolutions else {}
    settings = get_settings()
    already_in_transaction = session.in_transaction()

    def _run() -> MergeReport:
        manifest, payload, zf = read_bundle(blob, passphrase)
        try:
            created, matched, conflicts = _apply_all_tables(
                session, payload, resolutions, zf, settings
            )
        finally:
            zf.close()

        # Phase 10 (semantic search / sqlite-vec) regenerates embeddings from imported rows;
        # not installed yet on this build machine (CLAUDE.md environment constraints) —
        # stub only, no real work.
        logger.info("embeddings regeneration queued (stub)")

        return MergeReport(
            schema_version=manifest.schema_version,
            book_id=manifest.book_id,
            created=created,
            matched=matched,
            conflicts=conflicts,
            asset_warnings=list(manifest.asset_warnings),
        )

    if already_in_transaction:
        with session.begin_nested():
            return _run()
    with session.begin():
        return _run()
