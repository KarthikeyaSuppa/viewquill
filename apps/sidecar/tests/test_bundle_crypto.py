"""Tests for app.services.bundle_crypto — pure crypto module, no DB/app involved
(docs/05-EXPORT-IMPORT-SECURITY.md; Phase 7 task 2).

[SECURITY-REVIEW]: this module is one of CLAUDE.md's flagged files for a later
`reviewer` pass — the hard rules under test here are that a wrong passphrase and a
tampered blob both raise the same `BundlePassphraseError` (never the raw
`cryptography.exceptions.InvalidTag`), and that encryption is non-deterministic
(random salt + nonce per call).
"""

from __future__ import annotations

import pytest

from app.services.bundle_crypto import BundlePassphraseError, decrypt_bundle, encrypt_bundle


def test_round_trip_recovers_original_bytes() -> None:
    plaintext = b"hello world \x00\x01 binary"
    blob = encrypt_bundle(plaintext, "correct horse")
    assert decrypt_bundle(blob, "correct horse") == plaintext


def test_wrong_passphrase_raises_bundle_passphrase_error() -> None:
    blob = encrypt_bundle(b"secret manuscript text", "correct horse")
    with pytest.raises(BundlePassphraseError):
        decrypt_bundle(blob, "wrong horse")


def test_tampered_ciphertext_raises_bundle_passphrase_error() -> None:
    blob = encrypt_bundle(b"secret manuscript text", "correct horse")
    # Flip a byte well past the fixed-size header (magic + kdf_id + salt + nonce), i.e.
    # inside the ciphertext/tag region.
    header_len = 4 + 1 + 16 + 12
    tampered = bytearray(blob)
    tampered_index = header_len + 1
    tampered[tampered_index] ^= 0xFF
    with pytest.raises(BundlePassphraseError):
        decrypt_bundle(bytes(tampered), "correct horse")


def test_tampered_header_raises_bundle_passphrase_error() -> None:
    blob = encrypt_bundle(b"secret manuscript text", "correct horse")
    tampered = bytearray(blob)
    tampered[0] ^= 0xFF  # corrupt the magic header
    with pytest.raises(BundlePassphraseError):
        decrypt_bundle(bytes(tampered), "correct horse")


def test_ciphertext_differs_from_plaintext_and_encryptions_are_nondeterministic() -> None:
    plaintext = b"the quick brown fox jumps over the lazy dog"
    blob_a = encrypt_bundle(plaintext, "same passphrase")
    blob_b = encrypt_bundle(plaintext, "same passphrase")

    assert plaintext not in blob_a
    assert blob_a != blob_b  # fresh random salt + nonce each call

    # Both still decrypt to the same plaintext.
    assert decrypt_bundle(blob_a, "same passphrase") == plaintext
    assert decrypt_bundle(blob_b, "same passphrase") == plaintext


def test_empty_payload_round_trips() -> None:
    blob = encrypt_bundle(b"", "correct horse")
    assert decrypt_bundle(blob, "correct horse") == b""


def test_garbage_blob_raises_bundle_passphrase_error_not_a_crash() -> None:
    with pytest.raises(BundlePassphraseError):
        decrypt_bundle(b"not a real bundle at all", "whatever")

    with pytest.raises(BundlePassphraseError):
        decrypt_bundle(b"", "whatever")
