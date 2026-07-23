"""Tests for the "Profiles & local auth" backend part A: password hashing + the `users`
table + the reshaped `app_settings` table (docs: "Profiles & local auth" task).

[SECURITY-REVIEW + MIGRATION]: this covers the delicate schema-migration piece flagged for
a later `reviewer` pass — password hashing (`app/services/password_service.py`) and the
hand-written Alembic migration that rebuilds `app_settings` without losing existing rows.

This is a UI/profile LOCK, not encryption — the database stays plaintext on disk. No
Ollama/Groq call happens here; nothing in this file touches a network or model.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-authmigration-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import engine  # noqa: E402
from app.db.migrate import make_alembic_config  # noqa: E402
from app.main import app  # noqa: E402
from app.services import password_service  # noqa: E402

from conftest import reset_users_table  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        # See tests/conftest.py: every test module in this package actually shares one
        # SQLite database. This module creates its own throwaway profile via
        # auth_headers below — reset first so it never trips the 2-profile cap or a
        # username collision because of rows some other module left behind.
        reset_users_table()
        yield test_client


@pytest.fixture(scope="module")
def auth_headers(client: TestClient) -> dict[str, str]:
    """/settings is bearer-protected (docs/13 §Endpoints) — create a throwaway profile and
    log in once per module, same pattern as tests/test_profiles_auth.py."""
    client.post(
        "/profiles",
        json={"username": "authmigration-tester", "password": "s3cret-pass", "avatar": "fox"},
    )
    login_resp = client.post(
        "/auth/login", json={"username": "authmigration-tester", "password": "s3cret-pass"}
    )
    token = login_resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _column_names(table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}  # row: (cid, name, type, notnull, dflt_value, pk)


def _index_names(table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
    return {row[1] for row in rows}  # row: (seq, name, unique, origin, partial)


# ── Migration shape ───────────────────────────────────────────────────────────
def test_migrates_to_head_and_users_table_has_expected_columns(client: TestClient) -> None:
    assert _column_names("users") == {
        "id", "username", "password_hash", "display_name", "avatar", "created_at", "is_active",
    }


def test_app_settings_has_new_shape_and_writing_sessions_has_user_id(client: TestClient) -> None:
    assert _column_names("app_settings") == {"id", "user_id", "key", "value"}
    assert "user_id" in _column_names("writing_sessions")


def test_app_settings_has_both_partial_unique_indexes(client: TestClient) -> None:
    names = _index_names("app_settings")
    assert "uq_app_settings_user_key" in names
    assert "uq_app_settings_global_key" in names


# ── Round-trip: downgrade -1, then upgrade head, with no error ────────────────
def test_migration_round_trips_downgrade_then_upgrade(client: TestClient) -> None:
    cfg = make_alembic_config()
    command.downgrade(cfg, "-1")
    # Old shape is back.
    assert _column_names("app_settings") == {"key", "value"}
    assert "users" not in _table_names()
    assert "user_id" not in _column_names("writing_sessions")

    command.upgrade(cfg, "head")
    # New shape restored, cleanly, no error raised getting here.
    assert _column_names("app_settings") == {"id", "user_id", "key", "value"}
    assert "user_id" in _column_names("writing_sessions")
    assert "users" in _table_names()


def _table_names() -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    return {row[0] for row in rows}


# ── /settings still works post-migration (settings_service compatible) ────────
def test_settings_endpoint_still_works_after_migration(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/settings", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["values"]["theme_mode"] == "day"  # default

    patch_resp = client.patch(
        "/settings", json={"values": {"theme_mode": "night"}}, headers=auth_headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["values"]["theme_mode"] == "night"

    get_resp = client.get("/settings", headers=auth_headers)
    assert get_resp.json()["values"]["theme_mode"] == "night"


def test_patching_the_same_key_twice_upserts_not_duplicates(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # Two PATCHes of the same key must not raise (proves upsert against the global
    # partial-unique index, not a duplicate insert).
    # theme_mode is a PER_USER key (docs/13) — patch as this logged-in user, then check the
    # per-(user,key) row, not the global row (which stays untouched by this call).
    client.patch("/settings", json={"values": {"theme_mode": "day"}}, headers=auth_headers)
    resp = client.patch(
        "/settings", json={"values": {"theme_mode": "night"}}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["values"]["theme_mode"] == "night"

    user_id = client.get("/auth/me", headers=auth_headers).json()["id"]
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM app_settings WHERE key = 'theme_mode' AND user_id = :uid"),
            {"uid": user_id},
        ).scalar_one()
    assert count == 1


# ── password_service ───────────────────────────────────────────────────────────
def test_hash_password_never_equals_the_plaintext() -> None:
    hashed = password_service.hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert isinstance(hashed, str)
    assert len(hashed) > 0


def test_verify_password_true_for_correct_password() -> None:
    hashed = password_service.hash_password("s3cr3t-passphrase")
    assert password_service.verify_password("s3cr3t-passphrase", hashed) is True


def test_verify_password_false_for_wrong_password() -> None:
    hashed = password_service.hash_password("s3cr3t-passphrase")
    assert password_service.verify_password("wrong-passphrase", hashed) is False


def test_verify_password_false_for_malformed_hash_never_raises() -> None:
    assert password_service.verify_password("anything", "not-a-real-argon2-hash") is False
