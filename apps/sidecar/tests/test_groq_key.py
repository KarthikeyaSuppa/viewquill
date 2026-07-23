"""Tests for the Groq key dev seam (docs/06 Phase 2 tasks F1/F2, docs/08-AI-PROVIDER-MODES.md
"Secure API key storage"): `app/services/groq_key.py` + the `/llm/groq-key`,
`/llm/test-connection` endpoints, and `/settings`' computed `groq_key_present` flag.

[SECURITY-REVIEW]: this is exactly the module CLAUDE.md flags for a later `reviewer` pass —
the hard rule under test here is that the key value NEVER crosses the wire, is NEVER
persisted, and the seam module itself has no path to SQLite/disk. See
`app/services/groq_key.py`'s "DEV SEAM ONLY" docstring.

Runs entirely against `QUILLNIGHT_LLM_STUB=1` (the no-network `EchoProvider`, same as
test_llm_enhance.py) — no real Groq/Ollama call ever happens here or on this build machine
(CLAUDE.md "Environment constraints").
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-groqkey-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import groq_key  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client
    # Belt-and-suspenders: don't leak the test key into any other test module that
    # happens to run in the same process afterwards.
    groq_key.clear_key()


@pytest.fixture(scope="module")
def auth_headers(client: TestClient) -> dict[str, str]:
    """/settings is bearer-protected (docs/13 §Endpoints) — create a throwaway profile and
    log in once per module, same pattern as tests/test_profiles_auth.py."""
    client.post(
        "/profiles",
        json={"username": "groqkey-tester", "password": "s3cret-pass", "avatar": "fox"},
    )
    login_resp = client.post(
        "/auth/login", json={"username": "groqkey-tester", "password": "s3cret-pass"}
    )
    token = login_resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_groq_key_lifecycle_never_exposes_the_key_itself(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # 1. Nothing set yet.
    settings_resp = client.get("/settings", headers=auth_headers)
    assert settings_resp.status_code == 200
    assert settings_resp.json()["values"]["groq_key_present"] is False

    # 2. Set a key via the dev-seam endpoint.
    set_resp = client.post("/llm/groq-key", json={"key": "gsk_test_super_secret_value"})
    assert set_resp.status_code == 200
    assert set_resp.json() == {"present": True}

    # 3. /settings now reflects presence...
    settings_resp = client.get("/settings", headers=auth_headers)
    assert settings_resp.status_code == 200
    settings_body = settings_resp.json()
    assert settings_body["values"]["groq_key_present"] is True

    # ...but the raw key never appears anywhere in that response body.
    assert "gsk_test_super_secret_value" not in settings_resp.text

    # 4. The set-key response itself never echoes the key back either.
    assert "gsk_test_super_secret_value" not in set_resp.text

    # 5. Flip ai_mode to online so /llm/test-connection actually attempts a leg (default
    # is "offline", which must short-circuit to ok=False without a key check at all).
    patch_resp = client.patch(
        "/settings", json={"values": {"ai_mode": "online"}}, headers=auth_headers
    )
    assert patch_resp.status_code == 200

    test_conn_resp = client.post("/llm/test-connection")
    assert test_conn_resp.status_code == 200
    test_conn_body = test_conn_resp.json()
    assert test_conn_body["ok"] is True
    assert test_conn_body["provider"] == "ollama"  # EchoProvider always tags 'ollama'
    assert "gsk_test_super_secret_value" not in test_conn_resp.text

    # 6. Clear the key.
    delete_resp = client.delete("/llm/groq-key")
    assert delete_resp.status_code == 204

    settings_resp = client.get("/settings", headers=auth_headers)
    assert settings_resp.json()["values"]["groq_key_present"] is False

    # 7. With the key gone, test-connection declines without pretending to succeed.
    test_conn_resp = client.post("/llm/test-connection")
    assert test_conn_resp.status_code == 200
    assert test_conn_resp.json() == {"ok": False, "reason": "No Groq API key is set", "provider": None}


def test_test_connection_declines_when_ai_mode_is_offline(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # Restore ai_mode to the offline default and set a key — offline must win regardless
    # of key presence (never a "missing key" error, per the module docstring policy).
    client.patch("/settings", json={"values": {"ai_mode": "offline"}}, headers=auth_headers)
    client.post("/llm/groq-key", json={"key": "gsk_another_secret"})
    try:
        resp = client.post("/llm/test-connection")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["reason"] == "AI mode is offline"
        assert "gsk_another_secret" not in resp.text
    finally:
        client.delete("/llm/groq-key")
        client.patch("/settings", json={"values": {"ai_mode": "offline"}}, headers=auth_headers)


def test_groq_key_module_has_no_path_to_sqlite_settings_or_disk() -> None:
    """Structural check (docs' hard rule): `groq_key.py` must hold the key ONLY in the
    in-memory module variable — no SQLAlchemy/Session/AppSetting/settings_service import,
    and no file-write call of any kind."""
    import ast
    import inspect

    from app.services import groq_key as groq_key_module

    source = inspect.getsource(groq_key_module)
    tree = ast.parse(source)

    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)
            for alias in node.names:
                imported_names.add(alias.name)

    forbidden_imports = [
        "sqlalchemy",
        "Session",
        "AppSetting",
        "settings_service",
        "keyring",
        "app.db",
        "app.db.base",
        "app.models.orm",
        "pathlib",
        "os",
    ]
    for name in forbidden_imports:
        assert name not in imported_names, (
            f"app/services/groq_key.py must never import {name!r} — the key must live "
            "only in the in-memory module variable, never touch SQLite/disk"
        )

    # No disk-write call sites of any kind (open(), Path.write_text/write_bytes, etc.).
    forbidden_calls = ["open(", "write_text(", "write_bytes(", "sqlite", "keyring."]
    for token in forbidden_calls:
        assert token not in source, f"app/services/groq_key.py must never {token!r} — in-memory only"

    # And the module-level state really is just a plain variable, not a class/DB-backed store.
    assert "_key: str | None = None" in source


def test_groq_key_present_flag_is_computed_never_stored_in_settings_table() -> None:
    """`groq_key_present` must never be a persisted `app_settings` row — it's computed
    fresh on every `get_all_settings()` call from the in-memory seam."""
    from app.services.settings_service import DEFAULT_SETTINGS

    assert "groq_key_present" not in DEFAULT_SETTINGS
