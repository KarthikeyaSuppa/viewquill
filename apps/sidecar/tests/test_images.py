"""Tests for /images upload/serve/thumb + attaching a primary image to a Codex entry
(docs/03-DATA-MODEL.md `images`, docs/06 Phase 3 task BE-3 + Phase 5 tasks BE-1/BE-3/BE-4).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB + media dir are used for this test run only — never touches a real
app-data directory.
"""

from __future__ import annotations

import base64
import io
import os
import tempfile
import uuid

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image as PILImage  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

# A minimal valid 1x1 transparent PNG (67 bytes).
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
PNG_BYTES = base64.b64decode(_PNG_B64)


def _generate_png(width: int, height: int) -> bytes:
    """Builds a real, in-memory PNG of the given size for dimension/thumbnail assertions."""
    buf = io.BytesIO()
    PILImage.new("RGB", (width, height), color=(120, 60, 200)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        yield test_client


def _create_entry(client: TestClient, name: str = "Character") -> str:
    resp = client.post("/codex", json={"entry_type": "character", "name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def _upload_png(client: TestClient, data: bytes = PNG_BYTES) -> dict:
    resp = client.post(
        "/images",
        params={"filename": "avatar.png"},
        content=data,
        headers={"Content-Type": "image/png"},
    )
    return resp


def _upload(
    client: TestClient,
    *,
    bucket: str = "reference_pool",
    display_name: str | None = None,
    data: bytes | None = None,
):
    params: dict = {"bucket": bucket}
    if display_name is not None:
        params["display_name"] = display_name
    resp = client.post(
        "/images",
        params=params,
        content=data if data is not None else _generate_png(30, 20),
        headers={"Content-Type": "image/png"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _token() -> str:
    """A short, per-test-unique string to embed in names/descriptions/tags so search/filter
    assertions can't accidentally match leftover rows from other tests sharing this
    module-scoped ``client`` fixture's one database."""
    return uuid.uuid4().hex[:10]


def test_upload_png_returns_id_and_checksum(client: TestClient) -> None:
    resp = _upload_png(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"]
    assert body["bucket"] == "reference_pool"
    assert body["original_filename"] == "avatar.png"
    assert len(body["checksum_sha256"]) == 64
    int(body["checksum_sha256"], 16)  # valid hex


def test_get_image_returns_bytes_and_content_type(client: TestClient) -> None:
    upload = _upload_png(client)
    image_id = upload.json()["id"]

    resp = client.get(f"/images/{image_id}")
    assert resp.status_code == 200
    assert resp.content == PNG_BYTES
    assert resp.headers["content-type"].startswith("image/")


def test_upload_rejects_unsupported_content_type(client: TestClient) -> None:
    resp = client.post(
        "/images",
        content=b"not an image",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status_code == 415


def test_upload_rejects_empty_body(client: TestClient) -> None:
    resp = client.post(
        "/images",
        content=b"",
        headers={"Content-Type": "image/png"},
    )
    assert resp.status_code == 422


def test_upload_rejects_oversized_body(client: TestClient) -> None:
    oversized = b"\x00" * (10 * 1024 * 1024 + 1)
    resp = client.post(
        "/images",
        content=oversized,
        headers={"Content-Type": "image/png"},
    )
    assert resp.status_code == 413


def test_attach_primary_image_to_codex_entry(client: TestClient) -> None:
    entry_id = _create_entry(client, name="Attach Target")
    image_id = _upload_png(client).json()["id"]

    resp = client.patch(f"/codex/{entry_id}", json={"primary_image_id": image_id})
    assert resp.status_code == 200
    assert resp.json()["primary_image_id"] == image_id

    get_resp = client.get(f"/codex/{entry_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["primary_image_id"] == image_id


def test_get_unknown_image_returns_404(client: TestClient) -> None:
    resp = client.get("/images/does-not-exist")
    assert resp.status_code == 404


# ── Phase 5 task BE-1: both buckets, Pillow dimensions, decompression-bomb-safe decode,
# thumbnails ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bucket", ["reference_pool", "finalized_scene"])
def test_upload_accepts_both_buckets_and_populates_real_dimensions(
    client: TestClient, bucket: str
) -> None:
    png_bytes = _generate_png(40, 20)
    resp = client.post(
        "/images",
        params={"filename": "art.png", "bucket": bucket},
        content=png_bytes,
        headers={"Content-Type": "image/png"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["bucket"] == bucket
    assert body["width"] == 40
    assert body["height"] == 20

    # The thumbnail actually landed on disk under the (resolved) real media dir — mirrors
    # tests/test_voice.py's approach to the shared-get_settings() cross-module quirk
    # documented in tests/conftest.py.
    storage_path = get_settings().media_dir / body["storage_path"]
    thumb_path = storage_path.parent / "thumb" / storage_path.name
    assert thumb_path.is_file()

    # The thumbnail was actually downscaled (longest side capped), not just copied verbatim.
    with PILImage.open(thumb_path) as thumb_img:
        assert max(thumb_img.size) <= 320


def test_upload_rejects_unsupported_bucket(client: TestClient) -> None:
    resp = client.post(
        "/images",
        params={"bucket": "not_a_real_bucket"},
        content=PNG_BYTES,
        headers={"Content-Type": "image/png"},
    )
    assert resp.status_code == 422


def test_upload_rejects_bytes_that_fail_pillow_decode(client: TestClient) -> None:
    """Bytes that pass the content-type header allow-list check but aren't actually a
    decodable image (truncated/garbage) must be rejected as BAD_IMAGE, not silently stored
    with null dimensions or crash the decode."""
    resp = client.post(
        "/images",
        content=b"this-looks-like-nothing-pillow-can-decode" * 4,
        headers={"Content-Type": "image/png"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Not a valid image."


def test_get_image_thumb_returns_200(client: TestClient) -> None:
    image_id = _upload_png(client, data=_generate_png(50, 50)).json()["id"]

    resp = client.get(f"/images/{image_id}/thumb")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")


def test_get_image_thumb_falls_back_to_full_image_when_thumb_missing(
    client: TestClient,
) -> None:
    """If a thumbnail is missing on disk (e.g. generation failed for some pre-existing row),
    /thumb must still serve the full image rather than 404 — the UI should never see a
    broken thumb for an image that actually exists."""
    original_bytes = _generate_png(60, 60)
    image_id = _upload_png(client, data=original_bytes).json()["id"]

    from app.db.base import SessionLocal
    from app.services import images_service

    with SessionLocal() as db:
        image = images_service.get_image(db, image_id)
        thumb_path = images_service.resolve_thumb_path(image)
    thumb_path.unlink()
    assert not thumb_path.is_file()

    resp = client.get(f"/images/{image_id}/thumb")
    assert resp.status_code == 200
    assert resp.content == original_bytes


# ── Phase 5 task BE-2: list/search, patch, delete, tags ─────────────────────────────────


def test_list_images_filters_by_bucket(client: TestClient) -> None:
    token = _token()
    ref = _upload(client, bucket="reference_pool", display_name=f"Castle {token}")
    scene = _upload(client, bucket="finalized_scene", display_name=f"Forest {token}")

    both = client.get("/images", params={"q": token})
    assert both.status_code == 200
    both_ids = {img["id"] for img in both.json()}
    assert {ref["id"], scene["id"]} <= both_ids

    ref_only = client.get("/images", params={"q": token, "bucket": "reference_pool"})
    assert ref_only.status_code == 200
    ref_ids = {img["id"] for img in ref_only.json()}
    assert ref["id"] in ref_ids
    assert scene["id"] not in ref_ids

    scene_only = client.get("/images", params={"q": token, "bucket": "finalized_scene"})
    scene_ids = {img["id"] for img in scene_only.json()}
    assert scene["id"] in scene_ids
    assert ref["id"] not in scene_ids


def test_list_images_rejects_unsupported_bucket(client: TestClient) -> None:
    resp = client.get("/images", params={"bucket": "not_a_real_bucket"})
    assert resp.status_code == 422


def test_list_images_q_matches_display_name(client: TestClient) -> None:
    token = _token()
    img = _upload(client, display_name=f"Portrait {token}")

    resp = client.get("/images", params={"q": token})
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert img["id"] in ids

    # Case-insensitive.
    resp_upper = client.get("/images", params={"q": token.upper()})
    ids_upper = {row["id"] for row in resp_upper.json()}
    assert img["id"] in ids_upper


def test_list_images_q_matches_description(client: TestClient) -> None:
    token = _token()
    img = _upload(client)
    patched = client.patch(f"/images/{img['id']}", json={"description": f"a scene about {token}"})
    assert patched.status_code == 200

    resp = client.get("/images", params={"q": token})
    ids = {row["id"] for row in resp.json()}
    assert img["id"] in ids


def test_list_images_q_matches_tag(client: TestClient) -> None:
    token = _token()
    img = _upload(client)
    tag_resp = client.post(f"/images/{img['id']}/tags", json={"tag": token})
    assert tag_resp.status_code == 201

    resp = client.get("/images", params={"q": token})
    ids = {row["id"] for row in resp.json()}
    assert img["id"] in ids


def test_list_images_tag_filter_is_exact_not_substring(client: TestClient) -> None:
    token = _token()
    exact = _upload(client)
    client.post(f"/images/{exact['id']}/tags", json={"tag": token})

    prefix = _upload(client)
    client.post(f"/images/{prefix['id']}/tags", json={"tag": f"{token}-extra"})

    resp = client.get("/images", params={"tag": token})
    ids = {row["id"] for row in resp.json()}
    assert exact["id"] in ids
    assert prefix["id"] not in ids


def test_add_tag_idempotent_and_normalizes_and_meta_returns_sorted(client: TestClient) -> None:
    img = _upload(client)

    resp1 = client.post(f"/images/{img['id']}/tags", json={"tag": "  Beta  "})
    assert resp1.status_code == 201
    resp2 = client.post(f"/images/{img['id']}/tags", json={"tag": "Alpha"})
    assert resp2.status_code == 201
    # Re-adding an already-present tag (case/whitespace-insensitive) is a no-op, not an error
    # or a duplicate.
    resp3 = client.post(f"/images/{img['id']}/tags", json={"tag": "beta"})
    assert resp3.status_code == 201

    meta = client.get(f"/images/{img['id']}/meta")
    assert meta.status_code == 200
    assert meta.json()["tags"] == ["alpha", "beta"]


def test_add_tag_rejects_empty_or_whitespace(client: TestClient) -> None:
    img = _upload(client)

    empty = client.post(f"/images/{img['id']}/tags", json={"tag": ""})
    assert empty.status_code == 422

    whitespace = client.post(f"/images/{img['id']}/tags", json={"tag": "   "})
    assert whitespace.status_code == 422


def test_add_tag_missing_image_returns_404(client: TestClient) -> None:
    resp = client.post("/images/does-not-exist/tags", json={"tag": "x"})
    assert resp.status_code == 404


def test_remove_tag_is_idempotent_and_missing_image_404s(client: TestClient) -> None:
    img = _upload(client)
    client.post(f"/images/{img['id']}/tags", json={"tag": "temp"})

    first = client.delete(f"/images/{img['id']}/tags/temp")
    assert first.status_code == 204
    meta = client.get(f"/images/{img['id']}/meta")
    assert meta.json()["tags"] == []

    # Removing an already-absent tag is a no-op, not an error.
    second = client.delete(f"/images/{img['id']}/tags/temp")
    assert second.status_code == 204

    missing_image = client.delete("/images/does-not-exist/tags/temp")
    assert missing_image.status_code == 404


def test_patch_renames_and_updates_description_independently(client: TestClient) -> None:
    img = _upload(client, display_name="Original Name")
    assert img["description"] is None

    renamed = client.patch(f"/images/{img['id']}", json={"display_name": "New Name"})
    assert renamed.status_code == 200
    body = renamed.json()
    assert body["display_name"] == "New Name"
    assert body["description"] is None  # untouched by a patch that didn't mention it

    described = client.patch(f"/images/{img['id']}", json={"description": "Some words"})
    assert described.status_code == 200
    body2 = described.json()
    assert body2["display_name"] == "New Name"  # untouched by a patch that didn't mention it
    assert body2["description"] == "Some words"

    # Explicitly clearing description to "" is allowed and distinct from leaving it unset.
    cleared = client.patch(f"/images/{img['id']}", json={"description": ""})
    assert cleared.status_code == 200
    assert cleared.json()["description"] == ""
    assert cleared.json()["display_name"] == "New Name"


def test_patch_missing_image_returns_404(client: TestClient) -> None:
    resp = client.patch("/images/does-not-exist", json={"display_name": "x"})
    assert resp.status_code == 404


def test_delete_image_removes_row_files_and_cascades_tags(client: TestClient) -> None:
    img = _upload(client, data=_generate_png(64, 64))
    client.post(f"/images/{img['id']}/tags", json={"tag": "doomed"})

    from app.db.base import SessionLocal
    from app.models.orm import ImageTag
    from app.services import images_service

    with SessionLocal() as db:
        row = images_service.get_image(db, img["id"])
        original_path = images_service.resolve_path(row)
        thumb_path = images_service.resolve_thumb_path(row)
    assert original_path.is_file()
    assert thumb_path.is_file()

    resp = client.delete(f"/images/{img['id']}")
    assert resp.status_code == 204

    assert not original_path.is_file()
    assert not thumb_path.is_file()

    assert client.get(f"/images/{img['id']}").status_code == 404
    assert client.get(f"/images/{img['id']}/meta").status_code == 404

    with SessionLocal() as db:
        remaining_tags = db.query(ImageTag).filter(ImageTag.image_id == img["id"]).count()
    assert remaining_tags == 0


def test_delete_missing_image_returns_404(client: TestClient) -> None:
    resp = client.delete("/images/does-not-exist")
    assert resp.status_code == 404


def test_get_meta_returns_id_and_tags(client: TestClient) -> None:
    img = _upload(client, display_name="Meta Target")
    client.post(f"/images/{img['id']}/tags", json={"tag": "z-tag"})
    client.post(f"/images/{img['id']}/tags", json={"tag": "a-tag"})

    resp = client.get(f"/images/{img['id']}/meta")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == img["id"]
    assert body["tags"] == ["a-tag", "z-tag"]


def test_get_meta_missing_image_returns_404(client: TestClient) -> None:
    resp = client.get("/images/does-not-exist/meta")
    assert resp.status_code == 404


# ── Phase 5 task BE-3: polymorphic image<->entity attach/detach ─────────────────────────


def _create_scene(client: TestClient, title: str = "A Scene") -> str:
    resp = client.post("/scenes", json={"node_type": "scene", "title": title})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_book(client: TestClient, title: str = "A Book") -> str:
    resp = client.post("/books", json={"title": title, "book_type": "story_book"})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_attach_to_book_scene_and_codex_entry(client: TestClient) -> None:
    img = _upload(client)
    book_id = _create_book(client)
    scene_id = _create_scene(client)
    entry_id = _create_entry(client, name="Linked Character")

    for entity_type, entity_id in (
        ("book", book_id),
        ("scene", scene_id),
        ("codex_entry", entry_id),
    ):
        resp = client.post(
            f"/images/{img['id']}/links",
            json={"entity_type": entity_type, "entity_id": entity_id},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["image_id"] == img["id"]
        assert body["entity_type"] == entity_type
        assert body["entity_id"] == entity_id
        assert body["role"] is None


def test_attach_is_idempotent_for_same_image_entity_role(client: TestClient) -> None:
    img = _upload(client)
    book_id = _create_book(client)

    first = client.post(
        f"/images/{img['id']}/links", json={"entity_type": "book", "entity_id": book_id}
    )
    assert first.status_code == 201
    link_id = first.json()["id"]

    second = client.post(
        f"/images/{img['id']}/links", json={"entity_type": "book", "entity_id": book_id}
    )
    assert second.status_code == 201
    assert second.json()["id"] == link_id  # same row returned, not a duplicate

    listed = client.get(f"/entities/book/{book_id}/images")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()].count(img["id"]) == 1


def test_attach_with_and_without_role_are_distinct_links(client: TestClient) -> None:
    img = _upload(client)
    scene_id = _create_scene(client)

    no_role = client.post(
        f"/images/{img['id']}/links", json={"entity_type": "scene", "entity_id": scene_id}
    )
    assert no_role.status_code == 201
    with_role = client.post(
        f"/images/{img['id']}/links",
        json={"entity_type": "scene", "entity_id": scene_id, "role": "moodboard"},
    )
    assert with_role.status_code == 201
    assert with_role.json()["id"] != no_role.json()["id"]

    # Re-attaching the same role again is still idempotent (a distinct-but-stable link).
    with_role_again = client.post(
        f"/images/{img['id']}/links",
        json={"entity_type": "scene", "entity_id": scene_id, "role": "moodboard"},
    )
    assert with_role_again.status_code == 201
    assert with_role_again.json()["id"] == with_role.json()["id"]


def test_attach_rejects_bad_entity_type(client: TestClient) -> None:
    img = _upload(client)
    resp = client.post(
        f"/images/{img['id']}/links",
        json={"entity_type": "not_a_real_entity", "entity_id": "whatever"},
    )
    assert resp.status_code == 422


def test_attach_to_missing_image_returns_404(client: TestClient) -> None:
    resp = client.post(
        "/images/does-not-exist/links",
        json={"entity_type": "book", "entity_id": "whatever"},
    )
    assert resp.status_code == 404


def test_detach_with_and_without_role_then_idempotent(client: TestClient) -> None:
    img = _upload(client)
    scene_id = _create_scene(client)

    client.post(f"/images/{img['id']}/links", json={"entity_type": "scene", "entity_id": scene_id})
    client.post(
        f"/images/{img['id']}/links",
        json={"entity_type": "scene", "entity_id": scene_id, "role": "moodboard"},
    )

    # Detach the no-role link.
    first = client.delete(
        f"/images/{img['id']}/links",
        params={"entity_type": "scene", "entity_id": scene_id},
    )
    assert first.status_code == 204
    # Repeating is a no-op, still 204.
    second = client.delete(
        f"/images/{img['id']}/links",
        params={"entity_type": "scene", "entity_id": scene_id},
    )
    assert second.status_code == 204

    listed = client.get(f"/entities/scene/{scene_id}/images")
    remaining_roles = {row["id"] for row in listed.json()}
    assert img["id"] in remaining_roles  # the "moodboard"-role link is still there

    # Detach the "moodboard" role link.
    third = client.delete(
        f"/images/{img['id']}/links",
        params={"entity_type": "scene", "entity_id": scene_id, "role": "moodboard"},
    )
    assert third.status_code == 204
    fourth = client.delete(
        f"/images/{img['id']}/links",
        params={"entity_type": "scene", "entity_id": scene_id, "role": "moodboard"},
    )
    assert fourth.status_code == 204

    final_listed = client.get(f"/entities/scene/{scene_id}/images")
    assert img["id"] not in {row["id"] for row in final_listed.json()}


def test_detach_rejects_bad_entity_type(client: TestClient) -> None:
    img = _upload(client)
    resp = client.delete(
        f"/images/{img['id']}/links",
        params={"entity_type": "not_a_real_entity", "entity_id": "whatever"},
    )
    assert resp.status_code == 422


def test_list_entity_images_returns_linked_images_with_tags(client: TestClient) -> None:
    token = _token()
    img = _upload(client, display_name=f"Linked {token}")
    client.post(f"/images/{img['id']}/tags", json={"tag": token})
    book_id = _create_book(client)

    client.post(
        f"/images/{img['id']}/links", json={"entity_type": "book", "entity_id": book_id}
    )

    resp = client.get(f"/entities/book/{book_id}/images")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == img["id"]
    assert body[0]["tags"] == [token]


def test_list_entity_images_rejects_bad_entity_type(client: TestClient) -> None:
    resp = client.get("/entities/not_a_real_entity/some-id/images")
    assert resp.status_code == 422


# ── Phase 5 task BE-4: Book-scoped export-gather query ───────────────────────────────────
#
# DATA-SENSITIVE: a wrong scope here leaks another Book's private images into an export
# bundle. Every assertion below checks BOTH that the right images ARE present AND that the
# other Book's images are ABSENT.


def _add_scene_to_book(client: TestClient, book_id: str, scene_id: str) -> None:
    resp = client.post(f"/books/{book_id}/scenes/{scene_id}")
    assert resp.status_code == 201, resp.text


def _link_codex_to_book(client: TestClient, entry_id: str, book_id: str) -> None:
    resp = client.post(f"/codex/{entry_id}/books/{book_id}")
    assert resp.status_code == 201, resp.text


def _attach(client: TestClient, image_id: str, entity_type: str, entity_id: str) -> None:
    resp = client.post(
        f"/images/{image_id}/links",
        json={"entity_type": entity_type, "entity_id": entity_id},
    )
    assert resp.status_code == 201, resp.text


def _set_cover(client: TestClient, book_id: str, image_id: str) -> None:
    resp = client.patch(f"/books/{book_id}", json={"cover_image_id": image_id})
    assert resp.status_code == 200, resp.text


def test_get_book_images_scopes_correctly_and_excludes_other_book(client: TestClient) -> None:
    # Book A and its full set: book-attached, scene-attached, codex-attached, plus cover.
    book_a = _create_book(client, title="Book A")
    scene_a = _create_scene(client, title="Scene A")
    _add_scene_to_book(client, book_a, scene_a)
    entry_a = _create_entry(client, name="Entry A")
    _link_codex_to_book(client, entry_a, book_a)

    img_a_book = _upload(client, display_name="imgA_book")
    img_a_scene = _upload(client, display_name="imgA_scene")
    img_a_codex = _upload(client, display_name="imgA_codex")
    img_a_cover = _upload(client, display_name="imgA_cover")

    _attach(client, img_a_book["id"], "book", book_a)
    _attach(client, img_a_scene["id"], "scene", scene_a)
    _attach(client, img_a_codex["id"], "codex_entry", entry_a)
    _set_cover(client, book_a, img_a_cover["id"])

    # Book B and its own (disjoint) set — must never leak into Book A's results.
    book_b = _create_book(client, title="Book B")
    scene_b = _create_scene(client, title="Scene B")
    _add_scene_to_book(client, book_b, scene_b)

    img_b_scene = _upload(client, display_name="imgB_scene")
    img_b_book = _upload(client, display_name="imgB_book")
    _attach(client, img_b_scene["id"], "scene", scene_b)
    _attach(client, img_b_book["id"], "book", book_b)

    # An orphan image with no links at all — must appear in neither Book's result.
    img_orphan = _upload(client, display_name="imgOrphan")

    resp_a = client.get(f"/books/{book_a}/images")
    assert resp_a.status_code == 200
    ids_a = {row["id"] for row in resp_a.json()}
    assert ids_a == {
        img_a_book["id"],
        img_a_scene["id"],
        img_a_codex["id"],
        img_a_cover["id"],
    }
    assert img_b_scene["id"] not in ids_a
    assert img_b_book["id"] not in ids_a
    assert img_orphan["id"] not in ids_a

    resp_b = client.get(f"/books/{book_b}/images")
    assert resp_b.status_code == 200
    ids_b = {row["id"] for row in resp_b.json()}
    assert ids_b == {img_b_scene["id"], img_b_book["id"]}
    assert not (ids_b & ids_a)  # fully disjoint from Book A's set
    assert img_orphan["id"] not in ids_b


def test_get_book_images_excludes_codex_image_linked_only_to_other_book(
    client: TestClient,
) -> None:
    """Plants a codex-linked image on Book B ONLY (mirroring the codex-link setup in
    ``test_get_book_images_scopes_correctly_and_excludes_other_book`` above: create the
    entry, link it to the book via ``/codex/{id}/books/{id}``, then attach an image to the
    entry via ``/images/{id}/links``) and asserts it never leaks into Book A's results —
    the codex branch of the export-scope query must not ride on set-equality alone."""
    book_a = _create_book(client, title="Book A (codex isolation)")
    book_b = _create_book(client, title="Book B (codex isolation)")

    entry_b = _create_entry(client, name="Entry B Only")
    _link_codex_to_book(client, entry_b, book_b)

    img_b_codex = _upload(client, display_name="imgB_codex_only")
    _attach(client, img_b_codex["id"], "codex_entry", entry_b)

    resp_a = client.get(f"/books/{book_a}/images")
    assert resp_a.status_code == 200
    ids_a = {row["id"] for row in resp_a.json()}
    assert img_b_codex["id"] not in ids_a

    resp_b = client.get(f"/books/{book_b}/images")
    assert resp_b.status_code == 200
    ids_b = {row["id"] for row in resp_b.json()}
    assert img_b_codex["id"] in ids_b


def test_get_book_images_deduplicates_image_linked_via_multiple_paths(
    client: TestClient,
) -> None:
    book_id = _create_book(client)
    scene_id = _create_scene(client)
    _add_scene_to_book(client, book_id, scene_id)

    img = _upload(client, display_name="imgBoth")
    _attach(client, img["id"], "book", book_id)
    _attach(client, img["id"], "scene", scene_id)

    resp = client.get(f"/books/{book_id}/images")
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.json()]
    assert ids.count(img["id"]) == 1


def test_get_book_images_with_no_cover_set_is_absent_not_a_crash(client: TestClient) -> None:
    book_id = _create_book(client)
    resp = client.get(f"/books/{book_id}/images")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_book_images_missing_book_returns_404(client: TestClient) -> None:
    resp = client.get("/books/does-not-exist/images")
    assert resp.status_code == 404


def test_deleting_image_cascades_away_its_entity_links(client: TestClient) -> None:
    img = _upload(client)
    book_id = _create_book(client)
    client.post(
        f"/images/{img['id']}/links", json={"entity_type": "book", "entity_id": book_id}
    )
    assert len(client.get(f"/entities/book/{book_id}/images").json()) == 1

    resp = client.delete(f"/images/{img['id']}")
    assert resp.status_code == 204

    after = client.get(f"/entities/book/{book_id}/images")
    assert after.status_code == 200
    assert after.json() == []
