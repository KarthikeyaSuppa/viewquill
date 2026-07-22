"""SQLAlchemy 2.0 ORM models — the schema of record from docs/03-DATA-MODEL.md.

This module maps that schema 1:1 so it can serve as the first Alembic migration's
target. Later changes go through new Alembic revisions, never hand-edited DDL.

Conventions:
* Primary keys are UUID strings (``new_uuid``) — enables `.quillproj` merge-by-ID.
* Timestamps are ISO-8601 UTC text (``utcnow_iso``), matching the TEXT columns in the spec.
* ``CHECK`` constraints mirror the spec's enums exactly.
* ORM relationships are added per-phase as endpoints need them; this file defines the
  columns, keys, and constraints only, so the migration is unambiguous.

The derived search layer (``embeddings`` vec0 + ``search_fts`` FTS5) is intentionally NOT
modeled here — those are v1.1 virtual tables, rebuildable and excluded from backups; they
are created via raw SQL in the semantic-search service, not via migrations.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_uuid, utcnow_iso


# ── Books ────────────────────────────────────────────────────────────────────
class Book(Base):
    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint(
            "book_type IN ('story_book','movie_script','short_film_script','single_scene')",
            name="book_type",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String, nullable=False)
    book_type: Mapped[str] = mapped_column(String, nullable=False)
    structure_template_id: Mapped[str | None] = mapped_column(
        ForeignKey("structure_templates.id"), nullable=True
    )
    logline: Mapped[str | None] = mapped_column(Text, nullable=True)
    front_matter: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cover_image_id: Mapped[str | None] = mapped_column(ForeignKey("images.id"), nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, onupdate=utcnow_iso
    )


# ── Canonical node/scene entity (shared across Books) ─────────────────────────
class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        CheckConstraint("node_type IN ('scene','plot_point','thought')", name="node_type"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    node_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)  # mandatory per spec
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # NEVER cleared by conversion
    status: Mapped[str | None] = mapped_column(String, default="draft")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, onupdate=utcnow_iso
    )


# ── Structured screenplay content — coexists with Scene.description ───────────
class ScreenplayElement(Base):
    __tablename__ = "screenplay_elements"
    __table_args__ = (
        CheckConstraint(
            "element_type IN ('scene_heading','action','character','dialogue',"
            "'parenthetical','transition','shot','dual_dialogue')",
            name="element_type",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    element_type: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


# ── Per-Book canvas membership + layout ───────────────────────────────────────
class BookSceneLink(Base):
    __tablename__ = "book_scene_links"
    __table_args__ = (UniqueConstraint("book_id", "scene_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    canvas_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    canvas_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    color: Mapped[str | None] = mapped_column(String, nullable=True)
    added_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)


# ── Node-graph edges, scoped per Book ─────────────────────────────────────────
class SceneConnection(Base):
    __tablename__ = "scene_connections"
    __table_args__ = (
        CheckConstraint(
            "connection_type IN ('sequence','causal','reference','contradiction','custom')",
            name="connection_type",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    source_scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), nullable=False)
    target_scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), nullable=False)
    source_handle: Mapped[str | None] = mapped_column(String, nullable=True)
    target_handle: Mapped[str | None] = mapped_column(String, nullable=True)
    connection_type: Mapped[str | None] = mapped_column(String, nullable=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)


class StructureTemplate(Base):
    __tablename__ = "structure_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)  # 'Three-Act', "Hero's Journey", 'Freeform'
    applicable_book_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    beats: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{name, order_index, description}]


# ── Outline/Timeline mediator — ONE table backs BOTH views ────────────────────
class BookSceneOrder(Base):
    __tablename__ = "book_scene_order"
    __table_args__ = (UniqueConstraint("book_id", "scene_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id"), nullable=True)
    outline_order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    structure_beat: Mapped[str | None] = mapped_column(String, nullable=True)
    timeline_order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    in_story_time_label: Mapped[str | None] = mapped_column(String, nullable=True)
    in_story_time_sort_key: Mapped[float | None] = mapped_column(Float, nullable=True)


# ── Codex (canonical, shared across Books) ────────────────────────────────────
class CodexEntry(Base):
    __tablename__ = "codex_entries"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('character','location','faction','object_lore')", name="entry_type"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    entry_type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    primary_image_id: Mapped[str | None] = mapped_column(ForeignKey("images.id"), nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, onupdate=utcnow_iso
    )


class CodexRelationship(Base):
    __tablename__ = "codex_relationships"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    from_entry_id: Mapped[str] = mapped_column(
        ForeignKey("codex_entries.id", ondelete="CASCADE"), nullable=False
    )
    to_entry_id: Mapped[str] = mapped_column(
        ForeignKey("codex_entries.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class CodexArcState(Base):
    __tablename__ = "codex_arc_states"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    codex_entry_id: Mapped[str] = mapped_column(
        ForeignKey("codex_entries.id", ondelete="CASCADE"), nullable=False
    )
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    as_of_outline_order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    traits_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)


class BookCodexLink(Base):
    __tablename__ = "book_codex_links"
    __table_args__ = (UniqueConstraint("book_id", "codex_entry_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    codex_entry_id: Mapped[str] = mapped_column(
        ForeignKey("codex_entries.id", ondelete="CASCADE"), nullable=False
    )
    role_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CodexSceneLink(Base):
    __tablename__ = "codex_scene_links"
    __table_args__ = (UniqueConstraint("codex_entry_id", "scene_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    codex_entry_id: Mapped[str] = mapped_column(
        ForeignKey("codex_entries.id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── Images (two buckets) ──────────────────────────────────────────────────────
class Image(Base):
    __tablename__ = "images"
    __table_args__ = (
        CheckConstraint("bucket IN ('finalized_scene','reference_pool')", name="bucket"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    bucket: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)  # relative under app-data/media/
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # Enhance-able
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=utcnow_iso, onupdate=utcnow_iso
    )


class ImageTag(Base):
    __tablename__ = "image_tags"

    image_id: Mapped[str] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String, primary_key=True)


class EntityImage(Base):
    """Polymorphic attach — drives 'only images linked to THIS Book get exported'."""

    __tablename__ = "entity_images"
    __table_args__ = (
        CheckConstraint("entity_type IN ('book','scene','codex_entry')", name="entity_type"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    image_id: Mapped[str] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str | None] = mapped_column(String, nullable=True)


# ── Continuity flags (severity-tagged) ────────────────────────────────────────
class ContinuityFlag(Base):
    __tablename__ = "continuity_flags"
    __table_args__ = (
        CheckConstraint(
            "flag_type IN ('early_appearance','trait_contradiction','timeline_conflict','custom')",
            name="flag_type",
        ),
        CheckConstraint("severity IN ('critical','warning','hint')", name="severity"),
        CheckConstraint("status IN ('open','dismissed','resolved')", name="status"),
        CheckConstraint("source IN ('ai','manual')", name="source"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    scene_id: Mapped[str | None] = mapped_column(ForeignKey("scenes.id"), nullable=True)
    codex_entry_id: Mapped[str | None] = mapped_column(ForeignKey("codex_entries.id"), nullable=True)
    flag_type: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str] = mapped_column(String, default="warning")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="open")
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)


class DraftVersion(Base):
    __tablename__ = "draft_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)  # compiled snapshot on disk
    format_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_current: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class LlmRequestLog(Base):
    """Trust/audit trail: every LLM call, accepted or rejected, with which backend served it."""

    __tablename__ = "llm_request_log"
    __table_args__ = (CheckConstraint("provider IN ('ollama','groq')", name="provider"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    request_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    book_id: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accepted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)


class AppSetting(Base):
    """Key/value user preferences. NEVER holds secrets — the Groq API key lives only in the
    OS credential vault, accessed from the Rust shell (docs/03, docs/08)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[object | None] = mapped_column(JSON, nullable=True)


# ── Voice, delight & personalization (docs 10 and 12) ─────────────────────────
class VoiceNote(Base):
    __tablename__ = "voice_notes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('recorded','transcribed','attached','discarded')", name="status"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    audio_path: Mapped[str] = mapped_column(String, nullable=False)  # relative under app-data/audio/
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine: Mapped[str | None] = mapped_column(String, nullable=True)  # 'parakeet' | 'groq_whisper' | …
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attached_entity_type: Mapped[str | None] = mapped_column(String, nullable=True)
    attached_entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="transcribed")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)


class WritingSession(Base):
    __tablename__ = "writing_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    started_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    ended_at: Mapped[str | None] = mapped_column(String, nullable=True)
    words_added: Mapped[int] = mapped_column(Integer, default=0)
    book_id: Mapped[str | None] = mapped_column(ForeignKey("books.id"), nullable=True)


class Achievement(Base):
    __tablename__ = "achievements"

    key: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. 'first_chapter', 'night_owl'
    unlocked_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)


class PersonalDictionary(Base):
    __tablename__ = "personal_dictionary"
    __table_args__ = (CheckConstraint("source IN ('user','codex_auto')", name="source"),)

    word: Mapped[str] = mapped_column(String, primary_key=True)
    added_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
