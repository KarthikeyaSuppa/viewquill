"""Tests for app.services.bundle_import's dry-run half — `inspect_bundle`/`read_bundle`
(docs/05-EXPORT-IMPORT-SECURITY.md; Phase 7 task 5).

[SECURITY-REVIEW]: flagged for a later `reviewer` pass per CLAUDE.md — the hard invariant
under test here is that `inspect_bundle` is READ-ONLY (never mutates the database) and
correctly classifies every row into exactly one of created/matched/conflicts, so the
future apply() step (task 6) has a trustworthy plan to act on.

Uses its own throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app),
same pattern as tests/test_bundle_export.py.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import zipfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-bundle-import-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

import io  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.orm import (  # noqa: E402
    Book,
    BookCodexLink,
    BookSceneLink,
    CodexEntry,
    EntityImage,
    Image,
    ImageTag,
    Scene,
)
from app.services.bundle_crypto import BundlePassphraseError, encrypt_bundle  # noqa: E402
from app.services.bundle_export import export_book_to_zip_bytes  # noqa: E402
from app.services.bundle_import import (  # noqa: E402
    BundleImportError,
    inspect_bundle,
    read_bundle,
)
from app.services.bundle_schema import BundleSchemaError  # noqa: E402

_PASSPHRASE = "correct horse battery staple"  # noqa: S105 -- test-only bundle passphrase, not a real secret


@pytest.fixture(scope="module")
def client():
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


def _upload_png(client: TestClient) -> tuple[str, str]:
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
def seeded_book(client: TestClient) -> dict:
    """One Book with 2 scenes, 1 codex entry, 1 linked image — everything gets exported."""
    book_id = _create_book(client, "Seeded Book")
    scene_1 = _create_scene(client, "Scene One")
    scene_2 = _create_scene(client, "Scene Two")
    _add_scene_to_book(client, book_id, scene_1)
    _add_scene_to_book(client, book_id, scene_2)

    entry = _create_entry(client, "Hero")
    _link_entry_to_book(client, entry, book_id)

    image_id, storage_path = _upload_png(client)
    _link_image_to_scene(client, image_id, scene_1)

    return {
        "book_id": book_id,
        "scene_1": scene_1,
        "scene_2": scene_2,
        "entry": entry,
        "image_id": image_id,
        "storage_path": storage_path,
    }


@pytest.fixture(scope="module")
def bundle_blob(seeded_book: dict) -> bytes:
    with SessionLocal() as session:
        zip_bytes, _manifest = export_book_to_zip_bytes(
            session, seeded_book["book_id"], exported_at="2026-07-28T00:00:00+00:00"
        )
    return encrypt_bundle(zip_bytes, _PASSPHRASE)


def test_inspect_same_db_everything_matched(bundle_blob: bytes) -> None:
    with SessionLocal() as session:
        report = inspect_bundle(session, bundle_blob, _PASSPHRASE)

    assert report.created == []
    assert report.conflicts == []
    assert len(report.matched) > 0
    # Book + 2 scenes + codex entry + image should all show up as matched.
    matched_tables = {change.table for change in report.matched}
    assert {"books", "scenes", "codex_entries", "images"} <= matched_tables


def test_inspect_one_mutated_scene_title_yields_one_conflict(
    seeded_book: dict, bundle_blob: bytes
) -> None:
    with SessionLocal() as session:
        scene = session.get(Scene, seeded_book["scene_1"])
        assert scene is not None
        scene.title = "Mutated Title — not what's in the bundle"
        session.commit()

    with SessionLocal() as session:
        report = inspect_bundle(session, bundle_blob, _PASSPHRASE)

    assert len(report.conflicts) == 1
    conflict = report.conflicts[0]
    assert conflict.table == "scenes"
    assert conflict.id == seeded_book["scene_1"]
    assert "title" in conflict.differing_fields

    # Everything else that was matched before is still matched now.
    matched_ids = {change.id for change in report.matched}
    assert seeded_book["scene_2"] in matched_ids
    assert seeded_book["book_id"] in matched_ids
    assert report.created == []

    # Revert so later tests see the original (matched) state again.
    with SessionLocal() as session:
        scene = session.get(Scene, seeded_book["scene_1"])
        assert scene is not None
        scene.title = "Scene One"
        session.commit()


def test_inspect_never_writes_to_the_database(seeded_book: dict, bundle_blob: bytes) -> None:
    with SessionLocal() as session:
        before = session.get(Scene, seeded_book["scene_1"])
        before_title = before.title

    with SessionLocal() as session:
        inspect_bundle(session, bundle_blob, _PASSPHRASE)

    with SessionLocal() as session:
        after = session.get(Scene, seeded_book["scene_1"])
        assert after.title == before_title


def test_inspect_empty_db_everything_created(seeded_book: dict, bundle_blob: bytes) -> None:
    """Wipes every row this Book's bundle touches, then inspects into the now-empty
    database — every entity in the bundle must show up as `created`."""
    with SessionLocal() as session:
        session.query(EntityImage).delete()
        session.query(ImageTag).delete()
        session.query(Image).delete()
        session.query(BookCodexLink).delete()
        session.query(CodexEntry).delete()
        session.query(BookSceneLink).delete()
        session.query(Scene).delete()
        session.query(Book).delete()
        session.commit()

    with SessionLocal() as session:
        report = inspect_bundle(session, bundle_blob, _PASSPHRASE)

    assert report.matched == []
    assert report.conflicts == []
    created_tables = {change.table for change in report.created}
    assert {"books", "scenes", "codex_entries", "images", "book_scene_links"} <= created_tables

    created_book_ids = {c.id for c in report.created if c.table == "books"}
    assert created_book_ids == {seeded_book["book_id"]}


def test_read_bundle_unsupported_schema_version_raises(bundle_blob: bytes) -> None:
    from app.services.bundle_crypto import decrypt_bundle

    plaintext = decrypt_bundle(bundle_blob, _PASSPHRASE)
    with zipfile.ZipFile(io.BytesIO(plaintext)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        names = zf.namelist()
        contents = {name: zf.read(name) for name in names}

    manifest["schema_version"] = 99
    contents["manifest.json"] = json.dumps(manifest).encode("utf-8")

    rebuilt = io.BytesIO()
    with zipfile.ZipFile(rebuilt, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in contents.items():
            zf.writestr(name, data)

    bad_blob = encrypt_bundle(rebuilt.getvalue(), _PASSPHRASE)

    with pytest.raises(BundleSchemaError):
        read_bundle(bad_blob, _PASSPHRASE)

    with SessionLocal() as session:
        with pytest.raises(BundleSchemaError):
            inspect_bundle(session, bad_blob, _PASSPHRASE)


def test_wrong_passphrase_raises_bundle_passphrase_error(bundle_blob: bytes) -> None:
    with pytest.raises(BundlePassphraseError):
        read_bundle(bundle_blob, "definitely the wrong passphrase")

    with SessionLocal() as session:
        with pytest.raises(BundlePassphraseError):
            inspect_bundle(session, bundle_blob, "definitely the wrong passphrase")


def test_corrupt_bundle_raises_bundle_import_error() -> None:
    not_a_zip = encrypt_bundle(b"this is not a zip file at all", _PASSPHRASE)
    with pytest.raises(BundleImportError):
        read_bundle(not_a_zip, _PASSPHRASE)
