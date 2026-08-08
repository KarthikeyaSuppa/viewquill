"""Tests for the Node Canvas endpoints: per-Book scene membership/layout
(``book_scene_links``), graph edges (``scene_connections``), and cross-Book move/copy
(docs/03-DATA-MODEL.md, docs/06 Phase 2 tasks A3/A4/A5).

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


def test_canvas_membership_and_layout_persist(client: TestClient) -> None:
    book_id = _create_book(client, "Canvas Book")
    scene_a = _create_scene(client, "Scene A")
    scene_b = _create_scene(client, "Scene B")

    add_a = client.post(f"/books/{book_id}/scenes/{scene_a}", json={"canvas_x": 10, "canvas_y": 20})
    assert add_a.status_code == 201
    assert add_a.json()["scene_id"] == scene_a

    add_b = client.post(f"/books/{book_id}/scenes/{scene_b}")
    assert add_b.status_code == 201

    canvas = client.get(f"/books/{book_id}/canvas")
    assert canvas.status_code == 200
    body = canvas.json()
    assert {n["scene_id"] for n in body["nodes"]} == {scene_a, scene_b}

    patch_resp = client.patch(
        f"/books/{book_id}/scenes/{scene_a}", json={"canvas_x": 111, "canvas_y": 222, "color": "#fff"}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["canvas_x"] == 111
    assert patch_resp.json()["canvas_y"] == 222

    canvas_after = client.get(f"/books/{book_id}/canvas")
    node_a = next(n for n in canvas_after.json()["nodes"] if n["scene_id"] == scene_a)
    assert node_a["canvas_x"] == 111
    assert node_a["canvas_y"] == 222
    assert node_a["color"] == "#fff"


def test_adding_same_scene_twice_does_not_duplicate_link(client: TestClient) -> None:
    book_id = _create_book(client, "Dup Book")
    scene_id = _create_scene(client, "Dup Scene")

    first = client.post(f"/books/{book_id}/scenes/{scene_id}", json={"canvas_x": 1, "canvas_y": 1})
    assert first.status_code == 201
    second = client.post(f"/books/{book_id}/scenes/{scene_id}", json={"canvas_x": 999, "canvas_y": 999})
    assert second.status_code == 201
    assert first.json()["link_id"] == second.json()["link_id"]

    canvas = client.get(f"/books/{book_id}/canvas")
    matches = [n for n in canvas.json()["nodes"] if n["scene_id"] == scene_id]
    assert len(matches) == 1


def test_edges_are_book_scoped(client: TestClient) -> None:
    book1 = _create_book(client, "Edge Book 1")
    book2 = _create_book(client, "Edge Book 2")
    scene_a = _create_scene(client, "Edge Scene A")
    scene_b = _create_scene(client, "Edge Scene B")

    client.post(f"/books/{book1}/scenes/{scene_a}")
    client.post(f"/books/{book1}/scenes/{scene_b}")

    edge_resp = client.post(
        f"/books/{book1}/edges",
        json={
            "source_scene_id": scene_a,
            "target_scene_id": scene_b,
            "connection_type": "causal",
            "label": "leads to",
        },
    )
    assert edge_resp.status_code == 201
    edge_id = edge_resp.json()["id"]

    edges_book1 = client.get(f"/books/{book1}/edges")
    assert edges_book1.status_code == 200
    assert any(e["id"] == edge_id for e in edges_book1.json())

    edges_book2 = client.get(f"/books/{book2}/edges")
    assert edges_book2.status_code == 200
    assert edges_book2.json() == []

    patch_resp = client.patch(f"/edges/{edge_id}", json={"label": "updated label"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["label"] == "updated label"

    delete_resp = client.delete(f"/edges/{edge_id}")
    assert delete_resp.status_code == 204
    assert client.delete(f"/edges/{edge_id}").status_code == 404


def test_unlink_removes_link_but_scene_survives(client: TestClient) -> None:
    book_id = _create_book(client, "Unlink Book")
    scene_id = _create_scene(client, "Unlink Scene")

    client.post(f"/books/{book_id}/scenes/{scene_id}")
    unlink_resp = client.delete(f"/books/{book_id}/scenes/{scene_id}")
    assert unlink_resp.status_code == 204

    # The link is gone from this Book's canvas...
    canvas = client.get(f"/books/{book_id}/canvas")
    assert all(n["scene_id"] != scene_id for n in canvas.json()["nodes"])

    # ...but the canonical Scene row survives untouched.
    scene_resp = client.get(f"/scenes/{scene_id}")
    assert scene_resp.status_code == 200
    assert scene_resp.json()["id"] == scene_id

    # Unlinking again (already gone) 404s rather than silently no-op-ing.
    assert client.delete(f"/books/{book_id}/scenes/{scene_id}").status_code == 404


def test_move_scene_creates_no_new_scene_rows(client: TestClient) -> None:
    scenes_before = client.get("/scenes").json()
    count_before = len(scenes_before)

    book1 = _create_book(client, "Move Book 1")
    book2 = _create_book(client, "Move Book 2")
    scene_id = _create_scene(client, "Move Scene")

    client.post(f"/books/{book1}/scenes/{scene_id}")

    move_resp = client.post(f"/books/{book2}/scenes/{scene_id}/move?from_book_id={book1}")
    assert move_resp.status_code == 200
    assert move_resp.json()["scene_id"] == scene_id

    # Same canonical scene id now on book2's canvas...
    canvas2 = client.get(f"/books/{book2}/canvas")
    assert any(n["scene_id"] == scene_id for n in canvas2.json()["nodes"])

    # ...and removed from book1's canvas (moved, not duplicated).
    canvas1 = client.get(f"/books/{book1}/canvas")
    assert all(n["scene_id"] != scene_id for n in canvas1.json()["nodes"])

    # Total scenes row count is unchanged aside from the one we just created for this test
    # (we created exactly one new scene above, and move_scene must add zero more).
    scenes_after = client.get("/scenes").json()
    assert len(scenes_after) == count_before + 1


def test_move_without_from_book_id_just_adds_to_dest(client: TestClient) -> None:
    book1 = _create_book(client, "Move Book No Src 1")
    book2 = _create_book(client, "Move Book No Src 2")
    scene_id = _create_scene(client, "Move Scene No Src")

    client.post(f"/books/{book1}/scenes/{scene_id}")
    move_resp = client.post(f"/books/{book2}/scenes/{scene_id}/move")
    assert move_resp.status_code == 200

    # Scene stays linked to BOTH books until an explicit unlink/move-with-source happens.
    canvas1 = client.get(f"/books/{book1}/canvas")
    canvas2 = client.get(f"/books/{book2}/canvas")
    assert any(n["scene_id"] == scene_id for n in canvas1.json()["nodes"])
    assert any(n["scene_id"] == scene_id for n in canvas2.json()["nodes"])


def test_copy_scene_creates_exactly_one_new_scene_with_own_elements(client: TestClient) -> None:
    book1 = _create_book(client, "Copy Book 1")
    book2 = _create_book(client, "Copy Book 2")
    source_id = _create_scene(client, "Copy Source Scene")

    client.post(f"/books/{book1}/scenes/{source_id}")
    heading = client.post(
        f"/scenes/{source_id}/elements",
        json={"element_type": "scene_heading", "text": "INT. SOURCE - DAY"},
    )
    assert heading.status_code == 201
    action = client.post(
        f"/scenes/{source_id}/elements",
        json={"element_type": "action", "text": "Something happens."},
    )
    assert action.status_code == 201

    scenes_before = client.get("/scenes").json()
    count_before = len(scenes_before)

    copy_resp = client.post(f"/books/{book2}/scenes/{source_id}/copy")
    assert copy_resp.status_code == 201
    new_scene = copy_resp.json()
    new_id = new_scene["id"]
    assert new_id != source_id
    assert new_scene["title"] == "Copy Source Scene"

    scenes_after = client.get("/scenes").json()
    assert len(scenes_after) == count_before + 1

    # New scene is on book2's canvas; source scene is untouched on book1's canvas.
    canvas2 = client.get(f"/books/{book2}/canvas")
    assert any(n["scene_id"] == new_id for n in canvas2.json()["nodes"])
    canvas1 = client.get(f"/books/{book1}/canvas")
    assert any(n["scene_id"] == source_id for n in canvas1.json()["nodes"])

    # New scene has its OWN deep-copied elements, distinct ids, same content, same order.
    source_elements = client.get(f"/scenes/{source_id}/elements").json()
    new_elements = client.get(f"/scenes/{new_id}/elements").json()
    assert len(new_elements) == len(source_elements) == 2
    source_ids = {el["id"] for el in source_elements}
    new_ids = {el["id"] for el in new_elements}
    assert source_ids.isdisjoint(new_ids)
    assert [el["text"] for el in new_elements] == [el["text"] for el in source_elements]
    assert [el["element_type"] for el in new_elements] == [el["element_type"] for el in source_elements]

    # Editing the copy's element must NOT touch the source's element.
    new_first_id = new_elements[0]["id"]
    client.patch(f"/scenes/elements/{new_first_id}", json={"text": "Edited only on the copy."})
    source_elements_after = client.get(f"/scenes/{source_id}/elements").json()
    assert source_elements_after[0]["text"] == "INT. SOURCE - DAY"


def test_move_scene_same_book_is_noop_and_does_not_delete_link(client: TestClient) -> None:
    """Regression: ``move_scene`` used to add-then-remove the SAME link when
    ``from_book_id == dest_book_id`` (a same-book "move"), silently wiping the Scene off
    the canvas and returning a deleted ORM object. The service must guard against this,
    and the endpoint must reject it outright as a client error.
    """
    book_id = _create_book(client, "Same Book Move Book")
    scene_id = _create_scene(client, "Same Book Move Scene")

    client.post(f"/books/{book_id}/scenes/{scene_id}")

    # The endpoint rejects a same-book move as a client error rather than executing it.
    move_resp = client.post(f"/books/{book_id}/scenes/{scene_id}/move?from_book_id={book_id}")
    assert move_resp.status_code == 400

    # Regardless, the underlying scene must still be on the book's canvas — a same-book
    # "move" must never delete the link it just re-added.
    canvas = client.get(f"/books/{book_id}/canvas")
    assert any(n["scene_id"] == scene_id for n in canvas.json()["nodes"])

    # The service-level guard itself (not just the route's 400) must also be a no-op:
    # calling it directly must not remove the link or blow up on a deleted/expired instance.
    from app.db.base import SessionLocal
    from app.services import canvas_service

    with SessionLocal() as db:
        link = canvas_service.move_scene(db, scene_id, book_id, src_book_id=book_id)
        assert link is not None
        assert link.scene_id == scene_id
        assert link.book_id == book_id

    canvas_after = client.get(f"/books/{book_id}/canvas")
    assert any(n["scene_id"] == scene_id for n in canvas_after.json()["nodes"])


def test_apply_canvas_template_creates_scenes_and_sequential_edges(client: TestClient) -> None:
    book_id = _create_book(client, "Template Book")

    resp = client.post(
        f"/books/{book_id}/canvas/apply-template", json={"template_key": "three_act"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) == 3
    assert len(body["edges"]) == 2
    assert [n["title"] for n in sorted(body["nodes"], key=lambda n: n["canvas_x"])] == [
        "Act I — Setup",
        "Act II — Confrontation",
        "Act III — Resolution",
    ]
    # Edges connect sequentially in beat order.
    node_by_id = {n["scene_id"]: n for n in body["nodes"]}
    for edge in body["edges"]:
        assert edge["connection_type"] == "sequence"
        source_x = node_by_id[edge["source_scene_id"]]["canvas_x"]
        target_x = node_by_id[edge["target_scene_id"]]["canvas_x"]
        assert source_x < target_x

    # Confirm it persisted via a fresh GET too.
    canvas = client.get(f"/books/{book_id}/canvas")
    assert len(canvas.json()["nodes"]) == 3
    assert len(canvas.json()["edges"]) == 2


def test_apply_canvas_template_heros_journey_beat_count(client: TestClient) -> None:
    book_id = _create_book(client, "Heros Journey Book")

    resp = client.post(
        f"/books/{book_id}/canvas/apply-template", json={"template_key": "heros_journey"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) == 12
    assert len(body["edges"]) == 11


def test_apply_canvas_template_rejects_non_empty_canvas(client: TestClient) -> None:
    book_id = _create_book(client, "Non Empty Canvas Book")
    scene_id = _create_scene(client, "Existing Scene")
    client.post(f"/books/{book_id}/scenes/{scene_id}")

    resp = client.post(
        f"/books/{book_id}/canvas/apply-template", json={"template_key": "three_act"}
    )
    assert resp.status_code == 409

    # Nothing extra was added — canvas is untouched.
    canvas = client.get(f"/books/{book_id}/canvas")
    assert len(canvas.json()["nodes"]) == 1


def test_apply_canvas_template_unknown_key_is_400(client: TestClient) -> None:
    book_id = _create_book(client, "Unknown Template Book")
    resp = client.post(f"/books/{book_id}/canvas/apply-template", json={"template_key": "nope"})
    assert resp.status_code == 400


def test_apply_canvas_template_404_for_missing_book(client: TestClient) -> None:
    resp = client.post(
        "/books/does-not-exist/canvas/apply-template", json={"template_key": "three_act"}
    )
    assert resp.status_code == 404


def test_archived_link_is_invisible_to_canvas_and_not_addressable(client: TestClient) -> None:
    """Regression: an archived ``BookSceneLink`` (e.g. left behind by a scene merge, see
    ``merge_service.accept_merge`` step 5) must disappear from ``GET .../canvas`` and must
    not be reachable via PATCH/DELETE on ``/books/{book_id}/scenes/{scene_id}`` — otherwise a
    link that's supposed to be dormant until undo could be repositioned or deleted directly.
    """
    book_id = _create_book(client, "Archived Link Book")
    scene_id = _create_scene(client, "Archived Link Scene")

    add_resp = client.post(f"/books/{book_id}/scenes/{scene_id}", json={"canvas_x": 5, "canvas_y": 5})
    assert add_resp.status_code == 201

    from app.db.base import SessionLocal, utcnow_iso
    from app.services import canvas_service

    with SessionLocal() as db:
        link = canvas_service._get_link(db, book_id, scene_id)
        assert link is not None
        link.archived_at = utcnow_iso()
        db.commit()

    # Invisible to GET .../canvas.
    canvas = client.get(f"/books/{book_id}/canvas")
    assert all(n["scene_id"] != scene_id for n in canvas.json()["nodes"])

    # Not addressable via PATCH...
    patch_resp = client.patch(f"/books/{book_id}/scenes/{scene_id}", json={"canvas_x": 999})
    assert patch_resp.status_code == 404

    # ...or DELETE.
    delete_resp = client.delete(f"/books/{book_id}/scenes/{scene_id}")
    assert delete_resp.status_code == 404


def test_sequence_edges_get_monotonic_weight_and_others_stay_null(client: TestClient) -> None:
    """``connection_type: 'sequence'`` edges are directional and get an auto-assigned,
    per-Book monotonic-with-gaps ``sequence_weight``; every other connection_type
    (including omitted) is undirected and must have ``sequence_weight`` forced null."""
    book_id = _create_book(client, "Sequence Weight Book")
    scene_a = _create_scene(client, "Seq Scene A")
    scene_b = _create_scene(client, "Seq Scene B")
    scene_c = _create_scene(client, "Seq Scene C")
    for scene_id in (scene_a, scene_b, scene_c):
        client.post(f"/books/{book_id}/scenes/{scene_id}")

    first_sequence = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a,
            "target_scene_id": scene_b,
            "connection_type": "sequence",
        },
    )
    assert first_sequence.status_code == 201
    assert first_sequence.json()["sequence_weight"] == 10

    second_sequence = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_b,
            "target_scene_id": scene_c,
            "connection_type": "sequence",
        },
    )
    assert second_sequence.status_code == 201
    assert second_sequence.json()["sequence_weight"] == 20

    reference_edge = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a,
            "target_scene_id": scene_c,
            "connection_type": "reference",
        },
    )
    assert reference_edge.status_code == 201
    assert reference_edge.json()["sequence_weight"] is None

    untyped_edge = client.post(
        f"/books/{book_id}/edges",
        json={"source_scene_id": scene_a, "target_scene_id": scene_b},
    )
    assert untyped_edge.status_code == 201
    assert untyped_edge.json()["sequence_weight"] is None


def test_patching_connection_type_updates_sequence_weight(client: TestClient) -> None:
    book_id = _create_book(client, "Patch Sequence Weight Book")
    scene_a = _create_scene(client, "Patch Seq Scene A")
    scene_b = _create_scene(client, "Patch Seq Scene B")
    client.post(f"/books/{book_id}/scenes/{scene_a}")
    client.post(f"/books/{book_id}/scenes/{scene_b}")

    edge = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a,
            "target_scene_id": scene_b,
            "connection_type": "sequence",
        },
    )
    assert edge.status_code == 201
    edge_id = edge.json()["id"]
    assert edge.json()["sequence_weight"] == 10

    # sequence -> reference clears the weight to null.
    to_reference = client.patch(f"/edges/{edge_id}", json={"connection_type": "reference"})
    assert to_reference.status_code == 200
    assert to_reference.json()["connection_type"] == "reference"
    assert to_reference.json()["sequence_weight"] is None

    # reference -> sequence assigns a fresh non-null weight.
    back_to_sequence = client.patch(f"/edges/{edge_id}", json={"connection_type": "sequence"})
    assert back_to_sequence.status_code == 200
    assert back_to_sequence.json()["connection_type"] == "sequence"
    assert back_to_sequence.json()["sequence_weight"] is not None


def test_create_edge_writes_undo_log_row(client: TestClient) -> None:
    """Workstream B undo follow-up: creating an edge must write exactly one new
    ``UndoLog`` row with ``action_type="create_edge"`` whose payload contains the edge's
    real (DB-assigned) id — this test only checks the write's shape, not undo/redo
    consumption (that's ``test_undo.py``'s surface).
    """
    from app.db.base import SessionLocal
    from app.models.orm import UndoLog

    book_id = _create_book(client, "Undo Create Edge Book")
    scene_a = _create_scene(client, "Undo Create Edge Scene A")
    scene_b = _create_scene(client, "Undo Create Edge Scene B")
    client.post(f"/books/{book_id}/scenes/{scene_a}")
    client.post(f"/books/{book_id}/scenes/{scene_b}")

    with SessionLocal() as db:
        before_count = (
            db.query(UndoLog).filter(UndoLog.book_id == book_id).count()
        )

    edge_resp = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a,
            "target_scene_id": scene_b,
            "connection_type": "causal",
            "label": "undo create test",
        },
    )
    assert edge_resp.status_code == 201
    edge_id = edge_resp.json()["id"]

    with SessionLocal() as db:
        rows = (
            db.query(UndoLog)
            .filter(UndoLog.book_id == book_id)
            .order_by(UndoLog.sequence.desc())
            .all()
        )
        assert len(rows) == before_count + 1
        row = rows[0]
        assert row.action_type == "create_edge"
        assert row.payload["edge"]["id"] == edge_id
        assert row.payload["edge"]["connection_type"] == "causal"


def test_update_edge_connection_type_writes_undo_log_with_sequence_weight(
    client: TestClient,
) -> None:
    """Patching ``connection_type`` alone must produce an ``update_edge`` UndoLog row whose
    ``before``/``after`` also capture ``sequence_weight``, since it silently changes as a
    side effect of the connection_type toggle (see canvas_service.update_edge).
    """
    from app.db.base import SessionLocal
    from app.models.orm import UndoLog

    book_id = _create_book(client, "Undo Update Edge Book")
    scene_a = _create_scene(client, "Undo Update Edge Scene A")
    scene_b = _create_scene(client, "Undo Update Edge Scene B")
    client.post(f"/books/{book_id}/scenes/{scene_a}")
    client.post(f"/books/{book_id}/scenes/{scene_b}")

    edge_resp = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a,
            "target_scene_id": scene_b,
            "connection_type": "sequence",
        },
    )
    assert edge_resp.status_code == 201
    edge_id = edge_resp.json()["id"]
    original_weight = edge_resp.json()["sequence_weight"]
    assert original_weight is not None

    with SessionLocal() as db:
        before_count = (
            db.query(UndoLog).filter(UndoLog.book_id == book_id).count()
        )

    patch_resp = client.patch(f"/edges/{edge_id}", json={"connection_type": "reference"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["sequence_weight"] is None

    with SessionLocal() as db:
        rows = (
            db.query(UndoLog)
            .filter(UndoLog.book_id == book_id)
            .order_by(UndoLog.sequence.desc())
            .all()
        )
        assert len(rows) == before_count + 1
        row = rows[0]
        assert row.action_type == "update_edge"
        assert row.payload["edge_id"] == edge_id
        assert row.payload["before"] == {
            "connection_type": "sequence",
            "sequence_weight": original_weight,
        }
        assert row.payload["after"] == {
            "connection_type": "reference",
            "sequence_weight": None,
        }


def test_update_edge_noop_does_not_write_undo_log(client: TestClient) -> None:
    """Patching a key to its own current value must not create undo noise."""
    from app.db.base import SessionLocal
    from app.models.orm import UndoLog

    book_id = _create_book(client, "Undo Noop Update Edge Book")
    scene_a = _create_scene(client, "Undo Noop Scene A")
    scene_b = _create_scene(client, "Undo Noop Scene B")
    client.post(f"/books/{book_id}/scenes/{scene_a}")
    client.post(f"/books/{book_id}/scenes/{scene_b}")

    edge_resp = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a,
            "target_scene_id": scene_b,
            "connection_type": "causal",
            "label": "same label",
        },
    )
    assert edge_resp.status_code == 201
    edge_id = edge_resp.json()["id"]

    with SessionLocal() as db:
        before_count = (
            db.query(UndoLog).filter(UndoLog.book_id == book_id).count()
        )

    patch_resp = client.patch(f"/edges/{edge_id}", json={"label": "same label"})
    assert patch_resp.status_code == 200

    with SessionLocal() as db:
        after_count = (
            db.query(UndoLog).filter(UndoLog.book_id == book_id).count()
        )
    assert after_count == before_count


def test_delete_edge_writes_undo_log_with_full_snapshot(client: TestClient) -> None:
    """Deleting an edge must write a ``delete_edge`` UndoLog row with a full pre-delete
    row snapshot in its payload.
    """
    from app.db.base import SessionLocal
    from app.models.orm import UndoLog

    book_id = _create_book(client, "Undo Delete Edge Book")
    scene_a = _create_scene(client, "Undo Delete Edge Scene A")
    scene_b = _create_scene(client, "Undo Delete Edge Scene B")
    client.post(f"/books/{book_id}/scenes/{scene_a}")
    client.post(f"/books/{book_id}/scenes/{scene_b}")

    edge_resp = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a,
            "target_scene_id": scene_b,
            "connection_type": "contradiction",
            "label": "to be deleted",
        },
    )
    assert edge_resp.status_code == 201
    edge_id = edge_resp.json()["id"]

    with SessionLocal() as db:
        before_count = (
            db.query(UndoLog).filter(UndoLog.book_id == book_id).count()
        )

    delete_resp = client.delete(f"/edges/{edge_id}")
    assert delete_resp.status_code == 204

    with SessionLocal() as db:
        rows = (
            db.query(UndoLog)
            .filter(UndoLog.book_id == book_id)
            .order_by(UndoLog.sequence.desc())
            .all()
        )
        assert len(rows) == before_count + 1
        row = rows[0]
        assert row.action_type == "delete_edge"
        snapshot = row.payload["edge"]
        assert snapshot["id"] == edge_id
        assert snapshot["source_scene_id"] == scene_a
        assert snapshot["target_scene_id"] == scene_b
        assert snapshot["connection_type"] == "contradiction"
        assert snapshot["label"] == "to be deleted"
        assert snapshot["book_id"] == book_id


def test_canvas_and_edges_404_for_missing_book_or_scene(client: TestClient) -> None:
    assert client.get("/books/does-not-exist/canvas").status_code == 404
    assert client.post("/books/does-not-exist/scenes/also-missing").status_code == 404
    assert client.get("/books/does-not-exist/edges").status_code == 404

    book_id = _create_book(client, "Missing Scene Book")
    assert client.post(f"/books/{book_id}/scenes/does-not-exist").status_code == 404
    assert client.post(f"/books/{book_id}/scenes/does-not-exist/copy").status_code == 404
