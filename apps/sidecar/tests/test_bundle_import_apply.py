"""Tests for app.services.bundle_import's APPLY half — `apply_import` (docs/05-EXPORT-
IMPORT-SECURITY.md; Phase 7 task 6).

[SECURITY-REVIEW]: flagged for a later `reviewer` pass per CLAUDE.md — `apply_import` is
the ONLY writer in the whole import path. The invariants under test:
* full restore round-trips every table + on-disk asset, under the SAME UUIDs;
* re-importing into an unchanged database creates ZERO duplicate rows, especially for the
  join/association tables (the anti-duplication trap this task exists to fix);
* a same-PK conflict with no resolution supplied defaults to `keep_local` (never a silent
  overwrite);
* `take_imported` and `merge` behave exactly as specified (merge only fills local gaps);
* any failure mid-apply rolls back the WHOLE transaction — no partial writes.

Uses its own throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app),
same pattern as tests/test_bundle_import_inspect.py.
"""

from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import zipfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-bundle-apply-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.orm import (  # noqa: E402
    Book,
    BookCodexLink,
    BookSceneLink,
    BookSceneOrder,
    CodexEntry,
    EntityImage,
    Image,
    ImageTag,
    Scene,
)
from app.services.bundle_crypto import encrypt_bundle  # noqa: E402
from app.services.bundle_export import export_book_to_zip_bytes  # noqa: E402
from app.services.bundle_import import BundleImportError, apply_import  # noqa: E402

