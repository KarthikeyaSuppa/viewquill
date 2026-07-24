"""Tests for the Outline/Timeline mediator (docs/03-DATA-MODEL.md `book_scene_order`,
docs/06 Phase 4 task BE-3).

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


def _add_to_canvas(client: TestClient, book_id: str, scene_id: str) -> None:
    resp = client.post(f"/books/{book_id}/scenes/{scene_id}")
    assert resp.status_code == 201


def _create_chapter(client: TestClient, book_id: str, title: str = "Chapter") -> str:
    resp = client.post(f"/books/{book_id}/chapters", json={"title": title})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_assign_scene_sets_chapter_beat_and_index(client: TestClient) -> None:
    book_id = _create_book(client, "Assign Book")
    scene_id = _create_scene(client, "Scene 1")
    _add_to_canvas(client, book_id, scene_id)
    chapter_id = _create_chapter(client, book_id, "Chapter One")

    resp = client.post(
        f"/books/{book_id}/scenes/{scene_id}/assign",
        json={"chapter_id": chapter_id, "structure_beat": "inciting_incident", "outline_order_index": 0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["book_id"] == book_id
    assert body["scene_id"] == scene_id
    assert body["chapter_id"] == chapter_id
    assert body["structure_beat"] == "inciting_incident"
    assert body["outline_order_index"] == 0
    # Timeline fields on the same row are untouched/null.
    assert body["timeline_order_index"] is None
    assert body["in_story_time_label"] is None


def test_assign_scene_clears_structure_beat_to_null(client: TestClient) -> None:
    """Sending an explicit ``null`` for a field must CLEAR it (e.g. move a Scene back to
    "Unassigned" on the beat-board) — distinct from simply omitting the field, which must
    leave it untouched."""
    book_id = _create_book(client, "Clear Beat Book")
    scene_id = _create_scene(client, "Clear Beat Scene")
    _add_to_canvas(client, book_id, scene_id)
    chapter_id = _create_chapter(client, book_id, "Chapter One")

    setup = client.post(
        f"/books/{book_id}/scenes/{scene_id}/assign",
        json={
            "chapter_id": chapter_id,
            "structure_beat": "setup",
            "outline_order_index": 3,
        },
    )
    assert setup.status_code == 200
    assert setup.json()["structure_beat"] == "setup"

    # Omitting structure_beat entirely leaves it as-is.
    unrelated = client.post(
        f"/books/{book_id}/scenes/{scene_id}/assign", json={"outline_order_index": 3}
    )
    assert unrelated.status_code == 200
    assert unrelated.json()["structure_beat"] == "setup"

    # Explicit null clears structure_beat, while chapter_id/outline_order_index —
    # neither sent this time — remain unchanged.
    cleared = client.post(
        f"/books/{book_id}/scenes/{scene_id}/assign", json={"structure_beat": None}
    )
    assert cleared.status_code == 200
    body = cleared.json()
    assert body["structure_beat"] is None
    assert body["chapter_id"] == chapter_id
    assert body["outline_order_index"] == 3


def test_assign_scene_clears_chapter_id_to_null_skips_mismatch_check(
    client: TestClient,
) -> None:
    """Clearing chapter_id to null must not trigger the CHAPTER_MISMATCH validation (that
    check only applies when chapter_id is being set to a non-null value)."""
    book_id = _create_book(client, "Clear Chapter Book")
    scene_id = _create_scene(client, "Clear Chapter Scene")
    _add_to_canvas(client, book_id, scene_id)
    chapter_id = _create_chapter(client, book_id, "Chapter One")

    client.post(
        f"/books/{book_id}/scenes/{scene_id}/assign", json={"chapter_id": chapter_id}
    )
    resp = client.post(
        f"/books/{book_id}/scenes/{scene_id}/assign", json={"chapter_id": None}
    )
    assert resp.status_code == 200
    assert resp.json()["chapter_id"] is None


def test_assign_scene_missing_book_or_scene_404(client: TestClient) -> None:
    book_id = _create_book(client, "404 Book")
    scene_id = _create_scene(client, "404 Scene")

    resp = client.post(f"/books/does-not-exist/scenes/{scene_id}/assign", json={})
    assert resp.status_code == 404

    resp = client.post(f"/books/{book_id}/scenes/does-not-exist/assign", json={})
    assert resp.status_code == 404


def test_assign_scene_chapter_from_another_book_422(client: TestClient) -> None:
    book_a = _create_book(client, "Book A")
    book_b = _create_book(client, "Book B")
    scene_id = _create_scene(client, "Cross Book Scene")
    _add_to_canvas(client, book_a, scene_id)
    chapter_b = _create_chapter(client, book_b, "Chapter in B")

    resp = client.post(
        f"/books/{book_a}/scenes/{scene_id}/assign", json={"chapter_id": chapter_b}
    )
    assert resp.status_code == 422


def test_list_outline_orders_placed_before_unplaced(client: TestClient) -> None:
    book_id = _create_book(client, "Outline List Book")
    scene_a = _create_scene(client, "Scene A")
    scene_b = _create_scene(client, "Scene B")
    scene_c = _create_scene(client, "Scene C")
    for scene_id in (scene_a, scene_b, scene_c):
        _add_to_canvas(client, book_id, scene_id)

    # Place B first, then A — C is left with no outline row at all (never assigned).
    client.post(f"/books/{book_id}/scenes/{scene_b}/assign", json={"outline_order_index": 1})
    client.post(f"/books/{book_id}/scenes/{scene_a}/assign", json={"outline_order_index": 0})
    # Give C a row via the timeline side only, leaving outline_order_index NULL.
    client.post(f"/books/{book_id}/scenes/{scene_c}/timeline", json={"timeline_order_index": 0})

    resp = client.get(f"/books/{book_id}/outline")
    assert resp.status_code == 200
    rows = resp.json()
    scene_ids_in_order = [r["scene_id"] for r in rows]
    assert scene_ids_in_order == [scene_a, scene_b, scene_c]
    assert rows[0]["outline_order_index"] == 0
    assert rows[1]["outline_order_index"] == 1
    assert rows[2]["outline_order_index"] is None


def test_reorder_outline_reindexes_0_to_n(client: TestClient) -> None:
    book_id = _create_book(client, "Reorder Outline Book")
    scene_a = _create_scene(client, "Scene A")
    scene_b = _create_scene(client, "Scene B")
    scene_c = _create_scene(client, "Scene C")
    for scene_id in (scene_a, scene_b, scene_c):
        _add_to_canvas(client, book_id, scene_id)

    resp = client.post(
        f"/books/{book_id}/outline/reorder",
        json={"scene_ids": [scene_c, scene_a, scene_b]},
    )
    assert resp.status_code == 200
    by_scene = {r["scene_id"]: r["outline_order_index"] for r in resp.json()}
    assert by_scene[scene_c] == 0
    assert by_scene[scene_a] == 1
    assert by_scene[scene_b] == 2

    # A second reorder call re-persists the same rows (no duplicates), and list_outline
    # reflects the newest order.
    resp2 = client.post(
        f"/books/{book_id}/outline/reorder",
        json={"scene_ids": [scene_b, scene_c, scene_a]},
    )
    assert resp2.status_code == 200
    list_resp = client.get(f"/books/{book_id}/outline")
    rows = list_resp.json()
    assert len(rows) == 3  # still exactly one row per scene, never duplicated
    scene_ids_in_order = [r["scene_id"] for r in rows]
    assert scene_ids_in_order == [scene_b, scene_c, scene_a]


def test_reorder_outline_missing_book_or_scene_404(client: TestClient) -> None:
    book_id = _create_book(client, "Reorder 404 Book")
    resp = client.post(
        f"/books/does-not-exist/outline/reorder", json={"scene_ids": ["whatever"]}
    )
    assert resp.status_code == 404

    resp = client.post(
        f"/books/{book_id}/outline/reorder", json={"scene_ids": ["does-not-exist"]}
    )
    assert resp.status_code == 404


def test_set_and_reorder_timeline(client: TestClient) -> None:
    book_id = _create_book(client, "Timeline Book")
    scene_a = _create_scene(client, "Scene A")
    scene_b = _create_scene(client, "Scene B")
    for scene_id in (scene_a, scene_b):
        _add_to_canvas(client, book_id, scene_id)

    resp_a = client.post(
        f"/books/{book_id}/scenes/{scene_a}/timeline",
        json={"in_story_time_label": "Day 1", "in_story_time_sort_key": 1.0},
    )
    assert resp_a.status_code == 200
    assert resp_a.json()["in_story_time_label"] == "Day 1"
    assert resp_a.json()["in_story_time_sort_key"] == 1.0

    resp_b = client.post(
        f"/books/{book_id}/scenes/{scene_b}/timeline",
        json={"in_story_time_label": "Day 0 (flashback)", "in_story_time_sort_key": 0.0},
    )
    assert resp_b.status_code == 200

    list_resp = client.get(f"/books/{book_id}/timeline")
    assert list_resp.status_code == 200
    ordered = [r["scene_id"] for r in list_resp.json()]
    assert ordered == [scene_b, scene_a]  # sorted by in_story_time_sort_key, not creation order

    reorder_resp = client.post(
        f"/books/{book_id}/timeline/reorder", json={"scene_ids": [scene_a, scene_b]}
    )
    assert reorder_resp.status_code == 200
    by_scene = {r["scene_id"]: r["timeline_order_index"] for r in reorder_resp.json()}
    assert by_scene[scene_a] == 0
    assert by_scene[scene_b] == 1
    # in_story_time fields set earlier survive the reorder — reorder only touches
    # timeline_order_index.
    labels = {r["scene_id"]: r["in_story_time_label"] for r in reorder_resp.json()}
    assert labels[scene_a] == "Day 1"
    assert labels[scene_b] == "Day 0 (flashback)"


def test_set_timeline_clears_label_to_null(client: TestClient) -> None:
    """Same present-key-applies-even-if-null semantics as assign_scene: an explicit
    ``null`` clears ``in_story_time_label``, while omitted fields (here
    ``in_story_time_sort_key``) are left untouched."""
    book_id = _create_book(client, "Clear Timeline Book")
    scene_id = _create_scene(client, "Clear Timeline Scene")
    _add_to_canvas(client, book_id, scene_id)

    setup = client.post(
        f"/books/{book_id}/scenes/{scene_id}/timeline",
        json={"in_story_time_label": "Day 1", "in_story_time_sort_key": 1.0},
    )
    assert setup.status_code == 200
    assert setup.json()["in_story_time_label"] == "Day 1"

    # Omitting in_story_time_label entirely leaves it as-is.
    unrelated = client.post(
        f"/books/{book_id}/scenes/{scene_id}/timeline",
        json={"in_story_time_sort_key": 1.0},
    )
    assert unrelated.status_code == 200
    assert unrelated.json()["in_story_time_label"] == "Day 1"

    # Explicit null clears the label; the sort key (not sent) is unchanged.
    cleared = client.post(
        f"/books/{book_id}/scenes/{scene_id}/timeline",
        json={"in_story_time_label": None},
    )
    assert cleared.status_code == 200
    body = cleared.json()
    assert body["in_story_time_label"] is None
    assert body["in_story_time_sort_key"] == 1.0


def test_timeline_missing_book_or_scene_404(client: TestClient) -> None:
    book_id = _create_book(client, "Timeline 404 Book")
    scene_id = _create_scene(client, "Timeline 404 Scene")

    resp = client.post(f"/books/does-not-exist/scenes/{scene_id}/timeline", json={})
    assert resp.status_code == 404

    resp = client.post(f"/books/{book_id}/scenes/does-not-exist/timeline", json={})
    assert resp.status_code == 404


def test_assign_then_timeline_reuse_same_row_no_duplicate(client: TestClient) -> None:
    book_id = _create_book(client, "Reuse Row Book")
    scene_id = _create_scene(client, "Reuse Row Scene")
    _add_to_canvas(client, book_id, scene_id)

    assign_resp = client.post(
        f"/books/{book_id}/scenes/{scene_id}/assign",
        json={"structure_beat": "midpoint", "outline_order_index": 5},
    )
    assert assign_resp.status_code == 200
    row_id = assign_resp.json()["id"]

    timeline_resp = client.post(
        f"/books/{book_id}/scenes/{scene_id}/timeline",
        json={"timeline_order_index": 2, "in_story_time_label": "Day 3"},
    )
    assert timeline_resp.status_code == 200
    # Same underlying row — id unchanged, and the earlier Outline fields are still there.
    assert timeline_resp.json()["id"] == row_id
    assert timeline_resp.json()["structure_beat"] == "midpoint"
    assert timeline_resp.json()["outline_order_index"] == 5
    assert timeline_resp.json()["timeline_order_index"] == 2
    assert timeline_resp.json()["in_story_time_label"] == "Day 3"

    # Exactly one row for this (book, scene) pair — list_outline and list_timeline
    # both see the same single row.
    outline_rows = [r for r in client.get(f"/books/{book_id}/outline").json() if r["scene_id"] == scene_id]
    timeline_rows = [r for r in client.get(f"/books/{book_id}/timeline").json() if r["scene_id"] == scene_id]
    assert len(outline_rows) == 1
    assert len(timeline_rows) == 1
    assert outline_rows[0]["id"] == row_id
    assert timeline_rows[0]["id"] == row_id
