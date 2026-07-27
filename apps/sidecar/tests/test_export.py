"""Tests for /books/{book_id}/export/{format}, /books/{book_id}/draft-versions, and
/draft-versions/{id}/download (docs/03-DATA-MODEL.md `draft_versions`, docs/06 Phase 6 task
BE-7).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB + drafts dir are used for this test run only — never touches a real
app-data directory. Scenarios are built entirely through the real endpoints, matching the
pattern in test_outline.py / test_continuity_tier1.py.
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


def _build_book_with_scene(
    client: TestClient, title: str, book_type: str = "story_book"
) -> str:
    book_id = _create_book(client, title, book_type)
    scene_id = _create_scene(client, f"{title} Scene", description="Something happened.")
    _add_to_canvas(client, book_id, scene_id)
    return book_id


def test_export_markdown_and_download(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Markdown Book")

    resp = client.post(f"/books/{book_id}/export/markdown")
    assert resp.status_code == 200
    body = resp.json()
    assert body["book_id"] == book_id
    assert body["format"] == "markdown"
    assert body["is_current"] is True
    assert body["version_number"] == 1
    draft_id = body["id"]

    download = client.get(f"/draft-versions/{draft_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/markdown")
    assert len(download.content) > 0
    text = download.content.decode("utf-8")
    assert "Markdown Book" in text


def test_export_docx_and_download(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Docx Book")

    resp = client.post(f"/books/{book_id}/export/docx")
    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "docx"
    draft_id = body["id"]

    download = client.get(f"/draft-versions/{draft_id}/download")
    assert download.status_code == 200
    assert download.content[:2] == b"PK"  # DOCX/ZIP magic


def test_export_pdf_and_download(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Pdf Book")

    resp = client.post(f"/books/{book_id}/export/pdf")
    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "pdf"
    draft_id = body["id"]

    download = client.get(f"/draft-versions/{draft_id}/download")
    assert download.status_code == 200
    assert download.content[:4] == b"%PDF"


def test_export_fountain_and_fdx_for_movie_script(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Screenplay Book", book_type="movie_script")

    fountain_resp = client.post(f"/books/{book_id}/export/fountain")
    assert fountain_resp.status_code == 200
    assert fountain_resp.json()["format"] == "fountain"

    fdx_resp = client.post(f"/books/{book_id}/export/fdx")
    assert fdx_resp.status_code == 200
    assert fdx_resp.json()["format"] == "fdx"


def test_export_fountain_rejected_for_prose_book(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Prose Book")

    resp = client.post(f"/books/{book_id}/export/fountain")
    assert resp.status_code == 422
    assert resp.json()["detail"] == "FORMAT_NOT_SUPPORTED_FOR_BOOK_TYPE"


def test_repeated_export_versions_and_current_flag(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Versioned Book")

    first = client.post(f"/books/{book_id}/export/markdown")
    assert first.status_code == 200
    second = client.post(f"/books/{book_id}/export/markdown")
    assert second.status_code == 200

    listing = client.get(f"/books/{book_id}/draft-versions")
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 2
    assert all(row["format_settings"]["format"] == "markdown" for row in rows)

    current_rows = [row for row in rows if row["is_current"]]
    assert len(current_rows) == 1
    assert current_rows[0]["id"] == second.json()["id"]

    version_numbers = sorted(row["version_number"] for row in rows)
    assert version_numbers[1] == version_numbers[0] + 1


def test_export_404_for_unknown_book(client: TestClient) -> None:
    resp = client.post("/books/does-not-exist/export/markdown")
    assert resp.status_code == 404

    listing = client.get("/books/does-not-exist/draft-versions")
    assert listing.status_code == 404


def test_download_404_for_bogus_draft_version(client: TestClient) -> None:
    resp = client.get("/draft-versions/does-not-exist/download")
    assert resp.status_code == 404
