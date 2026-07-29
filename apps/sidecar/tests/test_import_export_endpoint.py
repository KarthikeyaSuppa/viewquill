"""Tests for POST /books/{book_id}/export/bundle (docs/05-EXPORT-IMPORT-SECURITY.md;
docs/06 Phase 7 task 4).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB + media dir are used for this test run only — never touches a real
app-data directory. Follows the same fixture pattern as test_export.py / test_bundle_export.py.
"""

from __future__ import annotations

import os
import tempfile
import zipfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-import-export-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

import io  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.bundle_crypto import decrypt_bundle  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        yield test_client


def _create_book(client: TestClient, title: str = "Bundle Book") -> str:
    resp = client.post("/books", json={"title": title, "book_type": "story_book"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_scene(client: TestClient, title: str = "Scene") -> str:
    resp = client.post("/scenes", json={"node_type": "scene", "title": title})
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_scene_to_book(client: TestClient, book_id: str, scene_id: str) -> None:
    resp = client.post(f"/books/{book_id}/scenes/{scene_id}", json={})
    assert resp.status_code == 201


def _build_book_with_scene(client: TestClient, title: str = "Bundle Book") -> str:
    book_id = _create_book(client, title)
    scene_id = _create_scene(client, f"{title} Scene")
    _add_scene_to_book(client, book_id, scene_id)
    return book_id


def test_export_bundle_round_trips(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "My Great Novel!!")

    resp = client.post(
        f"/books/{book_id}/export/bundle", json={"passphrase": "correct-horse-battery"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/octet-stream"
    disposition = resp.headers["content-disposition"]
    assert disposition.endswith('.quillproj"')

    plaintext = decrypt_bundle(resp.content, "correct-horse-battery")
    buffer = io.BytesIO(plaintext)
    assert zipfile.is_zipfile(buffer)
    with zipfile.ZipFile(buffer) as zf:
        assert "manifest.json" in zf.namelist()


def test_export_bundle_rejects_short_passphrase(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Short Passphrase Book")

    resp = client.post(f"/books/{book_id}/export/bundle", json={"passphrase": "short"})
    assert resp.status_code == 422


def test_export_bundle_404_for_unknown_book(client: TestClient) -> None:
    resp = client.post(
        "/books/does-not-exist/export/bundle", json={"passphrase": "correct-horse-battery"}
    )
    assert resp.status_code == 404
