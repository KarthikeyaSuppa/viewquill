"""Tests for the Phase 10 hybrid RRF search (PHASE10.md task 4,
docs/11-AI-INTELLIGENCE.md §2): app/services/hybrid_search_service.py's fused FTS5 + vec0
KNN search, and the `GET /search` endpoint (app/api/search.py).

No Ollama/network/model involved — QUILLNIGHT_LLM_STUB=1 is set before `app.main` is
imported so every embed() call here takes the deterministic stub path (same convention as
tests/test_search_index.py, tests/test_semantic_search_migration.py). Most entities are
indexed directly via `search_index_service.upsert_entity` (plus a real Scene/CodexEntry ORM
row so `hybrid_search_service.search`'s title/snippet resolution has something to join
against — see `_index_scene`/`_index_codex_entry` below), bypassing the full create-Scene/
create-CodexEntry API per the task's "no need to go through the full API" instruction; one
test (`test_results_resolve_title_snippet_and_book_ids`) does go through the API, since it
also needs a Book + canvas link to prove `book_ids` resolution.

Note on what the stub embedding can/can't prove: `embedding_service._stub_embed` derives a
vector from a text hash, not a real semantic model — texts about the same topic don't embed
close together the way a real model would. So these tests don't attempt to prove "semantic
similarity" finds conceptually-related-but-differently-worded text; they instead prove the
mechanics that don't depend on real semantics: the vector leg is deterministic (identical
text -> identical embedding -> distance 0, nearest neighbor of itself), the FTS leg does
real keyword matching, and RRF fusion combines both correctly (an entity found by both legs
outranks one found by only one).
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-hybridsearch-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.orm import CodexEntry, Scene  # noqa: E402
from app.services import hybrid_search_service, search_index_service  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(client: TestClient):
    with SessionLocal() as session:
        yield session


def _index_scene(entity_id: str, title: str, body: str = "") -> None:
    """Creates a real `Scene` ORM row (so `hybrid_search_service.search`'s title/snippet
    resolution has something to join against — same requirement `search_index_service.
    upsert_entity` documents: it only maintains `search_fts`/`embeddings`, never the source
    row) directly via the ORM, then indexes it via `upsert_entity` — bypassing the full
    `POST /scenes` create path per the task's "no need to go through the full API"
    instruction, while still leaving a resolvable Scene row behind."""
    with SessionLocal() as session:
        session.add(Scene(id=entity_id, node_type="scene", title=title, description=body))
        session.commit()
    search_index_service.upsert_entity("scene", entity_id, title, body)


def _index_codex_entry(entity_id: str, name: str, summary: str = "") -> None:
    with SessionLocal() as session:
        session.add(CodexEntry(id=entity_id, entry_type="character", name=name, summary=summary))
        session.commit()
    search_index_service.upsert_entity("codex_entry", entity_id, name, summary)


# ── Empty/invalid input handling ────────────────────────────────────────────────
def test_empty_query_returns_empty_list_not_an_error(db) -> None:
    assert hybrid_search_service.search(db, "") == []
    assert hybrid_search_service.search(db, "   ") == []


def test_invalid_entity_type_raises_value_error(db) -> None:
    with pytest.raises(ValueError, match="INVALID_ENTITY_TYPE"):
        hybrid_search_service.search(db, "anything", entity_type="not_a_real_type")


# ── FTS5 leg: real keyword matching ─────────────────────────────────────────────
def test_fts_leg_matches_a_rare_keyword_present_in_only_one_entity(client: TestClient, db) -> None:
    search_index_service.upsert_entity(
        "scene", "hs-scene-fts-1", "The Quenlorath Ambush", "Rangers strike at dawn."
    )
    search_index_service.upsert_entity(
        "scene", "hs-scene-fts-2", "A Quiet Morning", "Nothing much happens at all."
    )
    search_index_service.upsert_entity(
        "scene", "hs-scene-fts-3", "Market Day", "Vendors haggle over bread and salt."
    )

    keys = hybrid_search_service._fts_ranked_keys("Quenlorath", limit=10, entity_type=None)
    assert ("scene", "hs-scene-fts-1") in keys
    assert ("scene", "hs-scene-fts-2") not in keys
    assert ("scene", "hs-scene-fts-3") not in keys


def test_malformed_fts_query_is_treated_as_no_matches_not_a_500(client: TestClient, db) -> None:
    # An unbalanced quote is a syntax error to FTS5's MATCH parser.
    assert hybrid_search_service._fts_ranked_keys('"unbalanced', limit=10, entity_type=None) == []
    # The full search() still succeeds end-to-end (vector leg runs independently).
    results = hybrid_search_service.search(db, '"unbalanced', limit=10)
    assert isinstance(results, list)


# ── Vector leg: deterministic, not a real semantic model ────────────────────────
def test_vector_leg_ranks_identical_indexed_text_as_its_own_nearest_neighbor(
    client: TestClient, db
) -> None:
    title, body = "Harrowgate Falls", "The old bridge finally gives way in the storm."
    search_index_service.upsert_entity("scene", "hs-scene-vec-1", title, body)
    search_index_service.upsert_entity(
        "scene", "hs-scene-vec-2", "Unrelated Title", "Completely different body text."
    )

    # Same joined text `embed()`/`upsert_entity` used to index -> identical stub vector ->
    # distance 0 -> guaranteed nearest neighbor of itself.
    query = f"{title}\n\n{body}"
    keys = hybrid_search_service._vector_ranked_keys(query, limit=1, entity_type=None)
    assert keys == [("scene", "hs-scene-vec-1")]


# ── RRF fusion: both-legs beats one-leg ──────────────────────────────────────────
def test_fusion_ranks_entity_matching_both_legs_above_keyword_only_matches(
    client: TestClient, db
) -> None:
    # `hs-fused-match` is indexed with the exact query text (guarantees it's in the vector
    # leg's results at distance 0) AND contains the keyword (guarantees it's in the FTS
    # leg's results) -> both legs contribute to its score.
    query = "Silverthorn"
    _index_scene("hs-fused-match", query, "")
    # These three only ever match on keyword (their embeddings are unrelated to the query
    # text, so their vector-leg rank is arbitrary) or, if the corpus is small enough that
    # vec0's KNN returns everyone, only get a single vector-leg contribution — never a
    # second FTS contribution, since the word isn't in their text at all.
    _index_scene("hs-fused-other-1", "Different Title One", "x")
    _index_scene("hs-fused-other-2", "Different Title Two", "y")
    _index_scene("hs-fused-other-3", "Different Title Three", "z")

    results = hybrid_search_service.search(db, query, limit=10, entity_type="scene")
    result_ids = [r.entity_id for r in results]

    assert "hs-fused-match" in result_ids
    # Matched-both-legs entity ranks strictly first: its score is a sum of two positive RRF
    # terms, while every other candidate contributes at most one.
    assert result_ids[0] == "hs-fused-match"
    top_score = results[0].score
    assert all(r.score <= top_score for r in results)


# ── entity_type filtering ────────────────────────────────────────────────────────
def test_entity_type_filter_excludes_the_other_type(client: TestClient, db) -> None:
    shared_word = "Brackenmoor"
    _index_scene("hs-type-scene-1", shared_word, "")
    _index_codex_entry("hs-type-codex-1", shared_word, "")

    scene_only = hybrid_search_service.search(db, shared_word, limit=10, entity_type="scene")
    assert {r.entity_type for r in scene_only} == {"scene"}
    assert any(r.entity_id == "hs-type-scene-1" for r in scene_only)

    codex_only = hybrid_search_service.search(
        db, shared_word, limit=10, entity_type="codex_entry"
    )
    assert {r.entity_type for r in codex_only} == {"codex_entry"}
    assert any(r.entity_id == "hs-type-codex-1" for r in codex_only)


# ── Result shape: resolves the real Scene/CodexEntry row, not just raw ids ───────
def test_results_resolve_title_snippet_and_book_ids(client: TestClient) -> None:
    resp = client.post(
        "/books", json={"title": "Search Result Shape Test Book", "book_type": "story_book"}
    )
    assert resp.status_code == 201
    book_id = resp.json()["id"]

    scene_resp = client.post(
        "/scenes",
        json={
            "node_type": "scene",
            "title": "The Emberlight Vigil",
            "description": "A long description " * 20,
        },
    )
    scene_id = scene_resp.json()["id"]
    canvas_resp = client.post(f"/books/{book_id}/scenes/{scene_id}")
    assert canvas_resp.status_code == 201

    with SessionLocal() as db:
        results = hybrid_search_service.search(db, "Emberlight", limit=10, entity_type="scene")

    matches = [r for r in results if r.entity_id == scene_id]
    assert len(matches) == 1
    result = matches[0]
    assert result.title == "The Emberlight Vigil"
    assert result.snippet is not None
    assert len(result.snippet) <= 201  # _SNIPPET_LENGTH + ellipsis
    assert result.book_ids == [book_id]


# ── API endpoint ──────────────────────────────────────────────────────────────
def test_search_endpoint_returns_matches(client: TestClient) -> None:
    create_resp = client.post(
        "/codex",
        json={
            "entry_type": "character",
            "name": "Ophelia Rue",
            "summary": "Keeper of the lighthouse at Grayhollow.",
        },
    )
    entry_id = create_resp.json()["id"]

    resp = client.get("/search", params={"q": "Grayhollow"})
    assert resp.status_code == 200
    body = resp.json()
    assert any(r["entity_id"] == entry_id for r in body)


def test_search_endpoint_empty_query_returns_empty_list(client: TestClient) -> None:
    resp = client.get("/search", params={"q": ""})
    assert resp.status_code == 200
    assert resp.json() == []


def test_search_endpoint_rejects_invalid_entity_type(client: TestClient) -> None:
    resp = client.get("/search", params={"q": "anything", "entity_type": "not_a_type"})
    assert resp.status_code == 422
