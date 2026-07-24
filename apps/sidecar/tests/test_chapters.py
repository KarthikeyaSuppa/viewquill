"""Tests for Chapters CRUD (docs/03-DATA-MODEL.md `chapters`, docs/06 Phase 4 task BE-2).

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


def test_create_chapter_requires_existing_book(client: TestClient) -> None:
    resp = client.post("/books/does-not-exist/chapters", json={"title": "Chapter 1"})
    assert resp.status_code == 404


def test_create_chapter_requires_title(client: TestClient) -> None:
    book_id = _create_book(client, "Title Validation Book")
    resp = client.post(f"/books/{book_id}/chapters", json={})
    assert resp.status_code == 422


def test_chapters_crud_lifecycle(client: TestClient) -> None:
    book_id = _create_book(client, "Chapters Book")

    create_resp = client.post(f"/books/{book_id}/chapters", json={"title": "Chapter One"})
    assert create_resp.status_code == 201
    chapter = create_resp.json()
    chapter_id = chapter["id"]
    assert chapter["book_id"] == book_id
    assert chapter["title"] == "Chapter One"
    assert chapter["order_index"] == 0  # auto-appended, first chapter

    patch_resp = client.patch(f"/chapters/{chapter_id}", json={"title": "Chapter One Revised"})
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["title"] == "Chapter One Revised"
    assert patched["order_index"] == 0  # untouched field survives the partial update

    delete_resp = client.delete(f"/chapters/{chapter_id}")
    assert delete_resp.status_code == 204

    list_resp = client.get(f"/books/{book_id}/chapters")
    assert list_resp.status_code == 200
    assert all(c["id"] != chapter_id for c in list_resp.json())


def test_update_and_delete_missing_chapter_return_404(client: TestClient) -> None:
    assert client.patch("/chapters/does-not-exist", json={"title": "x"}).status_code == 404
    assert client.delete("/chapters/does-not-exist").status_code == 404


def test_list_chapters_ordered_and_auto_append(client: TestClient) -> None:
    book_id = _create_book(client, "Ordered Chapters Book")

    first = client.post(f"/books/{book_id}/chapters", json={"title": "First"})
    assert first.status_code == 201
    assert first.json()["order_index"] == 0

    second = client.post(f"/books/{book_id}/chapters", json={"title": "Second"})
    assert second.status_code == 201
    assert second.json()["order_index"] == 1

    # Explicit order_index is honored rather than auto-appended.
    explicit = client.post(
        f"/books/{book_id}/chapters", json={"title": "Inserted First", "order_index": 0}
    )
    assert explicit.status_code == 201
    assert explicit.json()["order_index"] == 0

    list_resp = client.get(f"/books/{book_id}/chapters")
    assert list_resp.status_code == 200
    titles_in_order = [c["title"] for c in list_resp.json()]
    # Two rows share order_index 0 — list is still deterministic-enough for this test:
    # both "Inserted First" and "First" precede "Second" in the returned order.
    assert titles_in_order.index("Second") > titles_in_order.index("First")
    assert titles_in_order.index("Second") > titles_in_order.index("Inserted First")

    # Next auto-append still continues from the current max (2), not affected by the
    # explicit order_index=0 insert above.
    third = client.post(f"/books/{book_id}/chapters", json={"title": "Third"})
    assert third.status_code == 201
    assert third.json()["order_index"] == 2


def test_chapters_scoped_per_book(client: TestClient) -> None:
    book_a = _create_book(client, "Book A")
    book_b = _create_book(client, "Book B")

    client.post(f"/books/{book_a}/chapters", json={"title": "A1"})
    client.post(f"/books/{book_b}/chapters", json={"title": "B1"})

    a_titles = {c["title"] for c in client.get(f"/books/{book_a}/chapters").json()}
    b_titles = {c["title"] for c in client.get(f"/books/{book_b}/chapters").json()}
    assert "A1" in a_titles and "B1" not in a_titles
    assert "B1" in b_titles and "A1" not in b_titles
