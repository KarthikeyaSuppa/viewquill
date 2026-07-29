"""Bundle encryption for `.quillproj` export/import (docs/05-EXPORT-IMPORT-SECURITY.md,
Phase 7 task 2).

The roadmap default in docs/05 was ``pyrage`` (age-based encryption), but it is not
installed on this build machine and has been dropped as the active choice. The active
engine here is ``cryptography`` (AES-256-GCM) + ``argon2-cffi`` (Argon2id for passphrase
key derivation) — both already pinned in pyproject.toml. This mirrors the
WeasyPrint -> ReportLab isolation posture from Phase 6 (docs/06-ROADMAP.md): the public
interface below is deliberately narrow (two functions + one exception) so the underlying
engine can be swapped later without touching any caller.

Blob format (versioned, self-describing) — see docs/05-EXPORT-IMPORT-SECURITY.md:

    +----------+----------+-----------------+------------------+------------------------+
    | magic(4) | kdf_id(1)| argon2 salt(16) | AES-GCM nonce(12)| ciphertext + tag(16)   |
    +----------+----------+-----------------+------------------+------------------------+

``magic`` is ``b"QNP1"`` (Quillnight Package v1). ``kdf_id`` 0x01 means Argon2id with the
cost parameters below. The header (magic + kdf_id) is passed as AES-GCM associated data,
so any tampering with it (e.g. downgrading the KDF id) is also detected, not just tampering
with the ciphertext.

Hard rule (CLAUDE.md / docs/01-PRODUCT-VISION.md): never log the passphrase, the derived
key, or plaintext. This module only logs (at warning level) that a decrypt attempt failed —
never any secret material or plaintext content.
"""

from __future__ import annotations

import logging
import os

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# --- Format constants -------------------------------------------------------------
_MAGIC = b"QNP1"
_KDF_ARGON2ID = 0x01
_SALT_LEN = 16
_NONCE_LEN = 12
_KEY_LEN = 32
_HEADER_LEN = len(_MAGIC) + 1  # magic + kdf_id byte

# --- Argon2id cost parameters (documented, not tuned per-machine) -----------------
# time_cost: number of iterations. memory_cost: KiB (64 * 1024 = 64 MiB). parallelism:
# threads. These are deliberately moderate so bundle export/import stays responsive on
# the target laptop (docs/00 hardware notes) while still being resistant to offline
# brute-force of a stolen .quillproj file.
_ARGON2_TIME_COST = 3
_ARGON2_MEMORY_COST = 64 * 1024
_ARGON2_PARALLELISM = 4


class BundlePassphraseError(Exception):
    """Raised for a wrong passphrase, or a corrupt/tampered/malformed bundle.

    Deliberately a single error type for all of these cases — the caller (and any UI
    built on top) must never be able to distinguish "wrong password" from "corrupted
    file" from the exception alone, since that distinction isn't actionable for the user
    and narrows an attacker's guessing feedback.
    """


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Argon2id key derivation. No logging of `passphrase` or the returned key."""
    return hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=salt,
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST,
        parallelism=_ARGON2_PARALLELISM,
        hash_len=_KEY_LEN,
        type=Type.ID,
    )


def encrypt_bundle(data: bytes, passphrase: str) -> bytes:
    """Encrypts `data` under `passphrase`, returning a self-describing blob per the
    module docstring's format. Fresh random salt + nonce on every call."""
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    key = _derive_key(passphrase, salt)

    header = _MAGIC + bytes([_KDF_ARGON2ID])
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, header)

    return header + salt + nonce + ciphertext


def decrypt_bundle(blob: bytes, passphrase: str) -> bytes:
    """Decrypts a blob produced by `encrypt_bundle`.

    Raises `BundlePassphraseError` for a wrong passphrase, a tampered/corrupted blob, or
    a malformed/unrecognized blob (too short, bad magic, unknown KDF id). Never lets a
    raw cryptography exception or stack trace escape this function.
    """
    min_len = _HEADER_LEN + _SALT_LEN + _NONCE_LEN
    if len(blob) < min_len:
        raise BundlePassphraseError("Not a valid .quillproj bundle")

    magic = blob[: len(_MAGIC)]
    if magic != _MAGIC:
        raise BundlePassphraseError("Not a valid .quillproj bundle")

    kdf_id = blob[len(_MAGIC)]
    if kdf_id != _KDF_ARGON2ID:
        raise BundlePassphraseError("Not a valid .quillproj bundle")

    header = blob[:_HEADER_LEN]
    salt = blob[_HEADER_LEN : _HEADER_LEN + _SALT_LEN]
    nonce = blob[_HEADER_LEN + _SALT_LEN : _HEADER_LEN + _SALT_LEN + _NONCE_LEN]
    ciphertext = blob[_HEADER_LEN + _SALT_LEN + _NONCE_LEN :]

    if not ciphertext:
        raise BundlePassphraseError("Not a valid .quillproj bundle")

    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext, header)
    except InvalidTag:
        logger.warning("Bundle decrypt failed: wrong passphrase or corrupted/tampered bundle")
        raise BundlePassphraseError("Wrong passphrase or corrupted bundle") from None
    except ValueError as exc:
        # cryptography raises ValueError for other malformed-input cases (e.g. nonce/key
        # length mismatches) — collapse these into the same safe error too.
        logger.warning("Bundle decrypt failed: malformed bundle (%s)", type(exc).__name__)
        raise BundlePassphraseError("Wrong passphrase or corrupted bundle") from None
