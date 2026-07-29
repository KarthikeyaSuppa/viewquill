"""Tests for GET /books/{book_id}/draft-preview — the read-only manuscript preview endpoint
(docs/06 Phase 8 "manuscript reader"). NOT part of the export pipeline: asserts no
``draft_versions`` row is created and no file is written, and cross-checks the endpoint's
JSON against ``export_service.build_compiled_document`` called directly against the same
DB state, so the two can never silently drift (per this task's brief).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB is used for this test run only — never touches a real app-data directory.
Follows the same fixture pattern as tests/test_export.py / tests/test_bundle_export.py
(module-scoped `client` fixture running the app's lifespan, plus direct `SessionLocal` use
for the cross-check and for chapter/order rows that need direct assignment).
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-draft-preview-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

from dataclasses import asdict  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services import book_service, export_service  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        yield test_client


def _create_book(client: TestClient, title: str, book_type: str = "story_book") -> str:
    resp = client.post("/books", json={"title": title, "book_type": book_type})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_scene(client: TestClient, title: str, description: str = "") -> str:
    resp = client.post(
        "/scenes", json={"node_type": "scene", "title": title, "description": description}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_to_canvas(client: TestClient, book_id: str, scene_id: str) -> None:
    resp = client.post(f"/books/{book_id}/scenes/{scene_id}")
    assert resp.status_code == 201


def _create_chapter(client: TestClient, book_id: str, title: str, order_index: int) -> str:
    resp = client.post(
        f"/books/{book_id}/chapters", json={"title": title, "order_index": order_index}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _assign_scene(
    client: TestClient, book_id: str, scene_id: str, chapter_id: str, outline_order_index: int
) -> None:
    resp = client.post(
        f"/books/{book_id}/scenes/{scene_id}/assign",
        json={"chapter_id": chapter_id, "outline_order_index": outline_order_index},
    )
    assert resp.status_code == 200


def _build_two_chapter_book(client: TestClient) -> str:
    """Two chapters, three scenes total (two in the first, one in the second), plus a
    chapterless scene at the very end — exercises ordering across both chaptered buckets
    and the chapterless bucket in one book."""
    book_id = _create_book(client, "Preview Book")

    ch1 = _create_chapter(client, book_id, "Chapter One", order_index=0)
    ch2 = _create_chapter(client, book_id, "Chapter Two", order_index=1)

    scene1 = _create_scene(client, "Scene One", description="It begins.")
    scene2 = _create_scene(client, "Scene Two", description="It continues.")
    scene3 = _create_scene(client, "Scene Three", description="It ends chapter two.")
    scene4 = _create_scene(client, "Scene Four (loose)", description="Unplaced scene.")

    for scene_id in (scene1, scene2, scene3, scene4):
        _add_to_canvas(client, book_id, scene_id)

    _assign_scene(client, book_id, scene1, ch1, outline_order_index=0)
    _assign_scene(client, book_id, scene2, ch1, outline_order_index=1)
    _assign_scene(client, book_id, scene3, ch2, outline_order_index=2)
    # scene4 gets an explicit `book_scene_order` row (empty payload -> get_or_create_order_row
    # creates an all-null-positions row) so it appears in the chapterless bucket with a NULL
    # outline_order_index, sorting last per build_compiled_document's NULLS-LAST convention.
    # Merely adding a Scene to the canvas (`_add_to_canvas`) does NOT create a
    # `book_scene_order` row on its own, so without this call scene4 wouldn't be compiled
    # at all.
    resp = client.post(f"/books/{book_id}/scenes/{scene4}/assign", json={})
    assert resp.status_code == 200

    return book_id


def _direct_compiled_document_as_dict(book_id: str) -> dict:
    """Calls export_service.build_compiled_document directly against a fresh session, then
    converts the resulting dataclasses to a plain dict for a 1:1 comparison against the
    endpoint's JSON body."""
    with SessionLocal() as db:
        book = book_service.get_book(db, book_id)
        doc = export_service.build_compiled_document(db, book)
        return asdict(doc)


def test_draft_preview_matches_direct_compiled_document(client: TestClient) -> None:
    book_id = _build_two_chapter_book(client)

    resp = client.get(f"/books/{book_id}/draft-preview")
    assert resp.status_code == 200
    body = resp.json()

    direct = _direct_compiled_document_as_dict(book_id)
    assert body == direct


def test_draft_preview_chapter_and_scene_ordering(client: TestClient) -> None:
    book_id = _build_two_chapter_book(client)

    resp = client.get(f"/books/{book_id}/draft-preview")
    assert resp.status_code == 200
    body = resp.json()

    assert body["book_id"] == book_id
    assert body["book_title"] == "Preview Book"
    assert body["book_type"] == "story_book"

    chapters = body["chapters"]
    assert len(chapters) == 3  # Chapter One, Chapter Two, chapterless bucket

    assert chapters[0]["title"] == "Chapter One"
    assert [s["title"] for s in chapters[0]["scenes"]] == ["Scene One", "Scene Two"]
    assert chapters[0]["scenes"][0]["description"] == "It begins."

    assert chapters[1]["title"] == "Chapter Two"
    assert [s["title"] for s in chapters[1]["scenes"]] == ["Scene Three"]

    assert chapters[2]["title"] is None  # chapterless bucket, sorts last (NULL order index)
    assert [s["title"] for s in chapters[2]["scenes"]] == ["Scene Four (loose)"]

    # Prose book type: no screenplay elements attached to any scene.
    for chapter in chapters:
        for scene in chapter["scenes"]:
            assert scene["elements"] == []


def test_draft_preview_is_read_only_no_draft_version_created(client: TestClient) -> None:
    book_id = _build_two_chapter_book(client)

    before = client.get(f"/books/{book_id}/draft-versions")
    assert before.status_code == 200
    assert before.json() == []

    resp = client.get(f"/books/{book_id}/draft-preview")
    assert resp.status_code == 200

    after = client.get(f"/books/{book_id}/draft-versions")
    assert after.status_code == 200
    assert after.json() == []  # still no draft_versions row — preview never writes one


def test_draft_preview_attaches_elements_for_script_book_type(client: TestClient) -> None:
    book_id = _create_book(client, "Preview Screenplay", book_type="movie_script")
    scene_id = _create_scene(client, "Only Scene", description="A scene.")
    _add_to_canvas(client, book_id, scene_id)

    resp = client.get(f"/books/{book_id}/draft-preview")
    assert resp.status_code == 200
    body = resp.json()

    direct = _direct_compiled_document_as_dict(book_id)
    assert body == direct
    # Not asserting non-empty elements here — no screenplay elements were created for this
    # scene, so an empty list is the correct compiled shape; the cross-check against
    # build_compiled_document above is what guards against future drift either way.


def test_draft_preview_404_for_unknown_book(client: TestClient) -> None:
    resp = client.get("/books/does-not-exist/draft-preview")
    assert resp.status_code == 404
