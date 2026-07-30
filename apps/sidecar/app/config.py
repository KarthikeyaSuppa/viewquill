"""Runtime configuration for the sidecar.

Only *operational* config lives here (where to bind, where the app-data directory is,
fallback model names). User-facing preferences (theme, fonts, delight level, AI mode,
model overrides) live in the ``app_settings`` table — see docs/03-DATA-MODEL.md — because
they are edited at runtime and travel with the data, not the binary.

The real app-data directory is owned by the Tauri shell (``app_data_dir()``); in packaged
mode Tauri passes it via ``QUILLNIGHT_DATA_DIR``. For standalone dev we fall back to a
platform-appropriate location so the sidecar runs on its own (``uvicorn app.main:app``).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    """Where the SQLite DB, media, and audio live when Tauri hasn't told us otherwise."""
    override = os.environ.get("QUILLNIGHT_DATA_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Quillnight"
    # dev fallback on non-Windows (CI, contributor machines)
    return Path.home() / ".local" / "share" / "quillnight"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QUILLNIGHT_", extra="ignore")

    # ── networking ────────────────────────────────────────────────
    # 127.0.0.1 only — the sidecar is never exposed off-host. Tauri assigns a dynamic
    # port in production and passes it in; 8756 is a stable default for standalone dev.
    host: str = "127.0.0.1"
    port: int = 8756

    # ── storage ───────────────────────────────────────────────────
    data_dir: Path = Field(default_factory=_default_data_dir)

    # ── model-name fallbacks (authoritative values live in app_settings) ──
    # Kept here only so a brand-new DB with no settings rows still has sane defaults.
    # docs/09 principle #9: "Model names are settings, not constants."
    default_local_model: str = "qwen3.5:4b"
    default_grammar_model: str = "gemma4:e4b"
    default_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_base_url: str = "http://127.0.0.1:11434"

    # ── backups ───────────────────────────────────────────────────
    # Cadence for the during-session periodic backup timer (app/main.py's lifespan),
    # on top of the startup + manual-trigger rotation (docs/14-DEFERRED-ENHANCEMENTS.md
    # §B2). The loop itself floors this at 5 minutes regardless of what's configured here,
    # so a misconfigured value can't hammer the DB with back-to-back VACUUM INTO calls.
    backup_interval_minutes: int = 60

    # ── LLM / model runtime ──────────────────────────────────────────
    # How long Ollama keeps a model resident in RAM after the last request before
    # unloading it (Ollama's own `keep_alive` semantics — a Go duration string like "5m",
    # "1h", "0" to unload immediately, or "-1" to never unload). Threaded into the
    # Ollama-leg LiteLLM call only (services/llm_orchestrator.py); Groq is a hosted API
    # with no local model residency to manage, so this has no effect on that leg.
    ollama_keep_alive: str = "5m"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "quillnight.sqlite"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def drafts_dir(self) -> Path:
        return self.data_dir / "drafts"

    @property
    def database_url(self) -> str:
        # forward slashes so the URL is valid on Windows too
        return f"sqlite:///{self.db_path.as_posix()}"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.media_dir, self.audio_dir, self.drafts_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
