"""Tests for the Phase 10 suggestion service (PHASE10.md task 5,
docs/11-AI-INTELLIGENCE.md §2 "auto codex-link suggestions on node save" /
"similar-scene detection surfaced when creating new nodes"):
app/services/suggestion_service.py's `suggest_codex_links`/`suggest_similar_scenes`, and the
`GET /search/scenes/{scene_id}/suggestions` endpoint (app/api/search.py).

No Ollama/network/model involved — QUILLNIGHT_LLM_STUB=1 is set before `app.main` is
imported so every embed() call here takes the deterministic stub path (same convention as
tests/test_hybrid_search.py, tests/test_search_index.py).

## What the stub embedding can and can't prove here

`embedding_service._stub_embed` hashes text into a vector — deterministic (same text, same
vector) but not semantically meaningful ("a knight" and "a warrior" won't embed anywhere near
each other the way a real model would). So these tests never assert that two *differently
worded but conceptually related* texts get suggested together — the stub genuinely can't
produce that.

There's a second, less obvious stub limitation this file works around: `hybrid_search_
service`'s vec0 leg always returns its `k` nearest neighbours, however irrelevant, ranked by
*some* distance — with the tiny corpora a test creates, an "unrelated" entry can trivially
land at vector rank 1 or 2 purely because there's nothing else in the table yet, which would
make it clear `SUGGESTION_RELEVANCE_FLOOR` (a rank-based cutoff) for reasons that have
nothing to do with real relevance and everything to do with corpus size at that point in the
test run. Asserting "excluded below the floor" against real end-to-end search would be
flaky for that reason, not because the mechanism is wrong. So the floor-filtering and
already-linked/self-exclusion *mechanics* are tested here by monkeypatching
`hybrid_search_service.search` with a small controlled result set (known scores, known ids) —
this proves `suggestion_service`'s own filtering logic deterministically, independent of
what the stub embedding or corpus size happen to produce. The FTS-leg-driven "same
distinctive word gets suggested" tests, by contrast, run the real end-to-end path, since an
exact keyword match reliably ranks first in FTS5 regardless of corpus size or embedding
quality — that's real signal, not corpus-size luck.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-suggestions-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.schemas import SearchResult  # noqa: E402
from app.services import suggestion_service  # noqa: E402


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


def _create_scene(client: TestClient, title: str, description: str = "") -> str:
    resp = client.post(
        "/scenes", json={"node_type": "scene", "title": title, "description": description}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_codex_entry(client: TestClient, name: str, summary: str = "") -> str:
    resp = client.post(
        "/codex", json={"entry_type": "character", "name": name, "summary": summary}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ── Not-found scene ────────────────────────────────────────────────────────────
def test_suggest_codex_links_raises_on_unknown_scene(db) -> None:
    with pytest.raises(ValueError, match="SCENE_NOT_FOUND"):
        suggestion_service.suggest_codex_links(db, "not-a-real-scene-id")


def test_suggest_similar_scenes_raises_on_unknown_scene(db) -> None:
    with pytest.raises(ValueError, match="SCENE_NOT_FOUND"):
        suggestion_service.suggest_similar_scenes(db, "not-a-real-scene-id")


# ── FTS-leg-driven suggestion: shared distinctive text surfaces a real match ─────
# (real end-to-end path — see module docstring for why this is safe from corpus-size luck)
def test_scene_mentioning_codex_entry_name_gets_it_suggested(client: TestClient, db) -> None:
    entry_id = _create_codex_entry(client, "Quenlorath", "A ranger captain of the north.")
    scene_id = _create_scene(
        client,
        "The Ambush",
        "Quenlorath leads the charge at dawn, blade drawn.",
    )

    suggestions = suggestion_service.suggest_codex_links(db, scene_id)
    assert any(s.codex_entry_id == entry_id for s in suggestions)


def test_similar_scenes_shared_distinctive_text_is_surfaced(client: TestClient, db) -> None:
    other_id = _create_scene(
        client, "Ravenscar Duel Confrontation", "Two rivals meet beneath the ravenscar cliffs."
    )
    scene_id = _create_scene(
        client,
        "A Different Title Entirely",
        "The ravenscar cliffs echo with an old duel confrontation.",
    )
    suggestions = suggestion_service.suggest_similar_scenes(db, scene_id)
    assert any(s.scene_id == other_id for s in suggestions)


# ── Already-linked exclusion — real end-to-end (keyword match is deterministic) ──
def test_already_linked_codex_entry_is_excluded_even_if_textually_similar(
    client: TestClient, db
) -> None:
    entry_id = _create_codex_entry(client, "Harrowgate", "Keeper of the old bridge.")
    scene_id = _create_scene(
        client, "Harrowgate Falls", "Harrowgate watches the bridge finally give way."
    )

    # Confirm it WOULD be suggested unlinked...
    before = suggestion_service.suggest_codex_links(db, scene_id)
    assert any(s.codex_entry_id == entry_id for s in before)

    # ...then link it and confirm it drops out of suggestions.
    link_resp = client.post(f"/codex/{entry_id}/scenes/{scene_id}")
    assert link_resp.status_code == 201

    after = suggestion_service.suggest_codex_links(db, scene_id)
    assert not any(s.codex_entry_id == entry_id for s in after)


# ── Relevance-floor filtering — controlled inputs via monkeypatch ────────────────
# See module docstring: real end-to-end search on a tiny test corpus can't reliably prove
# "below the floor is excluded" (vec0's KNN always returns its k nearest, however
# irrelevant), so these test `suggestion_service`'s own filtering logic directly against a
# known, controlled `hybrid_search_service.search` result set.
def test_suggest_codex_links_filters_by_relevance_floor(
    client: TestClient, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene_id = _create_scene(client, "Floor Filter Codex Test Scene")
    floor = suggestion_service.SUGGESTION_RELEVANCE_FLOOR
    fake_results = [
        SearchResult(
            entity_type="codex_entry",
            entity_id="above-floor",
            title="Above Floor",
            snippet=None,
            score=floor + 0.001,
            book_ids=[],
        ),
        SearchResult(
            entity_type="codex_entry",
            entity_id="below-floor",
            title="Below Floor",
            snippet=None,
            score=floor - 0.001,
            book_ids=[],
        ),
    ]
    monkeypatch.setattr(
        suggestion_service.hybrid_search_service, "search", lambda *a, **k: fake_results
    )

    suggestions = suggestion_service.suggest_codex_links(db, scene_id)
    ids = {s.codex_entry_id for s in suggestions}
    assert ids == {"above-floor"}


def test_suggest_similar_scenes_filters_by_relevance_floor(
    client: TestClient, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene_id = _create_scene(client, "Floor Filter Similar Scene Test Scene")
    floor = suggestion_service.SUGGESTION_RELEVANCE_FLOOR
    fake_results = [
        SearchResult(
            entity_type="scene",
            entity_id="scene-above-floor",
            title="Above Floor Scene",
            snippet=None,
            score=floor + 0.001,
            book_ids=[],
        ),
        SearchResult(
            entity_type="scene",
            entity_id="scene-below-floor",
            title="Below Floor Scene",
            snippet=None,
            score=floor - 0.001,
            book_ids=[],
        ),
    ]
    monkeypatch.setattr(
        suggestion_service.hybrid_search_service, "search", lambda *a, **k: fake_results
    )

    suggestions = suggestion_service.suggest_similar_scenes(db, scene_id)
    ids = {s.scene_id for s in suggestions}
    assert ids == {"scene-above-floor"}


def test_suggest_similar_scenes_excludes_itself_even_above_floor(
    client: TestClient, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene_id = _create_scene(client, "Self Exclusion Above Floor Test Scene")
    floor = suggestion_service.SUGGESTION_RELEVANCE_FLOOR
    fake_results = [
        # The scene ranked as its own top match (as it always is against real embeddings —
        # identical text is its own nearest neighbour) must still never appear in its own
        # suggestion list.
        SearchResult(
            entity_type="scene",
            entity_id=scene_id,
            title="Self",
            snippet=None,
            score=floor + 0.01,
            book_ids=[],
        ),
        SearchResult(
            entity_type="scene",
            entity_id="genuinely-other-scene",
            title="Other",
            snippet=None,
            score=floor + 0.001,
            book_ids=[],
        ),
    ]
    monkeypatch.setattr(
        suggestion_service.hybrid_search_service, "search", lambda *a, **k: fake_results
    )

    suggestions = suggestion_service.suggest_similar_scenes(db, scene_id)
    ids = {s.scene_id for s in suggestions}
    assert scene_id not in ids
    assert ids == {"genuinely-other-scene"}


def test_suggest_codex_links_respects_limit(
    client: TestClient, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene_id = _create_scene(client, "Limit Respecting Test Scene")
    floor = suggestion_service.SUGGESTION_RELEVANCE_FLOOR
    fake_results = [
        SearchResult(
            entity_type="codex_entry",
            entity_id=f"entry-{i}",
            title=f"Entry {i}",
            snippet=None,
            score=floor + (0.01 - i * 0.001),  # descending, all above floor
            book_ids=[],
        )
        for i in range(10)
    ]
    monkeypatch.setattr(
        suggestion_service.hybrid_search_service, "search", lambda *a, **k: fake_results
    )

    suggestions = suggestion_service.suggest_codex_links(db, scene_id, limit=3)
    assert len(suggestions) == 3


# ── Route shape ───────────────────────────────────────────────────────────────────
def test_suggestions_route_returns_both_lists_correctly_shaped(client: TestClient) -> None:
    entry_id = _create_codex_entry(client, "Sylvenmoor", "A quiet forest lore entry.")
    scene_id = _create_scene(client, "Sylvenmoor Awakens", "Sylvenmoor stirs before the storm.")

    resp = client.get(f"/search/scenes/{scene_id}/suggestions")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"codex_link_suggestions", "similar_scenes"}
    assert isinstance(body["codex_link_suggestions"], list)
    assert isinstance(body["similar_scenes"], list)
    assert any(s["codex_entry_id"] == entry_id for s in body["codex_link_suggestions"])
    for s in body["codex_link_suggestions"]:
        assert {"codex_entry_id", "name", "snippet", "score"} <= set(s.keys())
    for s in body["similar_scenes"]:
        assert {"scene_id", "title", "snippet", "score"} <= set(s.keys())


def test_suggestions_route_404s_on_unknown_scene(client: TestClient) -> None:
    resp = client.get("/search/scenes/not-a-real-scene-id/suggestions")
    assert resp.status_code == 404
