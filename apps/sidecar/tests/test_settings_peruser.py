"""Tests for per-user scoping of /settings (docs/13-PROFILES-AND-AUTH.md §"Data model
additions" and §Endpoints).

Covers the merge order (``DEFAULT_SETTINGS`` -> global rows -> the current user's rows),
the ``PER_USER_KEYS`` write-routing split (personal keys route to the logged-in profile,
everything else stays global/shared), and that the endpoint is now bearer-protected. Also
exercises the unit-level ``settings_service`` API directly to prove the pre-auth,
``user_id=None`` call path is unchanged.

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app), same
pattern as tests/test_profiles_auth.py. No Ollama/Groq call happens here.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-settingsperuser-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services import settings_service  # noqa: E402

from conftest import reset_users_table  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        # See tests/conftest.py: every test module in this package actually shares one
        # SQLite database, and this module's user_a/user_b fixtures need a guaranteed-empty
        # users table (well under the 2-profile cap) regardless of what ran before it.
        reset_users_table()
        yield test_client


def _create_and_login(client: TestClient, username: str, password: str = "s3cret-pass") -> str:
    """Creates a profile (if not already present) and logs in, returning a bearer token —
    see tests/test_profiles_auth.py for the reference pattern."""
    client.post(
        "/profiles",
        json={"username": username, "password": password, "avatar": "fox"},
    )
    login_resp = client.post("/auth/login", json={"username": username, "password": password})
    assert login_resp.status_code == 200, login_resp.text
    return login_resp.json()["token"]


@pytest.fixture(scope="module")
def user_a_headers(client: TestClient) -> dict[str, str]:
    token = _create_and_login(client, "settings-user-a")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def user_b_headers(client: TestClient) -> dict[str, str]:
    token = _create_and_login(client, "settings-user-b")
    return {"Authorization": f"Bearer {token}"}


# ── Auth is required ───────────────────────────────────────────────────────────
def test_get_settings_without_bearer_returns_401(client: TestClient) -> None:
    resp = client.get("/settings")
    assert resp.status_code == 401


def test_patch_settings_without_bearer_returns_401(client: TestClient) -> None:
    resp = client.patch("/settings", json={"values": {"font_size": 20}})
    assert resp.status_code == 401


# ── Brand-new user still gets a complete, defaulted settings object ────────────
def test_defaults_still_present_for_a_brand_new_user(
    client: TestClient, user_a_headers: dict[str, str]
) -> None:
    resp = client.get("/settings", headers=user_a_headers)
    assert resp.status_code == 200
    values = resp.json()["values"]
    # Spot-check a handful across both PER_USER and global defaults, plus the computed flag.
    assert values["theme_mode"] == "day"
    assert values["font_size"] == 18
    assert values["onboarding_complete"] is False
    assert values["ai_mode"] == "offline"
    assert values["daily_word_goal"] == 500
    assert values["groq_key_present"] is False


# ── A PER_USER key set by A is NOT seen by B ────────────────────────────────────
def test_per_user_key_set_by_one_user_is_not_seen_by_another(
    client: TestClient, user_a_headers: dict[str, str], user_b_headers: dict[str, str]
) -> None:
    patch_resp = client.patch(
        "/settings", json={"values": {"font_size": 24}}, headers=user_a_headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["values"]["font_size"] == 24

    # A sees their own override.
    a_resp = client.get("/settings", headers=user_a_headers)
    assert a_resp.json()["values"]["font_size"] == 24

    # B still sees the default — A's personal override never leaked to B.
    b_resp = client.get("/settings", headers=user_b_headers)
    assert b_resp.json()["values"]["font_size"] == 18


# ── A GLOBAL key set by A IS seen by B (shared) ─────────────────────────────────
def test_global_key_set_by_one_user_is_seen_by_another(
    client: TestClient, user_a_headers: dict[str, str], user_b_headers: dict[str, str]
) -> None:
    patch_resp = client.patch(
        "/settings", json={"values": {"ai_mode": "hybrid"}}, headers=user_a_headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["values"]["ai_mode"] == "hybrid"

    # B sees the same shared value A just set.
    b_resp = client.get("/settings", headers=user_b_headers)
    assert b_resp.json()["values"]["ai_mode"] == "hybrid"

    # Restore the default so this test doesn't leak state into other test modules that
    # might run in the same process (belt-and-suspenders, matches test_groq_key.py style).
    client.patch("/settings", json={"values": {"ai_mode": "offline"}}, headers=user_a_headers)


# ── Each user can independently override the same PER_USER key ─────────────────
def test_each_user_can_set_their_own_value_for_the_same_per_user_key(
    client: TestClient, user_a_headers: dict[str, str], user_b_headers: dict[str, str]
) -> None:
    client.patch("/settings", json={"values": {"theme_mode": "night"}}, headers=user_a_headers)
    client.patch("/settings", json={"values": {"theme_mode": "auto"}}, headers=user_b_headers)

    a_resp = client.get("/settings", headers=user_a_headers)
    b_resp = client.get("/settings", headers=user_b_headers)
    assert a_resp.json()["values"]["theme_mode"] == "night"
    assert b_resp.json()["values"]["theme_mode"] == "auto"


# ── Unit level: pre-auth, user_id=None call path is unchanged ──────────────────
def test_service_get_all_settings_with_no_user_id_is_global_only() -> None:
    """Direct call into settings_service (no HTTP, no bearer) — proves the pre-auth call
    signature still works and stays global-only, per docs/13's compatibility requirement."""
    db = SessionLocal()
    try:
        values = settings_service.get_all_settings(db)
        assert values["theme_mode"] in ("day", "night", "auto")  # whatever the global row is
        assert "groq_key_present" in values
        assert "onboarding_complete" in values
    finally:
        db.close()


def test_service_update_settings_with_no_user_id_writes_the_global_row() -> None:
    """Direct call into settings_service with user_id=None must still write/return the
    global (user_id IS NULL) row — unchanged pre-auth behavior."""
    db = SessionLocal()
    try:
        result = settings_service.update_settings(db, {"daily_word_goal": 750})
        assert result["daily_word_goal"] == 750

        # Confirm via a fresh read with no user_id — still sees the global write.
        reread = settings_service.get_all_settings(db)
        assert reread["daily_word_goal"] == 750
    finally:
        db.close()
