"""Tests for /profiles and /auth (docs/13-PROFILES-AND-AUTH.md).

This is a UI/profile LOCK, not encryption — the SQLite database stays plaintext on disk.
Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB is migrated to head for this test run only — never touches a real
app-data directory. No Ollama/Groq call happens here.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-profilesauth-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

from conftest import reset_users_table  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        # This module's assertions rely on the 2-profile cap and username-uniqueness
        # being GLOBAL invariants over a users table it owns exclusively — but
        # QUILLNIGHT_DATA_DIR is only honored by whichever test module wins the
        # collection-time race (app.config.get_settings() is lru_cache'd), so every
        # module in this package actually shares one SQLite database. Reset so this
        # module's tests start from zero users regardless of what ran before it.
        reset_users_table()
        yield test_client


def _create_profile(client: TestClient, username: str, password: str = "s3cret-pass") -> dict:
    resp = client.post(
        "/profiles",
        json={"username": username, "password": password, "display_name": "Ada", "avatar": "fox"},
    )
    return resp


def test_create_profile_returns_public_shape_without_password_hash(client: TestClient) -> None:
    resp = _create_profile(client, "ada")
    assert resp.status_code == 201
    body = resp.json()
    assert set(body.keys()) == {"id", "username", "display_name", "avatar"}
    assert body["username"] == "ada"
    assert body["display_name"] == "Ada"
    assert body["avatar"] == "fox"
    assert "password_hash" not in body
    assert "password" not in body


def test_list_profiles_includes_created_profile_without_hash(client: TestClient) -> None:
    resp = client.get("/profiles")
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) == 1
    assert users[0]["username"] == "ada"
    assert "password_hash" not in users[0]


def test_duplicate_username_case_insensitive_returns_409(client: TestClient) -> None:
    resp = _create_profile(client, "ADA")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "That username is already taken."


def test_second_profile_succeeds_then_third_returns_409(client: TestClient) -> None:
    resp = _create_profile(client, "grace")
    assert resp.status_code == 201

    resp3 = _create_profile(client, "linus")
    assert resp3.status_code == 409
    assert resp3.json()["detail"] == "Maximum of 2 profiles reached."


def test_create_profile_with_empty_username_returns_422(client: TestClient) -> None:
    resp = client.post("/profiles", json={"username": "   ", "password": "whatever"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Username and password are required."


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    resp = client.post("/auth/login", json={"username": "ada", "password": "wrong-one"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Incorrect username or password."


def test_login_success_returns_token_and_user(client: TestClient) -> None:
    resp = client.post("/auth/login", json={"username": "ada", "password": "s3cret-pass"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"token", "user"}
    assert isinstance(body["token"], str) and len(body["token"]) > 0
    assert body["user"]["username"] == "ada"
    assert "password_hash" not in body["user"]


def test_me_with_bearer_token_returns_current_profile(client: TestClient) -> None:
    login_resp = client.post("/auth/login", json={"username": "ada", "password": "s3cret-pass"})
    token = login_resp.json()["token"]

    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "ada"


def test_me_without_token_returns_401(client: TestClient) -> None:
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated."


def test_logout_then_me_returns_401(client: TestClient) -> None:
    login_resp = client.post("/auth/login", json={"username": "ada", "password": "s3cret-pass"})
    token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout_resp = client.post("/auth/logout", headers=headers)
    assert logout_resp.status_code == 200
    assert logout_resp.json() == {"ok": True}

    me_resp = client.get("/auth/me", headers=headers)
    assert me_resp.status_code == 401
    assert me_resp.json()["detail"] == "Invalid or expired session."


# ── DB-layer case-insensitive username uniqueness backstop ────────────────────
# app/models/orm.py's `User.__table_args__` adds a `COLLATE NOCASE` unique index
# (`uq_users_username`) so "Alice" and "alice" can never both exist even under a
# threadpool race — profiles_service's own case-insensitive check (strip+lower) is only
# the first line of defense. Reset the table first so this isn't tripped up by the
# 2-profile cap from the earlier tests in this module.
def test_case_variant_username_returns_409_duplicate(client: TestClient) -> None:
    reset_users_table()

    resp = _create_profile(client, "Alice")
    assert resp.status_code == 201

    resp2 = _create_profile(client, "alice")
    assert resp2.status_code == 409
    assert resp2.json()["detail"] == "That username is already taken."
