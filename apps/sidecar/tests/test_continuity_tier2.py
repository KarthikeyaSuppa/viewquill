"""Tests for Continuity Checker v2 Tier 2 — semantic (LLM, guarded) pass (docs/11-AI-
INTELLIGENCE.md §4 "Tier 2 — Semantic (LLM, guarded)", docs/06 Phase 4 task BE-5).

[MODEL-DEFERRED-TEST]: no real Ollama/Groq call happens here or ever on this build machine
(see CLAUDE.md "Environment constraints") — `QUILLNIGHT_LLM_STUB=1` selects the no-network
`EchoProvider` (app/services/llm_orchestrator.py). Under that stub, PASS 2's extraction call
echoes back its own task-instruction prose (not JSON), so `run_tier2`'s JSON parsing always
fails and ZERO `source='ai'` flags are ever persisted in these tests — that is the expected,
asserted behavior (see `test_include_ai_true_stub_path_keeps_tier1_flags_and_persists_zero_ai_flags`
below), not a bug. Real Tier-2 flag quality is verified later on the AI laptop.

The guardrail tests below (`apply_quote_guardrail`) are the important ones per the task spec:
they exercise the mechanical hallucination filter directly, with hand-built candidate dicts,
with no DB and no model involved at all.
"""

from __future__ import annotations

import os
import tempfile

# `QUILLNIGHT_DATA_DIR`/`QUILLNIGHT_LLM_STUB` must be set BEFORE any `app.*` module is
# imported — see conftest.py's module docstring and tests/test_llm_enhance.py for the same
# pattern.
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-continuity-tier2-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.continuity_service import apply_quote_guardrail  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        yield test_client


# ── Guardrail unit tests — pure, no DB, no model ─────────────────────────────────────────


def test_guardrail_keeps_candidate_whose_quote_is_exact_substring() -> None:
    scene_text = "Elena's eyes were a deep, unmistakable green in the candlelight."
    candidates = [
        {
            "reasoning": "The scene describes green eyes, but the codex says blue.",
            "evidence": "codex: Elena has blue eyes",
            "quote": "a deep, unmistakable green",
            "entity": "Elena",
            "flag_type": "trait_contradiction",
            "severity": "warning",
        }
    ]
    kept = apply_quote_guardrail(candidates, scene_text)
    assert kept == candidates


def test_guardrail_drops_candidate_with_fabricated_quote() -> None:
    scene_text = "Elena's eyes were a deep, unmistakable green in the candlelight."
    candidates = [
        {
            "reasoning": "Hallucinated — this text never appears in the scene.",
            "evidence": "codex: Elena has blue eyes",
            "quote": "her eyes were startlingly blue",
            "flag_type": "trait_contradiction",
            "severity": "warning",
        }
    ]
    assert apply_quote_guardrail(candidates, scene_text) == []


def test_guardrail_whitespace_normalization_rule() -> None:
    """Documented rule: both sides are stripped of leading/trailing whitespace, then every
    internal run of whitespace (spaces/tabs/newlines) is collapsed to a single space, before
    the substring check. A quote that differs from the scene text only in incidental
    whitespace (e.g. a line wrap) still survives."""
    scene_text = "He walked   across\nthe  long   corridor  in silence."
    candidates = [{"quote": "  walked across the long\n corridor  ", "flag_type": "custom", "severity": "hint"}]
    kept = apply_quote_guardrail(candidates, scene_text)
    assert len(kept) == 1


def test_guardrail_empty_candidates_returns_empty() -> None:
    assert apply_quote_guardrail([], "any scene text") == []


def test_guardrail_drops_non_dict_and_missing_or_blank_quote_candidates() -> None:
    scene_text = "Some scene text."
    candidates = [
        "not-a-dict",
        {"quote": ""},
        {"quote": None},
        {"no_quote_field": True},
        {"quote": "scene text"},
    ]
    kept = apply_quote_guardrail(candidates, scene_text)
    assert len(kept) == 1
    assert kept[0]["quote"] == "scene text"


# ── Integration — stub path via the real endpoint ────────────────────────────────────────


