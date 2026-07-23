"""In-memory session store for local profile auth (docs/13-PROFILES-AND-AUTH.md §Auth
mechanics).

This is a UI/profile LOCK, not encryption. Tokens live ONLY in this module-level dict —
never persisted to disk, never logged. A sidecar restart clears every session, which is
intended: relaunch shows the profile picker again.

Rejected: JWT (needs a signing secret; expiry/refresh buys nothing on a single local host)
and a persisted ``sessions`` table (we *want* re-pick on relaunch).
"""

from __future__ import annotations

import secrets

# token -> user_id. Memory-only by design; do not add persistence here.
_sessions: dict[str, str] = {}


def create_session(user_id: str) -> str:
    """Mints a new opaque token for ``user_id``, stores it, and returns it."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = user_id
    return token


def resolve(token: str) -> str | None:
    """Returns the ``user_id`` for ``token``, or ``None`` if unknown/expired (restart)."""
    return _sessions.get(token)


def revoke(token: str) -> None:
    """Invalidates ``token``. No-op (no error) if it isn't present."""
    _sessions.pop(token, None)
