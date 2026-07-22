"""Pydantic v2 schemas — request/response contracts.

These drive FastAPI's OpenAPI schema, which `openapi-typescript` turns into the frontend's
TS types (docs/02). Kept deliberately small for Phase 0 (health + settings); per-resource
schemas (books, scenes, codex, …) are added in their roadmap phases.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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
