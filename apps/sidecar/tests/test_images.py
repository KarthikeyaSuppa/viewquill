"""Tests for /images upload/serve + attaching a primary image to a Codex entry
(docs/03-DATA-MODEL.md `images`, docs/06 Phase 3 task BE-3).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB + media dir are used for this test run only — never touches a real
app-data directory.
"""

from __future__ import annotations

import base64
import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# A minimal valid 1x1 transparent PNG (67 bytes).
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
PNG_BYTES = base64.b64decode(_PNG_B64)


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
