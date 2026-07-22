"""DEV SEAM ONLY — in production the key is held in the OS keyring and handed in by the
Rust shell; never persist.

This module exists solely so the sidecar can be exercised standalone on this build
machine (no Tauri/Rust shell here — see CLAUDE.md "Environment constraints"). It holds
the Groq API key in a single process-lifetime module variable and nothing else:

* NEVER written to SQLite, `app_settings`, disk, or any log line.
* NEVER returned by any endpoint — only a computed boolean (`is_present()`) is exposed,
  via `settings_service.get_all_settings`'s `groq_key_present` field.
* Cleared on process exit (it's just a variable) — there is no persistence to clean up.

Task F2 (docs/06 Phase 2, docs/08-AI-PROVIDER-MODES.md "Secure API key storage") replaces
every call site of this module with the real OS-keyring-via-Rust binding; nothing here is
meant to survive that cutover.
"""

from __future__ import annotations

_key: str | None = None


def set_key(key: str) -> None:
    """Store the key in memory for the lifetime of this process. Never persisted."""
    global _key
    _key = key


def clear_key() -> None:
    """Forget the key. Never persisted, so there's nothing on disk to clean up."""
    global _key
    _key = None


def get_key() -> str | None:
    """The raw key, for passing straight into `ProviderClient.stream(groq_key=...)` /
    `speech_stt.transcribe(groq_key=...)`. Never expose this value through an API
    response or a log line."""
    return _key


def is_present() -> bool:
    """Safe-to-expose boolean — this is the only thing `/settings` may reveal about the
    key."""
    return _key is not None
