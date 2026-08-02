"""Tests for AI-assisted multi-scene merge (Workstream B task 10, PHASE11.md) —
``merge_service.accept_merge`` and its ``undo_service`` wiring (``merge_scenes``
action_type, previously a ``NotImplementedError`` stub).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB is migrated to head for this test run only — never touches a real
app-data directory.

These tests exercise the service layer directly against ``app.db.base.SessionLocal``, the
same pattern ``test_scenes.py``'s revision-history tests already use for service-level
assertions alongside the HTTP-level ones.

Task 11's HTTP route, ``POST /llm/merge-scenes/accept`` (``api/llm.py``), is covered by the
route-level tests at the bottom of this file — it's a thin, non-streaming delegation to
this same ``merge_service.accept_merge``, so those tests confirm delegation + response
shape + error mapping rather than re-proving every invariant already proven above.
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
from app.models.orm import BookSceneLink, Scene, SceneMerge, SceneRevision, UndoLog  # noqa: E402
from app.services import merge_service, undo_service  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        yield test_client


def _make_book_with_two_linked_scenes(client: TestClient) -> tuple[str, str, str]:
    """Creates a Book and two Scenes, each linked onto its canvas at a distinct position.

    Returns (book_id, scene_a_id, scene_b_id).
    """
    book_resp = client.post("/books", json={"title": "Merge Book", "book_type": "story_book"})
    assert book_resp.status_code == 201
    book_id = book_resp.json()["id"]

    scene_a_resp = client.post(
        "/scenes",
        json={"node_type": "scene", "title": "Scene A", "description": "Alpha prose."},
    )
    assert scene_a_resp.status_code == 201
    scene_a_id = scene_a_resp.json()["id"]

    scene_b_resp = client.post(
        "/scenes",
        json={"node_type": "scene", "title": "Scene B", "description": "Beta prose."},
    )
    assert scene_b_resp.status_code == 201
    scene_b_id = scene_b_resp.json()["id"]

    link_a = client.post(
        f"/books/{book_id}/scenes/{scene_a_id}",
        json={"canvas_x": 0, "canvas_y": 0, "color": "#a1a1a1"},
    )
    assert link_a.status_code == 201

    link_b = client.post(
        f"/books/{book_id}/scenes/{scene_b_id}",
        json={"canvas_x": 100, "canvas_y": 200, "color": "#b2b2b2"},
    )
    assert link_b.status_code == 201

    return book_id, scene_a_id, scene_b_id


def test_accept_merge_creates_scene_revision_merges_and_archives_sources(
    client: TestClient,
) -> None:
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    with SessionLocal() as db:
        merged = merge_service.accept_merge(
            db,
            book_id=book_id,
            source_scene_ids=[scene_a_id, scene_b_id],
            merged_title="Merged Scene",
            merged_description="Combined alpha and beta prose.",
        )
        merged_id = merged.id
        assert merged.title == "Merged Scene"
        assert merged.description == "Combined alpha and beta prose."
        assert merged.node_type == "scene"

    with SessionLocal() as db:
        # Exactly one SceneRevision, revision 1, ai_merge, matching the merged content.
        revisions = list(
            db.execute(
                select(SceneRevision).where(SceneRevision.scene_id == merged_id)
            ).scalars()
        )
        assert len(revisions) == 1
        assert revisions[0].revision_number == 1
        assert revisions[0].change_source == "ai_merge"
        assert revisions[0].title == "Merged Scene"
        assert revisions[0].description == "Combined alpha and beta prose."

        # Two SceneMerge rows, one per source, with frozen pre-merge snapshots.
        merges = list(
            db.execute(
                select(SceneMerge).where(SceneMerge.merged_scene_id == merged_id)
            ).scalars()
        )
        assert len(merges) == 2
        by_source = {m.source_scene_id: m for m in merges}
        assert by_source[scene_a_id].source_snapshot_title == "Scene A"
        assert by_source[scene_a_id].source_snapshot_description == "Alpha prose."
        assert by_source[scene_b_id].source_snapshot_title == "Scene B"
        assert by_source[scene_b_id].source_snapshot_description == "Beta prose."

        # Both sources' Scene rows still exist, completely untouched.
        source_a = db.get(Scene, scene_a_id)
        source_b = db.get(Scene, scene_b_id)
        assert source_a is not None and source_a.title == "Scene A"
        assert source_b is not None and source_b.title == "Scene B"

        # Both sources' BookSceneLinks are archived.
        link_a = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == scene_a_id
            )
        ).scalar_one()
        link_b = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == scene_b_id
            )
        ).scalar_one()
        assert link_a.archived_at is not None
        assert link_b.archived_at is not None

        # New merged scene has a non-archived link at the sources' midpoint (0,0)/(100,200).
        merged_link = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == merged_id
            )
        ).scalar_one()
        assert merged_link.archived_at is None
        assert merged_link.canvas_x == 50
        assert merged_link.canvas_y == 100

        # One UndoLog row, merge_scenes, not yet undone.
        undo_rows = list(
            db.execute(
                select(UndoLog).where(
                    UndoLog.book_id == book_id, UndoLog.action_type == "merge_scenes"
                )
            ).scalars()
        )
        assert len(undo_rows) == 1
        assert undo_rows[0].undone_at is None
        assert undo_rows[0].payload["merged_scene_id"] == merged_id


def test_undo_then_redo_merge_toggles_links_without_deleting_merged_scene(
    client: TestClient,
) -> None:
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    with SessionLocal() as db:
        merged = merge_service.accept_merge(
            db,
            book_id=book_id,
            source_scene_ids=[scene_a_id, scene_b_id],
            merged_title="Merged For Undo",
            merged_description="Merged prose.",
        )
        merged_id = merged.id

    # Undo: sources un-archived at their exact original positions, merged link archived.
    with SessionLocal() as db:
        undo_log = undo_service.undo_last_action(db, book_id)
        assert undo_log is not None
        assert undo_log.action_type == "merge_scenes"
        assert undo_log.undone_at is not None

    with SessionLocal() as db:
        link_a = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == scene_a_id
            )
        ).scalar_one()
        link_b = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == scene_b_id
            )
        ).scalar_one()
        assert link_a.archived_at is None
        assert link_a.canvas_x == 0
        assert link_a.canvas_y == 0
        assert link_a.color == "#a1a1a1"
        assert link_b.archived_at is None
        assert link_b.canvas_x == 100
        assert link_b.canvas_y == 200
        assert link_b.color == "#b2b2b2"

        merged_link = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == merged_id
            )
        ).scalar_one()
        assert merged_link.archived_at is not None

        # The merged Scene row itself still exists — undo is soft/reversible, not a delete.
        merged_scene = db.get(Scene, merged_id)
        assert merged_scene is not None
        assert merged_scene.title == "Merged For Undo"

    # Redo: re-applies — sources re-archived, merged scene's link un-archived again.
    with SessionLocal() as db:
        redo_log = undo_service.redo_last_action(db, book_id)
        assert redo_log is not None
        assert redo_log.action_type == "merge_scenes"
        assert redo_log.undone_at is None

    with SessionLocal() as db:
        link_a = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == scene_a_id
            )
        ).scalar_one()
        link_b = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == scene_b_id
            )
        ).scalar_one()
        assert link_a.archived_at is not None
        assert link_b.archived_at is not None

        merged_link = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == merged_id
            )
        ).scalar_one()
        assert merged_link.archived_at is None

        merged_scene = db.get(Scene, merged_id)
        assert merged_scene is not None


def test_merge_with_unknown_source_fails_with_no_partial_writes(client: TestClient) -> None:
    book_id, scene_a_id, _scene_b_id = _make_book_with_two_linked_scenes(client)

    with SessionLocal() as db:
        scene_count_before = db.execute(select(Scene)).scalars().all()
        merge_count_before = db.execute(select(SceneMerge)).scalars().all()
        undo_count_before = db.execute(select(UndoLog)).scalars().all()

    with SessionLocal() as db:
        with pytest.raises(ValueError, match="SCENE_NOT_FOUND"):
            merge_service.accept_merge(
                db,
                book_id=book_id,
                source_scene_ids=[scene_a_id, "does-not-exist"],
                merged_title="Should Never Exist",
                merged_description="Should never be written.",
            )
        db.rollback()

    with SessionLocal() as db:
        scene_count_after = db.execute(select(Scene)).scalars().all()
        merge_count_after = db.execute(select(SceneMerge)).scalars().all()
        undo_count_after = db.execute(select(UndoLog)).scalars().all()

    assert len(scene_count_after) == len(scene_count_before)
    assert len(merge_count_after) == len(merge_count_before)
    assert len(undo_count_after) == len(undo_count_before)
    assert not any(s.title == "Should Never Exist" for s in scene_count_after)


def test_merge_requires_book_and_nonempty_sources(client: TestClient) -> None:
    book_id, scene_a_id, _scene_b_id = _make_book_with_two_linked_scenes(client)

    with SessionLocal() as db:
        with pytest.raises(ValueError, match="BOOK_NOT_FOUND"):
            merge_service.accept_merge(
                db,
                book_id="does-not-exist",
                source_scene_ids=[scene_a_id],
                merged_title="x",
                merged_description="y",
            )
        db.rollback()

    with SessionLocal() as db:
        with pytest.raises(ValueError, match="SOURCE_SCENES_REQUIRED"):
            merge_service.accept_merge(
                db,
                book_id=book_id,
                source_scene_ids=[],
                merged_title="x",
                merged_description="y",
            )
        db.rollback()


def test_merge_source_scene_not_linked_to_book_fails(client: TestClient) -> None:
    book_id, scene_a_id, _scene_b_id = _make_book_with_two_linked_scenes(client)

    unlinked_resp = client.post(
        "/scenes",
        json={"node_type": "scene", "title": "Never Linked", "description": "orphan"},
    )
    assert unlinked_resp.status_code == 201
    unlinked_scene_id = unlinked_resp.json()["id"]

    with SessionLocal() as db:
        with pytest.raises(ValueError, match="SCENE_NOT_IN_BOOK"):
            merge_service.accept_merge(
                db,
                book_id=book_id,
                source_scene_ids=[scene_a_id, unlinked_scene_id],
                merged_title="x",
                merged_description="y",
            )
        db.rollback()


def test_hard_deleting_source_scene_after_merge_keeps_scene_merge_row(
    client: TestClient,
) -> None:
    """Opus reviewer MUST-FIX 1 regression: ``SceneMerge.source_scene_id`` used to be
    ``ondelete='CASCADE'``, so hard-deleting a source Scene (via the ordinary
    ``DELETE /scenes/{id}`` path — sources are meant to survive a merge as ordinary scenes)
    also deleted the ``SceneMerge`` row recording it, destroying exactly the frozen-snapshot
    history ``SceneMerge``'s own docstring says survives a source's hard-delete. The FK is
    now ``ondelete='SET NULL'`` — the row must survive with ``source_scene_id`` nulled out
    and its snapshot columns untouched.

    Deletes the Scene row directly (a plain ``db.delete``/commit) rather than going through
    ``scene_service.delete_scene``/``DELETE /scenes/{id}``: the FK's ``ondelete`` behavior is
    enforced by SQLite itself regardless of which code path issues the delete, and going
    around the service here avoids also writing a ``delete_scene`` ``UndoLog`` row that would
    collide with ``test_scenes.py``'s own single-row assertion on that same shared test DB.
    """
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    with SessionLocal() as db:
        merged = merge_service.accept_merge(
            db,
            book_id=book_id,
            source_scene_ids=[scene_a_id, scene_b_id],
            merged_title="Merged For Hard Delete",
            merged_description="Combined prose.",
        )
        merged_id = merged.id

    # Hard-delete source A's Scene row directly — exercises the same FK ``ondelete`` SQLite
    # enforces on any delete of this row, without going through the full delete_scene service.
    with SessionLocal() as db:
        scene_a = db.get(Scene, scene_a_id)
        db.delete(scene_a)
        db.commit()

    with SessionLocal() as db:
        assert db.get(Scene, scene_a_id) is None

        merge_row = db.execute(
            select(SceneMerge).where(
                SceneMerge.merged_scene_id == merged_id,
                SceneMerge.source_snapshot_title == "Scene A",
            )
        ).scalar_one()
        assert merge_row.source_scene_id is None
        assert merge_row.source_snapshot_title == "Scene A"
        assert merge_row.source_snapshot_description == "Alpha prose."

        # The other source's SceneMerge row is untouched.
        other_row = db.execute(
            select(SceneMerge).where(
                SceneMerge.merged_scene_id == merged_id,
                SceneMerge.source_scene_id == scene_b_id,
            )
        ).scalar_one()
        assert other_row.source_snapshot_title == "Scene B"


def test_undo_raises_when_expected_book_scene_link_is_missing(client: TestClient) -> None:
    """Opus reviewer MUST-FIX 2 regression: undo/redo used to silently skip restoring a
    ``BookSceneLink`` that no longer exists (e.g. removed via the ordinary canvas-remove
    path since the merge), reporting success even though the restoration was incomplete.
    It must now raise instead.
    """
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    with SessionLocal() as db:
        merge_service.accept_merge(
            db,
            book_id=book_id,
            source_scene_ids=[scene_a_id, scene_b_id],
            merged_title="Merged For Missing Link",
            merged_description="Combined prose.",
        )

    # Hard-delete source A's (now-archived) BookSceneLink directly, simulating it having
    # been removed via some other path in the meantime — undo still expects to find it.
    with SessionLocal() as db:
        link_a = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == scene_a_id
            )
        ).scalar_one()
        db.delete(link_a)
        db.commit()

    with SessionLocal() as db:
        with pytest.raises(ValueError, match="UNDO_TARGET_ROW_MISSING"):
            undo_service.undo_last_action(db, book_id)
        db.rollback()

    # The UndoLog entry must still be un-undone — the failed attempt didn't get marked done.
    with SessionLocal() as db:
        undo_rows = list(
            db.execute(
                select(UndoLog).where(
                    UndoLog.book_id == book_id, UndoLog.action_type == "merge_scenes"
                )
            ).scalars()
        )
        assert len(undo_rows) == 1
        assert undo_rows[0].undone_at is None


# ── POST /llm/merge-scenes/accept (Workstream B task 11, PHASE11.md) ──────────────
# Thin, non-streaming route delegating to the same `merge_service.accept_merge` proven
# above — these tests confirm delegation + response shape + error mapping, not every
# invariant already covered by the service-level tests.


def test_accept_route_creates_merged_scene_and_returns_canvas_node(client: TestClient) -> None:
    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    resp = client.post(
        "/llm/merge-scenes/accept",
        json={
            "book_id": book_id,
            "source_scene_ids": [scene_a_id, scene_b_id],
            "merged_title": "Route Merged Scene",
            "merged_description": "Combined via the HTTP route.",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    node = body["node"]
    assert node["title"] == "Route Merged Scene"
    assert node["description"] == "Combined via the HTTP route."
    assert node["node_type"] == "scene"
    assert node["canvas_x"] == 50
    assert node["canvas_y"] == 100
    assert node["link_id"]
    assert node["scene_id"]

    # DB state matches what the direct service-level test already proves in detail —
    # here just confirm the route's write actually landed (revision + sources archived).
    with SessionLocal() as db:
        merged_scene = db.get(Scene, node["scene_id"])
        assert merged_scene is not None
        assert merged_scene.title == "Route Merged Scene"

        revisions = list(
            db.execute(
                select(SceneRevision).where(SceneRevision.scene_id == node["scene_id"])
            ).scalars()
        )
        assert len(revisions) == 1
        assert revisions[0].change_source == "ai_merge"

        link_a = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == scene_a_id
            )
        ).scalar_one()
        link_b = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id, BookSceneLink.scene_id == scene_b_id
            )
        ).scalar_one()
        assert link_a.archived_at is not None
        assert link_b.archived_at is not None

        merged_link = db.get(BookSceneLink, node["link_id"])
        assert merged_link is not None
        assert merged_link.archived_at is None


def test_accept_route_unknown_source_scene_returns_404(client: TestClient) -> None:
    book_id, scene_a_id, _scene_b_id = _make_book_with_two_linked_scenes(client)

    resp = client.post(
        "/llm/merge-scenes/accept",
        json={
            "book_id": book_id,
            "source_scene_ids": [scene_a_id, "does-not-exist"],
            "merged_title": "x",
            "merged_description": "y",
        },
    )
    # SCENE_NOT_FOUND -> 404 per _handle_value_error's mapping (mirrors api/outline.py).
    assert resp.status_code == 404


def test_accept_route_scene_not_in_book_returns_422(client: TestClient) -> None:
    book_id, scene_a_id, _scene_b_id = _make_book_with_two_linked_scenes(client)

    unlinked_resp = client.post(
        "/scenes",
        json={"node_type": "scene", "title": "Route Never Linked", "description": "orphan"},
    )
    assert unlinked_resp.status_code == 201
    unlinked_scene_id = unlinked_resp.json()["id"]

    resp = client.post(
        "/llm/merge-scenes/accept",
        json={
            "book_id": book_id,
            "source_scene_ids": [scene_a_id, unlinked_scene_id],
            "merged_title": "x",
            "merged_description": "y",
        },
    )
    assert resp.status_code == 422


def test_accept_route_missing_book_returns_404(client: TestClient) -> None:
    _book_id, scene_a_id, _scene_b_id = _make_book_with_two_linked_scenes(client)

    resp = client.post(
        "/llm/merge-scenes/accept",
        json={
            "book_id": "does-not-exist",
            "source_scene_ids": [scene_a_id],
            "merged_title": "x",
            "merged_description": "y",
        },
    )
    assert resp.status_code == 404


def test_accept_route_empty_sources_returns_422(client: TestClient) -> None:
    book_id, _scene_a_id, _scene_b_id = _make_book_with_two_linked_scenes(client)

    resp = client.post(
        "/llm/merge-scenes/accept",
        json={
            "book_id": book_id,
            "source_scene_ids": [],
            "merged_title": "x",
            "merged_description": "y",
        },
    )
    # Pydantic's Field(min_length=1) rejects the empty list before the route body even
    # runs, so this is FastAPI's own 422 validation error, not `_handle_value_error`'s.
    assert resp.status_code == 422


def test_accept_route_never_calls_llm_and_ignores_stub_flag(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves this route is a pure DB write with no LLM/streaming path at all: it must
    succeed identically whether or not `QUILLNIGHT_LLM_STUB` is set, since `accept_merge`
    never calls `llm_orchestrator.get_provider_client()`. If this route accidentally grew a
    provider call, removing the stub flag here would make it try (and fail/hang on) a real
    Ollama/Groq call on this build machine (CLAUDE.md "no real AI testing here")."""
    monkeypatch.delenv("QUILLNIGHT_LLM_STUB", raising=False)

    book_id, scene_a_id, scene_b_id = _make_book_with_two_linked_scenes(client)

    resp = client.post(
        "/llm/merge-scenes/accept",
        json={
            "book_id": book_id,
            "source_scene_ids": [scene_a_id, scene_b_id],
            "merged_title": "No Stub Needed",
            "merged_description": "Still just a DB write.",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["node"]["title"] == "No Stub Needed"