def _create_book(client: TestClient, title: str = "Book") -> str:
    resp = client.post("/books", json={"title": title, "book_type": "story_book"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_scene(client: TestClient, title: str = "Scene", description: str | None = None) -> str:
    payload: dict = {"node_type": "scene", "title": title}
    if description is not None:
        payload["description"] = description
    resp = client.post("/scenes", json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_to_canvas(client: TestClient, book_id: str, scene_id: str) -> None:
    resp = client.post(f"/books/{book_id}/scenes/{scene_id}")
    assert resp.status_code == 201


def _assign_outline(client: TestClient, book_id: str, scene_id: str, index: int) -> None:
    resp = client.post(
        f"/books/{book_id}/scenes/{scene_id}/assign", json={"outline_order_index": index}
    )
    assert resp.status_code == 200


def _create_codex_entry(client: TestClient, name: str = "Entity") -> str:
    resp = client.post("/codex", json={"entry_type": "character", "name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def _link_codex_scene(client: TestClient, entry_id: str, scene_id: str) -> None:
    resp = client.post(f"/codex/{entry_id}/scenes/{scene_id}")
    assert resp.status_code == 201


def test_include_ai_defaults_false_never_calls_the_orchestrator(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`include_ai` defaults to false -> only Tier 1 runs; the orchestrator factory itself
    must never even be reached. Proven by monkeypatching it to raise if called, rather than
    just asserting the (weaker) absence of `source='ai'` flags in the response."""
    import app.services.continuity_service as continuity_service

    def _must_not_be_called() -> None:
        raise AssertionError("get_provider_client should not be called when include_ai is false")

    monkeypatch.setattr(continuity_service, "get_provider_client", _must_not_be_called)

    book_id = _create_book(client, "No AI Orchestrator Book")
    scene_id = _create_scene(client, "Scene", description="Some scene prose here.")
    _add_to_canvas(client, book_id, scene_id)
    _assign_outline(client, book_id, scene_id, 0)

    resp = client.post(f"/books/{book_id}/continuity/check")
    assert resp.status_code == 200
    flags = resp.json()
    assert [f for f in flags if f["source"] == "ai"] == []


def test_include_ai_true_stub_path_keeps_tier1_flags_and_persists_zero_ai_flags(
    client: TestClient,
) -> None:
    """`?include_ai=true` runs Tier 2 on top of Tier 1 through the real LLM orchestrator path
    (EchoProvider under QUILLNIGHT_LLM_STUB=1). The echoed PASS-2 output is plain instruction
    prose, not JSON, so `run_tier2` must not crash on it and must persist zero `source='ai'`
    flags. Tier-1's own (deterministic) flag for this same book must still be present. The
    scene's text must be byte-identical afterward — the never-write-scene-text invariant."""
    book_id = _create_book(client, "Include AI Book")
    entry_id = _create_codex_entry(client, "Sir Reginald")
    original_description = (
        "Sir Reginald's eyes were a deep, unmistakable green in the candlelight."
    )
    scene_id = _create_scene(client, "Placed Scene", description=original_description)
    _add_to_canvas(client, book_id, scene_id)
    _assign_outline(client, book_id, scene_id, 0)
    _link_codex_scene(client, entry_id, scene_id)

    # Arc-state introduced AFTER this scene's outline position -> guarantees a Tier-1
    # early_appearance flag, so we can assert it survives an include_ai=true call.
    arc_resp = client.post(
        f"/codex/{entry_id}/arc-states",
        json={"book_id": book_id, "as_of_outline_order_index": 5},
    )
    assert arc_resp.status_code == 201

    resp = client.post(f"/books/{book_id}/continuity/check", params={"include_ai": "true"})
    assert resp.status_code == 200
    flags = resp.json()

    tier1_flags = [f for f in flags if f["source"] == "deterministic"]
    assert len(tier1_flags) == 1
    assert tier1_flags[0]["flag_type"] == "early_appearance"

    ai_flags = [f for f in flags if f["source"] == "ai"]
    assert ai_flags == []

    scene_after = client.get(f"/scenes/{scene_id}")
    assert scene_after.status_code == 200
    assert scene_after.json()["description"] == original_description


def test_include_ai_true_with_no_placed_scenes_is_a_no_op_and_200s(client: TestClient) -> None:
    """A book with no outline-placed scenes has nothing for Tier 2 to check — no crash, no
    flags, still 200."""
    book_id = _create_book(client, "Empty Book")
    resp = client.post(f"/books/{book_id}/continuity/check", params={"include_ai": "true"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_include_ai_true_missing_book_404(client: TestClient) -> None:
    resp = client.post("/books/does-not-exist/continuity/check", params={"include_ai": "true"})
    assert resp.status_code == 404
