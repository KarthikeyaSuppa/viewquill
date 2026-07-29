"""Tests for app.services.bundle_export — the `.quillproj` gather + zip step (docs/05-
EXPORT-IMPORT-SECURITY.md; Phase 7 task 3).

[SECURITY-REVIEW]: flagged for a later `reviewer` pass per CLAUDE.md — the hard invariant
under test here is UUID scoping: a second, unrelated Book's rows/scenes must never appear
in the first Book's bundle, and a missing asset file must produce a warning, never a crash
(both are data-integrity guarantees, not just features).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB + media dir are used for this test run only — never touches a real
app-data directory. Follows the same fixture pattern as tests/test_codex_arc_states.py
(module-scoped `client` fixture that runs the app's lifespan/migrations, plus direct
`SessionLocal` use for rows that have no dedicated write endpoint).
"""

from __future__ import annotations

import os
import tempfile
import zipfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-bundle-export-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

import base64  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services.bundle_export import (  # noqa: E402
    BundleExportError,
    build_zip_bytes,
    gather_bundle,
)


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


def _add_scene_to_book(client: TestClient, book_id: str, scene_id: str) -> None:
    resp = client.post(f"/books/{book_id}/scenes/{scene_id}", json={})
    assert resp.status_code == 201


def _create_entry(client: TestClient, name: str = "Character") -> str:
    resp = client.post("/codex", json={"entry_type": "character", "name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def _link_entry_to_book(client: TestClient, entry_id: str, book_id: str) -> None:
    resp = client.post(f"/codex/{entry_id}/books/{book_id}")
    assert resp.status_code == 201


_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _upload_png(client: TestClient) -> str:
    png_bytes = base64.b64decode(_PNG_B64)
    resp = client.post(
        "/images",
        params={"bucket": "reference_pool", "filename": "avatar.png"},
        content=png_bytes,
        headers={"Content-Type": "image/png"},
    )
    assert resp.status_code == 201
    return resp.json()["id"], resp.json()["storage_path"]


def _link_image_to_scene(client: TestClient, image_id: str, scene_id: str) -> None:
    resp = client.post(
        f"/images/{image_id}/links",
        json={"entity_type": "scene", "entity_id": scene_id},
    )
    assert resp.status_code == 201


@pytest.fixture(scope="module")
def two_books(client: TestClient) -> dict:
    """Book A (the one we export) with 2 scenes + 1 codex entry + 1 linked image, and an
    unrelated Book B with its own scene — proves UUID-scoped isolation."""
    book_a = _create_book(client, "Book A")
    scene_1 = _create_scene(client, "Scene One")
    scene_2 = _create_scene(client, "Scene Two")
    _add_scene_to_book(client, book_a, scene_1)
    _add_scene_to_book(client, book_a, scene_2)

    entry = _create_entry(client, "Hero")
    _link_entry_to_book(client, entry, book_a)

    image_id, storage_path = _upload_png(client)
    _link_image_to_scene(client, image_id, scene_1)

    book_b = _create_book(client, "Book B — unrelated")
    scene_b = _create_scene(client, "Scene B")
    _add_scene_to_book(client, book_b, scene_b)

    return {
        "book_a": book_a,
        "scene_1": scene_1,
        "scene_2": scene_2,
        "entry": entry,
        "image_id": image_id,
        "storage_path": storage_path,
        "book_b": book_b,
        "scene_b": scene_b,
    }


def test_gather_bundle_scopes_to_one_book_only(two_books: dict) -> None:
    with SessionLocal() as session:
        manifest, payload, asset_files = gather_bundle(
            session, two_books["book_a"], exported_at="2026-07-28T00:00:00+00:00"
        )

    assert manifest.book_id == two_books["book_a"]
    assert manifest.entity_counts["books"] == 1
    assert manifest.entity_counts["scenes"] == 2
    assert manifest.entity_counts["codex_entries"] == 1

    scene_ids_in_payload = {row["id"] for row in payload.scenes}
    assert scene_ids_in_payload == {two_books["scene_1"], two_books["scene_2"]}
    assert two_books["scene_b"] not in scene_ids_in_payload

    book_ids_in_payload = {row["id"] for row in payload.books}
    assert book_ids_in_payload == {two_books["book_a"]}

    # The linked image made it into the payload and its asset file was collected.
    image_ids_in_payload = {row["id"] for row in payload.images}
    assert two_books["image_id"] in image_ids_in_payload
    arcnames = {arcname for arcname, _ in asset_files}
    assert f"media/{two_books['storage_path']}" in arcnames

    assert manifest.asset_warnings == []


def test_gather_bundle_missing_book_raises() -> None:
    with SessionLocal() as session:
        with pytest.raises(BundleExportError):
            gather_bundle(session, "not-a-real-book-id", exported_at="2026-07-28T00:00:00+00:00")


def test_build_zip_bytes_produces_valid_zip_with_expected_entries(two_books: dict) -> None:
    with SessionLocal() as session:
        manifest, payload, asset_files = gather_bundle(
            session, two_books["book_a"], exported_at="2026-07-28T00:00:00+00:00"
        )
    zip_bytes = build_zip_bytes(manifest, payload, asset_files)

    buf = io.BytesIO(zip_bytes)
    assert zipfile.is_zipfile(buf)

    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "data/scenes.json" in names
        assert f"media/{two_books['storage_path']}" in names

        manifest_out = json.loads(zf.read("manifest.json"))
        assert manifest_out["book_id"] == two_books["book_a"]

        scenes_out = json.loads(zf.read("data/scenes.json"))
        assert {row["id"] for row in scenes_out} == {
            two_books["scene_1"],
            two_books["scene_2"],
        }


def test_missing_asset_file_produces_warning_not_a_crash(two_books: dict) -> None:
    """Deletes the linked image's on-disk file before gathering — the export must record
    a warning and simply omit that asset, never raise."""
    settings = get_settings()
    source = settings.media_dir / two_books["storage_path"]
    assert source.is_file()
    source.unlink()

    with SessionLocal() as session:
        manifest, payload, asset_files = gather_bundle(
            session, two_books["book_a"], exported_at="2026-07-28T00:00:00+00:00"
        )

    assert len(manifest.asset_warnings) == 1
    assert two_books["image_id"] in manifest.asset_warnings[0]
    arcnames = {arcname for arcname, _ in asset_files}
    assert f"media/{two_books['storage_path']}" not in arcnames

    # Still builds a valid zip — the missing asset is simply absent, not fatal.
    zip_bytes = build_zip_bytes(manifest, payload, asset_files)
    assert zipfile.is_zipfile(io.BytesIO(zip_bytes))
