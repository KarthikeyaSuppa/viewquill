"""Gathers one Book's data into a `.quillproj` bundle and zips it (docs/05-EXPORT-IMPORT-
SECURITY.md; Phase 7 task 3).

`gather_bundle` walks every table that can be scoped to a single Book by UUID (via
`book_scene_links`/`book_codex_links` for the canonical Scene/Codex entries a Book
actually uses, and direct `book_id` foreign keys elsewhere) and returns a
`BundleManifest` + `BundlePayload` (see `app.services.bundle_schema`) plus a list of
on-disk asset files to include. `build_zip_bytes` then serializes those into a plain
(unencrypted) zip archive in memory.

Deliberately excluded, per `bundle_schema`'s own docstring: `llm_request_log`, `users`,
`app_settings`, `structure_templates`, `writing_sessions`, `achievements`,
`personal_dictionary`, and any embeddings/FTS derived-search tables — all local-only,
seed data, or regenerable post-import.

This module produces PLAINTEXT zip bytes only. Encryption (`app.services.bundle_crypto`)
is applied by the caller at the API endpoint layer (Phase 7 task 4) — this module must
never be given a passphrase and never imports `bundle_crypto`.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

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
from app.services.bundle_schema import CURRENT_SCHEMA_VERSION, BundleManifest, BundlePayload


class BundleExportError(Exception):
    """Raised when the requested Book (or other required data) cannot be exported."""


def _row_to_dict(row) -> dict:
    """Plain JSON-safe dict of a row's own columns — no relationships, no lazy loads."""
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def _rows(session: Session, model, *conditions) -> list:
    return list(session.execute(select(model).where(*conditions)).scalars().all())


def _rows_in(session: Session, model, column, ids: set) -> list:
    """Like `_rows` but for an `IN` filter — guards against emitting `IN ()` on an empty
    set (SQLAlchemy warns about that, and it's clearer to just short-circuit to [])."""
    if not ids:
        return []
    return list(session.execute(select(model).where(column.in_(ids))).scalars().all())


