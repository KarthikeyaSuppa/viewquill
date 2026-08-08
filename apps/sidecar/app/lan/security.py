"""In-memory (process-lifetime) pairing + device-token state for the LAN Notes surface.

Mirrors app/services/groq_key.py's secret-seam pattern exactly: every value here lives in a
module-level variable for the lifetime of this process only.
    * Pairing codes and device tokens are NEVER written to SQLite, `app_settings`, disk, or
      any log line.
    * `revoke_all()` (called on share-stop, app/main.py's ``POST /notes/lan/share/stop``)
      simply forgets everything — there is nothing on disk to clean up.
    * A device token, once minted, stays valid until `revoke_all()`. There is no separate
      per-token expiry today: this is a LAN-only, single desktop + a small number of paired
      personal devices convenience feature, not a multi-tenant auth system. Turning sharing
      off (which happens automatically whenever the app closes, or explicitly via the Notes
      UI) revokes every paired device at once.

Threat model this defends against (see app/lan/routes.py's `require_lan_auth` for the
matching HTTP-layer checks that consume this module):
    * A stranger on the same LAN scanning for the port: needs the current 6-digit pairing
      code to ever obtain a `device_token` — and that code is single-use, ~120s-lived, and
      redemption is capped at `_MAX_REDEEM_ATTEMPTS` tries, so it can't be brute-forced
      (1,000,000 possibilities, 5 guesses, then the code is dead until the desktop mints a
      new one).
    * A leaked/observed device_token: minted with `secrets.token_urlsafe(32)` (256 bits of
      randomness) and checked with `secrets.compare_digest` against every stored token, so
      guessing one is infeasible and comparing one is not vulnerable to a byte-by-byte
      timing side channel.
"""

from __future__ import annotations

import secrets
import time

# ~120s pairing-code lifetime (spec: "a ~120s expiry").
_PAIRING_TTL_SECONDS = 120.0

# Rate-limit: at most this many redemption attempts against one pairing code before it is
# locked out for the rest of its lifetime, regardless of whether the code itself was right.
_MAX_REDEEM_ATTEMPTS = 5

# ── Pairing-code state — only ONE active pairing code at a time (spec requirement); a
# fresh `start_pairing()` call always replaces whatever code was previously outstanding. ──
_pairing_code: str | None = None
_pairing_expires_at: float = 0.0
_pairing_used: bool = False
_pairing_attempts: int = 0

# ── Device tokens — every device that has ever successfully redeemed a pairing code since
# the last `revoke_all()`. A plain set is fine here: membership is always checked via
# `secrets.compare_digest` (see `verify_device_token`), never via `in`/hash lookup alone, so
# this is not a timing oracle. ──────────────────────────────────────────────────────────────
_device_tokens: set[str] = set()

# The exact shape a real pairing code always has (`start_pairing`'s `f"{...:06d}"`).
_CODE_LENGTH = 6


def _is_well_formed_code(code: str) -> bool:
    """``secrets.compare_digest`` raises ``TypeError`` if either ``str`` argument isn't
    ASCII-only — which would otherwise surface a malformed/non-ASCII pairing code as a 500
    instead of the clean 401 every other kind of wrong guess gets. A real code is always
    exactly ``_CODE_LENGTH`` ASCII digits, so anything else can never match regardless — this
    lets ``redeem_pairing`` reject it up front, before ever reaching the ``compare_digest``
    call, while still counting the attempt against the rate limit like any other guess."""
    return len(code) == _CODE_LENGTH and code.isascii() and code.isdigit()


def start_pairing() -> str:
    """Mints a fresh single-use 6-digit pairing code (``secrets``-backed, not
    ``random``), replacing any previously outstanding code. Returns the code so the
    caller (app/main.py's share/start endpoint) can render it + fold it into the QR
    payload for the desktop side to show the user."""
    global _pairing_code, _pairing_expires_at, _pairing_used, _pairing_attempts
    _pairing_code = f"{secrets.randbelow(1_000_000):06d}"
    _pairing_expires_at = time.monotonic() + _PAIRING_TTL_SECONDS
    _pairing_used = False
    _pairing_attempts = 0
    return _pairing_code


def redeem_pairing(code: str) -> str | None:
    """Validates ``code`` against the single active pairing code and, on success, mints and
    stores a new long-lived ``device_token``.

    Returns ``None`` on ANY failure (no active code, expired, already used, attempt cap
    hit, or simply wrong) without distinguishing which to the caller — ``app/lan/routes.py``
    turns every ``None`` into the same flat 401, so a caller probing this endpoint learns
    nothing about *why* a guess failed.

    Every call — including a wrong guess — counts against ``_MAX_REDEEM_ATTEMPTS``, so this
    is also this module's brute-force rate limit on the pairing code itself.
    """
    global _pairing_used, _pairing_attempts

    if _pairing_code is None or _pairing_used:
        return None
    if time.monotonic() > _pairing_expires_at:
        return None
    if _pairing_attempts >= _MAX_REDEEM_ATTEMPTS:
        return None

    _pairing_attempts += 1
    # Malformed input (wrong length, non-digit, or non-ASCII) can never match the stored
    # code AND would make `secrets.compare_digest` raise `TypeError` on a non-ASCII `str` —
    # reject it here as a plain failed guess (already counted above) instead of letting that
    # exception escape as a 500.
    if not _is_well_formed_code(code):
        return None
    if not secrets.compare_digest(code, _pairing_code):
        return None

    _pairing_used = True
    token = secrets.token_urlsafe(32)
    _device_tokens.add(token)
    return token


def verify_device_token(token: str) -> bool:
    """Constant-time-per-comparison membership check: every stored token is compared
    against ``token`` with ``secrets.compare_digest`` (never a plain ``in``/``==`` on
    attacker-controlled input, which short-circuits on the first differing byte and can leak
    timing information).

    Guards against ``secrets.compare_digest``'s ``TypeError`` on a non-ASCII ``str`` first —
    a real device token is always ``secrets.token_urlsafe``'s URL-safe-base64 ASCII output,
    so a non-ASCII token can never be valid; treating it as a plain ``False`` here keeps a
    malformed Bearer token a clean 401 (see ``app.lan.routes.require_lan_auth``) instead of
    a 500.
    """
    if not token.isascii():
        return False
    return any(secrets.compare_digest(token, stored) for stored in _device_tokens)


def revoke_all() -> None:
    """Called on share-stop: clears every device token and any active/pending pairing code.
    Nothing here was ever persisted, so there is nothing on disk to clean up — this is the
    entire teardown."""
    global _pairing_code, _pairing_expires_at, _pairing_used, _pairing_attempts
    _device_tokens.clear()
    _pairing_code = None
    _pairing_expires_at = 0.0
    _pairing_used = False
    _pairing_attempts = 0


def has_active_pairing_code() -> bool:
    """Read-only helper for app/lan/server.py's status/QR-payload building — never exposes
    the code itself, just whether one currently exists."""
    return _pairing_code is not None and not _pairing_used and time.monotonic() <= _pairing_expires_at
