"""Auto codex-link suggestions + similar-scene detection (Phase 10 task 5, PHASE10.md,
docs/11-AI-INTELLIGENCE.md §2 "auto codex-link suggestions on node save" /
"similar-scene detection surfaced when creating new nodes").

Both functions here are thin wrappers over `hybrid_search_service.search` — they don't add a
new retrieval mechanism, just a query shape (a Scene's own title+description) and two
post-filters: exclude irrelevant/self/already-linked candidates, and drop anything below a
relevance floor so the library's whole contents don't show up as "suggestions".

## Suggestions only — never auto-applied

This app's hard rule is Accept/Reject on every AI-adjacent transform (PROJECT-MAP.md §9,
`enhance-diff.tsx` is the canonical pattern). Nothing here is LLM-generated, but the same
posture applies: these functions are read-only and never write a `CodexSceneLink` or any
other row themselves — they return candidates for a human to accept or ignore. The frontend
piece that turns an entry in this list into an actual link (Phase 10 task 7, deferred) must
go through the existing explicit link-creation path (`codex_service.link_scene`), never a
shortcut invented here.

## Choosing the relevance floor

`hybrid_search_service.search`'s RRF fusion score for a candidate is
``sum(1 / (RRF_K + rank))`` across whichever leg(s) it appears in (RRF_K=60). The vector leg
(vec0 KNN) always returns its ``k`` nearest neighbours regardless of whether any of them are
actually relevant — sqlite-vec's MATCH doesn't have a "no match" concept — so a raw RRF score
alone can't distinguish "genuinely relevant" from "closest of a bad lot" if a candidate is
allowed to be arbitrarily deep in the vector leg's ranking. `SUGGESTION_RELEVANCE_FLOOR` is
therefore set at the score a candidate would get from a single leg's rank-``_RELEVANCE_RANK_
CUTOFF`` position (``1 / (RRF_K + _RELEVANCE_RANK_CUTOFF)``) — i.e. a candidate must rank
within the top `_RELEVANCE_RANK_CUTOFF` of at least one retrieval leg (FTS keyword match or
vector nearest-neighbour) to be surfaced at all. Below that, treat it as noise rather than a
suggestion. This is deliberately conservative (a real suggestion feature nagging with weak
matches erodes trust fast); it can be tuned once this runs against real embeddings on the
ASUS TUF F15.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orm import CodexSceneLink, Scene
from app.models.schemas import CodexLinkSuggestion, SimilarSceneSuggestion
from app.services import hybrid_search_service

# See module docstring "Choosing the relevance floor".
_RELEVANCE_RANK_CUTOFF = 10
SUGGESTION_RELEVANCE_FLOOR = 1.0 / (hybrid_search_service.RRF_K + _RELEVANCE_RANK_CUTOFF)

# How many extra candidates to pull from the underlying hybrid search beyond the caller's
# requested `limit`, so that excluding already-linked codex entries / the scene itself still
# leaves enough left over to fill `limit` suggestions.
_CANDIDATE_OVERFETCH = 20

# See `_build_query`'s docstring: words shorter than this are treated as filler and dropped
# when building the OR-query, since distinctive terms (character/location names, etc.) this
# feature cares about are almost always at least this long, while common filler ("the",
# "and", "with", "that") is not.
_MIN_QUERY_WORD_LENGTH = 5

# Cap on how many distinct words feed the OR-query, so a very long scene description doesn't
# turn into an unbounded FTS5 MATCH expression.
_MAX_QUERY_TERMS = 20

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _build_query(scene: Scene) -> str:
    """Builds the query string passed to `hybrid_search_service.search` for both its FTS5
    and vector legs, from this Scene's own title+description (the same "title\\n\\nbody, no
    arbitrary splitting" join `search_index_service.upsert_entity` used to index it).

    FTS5's MATCH defaults to implicit AND across bareword query terms — passing an entire
    scene's title+description straight through would require a candidate row to contain
    *every* word of that (often long) text, which essentially never happens for a different
    Scene/CodexEntry row (verified directly: a scene mentioning a codex entry's distinctive
    name produces zero FTS5 matches if the raw paragraph is passed as-is, since the entry's
    own short text can't possibly contain all of the scene's other words too). What this
    feature actually wants is "does this candidate share ANY distinctive word with this
    scene" — an OR, not an AND — so this builds an explicit ``"word1" OR "word2" OR ...``
    FTS5 query from the scene's distinctive words. Each term is individually double-quoted so
    a word that happens to collide with an FTS5 keyword (``OR``, ``NOT``, ``NEAR``, ...) is
    still parsed as a literal term rather than query syntax.

    The same string is also what `hybrid_search_service.search` embeds for its vector leg —
    an OR-joined keyword list isn't as natural a query for a real embedding model as prose
    would be, but this module has no lower-level seam to give the two legs different query
    strings without duplicating `hybrid_search_service.search`'s fusion/hydration logic. That
    trade-off is fine for the stub (any distinct text yields a distinct vector) and can be
    revisited once this runs against real embeddings on the ASUS TUF F15.

    Falls back to the raw title+body if no word clears the length filter (e.g. an
    all-short-words title).
    """
    text = f"{scene.title}\n\n{scene.description}" if scene.description else scene.title
    seen: set[str] = set()
    terms: list[str] = []
    for word in _WORD_RE.findall(text):
        lowered = word.lower()
        if len(word) < _MIN_QUERY_WORD_LENGTH or lowered in seen:
            continue
        seen.add(lowered)
        terms.append(lowered)
        if len(terms) >= _MAX_QUERY_TERMS:
            break
    if not terms:
        return text
    return " OR ".join(f'"{term}"' for term in terms)


def suggest_codex_links(
    db: Session, scene_id: str, limit: int = 5
) -> list[CodexLinkSuggestion]:
    """Codex entries this Scene's text mentions/resembles, that aren't already linked to it.

    Raises ``ValueError("SCENE_NOT_FOUND")`` if ``scene_id`` doesn't exist (mirroring
    `hybrid_search_service.search`'s ``ValueError`` + string-code convention for
    route-mappable errors).
    """
    scene = db.get(Scene, scene_id)
    if scene is None:
        raise ValueError("SCENE_NOT_FOUND")

    already_linked_ids = {
        row.codex_entry_id
        for row in db.execute(
            select(CodexSceneLink.codex_entry_id).where(CodexSceneLink.scene_id == scene_id)
        )
    }

    candidates = hybrid_search_service.search(
        db,
        _build_query(scene),
        limit=limit + _CANDIDATE_OVERFETCH,
        entity_type="codex_entry",
    )

    suggestions: list[CodexLinkSuggestion] = []
    for result in candidates:
        if result.score < SUGGESTION_RELEVANCE_FLOOR:
            break  # `candidates` is score-sorted descending; nothing after this clears the floor
        if result.entity_id in already_linked_ids:
            continue
        suggestions.append(
            CodexLinkSuggestion(
                codex_entry_id=result.entity_id,
                name=result.title,
                snippet=result.snippet,
                score=result.score,
            )
        )
        if len(suggestions) >= limit:
            break
    return suggestions


def suggest_similar_scenes(
    db: Session, scene_id: str, limit: int = 3
) -> list[SimilarSceneSuggestion]:
    """Other Scenes that resemble this one closely enough to flag as a possible
    near-duplicate — excludes the scene itself.

    Raises ``ValueError("SCENE_NOT_FOUND")`` if ``scene_id`` doesn't exist.
    """
    scene = db.get(Scene, scene_id)
    if scene is None:
        raise ValueError("SCENE_NOT_FOUND")

    candidates = hybrid_search_service.search(
        db,
        _build_query(scene),
        limit=limit + _CANDIDATE_OVERFETCH,
        entity_type="scene",
    )

    suggestions: list[SimilarSceneSuggestion] = []
    for result in candidates:
        if result.score < SUGGESTION_RELEVANCE_FLOOR:
            break
        if result.entity_id == scene_id:
            continue
        suggestions.append(
            SimilarSceneSuggestion(
                scene_id=result.entity_id,
                title=result.title,
                snippet=result.snippet,
                score=result.score,
            )
        )
        if len(suggestions) >= limit:
            break
    return suggestions
