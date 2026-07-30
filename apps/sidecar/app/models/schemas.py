"""Pydantic v2 schemas — request/response contracts.

These drive FastAPI's OpenAPI schema, which `openapi-typescript` turns into the frontend's
TS types (docs/02). Kept deliberately small for Phase 0 (health + settings); per-resource
schemas (books, scenes, codex, …) are added in their roadmap phases.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Health ────────────────────────────────────────────────────────────────────
class OllamaHealth(BaseModel):
    reachable: bool
    base_url: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    service: str = "quillnight-sidecar"
    version: str
    database: Literal["ok", "error"]
    ollama: OllamaHealth


# ── Settings (app_settings key/value store) ────────────────────────────────────
class SettingItem(BaseModel):
    key: str
    value: Any = None


class SettingsUpdate(BaseModel):
    """Patch one or more settings at once."""

    values: dict[str, Any] = Field(default_factory=dict)


class SettingsResponse(BaseModel):
    """All settings, merged over the built-in defaults so the client always gets a full set."""

    values: dict[str, Any]


# ── Books (docs/03-DATA-MODEL.md `books`; docs/06 Phase 1) ────────────────────
BookType = Literal["story_book", "movie_script", "short_film_script", "single_scene"]


class BookCreate(BaseModel):
    title: str = Field(min_length=1)
    book_type: BookType
    logline: str | None = None
    front_matter: dict[str, Any] | None = None


class BookUpdate(BaseModel):
    """Partial update — only the fields provided are changed."""

    title: str | None = None
    logline: str | None = None
    front_matter: dict[str, Any] | None = None
    structure_template_id: str | None = None
    cover_image_id: str | None = None


class BookConvert(BaseModel):
    book_type: BookType


class BookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    book_type: BookType
    structure_template_id: str | None
    logline: str | None
    front_matter: dict[str, Any] | None
    cover_image_id: str | None
    created_at: str
    updated_at: str


# ── Scenes (docs/03-DATA-MODEL.md `scenes`; docs/01 Node Canvas; docs/06 Phase 2) ─
NodeType = Literal["scene", "plot_point", "thought"]


class SceneCreate(BaseModel):
    node_type: NodeType
    title: str = Field(min_length=1)
    description: str | None = None


class SceneUpdate(BaseModel):
    """Partial update — only the fields provided are changed."""

    title: str | None = None
    description: str | None = None
    status: str | None = None


class SceneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    node_type: NodeType
    title: str
    description: str | None
    status: str | None
    word_count: int
    created_at: str
    updated_at: str


# ── Screenplay elements (docs/03-DATA-MODEL.md `screenplay_elements`; docs/01) ────
# NOTE: these coexist with Scene.description — adding/editing elements must NEVER
# clear or touch it (non-destructive conversion between prose and screenplay form).
ScreenplayElementType = Literal[
    "scene_heading",
    "action",
    "character",
    "dialogue",
    "parenthetical",
    "transition",
    "shot",
    "dual_dialogue",
]


class ScreenplayElementCreate(BaseModel):
    element_type: ScreenplayElementType
    text: str
    order_index: int | None = None


class ScreenplayElementUpdate(BaseModel):
    """Partial update — only the fields provided are changed."""

    element_type: ScreenplayElementType | None = None
    text: str | None = None
    order_index: int | None = None


class ScreenplayElementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scene_id: str
    order_index: int
    element_type: ScreenplayElementType
    text: str


class ScreenplayElementReorder(BaseModel):
    """Ordered list of element IDs — the new order_index is each id's position."""

    element_ids: list[str] = Field(min_length=1)


# ── Node Canvas — per-Book membership/layout + graph edges (docs/03-DATA-MODEL.md
# `book_scene_links` / `scene_connections`; docs/01 Node Canvas; docs/06 Phase 2 tasks A3-A5) ─
ConnectionType = Literal["sequence", "causal", "reference", "contradiction", "custom"]


class CanvasNode(BaseModel):
    """A Scene as placed on one Book's canvas — canonical Scene fields plus this Book's
    link (position/color). ``link_id`` identifies the ``BookSceneLink`` row itself, not the
    scene, since a Scene can appear on multiple Books' canvases."""

    link_id: str
    scene_id: str
    node_type: NodeType
    title: str
    description: str | None
    status: str | None
    canvas_x: float | None
    canvas_y: float | None
    color: str | None


