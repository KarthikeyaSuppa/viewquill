"""Tests for POST /import/quillproj/inspect and POST /import/quillproj/apply
(docs/05-EXPORT-IMPORT-SECURITY.md; docs/06 Phase 7 task 7).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB + media dir are used for this test run only. Follows the same fixture
pattern as test_import_export_endpoint.py.

Both import endpoints take the encrypted bundle as the RAW request body (no
python-multipart dependency — see app/api/import_export.py's module docstring) and the
passphrase via the `X-Quillnight-Passphrase` header, never a query parameter or JSON body
field, so it never ends up in an access log.
"""

from __future__ import annotations

import json
import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-import-endpoints-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSPHRASE = "correct-horse-battery"  # noqa: S105 -- test fixture value, not a real secret


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


def _export_bundle(client: TestClient, book_id: str, passphrase: str = PASSPHRASE) -> bytes:
    resp = client.post(f"/books/{book_id}/export/bundle", json={"passphrase": passphrase})
    assert resp.status_code == 200
    return resp.content


def _inspect(client: TestClient, data: bytes, passphrase: str):
    return client.post(
        "/import/quillproj/inspect",
        content=data,
        headers={"X-Quillnight-Passphrase": passphrase},
    )


def _apply(client: TestClient, data: bytes, passphrase: str, resolutions: dict | None = None):
    params = {}
    if resolutions is not None:
        params["resolutions"] = json.dumps(resolutions)
    return client.post(
        "/import/quillproj/apply",
        content=data,
        headers={"X-Quillnight-Passphrase": passphrase},
        params=params,
    )


def test_inspect_correct_passphrase_reports_matched(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Inspect Matched Book")
    data = _export_bundle(client, book_id)

    resp = _inspect(client, data, PASSPHRASE)
    assert resp.status_code == 200
    report = resp.json()
    assert report["book_id"] == book_id
    assert report["conflicts"] == []
    # Nothing was deleted first, so re-inspecting the just-exported bundle against the
    # unchanged database reports everything as already-matched, nothing created.
    assert report["created"] == []
    matched_tables = {row["table"] for row in report["matched"]}
    assert "books" in matched_tables
    assert "scenes" in matched_tables


def test_inspect_wrong_passphrase_is_400(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Inspect Wrong Passphrase Book")
    data = _export_bundle(client, book_id)

    resp = _inspect(client, data, "totally-wrong-passphrase")
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_inspect_missing_passphrase_header_is_400(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Inspect No Header Book")
    data = _export_bundle(client, book_id)

    resp = client.post("/import/quillproj/inspect", content=data)
    assert resp.status_code == 400


def test_apply_restores_deleted_book(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Restore Me Book")
    data = _export_bundle(client, book_id)

    delete_resp = client.delete(f"/books/{book_id}")
    assert delete_resp.status_code == 204
    assert client.get(f"/books/{book_id}").status_code == 404

    resp = _apply(client, data, PASSPHRASE, resolutions={})
    assert resp.status_code == 200
    report = resp.json()
    assert report["book_id"] == book_id

    get_resp = client.get(f"/books/{book_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == book_id
    assert get_resp.json()["title"] == "Restore Me Book"


def test_apply_reimport_unchanged_db_is_idempotent(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Idempotent Reimport Book")
    data = _export_bundle(client, book_id)

    first = _apply(client, data, PASSPHRASE, resolutions={})
    assert first.status_code == 200
    first_report = first.json()
    link_created_count = sum(
        1 for row in first_report["created"] if row["table"] == "book_scene_links"
    )
    assert link_created_count == 0  # link already existed before this apply call

    second = _apply(client, data, PASSPHRASE, resolutions={})
    assert second.status_code == 200
    second_report = second.json()
    # Re-importing into an unchanged database creates nothing new and reports everything
    # as already-matched (no duplicate book_scene_links row from the natural-key dedup).
    assert second_report["created"] == []
    assert second_report["conflicts"] == []
    link_matched_count = sum(
        1 for row in second_report["matched"] if row["table"] == "book_scene_links"
    )
    assert link_matched_count == 1


def test_apply_malformed_resolutions_is_422(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Malformed Resolutions Book")
    data = _export_bundle(client, book_id)

    resp = client.post(
        "/import/quillproj/apply",
        content=data,
        headers={"X-Quillnight-Passphrase": PASSPHRASE},
        params={"resolutions": "not-json"},
    )
    assert resp.status_code == 422


def test_apply_wrong_passphrase_is_400_and_writes_nothing(client: TestClient) -> None:
    book_id = _build_book_with_scene(client, "Apply Wrong Passphrase Book")
    data = _export_bundle(client, book_id)

    delete_resp = client.delete(f"/books/{book_id}")
    assert delete_resp.status_code == 204

    resp = _apply(client, data, "totally-wrong-passphrase", resolutions={})
    assert resp.status_code == 400

    # Nothing was restored -- the failed decrypt must never partially apply.
    assert client.get(f"/books/{book_id}").status_code == 404
