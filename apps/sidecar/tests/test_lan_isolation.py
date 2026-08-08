"""Isolation + auth tests for the LAN Notes surface (app/lan/*).

Core guarantee under test: `build_lan_app()` exposes ONLY `/pair` and `/note` — never any
other resource this app owns (books/scenes/codex/images/settings/export/...). Tests use
`fastapi.testclient.TestClient` directly against `build_lan_app()`'s ASGI app object — this
NEVER binds a real socket and NEVER starts uvicorn (that's `app/lan/server.py`'s
`start_lan_server`, deliberately not exercised here).

Throwaway-DB fixture mirrors tests/test_notes_service.py: QUILLNIGHT_DATA_DIR is set to a
fresh temp dir and migrations are run before any test touches the database, so this module
never touches a real app-data directory.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-lan-")
os.environ.setdefault("QUILLNIGHT_DATA_DIR", _TMP_DATA_DIR)

import pytest  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.migrate import run_migrations  # noqa: E402
from app.lan import security  # noqa: E402
from app.lan.server import build_lan_app  # noqa: E402

# Substrings that must NEVER appear in any path exposed by the LAN app — this is the
# "structurally impossible to expose other app data" guarantee, enforced by inspection
# rather than by trusting the module docstrings alone.
FORBIDDEN_PATH_SUBSTRINGS = (
    "book",
    "scene",
    "codex",
    "image",
    "settings",
    "export",
    "draft",
    "backup",
    "import",
    "search",
    "canvas",
    "llm",
    "voice",
    "chapter",
    "outline",
    "continuity",
    "profile",
    "auth",
    "health",
    "structure",
    "docs",
    "openapi",
    "redoc",
)


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    run_migrations()


@pytest.fixture(autouse=True)
def _reset_lan_security():
    """Every test starts and ends with a clean pairing/device-token slate — `security` is
    module-level (process-lifetime) state, so tests would otherwise leak into each other."""
    security.revoke_all()
    yield
    security.revoke_all()


@pytest.fixture
def lan_client():
    lan_app = build_lan_app()
    with TestClient(lan_app) as client:
        yield client


def _flatten_api_routes(routes) -> list[APIRoute]:
    """FastAPI 0.139's `include_router` wraps included routers in an internal
    `_IncludedRouter` lazy-matching object rather than flattening them straight into
    `app.routes` the way older FastAPI versions did — so `app.routes` alone no longer lists
    the actual `APIRoute` objects. This walks both shapes (a real `APIRoute`, or a wrapper
    exposing `.original_router.routes`) so the isolation assertion below is robust to that
    internal detail rather than silently passing on an empty set."""
    found: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
        elif hasattr(route, "original_router"):
            found.extend(_flatten_api_routes(route.original_router.routes))
    return found


# ── Core isolation guarantee ────────────────────────────────────────────────────────────
def test_lan_app_exposes_only_pair_and_note_routes() -> None:
    lan_app = build_lan_app()
    paths = {route.path for route in _flatten_api_routes(lan_app.routes)}
    assert paths == {"/pair", "/note"}

    for path in paths:
        lowered = path.lower()
        for forbidden in FORBIDDEN_PATH_SUBSTRINGS:
            assert forbidden not in lowered, f"LAN route {path!r} leaks {forbidden!r}"

    # No /docs, /redoc, /openapi.json either — confirms the disabled-docs config took.
    all_paths = {route.path for route in _flatten_api_routes(lan_app.routes)}
    all_paths |= {getattr(route, "path", "") for route in lan_app.routes}
    assert "/docs" not in all_paths
    assert "/redoc" not in all_paths
    assert "/openapi.json" not in all_paths


def test_lan_app_has_no_cors_middleware() -> None:
    lan_app = build_lan_app()
    middleware_classes = {m.cls.__name__ for m in lan_app.user_middleware}
    assert "CORSMiddleware" not in middleware_classes


# ── Auth rejections ─────────────────────────────────────────────────────────────────────
def test_get_note_without_token_is_rejected(lan_client: TestClient) -> None:
    resp = lan_client.get("/note", headers={"X-Quillnight-LAN": "1"})
    assert resp.status_code in (401, 403)


def test_put_note_without_token_is_rejected(lan_client: TestClient) -> None:
    resp = lan_client.put(
        "/note",
        headers={"X-Quillnight-LAN": "1"},
        json={"content": "x", "updated_at": 1, "updated_by": "attacker"},
    )
    assert resp.status_code in (401, 403)


def test_note_without_lan_header_is_rejected_even_with_valid_token(lan_client: TestClient) -> None:
    code = security.start_pairing()
    token = lan_client.post("/pair", json={"code": code}).json()["device_token"]

    resp = lan_client.get("/note", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code in (401, 403)


def test_note_with_valid_token_but_origin_header_is_rejected(lan_client: TestClient) -> None:
    code = security.start_pairing()
    pair_resp = lan_client.post("/pair", json={"code": code})
    assert pair_resp.status_code == 200
    token = pair_resp.json()["device_token"]

    resp = lan_client.get(
        "/note",
        headers={
            "X-Quillnight-LAN": "1",
            "Authorization": f"Bearer {token}",
            "Origin": "http://evil.example.com",
        },
    )
    assert resp.status_code == 403


def test_bad_pairing_code_is_rejected(lan_client: TestClient) -> None:
    code = security.start_pairing()
    # Deterministically-wrong code (never relies on random collision odds).
    wrong = ("1" if code[0] != "1" else "2") + code[1:]

    resp = lan_client.post("/pair", json={"code": wrong})
    assert resp.status_code == 401


def test_expired_pairing_code_is_rejected(lan_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    code = security.start_pairing()
    monkeypatch.setattr(security, "_pairing_expires_at", 0.0)

    resp = lan_client.post("/pair", json={"code": code})
    assert resp.status_code == 401


def test_pairing_code_is_single_use(lan_client: TestClient) -> None:
    code = security.start_pairing()

    first = lan_client.post("/pair", json={"code": code})
    assert first.status_code == 200

    second = lan_client.post("/pair", json={"code": code})
    assert second.status_code == 401


def test_pairing_code_locks_after_max_attempts(lan_client: TestClient) -> None:
    code = security.start_pairing()
    wrong = ("1" if code[0] != "1" else "2") + code[1:]

    # security._MAX_REDEEM_ATTEMPTS wrong guesses exhaust the attempt budget...
    for _ in range(security._MAX_REDEEM_ATTEMPTS):
        resp = lan_client.post("/pair", json={"code": wrong})
        assert resp.status_code == 401

    # ...so even the CORRECT code is now rejected until a fresh one is minted.
    resp = lan_client.post("/pair", json={"code": code})
    assert resp.status_code == 401


# ── Happy path ──────────────────────────────────────────────────────────────────────────
def test_happy_path_pair_then_note_roundtrip(lan_client: TestClient) -> None:
    code = security.start_pairing()
    pair_resp = lan_client.post("/pair", json={"code": code})
    assert pair_resp.status_code == 200
    token = pair_resp.json()["device_token"]
    headers = {"X-Quillnight-LAN": "1", "Authorization": f"Bearer {token}"}

    get_resp = lan_client.get("/note", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["channel"] == "lan"

    put_resp = lan_client.put(
        "/note",
        headers=headers,
        json={"content": "hello from phone", "updated_at": 999_999, "updated_by": "phone-1"},
    )
    assert put_resp.status_code == 200
    body = put_resp.json()
    assert body["content"] == "hello from phone"
    assert body["updated_at"] == 999_999
    assert body["updated_by"] == "phone-1"
    assert body["rev"] >= 1

    # LWW: a strictly-older write from a second device is a no-op, current content unchanged.
    stale_resp = lan_client.put(
        "/note",
        headers=headers,
        json={"content": "stale write", "updated_at": 1, "updated_by": "phone-2"},
    )
    assert stale_resp.status_code == 200
    stale_body = stale_resp.json()
    assert stale_body["content"] == "hello from phone"
    assert stale_body["updated_by"] == "phone-1"

    # A strictly-newer write DOES apply.
    newer_resp = lan_client.put(
        "/note",
        headers=headers,
        json={"content": "newer write", "updated_at": 1_000_000, "updated_by": "phone-2"},
    )
    assert newer_resp.status_code == 200
    newer_body = newer_resp.json()
    assert newer_body["content"] == "newer write"
    assert newer_body["updated_by"] == "phone-2"


# ── Review-fix regressions: malformed input must be a clean 4xx, never a 500 ──────────────
def test_non_ascii_pairing_code_is_rejected_not_500(lan_client: TestClient) -> None:
    """A non-ASCII ``code`` would make ``secrets.compare_digest`` raise ``TypeError`` if it
    ever reached the compare — this must be caught earlier and turned into the same flat 401
    every other bad guess gets, and it must still count against the rate limit."""
    code = security.start_pairing()
    wrong = ("1" if code[0] != "1" else "2") + code[1:]  # deterministically-wrong, well-formed

    resp = lan_client.post("/pair", json={"code": "١٢٣٤٥٦"})  # Arabic-Indic digits, len 6
    assert resp.status_code == 401

    # Counts as a real attempt: security._MAX_REDEEM_ATTEMPTS - 1 more bad guesses should
    # exhaust the budget (proving the malformed attempt above was tallied).
    for _ in range(security._MAX_REDEEM_ATTEMPTS - 1):
        assert lan_client.post("/pair", json={"code": wrong}).status_code == 401
    assert security._pairing_attempts == security._MAX_REDEEM_ATTEMPTS

    # ...so even the CORRECT code is now rejected too, budget already exhausted.
    assert lan_client.post("/pair", json={"code": code}).status_code == 401


def test_non_6_digit_pairing_code_is_rejected_not_500(lan_client: TestClient) -> None:
    security.start_pairing()

    for bad in ("12345", "1234567", "abcdef", ""):
        resp = lan_client.post("/pair", json={"code": bad})
        assert resp.status_code == 401


def test_malformed_bearer_token_is_rejected_not_500(lan_client: TestClient) -> None:
    """A non-ASCII/garbage Bearer token would make ``secrets.compare_digest`` raise
    ``TypeError`` if it reached the compare — must be a clean 401, never a 500.

    ``httpx`` (the TestClient's transport) refuses to encode a plain ``str`` header value
    containing non-ASCII characters client-side, so the non-ASCII byte sequence is passed as
    raw ``bytes`` here — this is exactly what a real HTTP client sends on the wire (headers
    are opaque byte sequences per the ASGI/HTTP spec; Starlette decodes them latin-1 on the
    server side), so it genuinely exercises the same code path a malicious/broken real
    client would.
    """
    resp = lan_client.get(
        "/note",
        headers={
            "X-Quillnight-LAN": "1",
            "Authorization": b"Bearer \xe9\xe9\xe9-not-ascii",
        },
    )
    assert resp.status_code == 401

    # Unit-level guard too: `verify_device_token` must never raise on non-ASCII input.
    assert security.verify_device_token("\xe9\xe9\xe9-not-ascii") is False


def test_pair_with_origin_header_is_rejected(lan_client: TestClient) -> None:
    """`/pair` shares the same unconditional Origin-header rejection `/note` uses — a native
    mobile client never sends `Origin`, so this only ever blocks a browser-based caller."""
    code = security.start_pairing()

    resp = lan_client.post(
        "/pair",
        json={"code": code},
        headers={"Origin": "http://evil.example.com"},
    )
    assert resp.status_code == 403


def test_revoke_all_invalidates_previously_issued_tokens(lan_client: TestClient) -> None:
    code = security.start_pairing()
    token = lan_client.post("/pair", json={"code": code}).json()["device_token"]
    headers = {"X-Quillnight-LAN": "1", "Authorization": f"Bearer {token}"}

    assert lan_client.get("/note", headers=headers).status_code == 200

    security.revoke_all()

    assert lan_client.get("/note", headers=headers).status_code == 401
