"""Tests for /voice — dictation intake + voice_notes lifecycle (docs/12-VOICE-AND-SPEECH.md
§1, docs/03-DATA-MODEL.md `voice_notes`, docs/06 Phase 2 tasks E1/E2).

Runs entirely against the STT stub (``QUILLNIGHT_STT_STUB=1``) — no onnx-asr, no network,
no model download, per CLAUDE.md "Environment constraints". Real-engine behavior is
[MODEL-DEFERRED] to the second laptop; see app/services/speech_stt.py.

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app), same
pattern as test_scenes.py, so the raw audio file this test writes can be asserted to
actually exist on disk without touching a real app-data directory.

NOTE on ``app.config.get_settings()``: it's ``@lru_cache``d, so across a *full test-suite*
run whichever test module imports ``app.*`` first "wins" the ``QUILLNIGHT_DATA_DIR`` value
for the whole pytest session (a pre-existing quirk shared by every ``test_*.py`` in this
package that sets this env var, not specific to this file). Since this is the one test
module that asserts real file paths on disk, it resolves paths via the actual cached
``get_settings().data_dir`` rather than its own local ``_TMP_DATA_DIR``, so the assertions
hold whether this file is run alone or as part of the full suite.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["QUILLNIGHT_STT_STUB"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against whatever data dir get_settings() actually resolved to (see module docstring).
    with TestClient(app) as test_client:
        yield test_client


def _data_dir() -> Path:
    return get_settings().data_dir


def _post_audio(client: TestClient, content_type: str = "audio/webm"):
    return client.post(
        "/voice/transcribe",
        content=b"\x00\x01\x02fake-audio-bytes\x03\x04",
        headers={"content-type": content_type},
    )


def test_transcribe_saves_audio_and_creates_voice_note(client: TestClient) -> None:
    resp = _post_audio(client)
    assert resp.status_code == 201
    body = resp.json()

    assert body["transcript"] == "stub transcript"
    assert body["engine"] == "stub"
    assert body["status"] == "transcribed"
    assert body["audio_path"].startswith("audio/")
    assert body["audio_path"].endswith(".webm")

    # The raw audio bytes actually landed on disk under the (resolved) data dir — never-lose-data.
    full_path = _data_dir() / body["audio_path"]
    assert full_path.exists()
    assert full_path.read_bytes() == b"\x00\x01\x02fake-audio-bytes\x03\x04"


def test_transcribe_unknown_content_type_falls_back_to_bin_extension(client: TestClient) -> None:
    resp = _post_audio(client, content_type="application/octet-stream")
    assert resp.status_code == 201
    assert resp.json()["audio_path"].endswith(".bin")


def test_list_voice_notes(client: TestClient) -> None:
    create_resp = _post_audio(client)
    note_id = create_resp.json()["id"]

    list_resp = client.get("/voice")
    assert list_resp.status_code == 200
    assert any(n["id"] == note_id for n in list_resp.json())


def test_attach_sets_status_and_entity(client: TestClient) -> None:
    note_id = _post_audio(client).json()["id"]

    attach_resp = client.post(
        f"/voice/{note_id}/attach",
        json={"attached_entity_type": "scene", "attached_entity_id": "some-scene-id"},
    )
    assert attach_resp.status_code == 200
    attached = attach_resp.json()
    assert attached["status"] == "attached"
    assert attached["attached_entity_type"] == "scene"
    assert attached["attached_entity_id"] == "some-scene-id"


def test_discard_sets_status_but_keeps_audio_file(client: TestClient) -> None:
    note = _post_audio(client).json()
    note_id = note["id"]
    audio_full_path = _data_dir() / note["audio_path"]
    assert audio_full_path.exists()

    discard_resp = client.post(f"/voice/{note_id}/discard")
    assert discard_resp.status_code == 200
    assert discard_resp.json()["status"] == "discarded"

    # Never-lose-data: discarding is a status flip only, the audio file must still exist.
    assert audio_full_path.exists()


def test_retranscribe_reuses_stored_audio_path(client: TestClient) -> None:
    note = _post_audio(client).json()
    note_id = note["id"]
    original_audio_path = note["audio_path"]

    retranscribe_resp = client.post(f"/voice/{note_id}/retranscribe")
    assert retranscribe_resp.status_code == 200
    retranscribed = retranscribe_resp.json()
    assert retranscribed["audio_path"] == original_audio_path
    assert retranscribed["transcript"] == "stub transcript"
    assert retranscribed["engine"] == "stub"
    assert retranscribed["status"] == "transcribed"


def test_transcribe_rejects_oversize_content_length_with_413(client: TestClient) -> None:
    """Regression: /voice/transcribe used to buffer the entire raw body with no size cap
    (OOM risk). A declared Content-Length over the cap must be rejected fast, before the
    (small, in this test) body is even fully read.
    """
    from app.api.voice import MAX_AUDIO_BYTES

    resp = client.post(
        "/voice/transcribe",
        content=b"\x00\x01small-body-but-lying-header\x02",
        headers={
            "content-type": "audio/webm",
            "content-length": str(MAX_AUDIO_BYTES + 1),
        },
    )
    assert resp.status_code == 413


def test_transcribe_rejects_actually_oversize_body_with_413(client: TestClient) -> None:
    """Even without a (correct) Content-Length header, a body that actually exceeds the
    cap must still be rejected with 413 once the streamed read crosses the limit — not
    buffered in full and accepted.
    """
    from app.api.voice import MAX_AUDIO_BYTES

    oversize_body = b"\x00" * (MAX_AUDIO_BYTES + 1024)
    resp = client.post(
        "/voice/transcribe",
        content=oversize_body,
        headers={"content-type": "audio/webm"},
    )
    assert resp.status_code == 413


def test_transcribe_normal_small_body_still_succeeds(client: TestClient) -> None:
    """Sanity check alongside the 413 tests above — the size guard must not affect a
    normal, well-under-the-cap request."""
    resp = _post_audio(client)
    assert resp.status_code == 201
    assert resp.json()["transcript"] == "stub transcript"


def test_attach_discard_retranscribe_missing_note_404(client: TestClient) -> None:
    assert client.post(
        "/voice/does-not-exist/attach",
        json={"attached_entity_type": "scene", "attached_entity_id": "x"},
    ).status_code == 404
    assert client.post("/voice/does-not-exist/discard").status_code == 404
    assert client.post("/voice/does-not-exist/retranscribe").status_code == 404