def gather_bundle(
    session: Session, book_id: str, *, exported_at: str
) -> tuple[BundleManifest, BundlePayload, list[tuple[str, Path]]]:
    """Gathers everything belonging to ONE Book (by UUID) into a manifest + payload +
    list of (arcname, absolute_source_path) asset files.

    Raises `BundleExportError` if `book_id` does not match any Book. Never raises for a
    missing asset FILE on disk — those are recorded in `manifest.asset_warnings` and
    skipped instead, so one damaged/moved file can never abort an entire export.
    """
    settings = get_settings()
    asset_warnings: list[str] = []
    asset_files: list[tuple[str, Path]] = []

    book = session.get(Book, book_id)
    if book is None:
        raise BundleExportError(f"Book {book_id} not found")

    book_scene_links = _rows(session, BookSceneLink, BookSceneLink.book_id == book_id)
    scene_ids = {link.scene_id for link in book_scene_links}

    scenes = _rows_in(session, Scene, Scene.id, scene_ids)
    screenplay_elements = _rows_in(
        session, ScreenplayElement, ScreenplayElement.scene_id, scene_ids
    )
    scene_connections = _rows(session, SceneConnection, SceneConnection.book_id == book_id)
    chapters = _rows(session, Chapter, Chapter.book_id == book_id)
    book_scene_order = _rows(session, BookSceneOrder, BookSceneOrder.book_id == book_id)

    book_codex_links = _rows(session, BookCodexLink, BookCodexLink.book_id == book_id)
    codex_entry_ids = {link.codex_entry_id for link in book_codex_links}

    codex_entries = _rows_in(session, CodexEntry, CodexEntry.id, codex_entry_ids)
    codex_relationships = (
        list(
            session.execute(
                select(CodexRelationship).where(
                    CodexRelationship.from_entry_id.in_(codex_entry_ids)
                    | CodexRelationship.to_entry_id.in_(codex_entry_ids)
                )
            )
            .scalars()
            .all()
        )
        if codex_entry_ids
        else []
    )
    codex_arc_states = _rows(session, CodexArcState, CodexArcState.book_id == book_id)
    codex_scene_links = (
        list(
            session.execute(
                select(CodexSceneLink).where(
                    CodexSceneLink.codex_entry_id.in_(codex_entry_ids),
                    CodexSceneLink.scene_id.in_(scene_ids),
                )
            )
            .scalars()
            .all()
        )
        if codex_entry_ids and scene_ids
        else []
    )

    continuity_flags = _rows(session, ContinuityFlag, ContinuityFlag.book_id == book_id)
    draft_versions = _rows(session, DraftVersion, DraftVersion.book_id == book_id)

    # ── Images: gather every entity_images row that attaches to this book/its scenes/its
    # codex entries, plus the book's cover image and each codex entry's primary image. ──
    entity_images_rows: list = []
    entity_images_rows += _rows(
        session,
        EntityImage,
        EntityImage.entity_type == "book",
        EntityImage.entity_id == book_id,
    )
    if scene_ids:
        entity_images_rows += list(
            session.execute(
                select(EntityImage).where(
                    EntityImage.entity_type == "scene",
                    EntityImage.entity_id.in_(scene_ids),
                )
            )
            .scalars()
            .all()
        )
    if codex_entry_ids:
        entity_images_rows += list(
            session.execute(
                select(EntityImage).where(
                    EntityImage.entity_type == "codex_entry",
                    EntityImage.entity_id.in_(codex_entry_ids),
                )
            )
            .scalars()
            .all()
        )

    image_ids: set[str] = {row.image_id for row in entity_images_rows}
    if book.cover_image_id:
        image_ids.add(book.cover_image_id)
    for entry in codex_entries:
        if entry.primary_image_id:
            image_ids.add(entry.primary_image_id)

    images = _rows_in(session, Image, Image.id, image_ids)
    image_tags = _rows_in(session, ImageTag, ImageTag.image_id, image_ids)

    # ── Voice notes attached to this book, its scenes, or its codex entries ──
    attach_ids = scene_ids | codex_entry_ids | {book_id}
    voice_notes = _rows_in(session, VoiceNote, VoiceNote.attached_entity_id, attach_ids)

    # ── Assets on disk ──
    for image in images:
        source = settings.media_dir / image.storage_path
        if source.is_file():
            asset_files.append((f"media/{image.storage_path}", source))
        else:
            asset_warnings.append(f"Missing image file for image {image.id}: {source}")

    for note in voice_notes:
        source = settings.audio_dir / note.audio_path
        if source.is_file():
            asset_files.append((f"audio/{note.audio_path}", source))
        else:
            asset_warnings.append(f"Missing audio file for voice note {note.id}: {source}")

    for draft in draft_versions:
        # `draft_versions.file_path` is stored RELATIVE TO `settings.data_dir` (already
        # includes its own "drafts/..." prefix — see app/api/export.py's
        # `_to_relative_file_path`), never relative to `drafts_dir` itself.
        stored_path = Path(draft.file_path)
        source = stored_path if stored_path.is_absolute() else settings.data_dir / stored_path
        if source.is_file():
            asset_files.append((f"drafts/{source.name}", source))
        else:
            asset_warnings.append(
                f"Missing draft file for draft version {draft.id}: {source}"
            )

    payload = BundlePayload(
        books=[_row_to_dict(book)],
        scenes=[_row_to_dict(r) for r in scenes],
        screenplay_elements=[_row_to_dict(r) for r in screenplay_elements],
        book_scene_links=[_row_to_dict(r) for r in book_scene_links],
        scene_connections=[_row_to_dict(r) for r in scene_connections],
        chapters=[_row_to_dict(r) for r in chapters],
        book_scene_order=[_row_to_dict(r) for r in book_scene_order],
        codex_entries=[_row_to_dict(r) for r in codex_entries],
        codex_relationships=[_row_to_dict(r) for r in codex_relationships],
        codex_arc_states=[_row_to_dict(r) for r in codex_arc_states],
        book_codex_links=[_row_to_dict(r) for r in book_codex_links],
        codex_scene_links=[_row_to_dict(r) for r in codex_scene_links],
        images=[_row_to_dict(r) for r in images],
        image_tags=[_row_to_dict(r) for r in image_tags],
        entity_images=[_row_to_dict(r) for r in entity_images_rows],
        continuity_flags=[_row_to_dict(r) for r in continuity_flags],
        draft_versions=[_row_to_dict(r) for r in draft_versions],
        voice_notes=[_row_to_dict(r) for r in voice_notes],
    )

    entity_counts = {
        field: len(value) for field, value in payload.model_dump().items() if value
    }

    manifest = BundleManifest(
        schema_version=CURRENT_SCHEMA_VERSION,
        book_id=book_id,
        exported_at=exported_at,
        entity_counts=entity_counts,
        checksums={},
        asset_warnings=asset_warnings,
    )

    return manifest, payload, asset_files


def build_zip_bytes(
    manifest: BundleManifest,
    payload: BundlePayload,
    asset_files: list[tuple[str, Path]],
) -> bytes:
    """Serializes `manifest` + `payload` + `asset_files` into plaintext zip bytes.

    `asset_files` is trusted to already only contain existing files — `gather_bundle`
    filters missing ones out into `manifest.asset_warnings` before this is called.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest.model_dump_json(indent=2))
        for field_name, value in payload.model_dump().items():
            if value:
                zf.writestr(f"data/{field_name}.json", json.dumps(value, indent=2, default=str))
        for arcname, source_path in asset_files:
            zf.write(source_path, arcname)
    return buffer.getvalue()


def export_book_to_zip_bytes(
    session: Session, book_id: str, *, exported_at: str
) -> tuple[bytes, BundleManifest]:
    """Convenience chain: `gather_bundle` -> `build_zip_bytes`. Returns the plaintext zip
    bytes and the manifest (so a caller can inspect `asset_warnings`/`entity_counts`
    without re-parsing the zip)."""
    manifest, payload, asset_files = gather_bundle(session, book_id, exported_at=exported_at)
    zip_bytes = build_zip_bytes(manifest, payload, asset_files)
    return zip_bytes, manifest
