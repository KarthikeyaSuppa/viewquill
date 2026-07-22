"""Tests for /codex CRUD and its links to Scenes/Books (docs/03-DATA-MODEL.md
`codex_entries` / `codex_scene_links` / `book_codex_links`, docs/06 Phase 2 tasks B1/B2).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB is migrated to head for this test run only — never touches a real
app-data directory.
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


def _create_book(client: TestClient, title: str = "Book") -> str:
    resp = client.post("/books", json={"title": title, "book_type": "story_book"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_scene(client: TestClient, title: str = "Scene") -> str:
    resp = client.post("/scenes", json={"node_type": "scene", "title": title})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_entry(
    client: TestClient, name: str = "Character", entry_type: str = "character"
) -> str:
    resp = client.post("/codex", json={"entry_type": entry_type, "name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_entry_requires_name(client: TestClient) -> None:
    resp = client.post("/codex", json={"entry_type": "character"})
    assert resp.status_code == 422


def test_codex_crud_lifecycle(client: TestClient) -> None:
    create_resp = client.post(
        "/codex",
        json={
            "entry_type": "character",
            "name": "Ada",
            "summary": "A curious inventor.",
            "custom_fields": {"eye_color": "brown"},
        },
    )
    assert create_resp.status_code == 201
    entry = create_resp.json()
    entry_id = entry["id"]
    assert entry["entry_type"] == "character"
    assert entry["name"] == "Ada"
    assert entry["summary"] == "A curious inventor."
    assert entry["custom_fields"] == {"eye_color": "brown"}
    assert entry["primary_image_id"] is None

    get_resp = client.get(f"/codex/{entry_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Ada"

    patch_resp = client.patch(f"/codex/{entry_id}", json={"summary": "A brilliant inventor."})
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["summary"] == "A brilliant inventor."
    assert patched["name"] == "Ada"  # untouched field survives the partial update

    delete_resp = client.delete(f"/codex/{entry_id}")
    assert delete_resp.status_code == 204

    missing_resp = client.get(f"/codex/{entry_id}")
    assert missing_resp.status_code == 404


def test_codex_update_and_delete_missing_return_404(client: TestClient) -> None:
    assert client.patch("/codex/does-not-exist", json={"name": "x"}).status_code == 404
    assert client.delete("/codex/does-not-exist").status_code == 404


def test_list_entries_filtered_by_entry_type(client: TestClient) -> None:
    char_id = _create_entry(client, "Filter Character", "character")
    loc_id = _create_entry(client, "Filter Location", "location")

    characters = client.get("/codex", params={"entry_type": "character"})
    assert characters.status_code == 200
    char_ids = {e["id"] for e in characters.json()}
    assert char_id in char_ids
    assert loc_id not in char_ids

    locations = client.get("/codex", params={"entry_type": "location"})
    assert locations.status_code == 200
    loc_ids = {e["id"] for e in locations.json()}
    assert loc_id in loc_ids
    assert char_id not in loc_ids

    all_entries = client.get("/codex")
    assert all_entries.status_code == 200
    all_ids = {e["id"] for e in all_entries.json()}
    assert {char_id, loc_id}.issubset(all_ids)


def test_link_scene_then_unlink_leaves_both_entities_intact(client: TestClient) -> None:
    entry_id = _create_entry(client, "Linked Character")
    scene_id = _create_scene(client, "Linked Scene")

    link_resp = client.post(f"/codex/{entry_id}/scenes/{scene_id}")
    assert link_resp.status_code == 201

    scene_codex = client.get(f"/scenes/{scene_id}/codex")
    assert scene_codex.status_code == 200
    assert any(e["id"] == entry_id for e in scene_codex.json())

    # Linking again must not duplicate — still exactly one match.
    link_again = client.post(f"/codex/{entry_id}/scenes/{scene_id}")
    assert link_again.status_code == 201
    scene_codex_after_dup = client.get(f"/scenes/{scene_id}/codex").json()
    matches = [e for e in scene_codex_after_dup if e["id"] == entry_id]
    assert len(matches) == 1

    unlink_resp = client.delete(f"/codex/{entry_id}/scenes/{scene_id}")
    assert unlink_resp.status_code == 204

    # The join row is gone...
    scene_codex_after = client.get(f"/scenes/{scene_id}/codex")
    assert all(e["id"] != entry_id for e in scene_codex_after.json())

    # ...but both the codex entry and the scene survive untouched.
    entry_resp = client.get(f"/codex/{entry_id}")
    assert entry_resp.status_code == 200
    scene_resp = client.get(f"/scenes/{scene_id}")
    assert scene_resp.status_code == 200

    # Unlinking again (already gone) 404s rather than silently no-op-ing.
    assert client.delete(f"/codex/{entry_id}/scenes/{scene_id}").status_code == 404


def test_link_book_then_unlink_leaves_both_entities_intact(client: TestClient) -> None:
    entry_id = _create_entry(client, "Book-Linked Character")
    book_id = _create_book(client, "Linked Book")

    link_resp = client.post(f"/codex/{entry_id}/books/{book_id}")
    assert link_resp.status_code == 201

    unlink_resp = client.delete(f"/codex/{entry_id}/books/{book_id}")
    assert unlink_resp.status_code == 204

    entry_resp = client.get(f"/codex/{entry_id}")
    assert entry_resp.status_code == 200
    book_resp = client.get(f"/books/{book_id}")
    assert book_resp.status_code == 200

    assert client.delete(f"/codex/{entry_id}/books/{book_id}").status_code == 404


def test_links_404_for_missing_entry_scene_or_book(client: TestClient) -> None:
    entry_id = _create_entry(client, "Missing Link Character")
    scene_id = _create_scene(client, "Missing Link Scene")
    book_id = _create_book(client, "Missing Link Book")

    assert client.post(f"/codex/does-not-exist/scenes/{scene_id}").status_code == 404
    assert client.post(f"/codex/{entry_id}/scenes/does-not-exist").status_code == 404
    assert client.post(f"/codex/does-not-exist/books/{book_id}").status_code == 404
    assert client.post(f"/codex/{entry_id}/books/does-not-exist").status_code == 404
    assert client.get("/scenes/does-not-exist/codex").status_code == 404
