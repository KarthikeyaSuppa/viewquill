"""Tests for Codex entity<->entity relationships (docs/03-DATA-MODEL.md
`codex_relationships`, docs/06 Phase 3 task BE-1).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB is migrated to head for this test run only — never touches a real
app-data directory. Mirrors tests/test_codex.py's own module-scoped ``client`` fixture.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        yield test_client


def _create_entry(
    client: TestClient, name: str = "Character", entry_type: str = "character"
) -> str:
    resp = client.post("/codex", json={"entry_type": entry_type, "name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_relationship_and_list_from_both_directions(client: TestClient) -> None:
    ada_id = _create_entry(client, "Ada")
    grace_id = _create_entry(client, "Grace")

    create_resp = client.post(
        f"/codex/{ada_id}/relationships",
        json={
            "to_entry_id": grace_id,
            "relationship_type": "ally",
            "description": "Fought together.",
        },
    )
    assert create_resp.status_code == 201
    rel = create_resp.json()
    assert rel["from_entry_id"] == ada_id
    assert rel["to_entry_id"] == grace_id
    assert rel["relationship_type"] == "ally"
    assert rel["description"] == "Fought together."
    rel_id = rel["id"]

    # Listed from the "from" side.
    from_list = client.get(f"/codex/{ada_id}/relationships")
    assert from_list.status_code == 200
    assert any(r["id"] == rel_id for r in from_list.json())

    # Also listed from the "to" side (bidirectional lookup).
    to_list = client.get(f"/codex/{grace_id}/relationships")
    assert to_list.status_code == 200
    assert any(r["id"] == rel_id for r in to_list.json())


def test_self_link_returns_422(client: TestClient) -> None:
    entry_id = _create_entry(client, "Solo")
    resp = client.post(
        f"/codex/{entry_id}/relationships",
        json={"to_entry_id": entry_id, "relationship_type": "rival"},
    )
    assert resp.status_code == 422


def test_nonexistent_target_returns_404(client: TestClient) -> None:
    entry_id = _create_entry(client, "Alone")
    resp = client.post(
        f"/codex/{entry_id}/relationships",
        json={"to_entry_id": "does-not-exist", "relationship_type": "rival"},
    )
    assert resp.status_code == 404


def test_nonexistent_from_entry_returns_404(client: TestClient) -> None:
    other_id = _create_entry(client, "OtherEntry")
    resp = client.post(
        f"/codex/does-not-exist/relationships",
        json={"to_entry_id": other_id, "relationship_type": "rival"},
    )
    assert resp.status_code == 404


def test_duplicate_relationship_returns_409(client: TestClient) -> None:
    a_id = _create_entry(client, "Dup A")
    b_id = _create_entry(client, "Dup B")

    first = client.post(
        f"/codex/{a_id}/relationships",
        json={"to_entry_id": b_id, "relationship_type": "sibling"},
    )
    assert first.status_code == 201

    second = client.post(
        f"/codex/{a_id}/relationships",
        json={"to_entry_id": b_id, "relationship_type": "sibling"},
    )
    assert second.status_code == 409


def test_delete_relationship_then_list_is_empty_and_delete_unknown_404s(
    client: TestClient,
) -> None:
    a_id = _create_entry(client, "Del A")
    b_id = _create_entry(client, "Del B")

    create_resp = client.post(
        f"/codex/{a_id}/relationships",
        json={"to_entry_id": b_id, "relationship_type": "mentor"},
    )
    assert create_resp.status_code == 201
    rel_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/codex/relationships/{rel_id}")
    assert delete_resp.status_code == 204

    list_resp = client.get(f"/codex/{a_id}/relationships")
    assert list_resp.status_code == 200
    assert list_resp.json() == []

    # Deleting an already-gone (or never-existed) relationship 404s rather than
    # silently no-op-ing.
    assert client.delete(f"/codex/relationships/{rel_id}").status_code == 404
    assert client.delete("/codex/relationships/does-not-exist").status_code == 404