_PASSPHRASE = "correct horse battery staple"  # noqa: S105 -- test-only bundle passphrase, not a real secret


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _create_book(client: TestClient, title: str = "Book") -> str:
    resp = client.post("/books", json={"title": title, "book_type": "story_book"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_scene(client: TestClient, title: str = "Scene", description: str | None = None) -> str:
    body = {"node_type": "scene", "title": title}
    if description is not None:
        body["description"] = description
    resp = client.post("/scenes", json=body)
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


def _build_seeded_book(client: TestClient, title: str) -> dict:
    """One Book with 2 scenes, 1 codex entry (linked), 1 image (linked to a scene, with a
    real on-disk file) — everything a bundle can carry, per the task's test #1."""
    book_id = _create_book(client, title)
    scene_1 = _create_scene(client, "Scene One", description="original description")
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


def _row_counts(session) -> dict[str, int]:
    counts = {}
    for model in (
        Book,
        Scene,
        CodexEntry,
        BookSceneLink,
        BookCodexLink,
        EntityImage,
        Image,
        ImageTag,
    ):
        counts[model.__tablename__] = session.execute(
            select(model)
        ).scalars().all().__len__()
    return counts


# ── Test 1: full restore ──────────────────────────────────────────────────────


def test_full_restore_same_uuids_and_asset_refile() -> None:
    with TestClient(app) as client:
        seeded = _build_seeded_book(client, "Restore Me")

    with SessionLocal() as session:
        zip_bytes, _manifest = export_book_to_zip_bytes(
            session, seeded["book_id"], exported_at="2026-07-28T00:00:00+00:00"
        )
    blob = encrypt_bundle(zip_bytes, _PASSPHRASE)

    settings = get_settings()
    image_file = settings.media_dir / seeded["storage_path"]
    assert image_file.is_file()

    # Delete the book and everything that hangs off it (mirrors a real "restore after
    # data loss" scenario), including the on-disk image file.
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
    image_file.unlink()
    assert not image_file.is_file()

    with SessionLocal() as session:
        report = apply_import(session, blob, _PASSPHRASE, {})
        session.commit()

    assert report.conflicts == []
    created_ids = {c.id for c in report.created}
    assert seeded["book_id"] in created_ids
    assert seeded["scene_1"] in created_ids
    assert seeded["scene_2"] in created_ids
    assert seeded["entry"] in created_ids
    assert seeded["image_id"] in created_ids

    with SessionLocal() as session:
        book = session.get(Book, seeded["book_id"])
        assert book is not None
        assert book.id == seeded["book_id"]

        scene_1 = session.get(Scene, seeded["scene_1"])
        assert scene_1 is not None and scene_1.id == seeded["scene_1"]

        entry = session.get(CodexEntry, seeded["entry"])
        assert entry is not None and entry.id == seeded["entry"]

        book_scene_links = session.execute(
            select(BookSceneLink).where(BookSceneLink.book_id == seeded["book_id"])
        ).scalars().all()
        assert len(book_scene_links) == 2  # exactly once each, not duplicated

        book_codex_links = session.execute(
            select(BookCodexLink).where(BookCodexLink.book_id == seeded["book_id"])
        ).scalars().all()
        assert len(book_codex_links) == 1

        entity_images = session.execute(
            select(EntityImage).where(EntityImage.image_id == seeded["image_id"])
        ).scalars().all()
        assert len(entity_images) == 1

    assert image_file.is_file()


# ── Test 2: re-import into an UNCHANGED db creates zero duplicates ───────────


def test_reimport_unchanged_db_creates_zero_duplicates() -> None:
    with TestClient(app) as client:
        seeded = _build_seeded_book(client, "No Duplicates")

    with SessionLocal() as session:
        zip_bytes, _manifest = export_book_to_zip_bytes(
            session, seeded["book_id"], exported_at="2026-07-28T00:00:00+00:00"
        )
    blob = encrypt_bundle(zip_bytes, _PASSPHRASE)

    with SessionLocal() as session:
        before = _row_counts(session)

    with SessionLocal() as session:
        report = apply_import(session, blob, _PASSPHRASE, {})
        session.commit()

    # Nothing was "created" — every row in the bundle already exists locally, unchanged.
    assert report.created == []
    assert report.conflicts == []

    with SessionLocal() as session:
        after = _row_counts(session)

    assert before == after, f"row counts changed on a no-op re-import: {before} -> {after}"


# ── Test 3/4/5: conflict resolution (keep_local default, take_imported, merge) ─


@pytest.fixture()
def conflict_fixture():
    with TestClient(app) as client:
        seeded = _build_seeded_book(client, "Conflict Fixture")

    with SessionLocal() as session:
        zip_bytes, _manifest = export_book_to_zip_bytes(
            session, seeded["book_id"], exported_at="2026-07-28T00:00:00+00:00"
        )
    blob = encrypt_bundle(zip_bytes, _PASSPHRASE)
    return seeded, blob


def test_keep_local_is_the_default_when_resolution_absent(conflict_fixture) -> None:
    seeded, blob = conflict_fixture

    with SessionLocal() as session:
        scene = session.get(Scene, seeded["scene_1"])
        scene.title = "Locally mutated title"
        session.commit()

    with SessionLocal() as session:
        report = apply_import(session, blob, _PASSPHRASE, {})  # no resolutions supplied
        session.commit()

    assert len(report.conflicts) == 1
    assert report.conflicts[0].id == seeded["scene_1"]

    with SessionLocal() as session:
        scene = session.get(Scene, seeded["scene_1"])
        assert scene.title == "Locally mutated title"  # untouched -- keep_local won


def test_take_imported_overwrites_local_value(conflict_fixture) -> None:
    seeded, blob = conflict_fixture

    with SessionLocal() as session:
        scene = session.get(Scene, seeded["scene_1"])
        scene.title = "Locally mutated title"
        session.commit()

    with SessionLocal() as session:
        report = apply_import(
            session, blob, _PASSPHRASE, {seeded["scene_1"]: "take_imported"}
        )
        session.commit()

    assert len(report.conflicts) == 1

    with SessionLocal() as session:
        scene = session.get(Scene, seeded["scene_1"])
        assert scene.title == "Scene One"  # the bundle's original title


def test_merge_fills_null_local_field_but_keeps_non_null_fields(conflict_fixture) -> None:
    seeded, blob = conflict_fixture

    with SessionLocal() as session:
        scene = session.get(Scene, seeded["scene_1"])
        assert scene.description == "original description"
        scene.description = None
        local_title_before = scene.title
        session.commit()

    with SessionLocal() as session:
        report = apply_import(session, blob, _PASSPHRASE, {seeded["scene_1"]: "merge"})
        session.commit()

    assert len(report.conflicts) == 1

    with SessionLocal() as session:
        scene = session.get(Scene, seeded["scene_1"])
        # gap-filled from the bundle
        assert scene.description == "original description"
        # local non-null field untouched -- merge never clobbers existing local content
        assert scene.title == local_title_before


# ── Test 6: any failure mid-apply rolls back the WHOLE transaction ───────────


def test_rollback_on_failure_leaves_no_partial_writes() -> None:
    with TestClient(app) as client:
        seeded = _build_seeded_book(client, "Rollback Me")

    with SessionLocal() as session:
        zip_bytes, _manifest = export_book_to_zip_bytes(
            session, seeded["book_id"], exported_at="2026-07-28T00:00:00+00:00"
        )
    blob = encrypt_bundle(zip_bytes, _PASSPHRASE)

    # Delete scene_2 (so the "scenes" table has real INSERT work to do) and mutate
    # scene_1's title (so it becomes a genuine conflict) -- whichever row `apply_import`
    # processes first, the OTHER one still proves a real write happened in this same
    # transaction before the forced failure below.
    with SessionLocal() as session:
        scene_2 = session.get(Scene, seeded["scene_2"])
        session.delete(scene_2)
        scene_1 = session.get(Scene, seeded["scene_1"])
        scene_1.title = "Locally mutated title"
        session.commit()

    with SessionLocal() as session:
        before = _row_counts(session)

    # An impossible resolution value forces `_resolve_conflict` to raise a
    # `BundleImportError` partway through the apply -- proving the whole transaction rolls
    # back (including scene_2's just-flushed re-insert), not just the failing row.
    with SessionLocal() as session:
        with pytest.raises(BundleImportError):
            apply_import(
                session, blob, _PASSPHRASE, {seeded["scene_1"]: "not_a_real_resolution"}
            )
        # `apply_import`'s own transaction context manager already rolled back on the
        # raised exception; an explicit rollback here is a no-op belt-and-suspenders.
        session.rollback()

    with SessionLocal() as session:
        after = _row_counts(session)

    assert before == after, f"rollback left partial writes: {before} -> {after}"


# ── Test 7 (reviewer FIX 2): book_scene_order natural-key dedup ──────────────
# `book_scene_order` has UniqueConstraint(book_id, scene_id) but a surrogate `id` PK. A
# local delete+recreate of the same (book_id, scene_id) row (new id, same natural key)
# used to be classified as "created" on re-import and hit the unique constraint on
# INSERT, aborting the whole import. It must now route through the join-table
# natural-key dedup path like book_scene_links/book_codex_links/etc.


def test_book_scene_order_natural_key_dedup_on_reimport() -> None:
    with TestClient(app) as client:
        book_id = _create_book(client, "Order Dedup")
        scene_id = _create_scene(client, "Ordered Scene")
        _add_scene_to_book(client, book_id, scene_id)
        resp = client.post(
            f"/books/{book_id}/scenes/{scene_id}/assign",
            json={"structure_beat": "Setup", "outline_order_index": 0},
        )
        assert resp.status_code == 200

    with SessionLocal() as session:
        zip_bytes, _manifest = export_book_to_zip_bytes(
            session, book_id, exported_at="2026-07-28T00:00:00+00:00"
        )
    blob = encrypt_bundle(zip_bytes, _PASSPHRASE)

    # Simulate "local delete + recreate": remove the existing book_scene_order row and
    # insert a fresh one with a NEW surrogate id but the SAME (book_id, scene_id) natural
    # key -- exactly what a user re-doing outline assignment locally would produce.
    with SessionLocal() as session:
        rows = session.execute(
            select(BookSceneOrder).where(
                BookSceneOrder.book_id == book_id, BookSceneOrder.scene_id == scene_id
            )
        ).scalars().all()
        assert len(rows) == 1
        session.delete(rows[0])
        session.flush()
        session.add(
            BookSceneOrder(
                book_id=book_id,
                scene_id=scene_id,
                structure_beat="Setup (recreated locally)",
            )
        )
        session.commit()

    with SessionLocal() as session:
        # Must NOT raise an IntegrityError from the unique constraint.
        report = apply_import(session, blob, _PASSPHRASE, {})
        session.commit()

    assert report is not None

    with SessionLocal() as session:
        rows = session.execute(
            select(BookSceneOrder).where(
                BookSceneOrder.book_id == book_id, BookSceneOrder.scene_id == scene_id
            )
        ).scalars().all()
        # Exactly one row for this natural key -- no duplicate was created.
        assert len(rows) == 1


# ── Test 8 (reviewer FIX 3): zip-slip regression ─────────────────────────────
# `_safe_extract_asset` (bundle_import.py, ~line 511) guards against a malicious/tampered
# bundle whose `images.storage_path` tries to escape `settings.media_dir` via `../`
# segments. This must be REFUSED: the whole import rolls back (no image row persists)
# and no file is ever written outside `media_dir`.


def _rebuild_zip_with_evil_image_path(zip_bytes: bytes, image_id: str, evil_path: str) -> bytes:
    """Rewrites a valid plaintext bundle zip so the `images` row identified by `image_id`
    has `storage_path` = `evil_path`, and adds a matching (equally malicious) `media/...`
    zip entry so the tampered path is actually reachable during extraction."""
    src = zipfile.ZipFile(io.BytesIO(zip_bytes))
    try:
        images_raw = json.loads(src.read("data/images.json"))
        found = False
        for row in images_raw:
            if row["id"] == image_id:
                row["storage_path"] = evil_path
                found = True
        assert found, "image row not present in bundle -- test setup is wrong"

        out_buffer = io.BytesIO()
        with zipfile.ZipFile(out_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                if info.filename == "data/images.json":
                    dst.writestr("data/images.json", json.dumps(images_raw))
                elif info.filename.startswith("media/"):
                    # Drop the original (legitimate) media entry for this image; replace
                    # it with one at the malicious arcname `_extract_image_asset` will
                    # actually look up: f"media/{evil_path}".
                    continue
                else:
                    dst.writestr(info.filename, src.read(info.filename))
            dst.writestr(f"media/{evil_path}", b"not a real png -- zip-slip payload")
        return out_buffer.getvalue()
    finally:
        src.close()


def test_zip_slip_image_path_is_refused_and_rolled_back() -> None:
    with TestClient(app) as client:
        seeded = _build_seeded_book(client, "Zip Slip Target")

    with SessionLocal() as session:
        zip_bytes, _manifest = export_book_to_zip_bytes(
            session, seeded["book_id"], exported_at="2026-07-28T00:00:00+00:00"
        )

    evil_relative = "../../evil.png"
    evil_blob = encrypt_bundle(
        _rebuild_zip_with_evil_image_path(zip_bytes, seeded["image_id"], evil_relative),
        _PASSPHRASE,
    )

    settings = get_settings()
    escape_target = (settings.media_dir / evil_relative).resolve()
    assert not escape_target.exists()  # nothing there before the attempt

    # Wipe the local db first so this book's rows would otherwise import as fresh
    # "created" rows (proving the guard fires on a genuine create path, not a no-op).
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

    try:
        with SessionLocal() as session:
            with pytest.raises(BundleImportError):
                apply_import(session, evil_blob, _PASSPHRASE, {})
            session.rollback()

        # Whole transaction rolled back: the malicious image row never persisted.
        with SessionLocal() as session:
            assert session.get(Image, seeded["image_id"]) is None
            assert session.get(Book, seeded["book_id"]) is None

        # And no file was ever written outside media_dir.
        assert not escape_target.exists()
    finally:
        # Belt-and-suspenders cleanup in case the guard somehow failed and the file
        # landed outside media_dir anyway -- never leave a stray file behind.
        if escape_target.exists():
            escape_target.unlink()
