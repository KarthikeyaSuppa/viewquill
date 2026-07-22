"""Tests for /scenes CRUD and nested /scenes/{id}/elements screenplay endpoints
(docs/03-DATA-MODEL.md `scenes` / `screenplay_elements`, docs/06 Phase 2 tasks A1/A2/A6).

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


def test_create_scene_requires_title(client: TestClient) -> None:
    resp = client.post("/scenes", json={"node_type": "scene", "description": "no title here"})
    assert resp.status_code == 422


def test_create_scene_derives_word_count(client: TestClient) -> None:
    resp = client.post(
        "/scenes",
        json={
            "node_type": "scene",
            "title": "Opening",
            "description": "The quick brown fox jumps",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["word_count"] == 5
    assert body["title"] == "Opening"
    assert body["status"] == "draft"


def test_scene_crud_lifecycle(client: TestClient) -> None:
    create_resp = client.post("/scenes", json={"node_type": "plot_point", "title": "Inciting Incident"})
    assert create_resp.status_code == 201
    scene_id = create_resp.json()["id"]
    assert create_resp.json()["word_count"] == 0

    list_resp = client.get("/scenes")
    assert list_resp.status_code == 200
    assert any(s["id"] == scene_id for s in list_resp.json())

    get_resp = client.get(f"/scenes/{scene_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Inciting Incident"

    patch_resp = client.patch(
        f"/scenes/{scene_id}",
        json={"description": "one two three", "status": "final"},
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["word_count"] == 3
    assert patched["status"] == "final"

    delete_resp = client.delete(f"/scenes/{scene_id}")
    assert delete_resp.status_code == 204

    missing_resp = client.get(f"/scenes/{scene_id}")
    assert missing_resp.status_code == 404


def test_scene_update_and_delete_missing_return_404(client: TestClient) -> None:
    assert client.patch("/scenes/does-not-exist", json={"title": "x"}).status_code == 404
    assert client.delete("/scenes/does-not-exist").status_code == 404


def test_screenplay_elements_never_touch_scene_description(client: TestClient) -> None:
    scene_resp = client.post(
        "/scenes",
        json={
            "node_type": "scene",
            "title": "Diner",
            "description": "Original prose description that must survive.",
        },
    )
    scene_id = scene_resp.json()["id"]
    original_description = scene_resp.json()["description"]

    heading_resp = client.post(
        f"/scenes/{scene_id}/elements",
        json={"element_type": "scene_heading", "text": "INT. DINER - NIGHT"},
    )
    assert heading_resp.status_code == 201
    assert heading_resp.json()["order_index"] == 0

    action_resp = client.post(
        f"/scenes/{scene_id}/elements",
        json={"element_type": "action", "text": "Rain hammers the window."},
    )
    assert action_resp.status_code == 201
    assert action_resp.json()["order_index"] == 1

    dialogue_resp = client.post(
        f"/scenes/{scene_id}/elements",
        json={"element_type": "dialogue", "text": "You're late."},
    )
    assert dialogue_resp.status_code == 201
    assert dialogue_resp.json()["order_index"] == 2

    # The parent scene's description must be completely untouched.
    scene_after = client.get(f"/scenes/{scene_id}")
    assert scene_after.json()["description"] == original_description

    elements = client.get(f"/scenes/{scene_id}/elements")
    assert elements.status_code == 200
    ids_in_order = [el["id"] for el in elements.json()]
    assert len(ids_in_order) == 3

    # Reorder: reverse the order.
    reversed_ids = list(reversed(ids_in_order))
    reorder_resp = client.post(
        f"/scenes/{scene_id}/elements/reorder", json={"element_ids": reversed_ids}
    )
    assert reorder_resp.status_code == 200
    reordered = reorder_resp.json()
    assert [el["id"] for el in reordered] == reversed_ids
    assert [el["order_index"] for el in reordered] == [0, 1, 2]

    # Persisted — a fresh GET reflects the new order.
    elements_after = client.get(f"/scenes/{scene_id}/elements")
    assert [el["id"] for el in elements_after.json()] == reversed_ids

    # Description is STILL untouched after reorder.
    scene_after_reorder = client.get(f"/scenes/{scene_id}")
    assert scene_after_reorder.json()["description"] == original_description

    # Update one element's text.
    first_id = reversed_ids[0]
    update_resp = client.patch(f"/scenes/elements/{first_id}", json={"text": "You're late again."})
    assert update_resp.status_code == 200
    assert update_resp.json()["text"] == "You're late again."

    # Delete one element.
    delete_resp = client.delete(f"/scenes/elements/{first_id}")
    assert delete_resp.status_code == 204
    elements_final = client.get(f"/scenes/{scene_id}/elements")
    assert len(elements_final.json()) == 2

    # Description is STILL untouched after edit + delete.
    scene_final = client.get(f"/scenes/{scene_id}")
    assert scene_final.json()["description"] == original_description


def test_elements_for_missing_scene_404(client: TestClient) -> None:
    assert client.get("/scenes/does-not-exist/elements").status_code == 404
    resp = client.post(
        "/scenes/does-not-exist/elements",
        json={"element_type": "action", "text": "x"},
    )
    assert resp.status_code == 404


def test_update_and_delete_missing_element_404(client: TestClient) -> None:
    assert client.patch("/scenes/elements/does-not-exist", json={"text": "x"}).status_code == 404
    assert client.delete("/scenes/elements/does-not-exist").status_code == 404
