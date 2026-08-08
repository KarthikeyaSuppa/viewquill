"""Tests for scoped undo/redo (Workstream B task 7, PHASE11.md) —
POST /books/{book_id}/undo and /redo, built on the `UndoLog` tombstone rows
`scene_service.delete_scene` writes (task 6, see test_scenes.py's
test_permanent_delete_writes_undo_log_and_still_deletes_rows).

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
from sqlalchemy import func, select  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.orm import Scene, SceneConnection, SceneMerge, SceneRevision  # noqa: E402
from app.services import merge_service, undo_service  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        yield test_client


def _make_book_with_scene(client: TestClient) -> tuple[str, str, str]:
    """Creates a Book, a Scene linked onto its canvas, and one screenplay element.

    Returns (book_id, scene_id, element_id).
    """
    book_resp = client.post("/books", json={"title": "Undo/Redo Book", "book_type": "story_book"})
    assert book_resp.status_code == 201
    book_id = book_resp.json()["id"]

    scene_resp = client.post(
        "/scenes",
        json={
            "node_type": "scene",
            "title": "Scene To Undo",
            "description": "Some prose worth restoring.",
        },
    )
    assert scene_resp.status_code == 201
    scene_id = scene_resp.json()["id"]

    link_resp = client.post(
        f"/books/{book_id}/scenes/{scene_id}",
        json={"canvas_x": 11, "canvas_y": 22, "color": "#abc"},
    )
    assert link_resp.status_code == 201

    element_resp = client.post(
        f"/scenes/{scene_id}/elements",
        json={"element_type": "action", "text": "Someone enters quietly."},
    )
    assert element_resp.status_code == 201
    element_id = element_resp.json()["id"]

    return book_id, scene_id, element_id


def test_undo_restores_scene_links_and_elements(client: TestClient) -> None:
    book_id, scene_id, element_id = _make_book_with_scene(client)

    delete_resp = client.delete(f"/scenes/{scene_id}")
    assert delete_resp.status_code == 204
    assert client.get(f"/scenes/{scene_id}").status_code == 404

    undo_resp = client.post(f"/books/{book_id}/undo")
    assert undo_resp.status_code == 200
    body = undo_resp.json()
    assert body["action_type"] == "delete_scene"
    assert body["scene_id"] == scene_id
    assert body["undone_at"] is not None

    # Scene itself restored with matching data.
    restored_scene = client.get(f"/scenes/{scene_id}")
    assert restored_scene.status_code == 200
    assert restored_scene.json()["title"] == "Scene To Undo"
    assert restored_scene.json()["description"] == "Some prose worth restoring."

    # Screenplay element restored.
    elements = client.get(f"/scenes/{scene_id}/elements")
    assert elements.status_code == 200
    assert len(elements.json()) == 1
    assert elements.json()[0]["id"] == element_id
    assert elements.json()[0]["text"] == "Someone enters quietly."

    # Book-scene link restored — canvas shows the node again with its original placement.
    canvas_resp = client.get(f"/books/{book_id}/canvas")
    assert canvas_resp.status_code == 200
    nodes = canvas_resp.json()["nodes"]
    matching = [n for n in nodes if n["scene_id"] == scene_id]
    assert len(matching) == 1
    assert matching[0]["canvas_x"] == 11
    assert matching[0]["canvas_y"] == 22


def test_undo_again_with_nothing_left_is_404(client: TestClient) -> None:
    book_id, scene_id, _element_id = _make_book_with_scene(client)

    delete_resp = client.delete(f"/scenes/{scene_id}")
    assert delete_resp.status_code == 204

    first_undo = client.post(f"/books/{book_id}/undo")
    assert first_undo.status_code == 200

    # Nothing new destructive happened since — this Book has nothing left to undo.
    second_undo = client.post(f"/books/{book_id}/undo")
    assert second_undo.status_code == 404


def test_redo_reapplies_the_delete(client: TestClient) -> None:
    book_id, scene_id, _element_id = _make_book_with_scene(client)

    delete_resp = client.delete(f"/scenes/{scene_id}")
    assert delete_resp.status_code == 204

    undo_resp = client.post(f"/books/{book_id}/undo")
    assert undo_resp.status_code == 200
    assert client.get(f"/scenes/{scene_id}").status_code == 200

    redo_resp = client.post(f"/books/{book_id}/redo")
    assert redo_resp.status_code == 200
    redo_body = redo_resp.json()
    assert redo_body["action_type"] == "delete_scene"
    assert redo_body["scene_id"] == scene_id
    assert redo_body["undone_at"] is None

    # The scene is deleted again.
    assert client.get(f"/scenes/{scene_id}").status_code == 404

    # Redo must NOT have created a second UndoLog row — undo is available again for the
    # SAME action (toggle, not a new entry), and there's still nothing further to redo.
    assert client.post(f"/books/{book_id}/redo").status_code == 404


def test_undo_with_no_undo_log_rows_is_404(client: TestClient) -> None:
    book_resp = client.post(
        "/books", json={"title": "Never Deleted Anything", "book_type": "story_book"}
    )
    assert book_resp.status_code == 201
    book_id = book_resp.json()["id"]

    assert client.post(f"/books/{book_id}/undo").status_code == 404
    assert client.post(f"/books/{book_id}/redo").status_code == 404


def test_undo_and_redo_missing_book_404(client: TestClient) -> None:
    assert client.post("/books/does-not-exist/undo").status_code == 404
    assert client.post("/books/does-not-exist/redo").status_code == 404


# ── GET /books/{book_id}/undo-status ────────────────────────────────────────────
def test_undo_status_fresh_book_is_all_false(client: TestClient) -> None:
    book_resp = client.post(
        "/books", json={"title": "Fresh Undo Status Book", "book_type": "story_book"}
    )
    assert book_resp.status_code == 201
    book_id = book_resp.json()["id"]

    status_resp = client.get(f"/books/{book_id}/undo-status")
    assert status_resp.status_code == 200
    assert status_resp.json() == {"can_undo": False, "can_redo": False}


def test_undo_status_after_delete_only_can_undo(client: TestClient) -> None:
    book_id, scene_id, _element_id = _make_book_with_scene(client)

    delete_resp = client.delete(f"/scenes/{scene_id}")
    assert delete_resp.status_code == 204

    status_resp = client.get(f"/books/{book_id}/undo-status")
    assert status_resp.status_code == 200
    assert status_resp.json() == {"can_undo": True, "can_redo": False}


def test_undo_status_after_undo_only_can_redo(client: TestClient) -> None:
    book_id, scene_id, _element_id = _make_book_with_scene(client)

    assert client.delete(f"/scenes/{scene_id}").status_code == 204
    assert client.post(f"/books/{book_id}/undo").status_code == 200

    status_resp = client.get(f"/books/{book_id}/undo-status")
    assert status_resp.status_code == 200
    assert status_resp.json() == {"can_undo": False, "can_redo": True}


def test_undo_status_redo_stale_after_newer_action(client: TestClient) -> None:
    """Delete scene A, undo it (redo becomes available), then delete scene B — a NEW
    destructive action. The undone row for A is still technically ``undone_at IS NOT
    NULL`` in the table, but it's no longer the Book's most recent action, so
    ``can_redo`` must report False (redoing it would silently resurrect a stale action);
    ``can_undo`` must report True since B's delete is now the latest undoable action.
    """
    book_id, scene_a_id, _element_id = _make_book_with_scene(client)

    scene_b_resp = client.post(
        "/scenes",
        json={"node_type": "scene", "title": "Scene B", "description": "Beta prose."},
    )
    assert scene_b_resp.status_code == 201
    scene_b_id = scene_b_resp.json()["id"]
    link_b_resp = client.post(f"/books/{book_id}/scenes/{scene_b_id}", json={})
    assert link_b_resp.status_code == 201

    assert client.delete(f"/scenes/{scene_a_id}").status_code == 204
    assert client.post(f"/books/{book_id}/undo").status_code == 200

    # Sanity check: redo is available right after the undo, before B is deleted.
    mid_status = client.get(f"/books/{book_id}/undo-status")
    assert mid_status.json() == {"can_undo": False, "can_redo": True}

    assert client.delete(f"/scenes/{scene_b_id}").status_code == 204

    status_resp = client.get(f"/books/{book_id}/undo-status")
    assert status_resp.status_code == 200
    assert status_resp.json() == {"can_undo": True, "can_redo": False}


def test_undo_status_missing_book_404(client: TestClient) -> None:
    assert client.get("/books/does-not-exist/undo-status").status_code == 404


# ── Delete/undo must not lose a scene's permanent revision/merge history ────────
def test_undo_restores_scene_revisions_and_scene_merges(client: TestClient) -> None:
    """A scene with SceneRevision history AND SceneMerge provenance, hard-deleted then
    undone, must come back with both intact — SceneRevision rows are ``ON DELETE CASCADE``
    (gone with the Scene, so undo must reinsert them) while SceneMerge rows are
    ``ON DELETE SET NULL`` (the row survives but its FK to this scene is nulled, so undo
    must restore that column instead of reinserting a row) — see
    ``scene_service._build_delete_undo_payload`` / ``undo_service._restore_delete_scene``.
    """
    book_resp = client.post(
        "/books", json={"title": "History Undo Book", "book_type": "story_book"}
    )
    assert book_resp.status_code == 201
    book_id = book_resp.json()["id"]

    scene_a_resp = client.post(
        "/scenes", json={"node_type": "scene", "title": "Scene A", "description": "Alpha prose."}
    )
    assert scene_a_resp.status_code == 201
    scene_a_id = scene_a_resp.json()["id"]

    scene_b_resp = client.post(
        "/scenes", json={"node_type": "scene", "title": "Scene B", "description": "Beta prose."}
    )
    assert scene_b_resp.status_code == 201
    scene_b_id = scene_b_resp.json()["id"]

    assert client.post(f"/books/{book_id}/scenes/{scene_a_id}", json={}).status_code == 201
    assert client.post(f"/books/{book_id}/scenes/{scene_b_id}", json={}).status_code == 201

    with SessionLocal() as db:
        merged = merge_service.accept_merge(
            db,
            book_id=book_id,
            source_scene_ids=[scene_a_id, scene_b_id],
            merged_title="Merged Scene",
            merged_description="Combined alpha and beta prose.",
        )
        merged_id = merged.id

    # A manual edit after the merge adds a second SceneRevision row (revision 1 already
    # came from the merge itself).
    patch_resp = client.patch(f"/scenes/{merged_id}", json={"title": "Merged Scene Edited"})
    assert patch_resp.status_code == 200

    with SessionLocal() as db:
        merge_ids_before = [
            m.id
            for m in db.execute(
                select(SceneMerge).where(SceneMerge.merged_scene_id == merged_id)
            ).scalars()
        ]
        assert len(merge_ids_before) == 2

    delete_resp = client.delete(f"/scenes/{merged_id}")
    assert delete_resp.status_code == 204
    assert client.get(f"/scenes/{merged_id}").status_code == 404

    with SessionLocal() as db:
        # SceneRevision rows cascade-deleted with the Scene.
        assert (
            list(
                db.execute(
                    select(SceneRevision).where(SceneRevision.scene_id == merged_id)
                ).scalars()
            )
            == []
        )
        # SceneMerge rows survive, but their FK to the deleted scene is nulled out.
        merges_after_delete = list(
            db.execute(select(SceneMerge).where(SceneMerge.id.in_(merge_ids_before))).scalars()
        )
        assert len(merges_after_delete) == 2
        assert all(m.merged_scene_id is None for m in merges_after_delete)

    undo_resp = client.post(f"/books/{book_id}/undo")
    assert undo_resp.status_code == 200
    assert client.get(f"/scenes/{merged_id}").status_code == 200

    with SessionLocal() as db:
        revisions_after = list(
            db.execute(
                select(SceneRevision).where(SceneRevision.scene_id == merged_id)
            ).scalars()
        )
        assert {r.revision_number for r in revisions_after} == {1, 2}

        merges_after = list(
            db.execute(
                select(SceneMerge).where(SceneMerge.merged_scene_id == merged_id)
            ).scalars()
        )
        assert {m.source_scene_id for m in merges_after} == {scene_a_id, scene_b_id}


# ── Edge undo/redo (`create_edge` / `delete_edge` / `update_edge`) ──────────────
#
# `canvas_service.py`'s edge CRUD (a separate, parallel task per PHASE11.md) already
# writes the `UndoLog` rows these three action types consume — see test_canvas.py's
# test_create_edge_writes_undo_log_row /
# test_update_edge_connection_type_writes_undo_log_with_sequence_weight /
# test_delete_edge_writes_undo_log_with_full_snapshot for coverage that the WRITE side
# produces the right payload shape. These tests instead drive the real
# POST/PATCH/DELETE /edges endpoints end-to-end through undo_service's CONSUME side
# (`/books/{book_id}/undo` and `/redo`), proving the round trip actually restores/reapplies
# correctly — not just that a row got logged.


def _row_to_dict(row) -> dict:
    """Plain JSON-safe dict of a row's own columns — same pattern as
    `scene_service._row_to_dict` / `bundle_export._row_to_dict`.
    """
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def _make_book_with_two_linked_scenes(client: TestClient) -> tuple[str, str, str]:
    """Creates a Book with two Scenes linked onto its canvas. Returns (book_id, scene_a_id,
    scene_b_id).
    """
    book_resp = client.post(
        "/books", json={"title": "Edge Undo/Redo Book", "book_type": "story_book"}
    )
    assert book_resp.status_code == 201
    book_id = book_resp.json()["id"]

    scene_a_resp = client.post("/scenes", json={"node_type": "scene", "title": "Edge Scene A"})
    assert scene_a_resp.status_code == 201
    scene_a_id = scene_a_resp.json()["id"]

    scene_b_resp = client.post("/scenes", json={"node_type": "scene", "title": "Edge Scene B"})
    assert scene_b_resp.status_code == 201
    scene_b_id = scene_b_resp.json()["id"]

    assert client.post(f"/books/{book_id}/scenes/{scene_a_id}", json={}).status_code == 201
    assert client.post(f"/books/{book_id}/scenes/{scene_b_id}", json={}).status_code == 201

    return book_id, scene_a_id, scene_b_id


def test_create_edge_undo_removes_it_and_redo_readds_with_identical_values(
    client: TestClient,
) -> None:
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    edge_resp = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a_id,
            "target_scene_id": scene_b_id,
            "connection_type": "sequence",
            "label": "then",
            "sequence_weight": 10,
        },
    )
    assert edge_resp.status_code == 201
    edge_id = edge_resp.json()["id"]

    with SessionLocal() as db:
        edge_row = db.get(SceneConnection, edge_id)
        assert edge_row is not None
        edge_snapshot = _row_to_dict(edge_row)
    assert edge_snapshot["sequence_weight"] == 10

    undo_resp = client.post(f"/books/{book_id}/undo")
    assert undo_resp.status_code == 200
    assert undo_resp.json()["action_type"] == "create_edge"

    edges_after_undo = client.get(f"/books/{book_id}/edges").json()
    assert edge_id not in [e["id"] for e in edges_after_undo]
    with SessionLocal() as db:
        assert db.get(SceneConnection, edge_id) is None

    redo_resp = client.post(f"/books/{book_id}/redo")
    assert redo_resp.status_code == 200
    assert redo_resp.json()["action_type"] == "create_edge"

    with SessionLocal() as db:
        restored = db.get(SceneConnection, edge_id)
        assert restored is not None
        # Identical values, including the id and sequence_weight — a verbatim replay of the
        # originally-persisted row, not a recomputed one.
        assert _row_to_dict(restored) == edge_snapshot


def test_delete_edge_undo_readds_it_and_redo_removes_it_again(client: TestClient) -> None:
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    edge_resp = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a_id,
            "target_scene_id": scene_b_id,
            "connection_type": "causal",
            "label": "because",
        },
    )
    assert edge_resp.status_code == 201
    edge_id = edge_resp.json()["id"]

    with SessionLocal() as db:
        edge_row = db.get(SceneConnection, edge_id)
        assert edge_row is not None
        edge_snapshot = _row_to_dict(edge_row)

    delete_resp = client.delete(f"/edges/{edge_id}")
    assert delete_resp.status_code == 204
    with SessionLocal() as db:
        assert db.get(SceneConnection, edge_id) is None

    undo_resp = client.post(f"/books/{book_id}/undo")
    assert undo_resp.status_code == 200
    assert undo_resp.json()["action_type"] == "delete_edge"

    with SessionLocal() as db:
        restored = db.get(SceneConnection, edge_id)
        assert restored is not None
        assert _row_to_dict(restored) == edge_snapshot

    redo_resp = client.post(f"/books/{book_id}/redo")
    assert redo_resp.status_code == 200
    assert redo_resp.json()["action_type"] == "delete_edge"

    with SessionLocal() as db:
        assert db.get(SceneConnection, edge_id) is None


def test_update_edge_undo_restores_prior_connection_type_and_weight_and_redo_reapplies(
    client: TestClient,
) -> None:
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    edge_resp = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a_id,
            "target_scene_id": scene_b_id,
            "connection_type": "custom",
        },
    )
    assert edge_resp.status_code == 201
    edge_id = edge_resp.json()["id"]
    assert edge_resp.json()["sequence_weight"] is None

    # Toggling to "sequence" also auto-assigns sequence_weight as a side effect
    # (canvas_service.update_edge / _next_sequence_weight) — the update_edge UndoLog row's
    # "before"/"after" payload must capture BOTH changed columns, not just the one the
    # caller explicitly passed.
    update_resp = client.patch(f"/edges/{edge_id}", json={"connection_type": "sequence"})
    assert update_resp.status_code == 200
    resolved_weight = update_resp.json()["sequence_weight"]
    assert resolved_weight is not None

    undo_resp = client.post(f"/books/{book_id}/undo")
    assert undo_resp.status_code == 200
    assert undo_resp.json()["action_type"] == "update_edge"

    with SessionLocal() as db:
        edge_row = db.get(SceneConnection, edge_id)
        assert edge_row is not None
        assert edge_row.connection_type == "custom"
        assert edge_row.sequence_weight is None

    redo_resp = client.post(f"/books/{book_id}/redo")
    assert redo_resp.status_code == 200
    assert redo_resp.json()["action_type"] == "update_edge"

    with SessionLocal() as db:
        edge_row = db.get(SceneConnection, edge_id)
        assert edge_row is not None
        assert edge_row.connection_type == "sequence"
        assert edge_row.sequence_weight == resolved_weight


def test_update_edge_redo_does_not_drift_when_another_sequence_edge_is_created_between(
    client: TestClient,
) -> None:
    """`_next_sequence_weight` assigns weights via a per-book MAX(sequence_weight)+10
    counter (canvas_service.py). If redo ever recomputed a fresh weight instead of
    replaying the exact `payload["after"]` value captured at mutation time, creating a new
    `sequence` edge between the undo and the redo would bump the shared counter and cause
    the redone edge to drift to a different weight than it originally had. This asserts the
    redo always replays the captured value verbatim, regardless of counter state at redo
    time.

    A surviving `sequence` edge (B) is created BEFORE edge A's toggle-then-undo, and kept
    untouched throughout, so the per-book MAX is still non-zero after A is undone — this is
    what makes a naive "recompute at redo time" implementation actually drift, rather than
    coincidentally landing on the same value because the counter reset to zero.

    Edges C and D (which bump the counter between the undo and the redo) are inserted
    directly via the ORM rather than through `POST /edges` — going through the real
    endpoint would write its own `create_edge` UndoLog rows, which (correctly, per reviewer
    fix #3's staleness guard) would make edge A's undone `update_edge` row stale and block
    the redo entirely. Inserting directly bumps the same per-book `sequence_weight` counter
    `_next_sequence_weight` reads, preserving this test's actual mechanism (a counter that
    has moved on by redo time), without an unrelated action appearing in the Book's `UndoLog`
    ledger, matching how a real caller would bump the counter via some out-of-band data
    change rather than through this Book's own undo/redo history.
    """
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    scene_c_resp = client.post("/scenes", json={"node_type": "scene", "title": "Scene C"})
    assert scene_c_resp.status_code == 201
    scene_c_id = scene_c_resp.json()["id"]
    scene_d_resp = client.post("/scenes", json={"node_type": "scene", "title": "Scene D"})
    assert scene_d_resp.status_code == 201
    scene_d_id = scene_d_resp.json()["id"]
    scene_e_resp = client.post("/scenes", json={"node_type": "scene", "title": "Scene E"})
    assert scene_e_resp.status_code == 201
    scene_e_id = scene_e_resp.json()["id"]

    # Edge B: a surviving sequence edge, created first and never touched again — this is
    # what keeps the per-book counter non-zero after edge A is undone below.
    edge_b_resp = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_b_id,
            "target_scene_id": scene_c_id,
            "connection_type": "sequence",
        },
    )
    assert edge_b_resp.status_code == 201
    edge_b_weight = edge_b_resp.json()["sequence_weight"]

    # Edge A: created as undirected, toggled to sequence (its weight resolves on top of
    # edge B's), then that toggle is undone.
    edge_a_resp = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a_id,
            "target_scene_id": scene_b_id,
            "connection_type": "custom",
        },
    )
    assert edge_a_resp.status_code == 201
    edge_a_id = edge_a_resp.json()["id"]

    update_resp = client.patch(f"/edges/{edge_a_id}", json={"connection_type": "sequence"})
    assert update_resp.status_code == 200
    original_weight = update_resp.json()["sequence_weight"]
    assert original_weight is not None
    assert original_weight > edge_b_weight

    undo_resp = client.post(f"/books/{book_id}/undo")
    assert undo_resp.status_code == 200

    # Edges C and D: two more sequence edges, inserted directly so they bump the per-book
    # counter without appearing in this Book's UndoLog ledger (see docstring above). Edge B
    # still holds its weight, so C resolves on top of it — and since undoing A only ever
    # removed A's own increment, C's weight coincidentally lands back on `original_weight`.
    # D resolves on top of C, landing strictly past `original_weight` — a naive
    # "recompute on redo" implementation would cause edge A's redo to land here instead of
    # its true original value.
    from app.db.base import new_uuid

    with SessionLocal() as db:
        max_weight = db.execute(
            select(func.max(SceneConnection.sequence_weight)).where(
                SceneConnection.book_id == book_id
            )
        ).scalar() or 0
        edge_c_weight = max_weight + 10
        db.add(
            SceneConnection(
                id=new_uuid(),
                book_id=book_id,
                source_scene_id=scene_c_id,
                target_scene_id=scene_d_id,
                connection_type="sequence",
                sequence_weight=edge_c_weight,
            )
        )
        naive_recompute_weight = edge_c_weight + 10
        db.add(
            SceneConnection(
                id=new_uuid(),
                book_id=book_id,
                source_scene_id=scene_d_id,
                target_scene_id=scene_e_id,
                connection_type="sequence",
                sequence_weight=naive_recompute_weight,
            )
        )
        db.commit()
    assert naive_recompute_weight > original_weight

    redo_resp = client.post(f"/books/{book_id}/redo")
    assert redo_resp.status_code == 200

    with SessionLocal() as db:
        edge_a_row = db.get(SceneConnection, edge_a_id)
        assert edge_a_row is not None
        assert edge_a_row.connection_type == "sequence"
        assert edge_a_row.sequence_weight == original_weight
        assert edge_a_row.sequence_weight != naive_recompute_weight


def test_create_edge_undo_missing_row_raises(client: TestClient) -> None:
    """If the edge a `create_edge` UndoLog row refers to has already been removed via some
    other path (simulated here with a direct hard delete bypassing
    `canvas_service.delete_edge`, mirroring test_merge.py's
    "missing source link" pattern for `merge_scenes`), undo must raise
    `UNDO_TARGET_ROW_MISSING` rather than silently reporting success.
    """
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    edge_resp = client.post(
        f"/books/{book_id}/edges",
        json={"source_scene_id": scene_a_id, "target_scene_id": scene_b_id},
    )
    assert edge_resp.status_code == 201
    edge_id = edge_resp.json()["id"]

    # Hard-delete the edge directly, bypassing canvas_service.delete_edge (so no
    # delete_edge UndoLog row is written) — simulates the row having been removed via some
    # other path in the meantime. The create_edge UndoLog row from creating it above is
    # still the Book's latest active action.
    with SessionLocal() as db:
        edge_row = db.get(SceneConnection, edge_id)
        db.delete(edge_row)
        db.commit()

    with SessionLocal() as db:
        with pytest.raises(ValueError, match="UNDO_TARGET_ROW_MISSING"):
            undo_service.undo_last_action(db, book_id)
        db.rollback()


# ── Reviewer follow-up (single-commit create/update_edge + redo FK/staleness guards) ──


def test_create_edge_mutation_and_undo_log_are_committed_together(
    client: TestClient,
) -> None:
    """`create_edge` must produce its ``SceneConnection`` row and its ``create_edge``
    ``UndoLog`` row in ONE commit (canvas_service.create_edge, reviewer fix #1) — every
    value the ``UndoLog`` payload needs (the new edge's id/resolved sequence_weight) is
    already known in Python before any commit, so there is no need for the old two-commit
    shape. Verified behaviorally: both rows must already be visible, without any further
    write, the instant the create call returns.
    """
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    edge_resp = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a_id,
            "target_scene_id": scene_b_id,
            "connection_type": "sequence",
        },
    )
    assert edge_resp.status_code == 201
    edge_id = edge_resp.json()["id"]

    with SessionLocal() as db:
        edge_row = db.get(SceneConnection, edge_id)
        assert edge_row is not None
        from app.models.orm import UndoLog as UndoLogRow

        log_rows = db.execute(
            select(UndoLogRow).where(
                UndoLogRow.book_id == book_id, UndoLogRow.action_type == "create_edge"
            )
        ).scalars().all()
        assert len(log_rows) == 1
        assert log_rows[0].payload["edge"]["id"] == edge_id


def test_update_edge_mutation_and_undo_log_are_committed_together(
    client: TestClient,
) -> None:
    """Same single-commit guarantee (reviewer fix #1) for `update_edge`: the mutated
    ``SceneConnection`` row and its ``update_edge`` ``UndoLog`` row must both already be
    visible the instant the PATCH call returns.
    """
    from app.models.orm import UndoLog as UndoLogRow

    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    edge_resp = client.post(
        f"/books/{book_id}/edges",
        json={
            "source_scene_id": scene_a_id,
            "target_scene_id": scene_b_id,
            "connection_type": "custom",
        },
    )
    assert edge_resp.status_code == 201
    edge_id = edge_resp.json()["id"]

    patch_resp = client.patch(f"/edges/{edge_id}", json={"label": "renamed"})
    assert patch_resp.status_code == 200

    with SessionLocal() as db:
        edge_row = db.get(SceneConnection, edge_id)
        assert edge_row is not None
        assert edge_row.label == "renamed"
        log_rows = db.execute(
            select(UndoLogRow).where(
                UndoLogRow.book_id == book_id, UndoLogRow.action_type == "update_edge"
            )
        ).scalars().all()
        assert len(log_rows) == 1
        assert log_rows[0].payload["after"] == {"label": "renamed"}


def test_redo_create_edge_missing_scene_raises_directly(client: TestClient) -> None:
    """Direct unit-level coverage of ``_redo_create_edge``'s FK-target guard (reviewer fix
    #2): a payload referencing Scenes that no longer exist must raise
    ``UNDO_TARGET_ROW_MISSING`` rather than tripping SQLite's raw FK ``IntegrityError``.

    Exercised directly against ``undo_service._redo_create_edge`` (bypassing
    ``redo_last_action``'s staleness guard, reviewer fix #3, which would otherwise
    intercept the equivalent end-to-end scenario before it ever reaches this guard — see
    ``test_redo_create_edge_after_target_scene_deleted_is_a_clean_error`` for that
    end-to-end path).
    """
    with SessionLocal() as db:
        with pytest.raises(ValueError, match="UNDO_TARGET_ROW_MISSING"):
            undo_service._redo_create_edge(
                db,
                {
                    "edge": {
                        "id": "missing-edge",
                        "book_id": "missing-book",
                        "source_scene_id": "does-not-exist-a",
                        "target_scene_id": "does-not-exist-b",
                        "source_handle": None,
                        "target_handle": None,
                        "connection_type": None,
                        "label": None,
                        "sequence_weight": None,
                    }
                },
            )
        db.rollback()


def test_restore_delete_edge_missing_scene_raises_directly(client: TestClient) -> None:
    """Same direct coverage as above for ``_restore_delete_edge``'s FK-target guard
    (reviewer fix #2) — reached via ``undo_last_action`` when undoing a ``delete_edge``
    action whose edge referenced a Scene that has since been hard-deleted.
    """
    with SessionLocal() as db:
        with pytest.raises(ValueError, match="UNDO_TARGET_ROW_MISSING"):
            undo_service._restore_delete_edge(
                db,
                {
                    "edge": {
                        "id": "missing-edge-2",
                        "book_id": "missing-book",
                        "source_scene_id": "does-not-exist-c",
                        "target_scene_id": "does-not-exist-d",
                        "source_handle": None,
                        "target_handle": None,
                        "connection_type": None,
                        "label": None,
                        "sequence_weight": None,
                    }
                },
            )
        db.rollback()


def test_redo_create_edge_after_target_scene_deleted_is_a_clean_error(
    client: TestClient,
) -> None:
    """Reviewer-traced repro: create an edge, undo it (edge deleted), delete the edge's
    target Scene, then attempt ``POST /books/{book_id}/redo`` — must be a clean 4xx, never
    an unhandled 500/IntegrityError from re-inserting a ``SceneConnection`` FK'd onto a
    Scene that no longer exists.

    Deleting the target Scene is ITSELF a new destructive action for this Book (it writes
    its own ``delete_scene`` ``UndoLog`` row), so by the time redo is attempted, the
    undone ``create_edge`` row is not just missing its FK target — it is also now STALE
    (reviewer fix #3's staleness guard, mirroring ``get_undo_status``'s ``can_redo``
    check). That guard fires first and reports "nothing to redo" (404) before the request
    ever reaches fix #2's FK guard on ``_redo_create_edge`` — which is exactly the point of
    fix #3: refuse to even attempt a stale redo, rather than attempt it and rely on fix #2
    to turn the resulting crash into a 409. Either way this must never be a 500.
    """
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    edge_resp = client.post(
        f"/books/{book_id}/edges",
        json={"source_scene_id": scene_a_id, "target_scene_id": scene_b_id},
    )
    assert edge_resp.status_code == 201

    undo_resp = client.post(f"/books/{book_id}/undo")
    assert undo_resp.status_code == 200
    assert undo_resp.json()["action_type"] == "create_edge"

    delete_resp = client.delete(f"/scenes/{scene_b_id}")
    assert delete_resp.status_code == 204

    redo_resp = client.post(f"/books/{book_id}/redo")
    assert redo_resp.status_code != 500
    # Stale (fix #3) rather than a raw FK crash: the deleted-scene action is now this
    # Book's latest action, so there is nothing valid left to redo.
    assert redo_resp.status_code == 404


def test_redo_after_newer_action_on_same_book_is_404_not_reapplied(
    client: TestClient,
) -> None:
    """General-purpose coverage of reviewer fix #3 (not edge-specific): once a NEWER
    destructive action has happened for a Book since an earlier action was undone,
    ``redo_last_action`` must refuse to reapply that earlier action at all (404, same as
    "nothing to undone left to redo") rather than silently resurrecting something the user
    has since moved past. Mirrors ``get_undo_status``'s existing ``can_redo`` staleness
    check (``test_undo_status_redo_stale_after_newer_action``) but asserts the actual
    redo call, not just the status read.
    """
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    delete_a = client.delete(f"/scenes/{scene_a_id}")
    assert delete_a.status_code == 204

    undo_resp = client.post(f"/books/{book_id}/undo")
    assert undo_resp.status_code == 200
    assert undo_resp.json()["scene_id"] == scene_a_id

    # A newer destructive action for the SAME book — the undone delete of scene A is now
    # stale relative to this.
    delete_b = client.delete(f"/scenes/{scene_b_id}")
    assert delete_b.status_code == 204

    redo_resp = client.post(f"/books/{book_id}/redo")
    assert redo_resp.status_code == 404

    with SessionLocal() as db:
        # Scene A must still be restored (from the undo above) and NOT re-deleted by the
        # rejected redo attempt.
        assert db.get(Scene, scene_a_id) is not None
