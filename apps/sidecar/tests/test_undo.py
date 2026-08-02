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
from sqlalchemy import select  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.orm import SceneMerge, SceneRevision  # noqa: E402
from app.services import merge_service  # noqa: E402


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


# ── Delete/undo must not lose a scene's permanent revision/merge history ────────
def test_undo_restores_scene_revisions_and_scene_merges(client: TestClient) -> None:
    """A scene with SceneRevision history AND SceneMerge provenance, hard-deleted then
    undone, must come back with both intact — SceneRevision rows are ``ON DELETE CASCADE``
    (gone with the Scene, so undo must reinsert them) while SceneMerge rows are
    ``ON DELETE SET NULL`` (the row survives but its FK to this scene is nulled, so undo
    must restore that column instead of reinserting a row) — see
    ``scene_service._build_delete_undo_payload`` / ``undo_service._restore_delete_scene``.
    """
    book_resp = client.post("/books", json={"title": "History Undo Book", "book_type": "story_book"})
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
