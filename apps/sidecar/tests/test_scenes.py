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
from sqlalchemy import select  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.orm import ScreenplayElement, UndoLog  # noqa: E402


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


def test_update_scene_writes_revision_history(client: TestClient) -> None:
    from app.db.base import SessionLocal
    from app.models.orm import SceneRevision

    create_resp = client.post(
        "/scenes",
        json={
            "node_type": "scene",
            "title": "Original Title",
            "description": "Original description here.",
        },
    )
    assert create_resp.status_code == 201
    scene_id = create_resp.json()["id"]

    # First edit — should snapshot the PRE-update (original) values as revision 1.
    patch1 = client.patch(f"/scenes/{scene_id}", json={"title": "Revised Title"})
    assert patch1.status_code == 200

    with SessionLocal() as db:
        revisions = (
            db.query(SceneRevision)
            .filter(SceneRevision.scene_id == scene_id)
            .order_by(SceneRevision.revision_number)
            .all()
        )
        assert len(revisions) == 1
        rev1 = revisions[0]
        assert rev1.revision_number == 1
        assert rev1.change_source == "manual_edit"
        assert rev1.parent_revision_id is None
        assert rev1.title == "Original Title"
        assert rev1.description == "Original description here."

    # Second edit — should snapshot the state after edit 1 (pre-image of edit 2) as
    # revision 2, chained to revision 1 via parent_revision_id.
    patch2 = client.patch(
        f"/scenes/{scene_id}",
        json={"title": "Revised Again", "description": "New description."},
    )
    assert patch2.status_code == 200

    with SessionLocal() as db:
        revisions = (
            db.query(SceneRevision)
            .filter(SceneRevision.scene_id == scene_id)
            .order_by(SceneRevision.revision_number)
            .all()
        )
        assert len(revisions) == 2
        rev2 = revisions[1]
        assert rev2.revision_number == 2
        assert rev2.parent_revision_id == rev1.id
        assert rev2.title == "Revised Title"
        assert rev2.description == "Original description here."

    # A patch whose values are identical to what's already stored must not write a
    # redundant revision row.
    patch3 = client.patch(
        f"/scenes/{scene_id}",
        json={"title": "Revised Again", "description": "New description."},
    )
    assert patch3.status_code == 200
    with SessionLocal() as db:
        count = (
            db.query(SceneRevision).filter(SceneRevision.scene_id == scene_id).count()
        )
        assert count == 2


def test_list_revisions_empty_for_never_edited_scene(client: TestClient) -> None:
    create_resp = client.post(
        "/scenes", json={"node_type": "scene", "title": "Untouched Scene"}
    )
    assert create_resp.status_code == 201
    scene_id = create_resp.json()["id"]

    resp = client.get(f"/scenes/{scene_id}/revisions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_revisions_returns_history_newest_first(client: TestClient) -> None:
    create_resp = client.post(
        "/scenes",
        json={
            "node_type": "scene",
            "title": "History Scene",
            "description": "First description.",
        },
    )
    assert create_resp.status_code == 201
    scene_id = create_resp.json()["id"]

    patch1 = client.patch(f"/scenes/{scene_id}", json={"title": "History Scene v2"})
    assert patch1.status_code == 200

    patch2 = client.patch(
        f"/scenes/{scene_id}",
        json={"title": "History Scene v3", "description": "Second description."},
    )
    assert patch2.status_code == 200

    resp = client.get(f"/scenes/{scene_id}/revisions")
    assert resp.status_code == 200
    revisions = resp.json()
    assert len(revisions) == 2
    assert [r["revision_number"] for r in revisions] == [2, 1]
    assert revisions[0]["title"] == "History Scene v2"
    assert revisions[0]["description"] == "First description."
    assert revisions[1]["title"] == "History Scene"
    assert revisions[1]["description"] == "First description."
    assert revisions[0]["parent_revision_id"] == revisions[1]["id"]
    assert revisions[1]["parent_revision_id"] is None
    assert revisions[0]["change_source"] == "manual_edit"


def test_list_revisions_missing_scene_404(client: TestClient) -> None:
    resp = client.get("/scenes/does-not-exist/revisions")
    assert resp.status_code == 404


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


# ── Workstream B task 6: permanent delete writes an undo tombstone ──────────────
def test_permanent_delete_writes_undo_log_and_still_deletes_rows(client: TestClient) -> None:
    book_resp = client.post("/books", json={"title": "Undo Book", "book_type": "story_book"})
    assert book_resp.status_code == 201
    book_id = book_resp.json()["id"]

    scene_resp = client.post(
        "/scenes",
        json={
            "node_type": "scene",
            "title": "Scene To Delete",
            "description": "Some prose.",
        },
    )
    assert scene_resp.status_code == 201
    scene_id = scene_resp.json()["id"]

    link_resp = client.post(
        f"/books/{book_id}/scenes/{scene_id}", json={"canvas_x": 5, "canvas_y": 6}
    )
    assert link_resp.status_code == 201

    element_resp = client.post(
        f"/scenes/{scene_id}/elements",
        json={"element_type": "action", "text": "Someone walks in."},
    )
    assert element_resp.status_code == 201
    element_id = element_resp.json()["id"]

    delete_resp = client.delete(f"/scenes/{scene_id}")
    assert delete_resp.status_code == 204

    # Scene and its screenplay element are actually gone — no regression on the delete.
    assert client.get(f"/scenes/{scene_id}").status_code == 404
    with SessionLocal() as db:
        remaining_elements = list(
            db.execute(
                select(ScreenplayElement).where(ScreenplayElement.scene_id == scene_id)
            ).scalars()
        )
        assert remaining_elements == []

        # Scoped by book_id, not just action_type — this suite shares one SQLite database
        # across every test module in a full-suite run (see tests/conftest.py's module
        # docstring), so an unscoped query here would also pick up "delete_scene" UndoLog
        # rows written by other books in other test modules (e.g. tests/test_undo.py's
        # revision/merge-history undo test).
        undo_rows = list(
            db.execute(
                select(UndoLog).where(
                    UndoLog.book_id == book_id, UndoLog.action_type == "delete_scene"
                )
            ).scalars()
        )
    assert len(undo_rows) == 1
    undo_row = undo_rows[0]
    assert undo_row.undone_at is None
    assert undo_row.book_id == book_id

    payload = undo_row.payload
    assert payload["scene"]["id"] == scene_id
    assert payload["scene"]["title"] == "Scene To Delete"
    assert payload["scene"]["description"] == "Some prose."
    assert len(payload["book_scene_links"]) == 1
    assert payload["book_scene_links"][0]["book_id"] == book_id
    assert payload["book_scene_links"][0]["scene_id"] == scene_id
    assert payload["book_scene_links"][0]["canvas_x"] == 5
    assert len(payload["screenplay_elements"]) == 1
    assert payload["screenplay_elements"][0]["id"] == element_id
    assert payload["screenplay_elements"][0]["text"] == "Someone walks in."
