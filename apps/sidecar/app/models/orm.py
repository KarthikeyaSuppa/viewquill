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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
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
    archived_at: Mapped[str | None] = mapped_column(String, nullable=True)


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
    # Rendering/sort hint only: NULL = not part of the lineage view (default for all
    # existing edges). Distinguishes lineage/sequence edges from free-form connections.
    # Unrelated to BookSceneOrder's chronological ordering.
    sequence_weight: Mapped[int | None] = mapped_column(Integer, nullable=True)


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
    # Nullable "which one is primary / thumbnail-strip order" position (PHASE-UI-EFFECTS-2.md
    # §4 B2). NULL (every existing row, until a user explicitly reorders) means "no explicit
    # order" and falls back to entity_images_service.list_for_entity's original
    # created_at DESC, id DESC ordering — see that function's ORDER BY for the exact rule.
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)


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
        CheckConstraint("source IN ('deterministic','ai','manual')", name="source"),
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


class SceneRevision(Base):
    """Append-only per-scene history ("commit") row — Workstream B git-like history.

    Snapshots ``Scene.title``/``description``/``status`` at the moment of the change so
    history/diff/restore can work even after the live Scene row moves on. ``parent_revision_id``
    self-references the prior revision in the chain (nullable — the first revision has none);
    ``ON DELETE SET NULL`` so pruning an ancestor never cascades into losing later history.
    """

    __tablename__ = "scene_revisions"
    __table_args__ = (
        CheckConstraint(
            "change_source IN ('manual_edit','enhance_accept','ai_merge','restore')",
            name="change_source",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    change_source: Mapped[str] = mapped_column(String, nullable=False)
    parent_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("scene_revisions.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)


class SceneMerge(Base):
    """One row per source Scene absorbed into a merged Scene — Workstream B AI-assisted merge.

    N:1 with the resulting merged scene: a single merge produces one ``merged_scene_id`` and
    one row here per ``source_scene_id`` it absorbed. Snapshot columns freeze the source's
    title/description at merge time so the merge remains inspectable even if the source Scene
    is later hard-deleted. Both FKs are ``ON DELETE SET NULL`` (nullable), mirroring
    ``SceneRevision.parent_revision_id``'s self-referential pattern above: a hard-delete of
    either the merged Scene or a source Scene (via the ordinary ``DELETE /scenes/{id}`` path —
    sources are meant to survive a merge as ordinary scenes, and nothing stops the merged scene
    itself from later being deleted the same way) must never cascade away this row, since the
    frozen snapshot columns are exactly what's supposed to survive that.
    """

    __tablename__ = "scene_merges"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    merged_scene_id: Mapped[str | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True
    )
    source_scene_id: Mapped[str | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True
    )
    source_snapshot_title: Mapped[str] = mapped_column(String, nullable=False)
    source_snapshot_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)


class UndoLog(Base):
    """Last reversible destructive/AI action per Book — Workstream B scoped undo.

    Stores just enough reconstruction data in ``payload`` (JSON) to reverse one
    ``action_type`` of action (``delete_scene`` / ``merge_scenes`` / ``create_edge`` /
    ``delete_edge`` / ``update_edge``); ``undone_at`` is set once the action has been
    reversed so the same entry isn't replayed twice.
    """

    __tablename__ = "undo_log"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('delete_scene','merge_scenes','create_edge',"
            "'delete_edge','update_edge')",
            name="action_type",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    undone_at: Mapped[str | None] = mapped_column(String, nullable=True)
    # Secondary, strictly-increasing tiebreaker for ``created_at`` ordering — ``created_at``
    # (via ``utcnow_iso``) only has 1-second resolution, so two actions logged in the same
    # second are otherwise ambiguous to order; ``id`` is a uuid4 string (not creation-ordered),
    # so it can't serve as the tiebreaker either. NOT the primary key (``id`` already is that);
    # populated in Python at insert time (``undo_service.next_sequence``), the same
    # compute-max-then-add-one pattern ``SceneRevision.revision_number`` already uses in
    # ``scene_service.py``, rather than relying on SQLite `AUTOINCREMENT` (which only applies
    # to a table's single `INTEGER PRIMARY KEY` rowid alias — not available here since ``id``,
    # the real primary key, is a TEXT uuid).
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)


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


# ── Profiles & local auth (UI/profile LOCK — NOT encryption; the SQLite DB stays
# plaintext on disk. See app/services/password_service.py) ───────────────────
class User(Base):
    """A local profile. ``password_hash`` is an argon2 hash, never the plaintext.

    ``username`` uniqueness is enforced case-insensitively at the DB layer via a
    ``COLLATE NOCASE`` unique index (``uq_users_username``) — this backstops
    ``profiles_service``'s own case-insensitive check (strip+lower) so "Alice" and
    "alice" can never both exist, even under a threadpool race.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_username", text("username COLLATE NOCASE"), unique=True),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    username: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AppSetting(Base):
    """Key/value preferences. NEVER holds secrets — the Groq API key lives only in the
    OS credential vault, accessed from the Rust shell (docs/03, docs/08).

    ``user_id`` NULL rows are global settings; non-NULL rows are per-user overrides
    (per-user scoping is threaded through the endpoints in a later task — for now
    ``settings_service`` only reads/writes the global (``user_id IS NULL``) rows, so
    current behavior is unchanged). Two partial-unique indexes (created in the
    migration) enforce at most one row per key per scope."""

    __tablename__ = "app_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    key: Mapped[str] = mapped_column(String, nullable=False)
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
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


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


# ── LAN Notes (last-write-wins singleton row per channel) ─────────────────────
class Note(Base):
    """One singleton row per ``channel`` (e.g. ``'lan'``) — a shared scratch-note the
    desktop app and a later LAN server both read/write. Conflict resolution is
    last-write-wins keyed on ``updated_at`` (client-supplied epoch milliseconds, NOT a
    DB-generated timestamp — see ``app/services/notes_service.py``'s ``apply_note``),
    so this deliberately does NOT use the rest of this file's ``new_uuid``/``utcnow_iso``
    conventions: ``channel`` is a small fixed vocabulary (not a UUID identity, since there's
    exactly one row per channel to merge-by-ID), and the clock must be caller-supplied so a
    write made on another device stays comparable to one made here.
    """

    __tablename__ = "notes"

    channel: Mapped[str] = mapped_column(String, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_by: Mapped[str] = mapped_column(String, nullable=False)
    rev: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
