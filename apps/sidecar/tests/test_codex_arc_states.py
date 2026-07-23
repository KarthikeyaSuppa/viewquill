"""Tests for /codex/{entry_id}/arc-states — point-in-time entity snapshots
(docs/03-DATA-MODEL.md `codex_arc_states`, docs/06 Phase 3 task BE-2).

DATA-SENSITIVE: arc-states feed the anti-spoiler filter in
app.services.prompt_builder.build_codex_context (only the latest arc-state with
``as_of_outline_order_index <= scene's outline index`` may be resolved). This suite locks
that read contract with a real `build_codex_context` call, in addition to covering the
CRUD/list/ordering/404 behavior of the write-side routes added here.

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB is migrated to head for this test run only — never touches a real
app-data directory. Follows the same fixture pattern as tests/test_codex.py (no shared
client fixture in conftest.py).
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-arc-states-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.orm import BookSceneOrder  # noqa: E402
from app.services import prompt_builder  # noqa: E402


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


def _create_entry(
    client: TestClient, name: str = "Character", entry_type: str = "character"
) -> str:
    resp = client.post("/codex", json={"entry_type": entry_type, "name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_scene(client: TestClient, title: str = "Scene") -> str:
    resp = client.post("/scenes", json={"node_type": "scene", "title": title})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_arc_state_round_trips_fields(client: TestClient) -> None:
    book_id = _create_book(client, "RoundTrip Book")
    entry_id = _create_entry(client, "Ada")

    resp = client.post(
        f"/codex/{entry_id}/arc-states",
        json={
            "book_id": book_id,
            "as_of_outline_order_index": 3,
            "status_summary": "Has left home for the capital.",
            "traits_snapshot": {"confidence": "growing"},
        },
    )
    assert resp.status_code == 201
    arc_state = resp.json()
    assert arc_state["codex_entry_id"] == entry_id
    assert arc_state["book_id"] == book_id
    assert arc_state["as_of_outline_order_index"] == 3
    assert arc_state["status_summary"] == "Has left home for the capital."
    assert arc_state["traits_snapshot"] == {"confidence": "growing"}
    assert "id" in arc_state
    assert "created_at" in arc_state


def test_list_arc_states_filters_by_book(client: TestClient) -> None:
    book_a = _create_book(client, "Book A")
    book_b = _create_book(client, "Book B")
    entry_id = _create_entry(client, "Bram")

    resp_a = client.post(
        f"/codex/{entry_id}/arc-states",
        json={"book_id": book_a, "as_of_outline_order_index": 1, "status_summary": "In Book A"},
    )
    assert resp_a.status_code == 201

    resp_b = client.post(
        f"/codex/{entry_id}/arc-states",
        json={"book_id": book_b, "as_of_outline_order_index": 1, "status_summary": "In Book B"},
    )
    assert resp_b.status_code == 201

    list_all = client.get(f"/codex/{entry_id}/arc-states")
    assert list_all.status_code == 200
    assert len(list_all.json()) == 2

    list_a = client.get(f"/codex/{entry_id}/arc-states", params={"book_id": book_a})
    assert list_a.status_code == 200
    a_summaries = [row["status_summary"] for row in list_a.json()]
    assert a_summaries == ["In Book A"]

    list_b = client.get(f"/codex/{entry_id}/arc-states", params={"book_id": book_b})
    assert list_b.status_code == 200
    b_summaries = [row["status_summary"] for row in list_b.json()]
    assert b_summaries == ["In Book B"]


def test_create_arc_state_nonexistent_entry_404(client: TestClient) -> None:
    book_id = _create_book(client, "Orphan Book")
    resp = client.post(
        "/codex/nonexistent-entry/arc-states",
        json={"book_id": book_id, "as_of_outline_order_index": 0},
    )
    assert resp.status_code == 404


def test_create_arc_state_nonexistent_book_404(client: TestClient) -> None:
    entry_id = _create_entry(client, "Cass")
    resp = client.post(
        f"/codex/{entry_id}/arc-states",
        json={"book_id": "nonexistent-book", "as_of_outline_order_index": 0},
    )
    assert resp.status_code == 404


def test_list_arc_states_ordered_ascending_by_index(client: TestClient) -> None:
    book_id = _create_book(client, "Ordering Book")
    entry_id = _create_entry(client, "Dana")

    for idx in (5, 2, 8):
        resp = client.post(
            f"/codex/{entry_id}/arc-states",
            json={"book_id": book_id, "as_of_outline_order_index": idx},
        )
        assert resp.status_code == 201

    listed = client.get(f"/codex/{entry_id}/arc-states", params={"book_id": book_id})
    assert listed.status_code == 200
    indices = [row["as_of_outline_order_index"] for row in listed.json()]
    assert indices == [2, 5, 8]


def test_delete_arc_state(client: TestClient) -> None:
    book_id = _create_book(client, "Delete Book")
    entry_id = _create_entry(client, "Eve")

    create_resp = client.post(
        f"/codex/{entry_id}/arc-states",
        json={"book_id": book_id, "as_of_outline_order_index": 1},
    )
    assert create_resp.status_code == 201
    arc_state_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/codex/arc-states/{arc_state_id}")
    assert delete_resp.status_code == 204

    listed = client.get(f"/codex/{entry_id}/arc-states", params={"book_id": book_id})
    assert listed.json() == []

    delete_again = client.delete(f"/codex/arc-states/{arc_state_id}")
    assert delete_again.status_code == 404


def test_delete_unknown_arc_state_404(client: TestClient) -> None:
    resp = client.delete("/codex/arc-states/does-not-exist")
    assert resp.status_code == 404


def test_anti_spoiler_build_codex_context_resolves_earlier_snapshot_only(
    client: TestClient,
) -> None:
    """Locks the read contract prompt_builder.build_codex_context relies on: for a scene
    placed at outline index 5, an arc-state at index 8 (the future) must NOT be visible,
    while the arc-state at index 2 (the past) must be."""
    book_id = _create_book(client, "Anti-Spoiler Book")
    entry_id = _create_entry(client, "Fiona")
    scene_id = _create_scene(client, "Midpoint Scene")

    link_resp = client.post(f"/codex/{entry_id}/scenes/{scene_id}")
    assert link_resp.status_code == 201

    past_resp = client.post(
        f"/codex/{entry_id}/arc-states",
        json={
            "book_id": book_id,
            "as_of_outline_order_index": 2,
            "status_summary": "Still training under the old master.",
        },
    )
    assert past_resp.status_code == 201

    future_resp = client.post(
        f"/codex/{entry_id}/arc-states",
        json={
            "book_id": book_id,
            "as_of_outline_order_index": 8,
            "status_summary": "Has betrayed the old master and fled the city.",
        },
    )
    assert future_resp.status_code == 201

    # Place the scene at outline index 5 in this Book. There is no HTTP route for this yet
    # (Outline/Timeline is a later phase per docs/06-ROADMAP.md) — this mirrors how
    # tests/test_prompt_builder.py seeds BookSceneOrder directly via the ORM, against the
    # same on-disk SQLite DB the TestClient's routes above wrote through.
    db = SessionLocal()
    try:
        db.add(BookSceneOrder(book_id=book_id, scene_id=scene_id, outline_order_index=5))
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        resolved = prompt_builder.build_codex_context(db, scene_id=scene_id, book_id=book_id)
    finally:
        db.close()

    assert len(resolved) == 1
    custom_fields = resolved[0]["custom_fields"]
    assert custom_fields.get("arc_status_summary") == "Still training under the old master."
    assert "betrayed" not in str(custom_fields)
