"""Tests for /llm/enhance (SSE streaming) and /llm/log/{id}/accept (docs/04-LLM-INTEGRATION.md,
docs/06 Phase 2 tasks D1/D2).

[MODEL-DEFERRED-TEST]: no real Ollama/Groq call happens here or ever on this build machine
(see CLAUDE.md "Environment constraints") — `QUILLNIGHT_LLM_STUB=1` selects the no-network
`EchoProvider` (app/services/llm_orchestrator.py), which proves the request/stream/log
plumbing end-to-end without a model. Real streamed Enhance quality/latency is verified later
on the AI laptop.

Note on what gets echoed: the request pipeline builds messages via
`prompt_builder.build_enhance_prompt`, whose hard message order (module docstring) puts the
mode's static task instruction as the LAST message with role="user" — AFTER the caller's
raw `text`. `EchoProvider.stream()` echoes the *last* user-role message it's given, so for a
call routed through this endpoint it echoes the mode's task instruction, not the raw input
text. That is exercised/asserted directly below rather than assumed.
"""

from __future__ import annotations

import json
import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-llm-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.prompt_builder import _TASK_INSTRUCTIONS  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _parse_sse(lines: list[str]) -> list[dict]:
    """Group raw SSE lines into a list of {"event": str|None, "data": dict} events."""
    events: list[dict] = []
    current_event: str | None = None
    current_data_lines: list[str] = []

    def flush() -> None:
        nonlocal current_event, current_data_lines
        if current_data_lines:
            payload = json.loads("".join(current_data_lines))
            events.append({"event": current_event, "data": payload})
        current_event = None
        current_data_lines = []

    for line in lines:
        if line == "":
            flush()
        elif line.startswith("event:"):
            current_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current_data_lines.append(line[len("data:") :].strip())
    flush()
    return events


def _stream_enhance(client: TestClient, payload: dict) -> tuple[list[dict], object]:
    with client.stream("POST", "/llm/enhance", json=payload) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = list(response.iter_lines())
    return _parse_sse(lines), response


def test_enhance_streams_echoed_task_instruction_and_done_event(client: TestClient) -> None:
    events, _ = _stream_enhance(
        client, {"mode": "grammar", "text": "The quick brown fox jump over the lazy dog."}
    )

    delta_events = [e for e in events if e["event"] is None]
    assert delta_events, "expected at least one delta event"
    reconstructed = "".join(e["data"]["delta"] for e in delta_events).strip()
    assert reconstructed == _TASK_INSTRUCTIONS["grammar"]
    assert all(e["data"]["provider"] == "ollama" for e in delta_events)

    done_events = [e for e in events if e["event"] == "done"]
    assert len(done_events) == 1
    assert done_events[0]["data"]["provider"] == "ollama"
    assert done_events[0]["data"]["log_id"]


def test_enhance_log_created_and_accept_flips_accepted(client: TestClient) -> None:
    events, _ = _stream_enhance(client, {"mode": "prose", "text": "She walked into the room."})
    done = next(e for e in events if e["event"] == "done")
    log_id = done["data"]["log_id"]

    accept_resp = client.post(f"/llm/log/{log_id}/accept", json={"accepted": True})
    assert accept_resp.status_code == 200
    body = accept_resp.json()
    assert body["id"] == log_id
    assert body["provider"] == "ollama"
    assert body["accepted"] == 1
    assert body["request_type"] == "prose"
    assert body["latency_ms"] is not None


def test_accept_missing_log_returns_404(client: TestClient) -> None:
    resp = client.post("/llm/log/does-not-exist/accept", json={"accepted": False})
    assert resp.status_code == 404


