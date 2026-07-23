"""Password hashing for local profile locks (docs "Profiles & local auth").

This is a UI/profile LOCK, not encryption — the SQLite database stays plaintext on disk
(settled, see docs/03-DATA-MODEL.md). Hashing here exists only so a profile's password
isn't stored in the clear; it does not make the app's data encrypted at rest.

Wraps ``argon2.PasswordHasher`` (argon2-cffi, already installed — see pyproject.toml).
Never log the plaintext password or the resulting hash.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Returns an argon2 hash string (includes algorithm params + salt) — never the
    plaintext itself."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True only if ``password`` matches ``password_hash``. Any verification failure
    (mismatch, malformed hash) returns False rather than raising."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