class CanvasEdge(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_scene_id: str
    target_scene_id: str
    source_handle: str | None
    target_handle: str | None
    connection_type: ConnectionType | None
    label: str | None


class CanvasResponse(BaseModel):
    nodes: list[CanvasNode]
    edges: list[CanvasEdge]


class LinkCreate(BaseModel):
    """Add an existing Scene to a Book's canvas. Never creates a new Scene."""

    canvas_x: float | None = None
    canvas_y: float | None = None
    color: str | None = None


class LinkUpdate(BaseModel):
    """Partial update — only the fields provided are changed."""

    canvas_x: float | None = None
    canvas_y: float | None = None
    color: str | None = None


class ApplyCanvasTemplateRequest(BaseModel):
    """Seed a Book's (blank) canvas with a starter template — see
    ``services/canvas_template_service.py`` for the available ``template_key``s."""

    template_key: str


class EdgeCreate(BaseModel):
    source_scene_id: str
    target_scene_id: str
    source_handle: str | None = None
    target_handle: str | None = None
    connection_type: ConnectionType | None = None
    label: str | None = None


class EdgeUpdate(BaseModel):
    """Partial update — only the fields provided are changed."""

    source_scene_id: str | None = None
    target_scene_id: str | None = None
    source_handle: str | None = None
    target_handle: str | None = None
    connection_type: ConnectionType | None = None
    label: str | None = None


# ── Codex (docs/03-DATA-MODEL.md `codex_entries`; docs/01 Codex; docs/06 Phase 2 tasks B1/B2) ─
# Codex entries are canonical and shared across Books, like Scenes — this covers only the
# entry row itself plus its links to Scenes/Books; relationships/arc states are later tasks.
CodexEntryType = Literal["character", "location", "faction", "object_lore"]


class CodexEntryCreate(BaseModel):
    entry_type: CodexEntryType
    name: str = Field(min_length=1)
    summary: str | None = None
    custom_fields: dict[str, Any] | None = None


class CodexEntryUpdate(BaseModel):
    """Partial update — only the fields provided are changed."""

    name: str | None = None
    summary: str | None = None
    custom_fields: dict[str, Any] | None = None
    primary_image_id: str | None = None


class CodexEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entry_type: CodexEntryType
    name: str
    summary: str | None
    custom_fields: dict[str, Any] | None
    primary_image_id: str | None
    created_at: str
    updated_at: str


# ── Images (docs/03-DATA-MODEL.md `images` / `image_tags`; docs/06 Phase 3 task BE-3,
# Phase 5 tasks BE-1/BE-2) — both buckets, real Pillow-decoded dimensions, thumbnails, and
# freeform tags. `tags` is always populated (sorted) alongside the Image row itself so
# list/detail/upload responses stay consistent — see
# app/services/images_service.py's `_read_with_tags` helper. ───────────────────────────
class ImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bucket: str
    storage_path: str
    display_name: str
    original_filename: str | None
    description: str | None
    width: int | None
    height: int | None
    checksum_sha256: str | None
    tags: list[str] = []
    created_at: str
    updated_at: str


class ImageUpdate(BaseModel):
    """Partial update — only the fields provided are changed. ``description`` may be set to
    ``""`` deliberately (clearing it); leaving it unset leaves the stored value untouched —
    see the `exclude_unset` dict-based partial-update pattern used by every other PATCH route
    in this codebase (e.g. `CodexEntryUpdate`)."""

    display_name: str | None = None
    description: str | None = None


class ImageTagAdd(BaseModel):
    tag: str


# ── Polymorphic image<->entity attach (docs/03-DATA-MODEL.md `entity_images`; docs/06
# Phase 5 task BE-3) — links an Image to a book/scene/codex_entry, independent of
# `cover_image_id` / `primary_image_id` (those are single-slot pointers; this is a
# many-to-many attach list, e.g. a Scene's moodboard). Named `EntityImageLinkCreate`
# rather than `LinkCreate` to avoid clashing with the canvas `LinkCreate` schema above
# (Book<->Scene canvas membership), which is an unrelated resource. ─────────────────────
EntityImageEntityType = Literal["book", "scene", "codex_entry"]


class EntityImageLinkCreate(BaseModel):
    entity_type: EntityImageEntityType
    entity_id: str = Field(min_length=1)
    role: str | None = None


class EntityImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    image_id: str
    entity_type: str
    entity_id: str
    role: str | None


# ── Structure templates (docs/03-DATA-MODEL.md `structure_templates`; docs/06 Phase 4
# task BE-2) — built-in seed data (Three-Act, Hero's Journey, Freeform), read-only over
# the wire. ``applicable_book_types`` of ``None`` means "applies to every book type". ──
class StructureTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    applicable_book_types: list[str] | None
    beats: list[dict[str, Any]] | None


# ── Chapters (docs/03-DATA-MODEL.md `chapters`; docs/06 Phase 4 task BE-2) — per-Book
# grouping of the Outline view. Unlike Scenes/Codex, Chapters are NOT canonical/shared —
# they belong to exactly one Book and cascade-delete with it. ────────────────────────────
class ChapterCreate(BaseModel):
    title: str = Field(min_length=1)
    order_index: int | None = Field(default=None, ge=0)


class ChapterUpdate(BaseModel):
    """Partial update — only the fields provided are changed."""

    title: str | None = None
    order_index: int | None = Field(default=None, ge=0)


class ChapterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    book_id: str
    title: str
    order_index: int


# ── Outline/Timeline mediator (docs/03-DATA-MODEL.md `book_scene_order`; docs/06 Phase 4
# task BE-3) — ONE row per (book_id, scene_id) backs BOTH the Outline (beat-board) and
# Timeline views; see app/services/outline_service.py module docstring. ─────────────────
class BookSceneOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    book_id: str
    scene_id: str
    chapter_id: str | None
    outline_order_index: int | None
    structure_beat: str | None
    timeline_order_index: int | None
    in_story_time_label: str | None
    in_story_time_sort_key: float | None


class AssignSceneRequest(BaseModel):
    """Partial update — only the fields provided are changed; other fields on the same
    (book, scene) row — including any Timeline fields — are left untouched."""

    chapter_id: str | None = None
    structure_beat: str | None = None
    outline_order_index: int | None = Field(default=None, ge=0)


class ReorderRequest(BaseModel):
    """Authoritative reindex — each id's position in this list becomes its new
    order_index (0..n)."""

    scene_ids: list[str] = Field(min_length=1)


class TimelineSetRequest(BaseModel):
    """Partial update — only the fields provided are changed; any already-set Outline
    fields on the same (book, scene) row are left untouched."""

    timeline_order_index: int | None = Field(default=None, ge=0)
    in_story_time_label: str | None = None
    in_story_time_sort_key: float | None = None


# ── Codex relationships (docs/03-DATA-MODEL.md `codex_relationships`; docs/06 Phase 3
# task BE-1) — entity<->entity cross-linking, distinct from the Scene/Book links above. ─
class CodexRelationshipCreate(BaseModel):
    """``from_entry_id`` comes from the path (``POST /codex/{entry_id}/relationships``),
    not the body."""

    to_entry_id: str
    relationship_type: str = Field(min_length=1, max_length=64)
    description: str | None = None


class CodexRelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    from_entry_id: str
    to_entry_id: str
    relationship_type: str
    description: str | None


# ── Codex arc-states (docs/03-DATA-MODEL.md `codex_arc_states`; docs/06 Phase 3 task BE-2) —
# point-in-time entity snapshots consumed by prompt_builder.build_codex_context's anti-spoiler
# filter. ``codex_entry_id`` comes from the path (``POST /codex/{entry_id}/arc-states``), not
# the body. ────────────────────────────────────────────────────────────────────────────────
class CodexArcStateCreate(BaseModel):
    book_id: str
    as_of_outline_order_index: int = Field(ge=0)
    status_summary: str | None = None
    traits_snapshot: dict[str, Any] | None = None


class CodexArcStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    codex_entry_id: str
    book_id: str
    as_of_outline_order_index: int
    status_summary: str | None
    traits_snapshot: dict[str, Any] | None
    created_at: str


# ── LLM Enhance/audit log (docs/04-LLM-INTEGRATION.md, docs/06 Phase 2 tasks D1/D2) ────
# The `/llm/enhance` endpoint streams a suggestion; it NEVER writes to `scenes` or
# `screenplay_elements` itself — Accept is a separate, explicit client-driven PATCH to the
# entity in question. This schema block only covers the request + the audit-log resource.
EnhanceMode = Literal["grammar", "prose", "continuity"]


class ContinuityFlagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    book_id: str
    scene_id: str | None
    codex_entry_id: str | None
    flag_type: str | None
    severity: str
    description: str
    status: str
    source: str | None
    created_at: str


class FlagStatusUpdate(BaseModel):
    status: Literal["open", "dismissed", "resolved"]


class EnhanceRequest(BaseModel):
    mode: EnhanceMode
    text: str = Field(min_length=1)
    entity_type: str | None = None
    entity_id: str | None = None
    field: str | None = None
    scene_id: str | None = None
    book_id: str | None = None


class LogAccept(BaseModel):
    accepted: bool


# ── Groq key seam (docs/06 Phase 2 task F1/F2, docs/08 "Secure API key storage") ──────
# DEV SEAM ONLY — see app/services/groq_key.py. The key value itself is NEVER a response
# field on any schema below; only a `present` boolean ever crosses the wire.
class GroqKeySet(BaseModel):
    key: str = Field(min_length=1)


class GroqKeyPresence(BaseModel):
    present: bool


class TestConnectionResult(BaseModel):
    ok: bool
    reason: str | None = None
    provider: str | None = None


class LlmLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    request_type: str | None
    entity_type: str | None
    entity_id: str | None
    book_id: str | None
    provider: str | None
    model_name: str | None
    latency_ms: int | None
    accepted: int | None
    created_at: str


# ── Voice notes (docs/03-DATA-MODEL.md `voice_notes`; docs/12-VOICE-AND-SPEECH.md;
# docs/06 Phase 2 tasks E1/E2) ─────────────────────────────────────────────────
# Dictation audio always arrives as the raw request body (browser MediaRecorder blob) —
# there is no VoiceNoteCreate; `POST /voice/transcribe` builds the row itself from the
# uploaded bytes plus the transcription result. See app/services/speech_stt.py.
VoiceNoteStatus = Literal["recorded", "transcribed", "attached", "discarded"]


class VoiceNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    audio_path: str
    transcript: str | None
    engine: str | None
    duration_ms: int | None
    attached_entity_type: str | None
    attached_entity_id: str | None
    status: VoiceNoteStatus
    created_at: str


class AttachRequest(BaseModel):
    """Points a voice note at the entity/field it was dictated into (docs/12 "the
    transcript lands in the focused field"). Attaching never deletes the audio."""

    attached_entity_type: str = Field(min_length=1)
    attached_entity_id: str = Field(min_length=1)


# ── Profiles & local auth (docs/13-PROFILES-AND-AUTH.md) ──────────────────────
# A UI/profile LOCK, not encryption — the SQLite database stays plaintext on disk.
# ``ProfilePublic`` NEVER includes ``password_hash``.
class ProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: str | None
    avatar: str | None


class ProfileCreate(BaseModel):
    """Validation of non-empty username/password is deliberately left to
    ``profiles_service.create_profile`` (not a Pydantic ``Field(min_length=1)``) so the
    422 error message stays the app's own contract rather than FastAPI's default shape.
    ``max_length`` bounds are still set here so an arbitrarily huge password is never fed
    to argon2."""

    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
    display_name: str | None = None
    avatar: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class LoginResponse(BaseModel):
    token: str
    user: ProfilePublic


# ── Draft versions / export (docs/03-DATA-MODEL.md `draft_versions`; docs/06 Phase 6
# task BE-1) — a compiled export snapshot of a Book. There is no `format` column on the
# ORM `DraftVersion` (it lives inside `format_settings` JSON, e.g. `{"format": "docx", ...}`),
# so `from_attributes=True` alone can NOT populate this schema — callers must construct
# `DraftVersionRead` explicitly (see app/services, not this module) pulling `format` out of
# `row.format_settings["format"]`. ────────────────────────────────────────────────────────
ExportFormat = Literal["markdown", "docx", "pdf", "fountain", "fdx"]


class DraftVersionRead(BaseModel):
    id: str
    book_id: str
    version_number: int
    format: str
    format_settings: dict | None = None
    is_current: bool
    generated_at: str
    notes: str | None = None


# ── `.quillproj` bundle export/import (docs/05-EXPORT-IMPORT-SECURITY.md; docs/06
# Phase 7 task 4). ``passphrase`` is never logged and never persisted anywhere — it only
# exists in-memory for the duration of one request (see app/services/bundle_crypto.py). ──
class BundleExportRequest(BaseModel):
    passphrase: str = Field(min_length=8)
    model_config = ConfigDict(from_attributes=True)


# ── Read-only manuscript preview (docs/06 Phase 8 — "manuscript reader"). Mirrors
# ``export_service``'s ``CompiledDocument``/``CompiledChapter``/``CompiledScene``/
# ``ScreenplayElementLike`` dataclasses field-for-field, but as its OWN Pydantic models —
# those dataclasses are internal to the export pipeline and are never returned directly from
# an HTTP handler (mirrors why ``DraftVersionRead`` exists separately from the ORM
# ``DraftVersion``). This is NOT an export: no file is written, no ``draft_versions`` row is
# created — see app/api/draft_preview.py. ───────────────────────────────────────────────────
class ScreenplayElementPreviewOut(BaseModel):
    element_type: str
    text: str
    order_index: int


class CompiledScenePreviewOut(BaseModel):
    title: str
    description: str
    elements: list[ScreenplayElementPreviewOut] = Field(default_factory=list)


class CompiledChapterPreviewOut(BaseModel):
    title: str | None
    scenes: list[CompiledScenePreviewOut] = Field(default_factory=list)


class DraftPreviewOut(BaseModel):
    book_id: str
    book_title: str
    book_type: str
    logline: str | None
    front_matter: dict | None
    cover_image_id: str | None
    chapters: list[CompiledChapterPreviewOut] = Field(default_factory=list)
