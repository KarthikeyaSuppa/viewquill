"""`.quillproj` bundle serialization schema (docs/05-EXPORT-IMPORT-SECURITY.md).

Defines the on-disk contract for a `.quillproj` export bundle: a `BundleManifest`
(metadata about the export — schema version, source book, row counts, asset
checksums/warnings) and a `BundlePayload` (the actual exported rows, one plain-dict
list per table).

Deliberately excluded from `BundlePayload`: `llm_request_log`, `users`,
`app_settings`, `structure_templates` (seed data referenced by id only),
`writing_sessions`, `achievements`, `personal_dictionary`, and any
embeddings/FTS tables — all of these are either local-only, seed data, or
derived/regenerated post-import (docs/11-AI-INTELLIGENCE.md §2).

Rows are kept as plain JSON-safe dicts rather than nested ORM/Pydantic models on
purpose: it keeps this schema dumb, stable, and forward-compatible across app
versions — table-shape changes are handled by the (future) import merge logic,
not by this module.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

CURRENT_SCHEMA_VERSION = 1


class BundleSchemaError(Exception):
    """Raised when a `.quillproj` bundle's schema_version is not supported."""


class BundleManifest(BaseModel):
    """Top-level metadata for a `.quillproj` export bundle."""

    schema_version: int = CURRENT_SCHEMA_VERSION
    book_id: str
    exported_at: str
    app_version: str = "0.0.0"
    entity_counts: dict[str, int] = Field(default_factory=dict)
    checksums: dict[str, str] = Field(default_factory=dict)
    asset_warnings: list[str] = Field(default_factory=list)


class BundlePayload(BaseModel):
    """The exported rows themselves — one plain-dict list per serialized table."""

    books: list[dict] = Field(default_factory=list)
    scenes: list[dict] = Field(default_factory=list)
    screenplay_elements: list[dict] = Field(default_factory=list)
    book_scene_links: list[dict] = Field(default_factory=list)
    scene_connections: list[dict] = Field(default_factory=list)
    chapters: list[dict] = Field(default_factory=list)
    book_scene_order: list[dict] = Field(default_factory=list)
    codex_entries: list[dict] = Field(default_factory=list)
    codex_relationships: list[dict] = Field(default_factory=list)
    codex_arc_states: list[dict] = Field(default_factory=list)
    book_codex_links: list[dict] = Field(default_factory=list)
    codex_scene_links: list[dict] = Field(default_factory=list)
    images: list[dict] = Field(default_factory=list)
    image_tags: list[dict] = Field(default_factory=list)
    entity_images: list[dict] = Field(default_factory=list)
    continuity_flags: list[dict] = Field(default_factory=list)
    draft_versions: list[dict] = Field(default_factory=list)
    voice_notes: list[dict] = Field(default_factory=list)


def validate_manifest_version(manifest: BundleManifest) -> None:
    """Raise `BundleSchemaError` if `manifest`'s schema_version isn't supported."""

    if manifest.schema_version != CURRENT_SCHEMA_VERSION:
        raise BundleSchemaError(
            f"Unsupported bundle schema_version {manifest.schema_version}; "
            f"this app supports {CURRENT_SCHEMA_VERSION}"
        )
