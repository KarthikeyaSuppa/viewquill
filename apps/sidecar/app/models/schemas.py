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


# ── LLM Enhance/audit log (docs/04-LLM-INTEGRATION.md, docs/06 Phase 2 tasks D1/D2) ────
# The `/llm/enhance` endpoint streams a suggestion; it NEVER writes to `scenes` or
# `screenplay_elements` itself — Accept is a separate, explicit client-driven PATCH to the
# entity in question. This schema block only covers the request + the audit-log resource.
EnhanceMode = Literal["grammar", "prose", "continuity"]


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