def test_enhance_never_writes_to_the_referenced_scene(client: TestClient) -> None:
    book_resp = client.post("/books", json={"title": "No-Write Guarantee", "book_type": "story_book"})
    assert book_resp.status_code == 201
    book_id = book_resp.json()["id"]

    original_description = "This exact description must survive an Enhance call byte-for-byte."
    scene_resp = client.post(
        "/scenes",
        json={"node_type": "scene", "title": "Untouched Scene", "description": original_description},
    )
    assert scene_resp.status_code == 201
    scene_id = scene_resp.json()["id"]

    events, _ = _stream_enhance(
        client,
        {
            "mode": "continuity",
            "text": "A rewritten version of the scene the AI is not allowed to save.",
            "entity_type": "scene",
            "entity_id": scene_id,
            "field": "description",
            "scene_id": scene_id,
            "book_id": book_id,
        },
    )
    done = next(e for e in events if e["event"] == "done")
    assert done["data"]["log_id"]

    scene_after = client.get(f"/scenes/{scene_id}")
    assert scene_after.status_code == 200
    assert scene_after.json()["description"] == original_description


def _stream_merge(client: TestClient, payload: dict):
    with client.stream("POST", "/llm/merge-scenes", json=payload) as response:
        lines = list(response.iter_lines())
        return response.status_code, response.headers, _parse_sse(lines)


def test_merge_scenes_streams_same_sse_shape_as_enhance(client: TestClient) -> None:
    book_resp = client.post("/books", json={"title": "Merge Book", "book_type": "story_book"})
    assert book_resp.status_code == 201
    book_id = book_resp.json()["id"]

    scene_a = client.post(
        "/scenes", json={"node_type": "scene", "title": "Scene A", "description": "First half."}
    )
    scene_b = client.post(
        "/scenes", json={"node_type": "scene", "title": "Scene B", "description": "Second half."}
    )
    assert scene_a.status_code == 201
    assert scene_b.status_code == 201
    scene_a_id = scene_a.json()["id"]
    scene_b_id = scene_b.json()["id"]
    scene_a_desc = scene_a.json()["description"]
    scene_b_desc = scene_b.json()["description"]

    status_code, headers, events = _stream_merge(
        client, {"scene_ids": [scene_a_id, scene_b_id], "book_id": book_id}
    )

    assert status_code == 200
    assert headers["content-type"].startswith("text/event-stream")

    delta_events = [e for e in events if e["event"] is None]
    assert delta_events, "expected at least one delta event"
    assert all("delta" in e["data"] and "provider" in e["data"] for e in delta_events)

    done_events = [e for e in events if e["event"] == "done"]
    assert len(done_events) == 1
    log_id = done_events[0]["data"]["log_id"]
    assert log_id
    assert done_events[0]["data"]["provider"] == "ollama"

    # Confirm the audit row was written with the new request_type, and that this
    # suggest-only endpoint never touched either source scene.
    accept_resp = client.post(f"/llm/log/{log_id}/accept", json={"accepted": True})
    assert accept_resp.status_code == 200
    assert accept_resp.json()["request_type"] == "merge"

    scene_a_after = client.get(f"/scenes/{scene_a_id}")
    scene_b_after = client.get(f"/scenes/{scene_b_id}")
    assert scene_a_after.status_code == 200
    assert scene_b_after.status_code == 200
    assert scene_a_after.json()["description"] == scene_a_desc
    assert scene_b_after.json()["description"] == scene_b_desc


def test_merge_scenes_missing_scene_id_returns_404(client: TestClient) -> None:
    book_resp = client.post("/books", json={"title": "Merge Book 2", "book_type": "story_book"})
    book_id = book_resp.json()["id"]

    resp = client.post(
        "/llm/merge-scenes", json={"scene_ids": ["does-not-exist"], "book_id": book_id}
    )
    assert resp.status_code == 404


def test_merge_scenes_empty_scene_ids_returns_422(client: TestClient) -> None:
    book_resp = client.post("/books", json={"title": "Merge Book 3", "book_type": "story_book"})
    book_id = book_resp.json()["id"]

    resp = client.post("/llm/merge-scenes", json={"scene_ids": [], "book_id": book_id})
    assert resp.status_code == 422
