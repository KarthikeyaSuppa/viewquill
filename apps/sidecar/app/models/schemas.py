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
