"""Hybrid RRF search — FTS5 keyword rank + vec0 KNN vector rank fused via Reciprocal Rank
Fusion (Phase 10 task 4, PHASE10.md, docs/11-AI-INTELLIGENCE.md §2 "Hybrid retrieval
(vectors + keywords, fused)", following the FTS5+vector RRF pattern docs/11 cites at
https://ceaksan.com/en/hybrid-search-fts5-vector-rrf).

## Why this search is NOT scoped to a single `book_id`

Scene and CodexEntry rows are canonical and shared across Books — `scene_service.py`/
`codex_service.py`'s module docstrings both say so, and neither `scenes` nor
`codex_entries` (app/models/orm.py) has a `book_id` column: a Scene/CodexEntry can belong
to zero, one, or many Books via the many-to-many `book_scene_links`/`book_codex_links`
join tables. docs/11 §2 explicitly frames semantic search this way too ("Semantic search:
'find scenes where someone betrays someone' — across the whole library"), matching
PROJECT-MAP.md's "one shared live Story Library database for instant cross-Book reuse"
framing. Forcing a `book_id` filter here would require an arbitrary "pick one Book" rule
for multiply-linked entities, contradicting that shared-library model — so this service
searches the whole library and instead reports every Book each result is currently linked
to (`SearchResult.book_ids`), letting a caller filter/display Book context client-side
without narrowing the search itself.

## The RRF formula

Two independently-ranked lists are computed — FTS5 bm25 keyword rank over `search_fts`,
and vec0 KNN distance rank over `embeddings` — then fused into one score per
(entity_type, entity_id):

    score = sum(1 / (RRF_K + rank))

summed across whichever list(s) the result appears in, ``rank`` being the 1-based position
in that list. No score normalization needed (RRF's whole point) — a result appearing near
the top of BOTH lists outranks one appearing in only one, per docs/11 §2's exact formula
(``score = Σ 1/(60 + rank)``). ``RRF_K=60`` is both the standard constant from the original
RRF paper and the literal value docs/11 §2 specifies, kept as a module constant since it's
a tunable rather than a magic number buried in the fusion loop.
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.base import engine
from app.models.orm import BookCodexLink, BookSceneLink, CodexEntry, Scene
from app.models.schemas import SearchResult
from app.services.embedding_service import embed, pack_embedding

# Standard RRF constant; docs/11-AI-INTELLIGENCE.md §2 specifies this exact value.
RRF_K = 60

# How much of each entity's body text to surface as a result "snippet" — just enough for a
# frontend list item, not the full text (the caller can fetch the full Scene/CodexEntry by
# id if they need more).
_SNIPPET_LENGTH = 200

VALID_ENTITY_TYPES = ("scene", "codex_entry")

EntityKey = tuple[str, str]  # (entity_type, entity_id)


def _snippet(body: str | None) -> str | None:
    if not body:
        return None
    if len(body) <= _SNIPPET_LENGTH:
        return body
    return body[:_SNIPPET_LENGTH].rstrip() + "…"


def _fts_ranked_keys(query: str, limit: int, entity_type: str | None) -> list[EntityKey]:
    """(entity_type, entity_id) pairs ranked by FTS5's built-in bm25 `rank`, best match
    first. Returns an empty list (rather than raising) on a malformed MATCH query — FTS5's
    query syntax treats bare characters like unmatched quotes or leading operators as
    syntax errors, and a free-text search box shouldn't 500 just because the user typed
    something FTS5's parser doesn't like; the vector leg below still runs independently."""
    sql = "SELECT entity_type, entity_id FROM search_fts WHERE search_fts MATCH :query"
    params: dict[str, object] = {"query": query, "limit": limit}
    if entity_type is not None:
        sql += " AND entity_type = :entity_type"
        params["entity_type"] = entity_type
    sql += " ORDER BY rank LIMIT :limit"

    with engine.connect() as conn:
        try:
            rows = conn.execute(text(sql), params).fetchall()
        except Exception:
            return []
    return [(row.entity_type, row.entity_id) for row in rows]


def _vector_ranked_keys(query: str, limit: int, entity_type: str | None) -> list[EntityKey]:
    """(entity_type, entity_id) pairs ranked by vec0 KNN distance, closest first."""
    packed = pack_embedding(embed(query))
    sql = (
        "SELECT entity_type, entity_id FROM embeddings "
        "WHERE embedding MATCH :embedding AND k = :limit"
    )
    params: dict[str, object] = {"embedding": packed, "limit": limit}
    if entity_type is not None:
        sql += " AND entity_type = :entity_type"
        params["entity_type"] = entity_type
    sql += " ORDER BY distance"

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [(row.entity_type, row.entity_id) for row in rows]


def _fuse(fts_keys: list[EntityKey], vector_keys: list[EntityKey]) -> list[tuple[EntityKey, float]]:
    scores: dict[EntityKey, float] = {}
    for rank, key in enumerate(fts_keys, start=1):
        scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
    for rank, key in enumerate(vector_keys, start=1):
        scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def _book_ids_by_scene(db: Session, scene_ids: list[str]) -> dict[str, list[str]]:
    if not scene_ids:
        return {}
    rows = db.execute(
        select(BookSceneLink.scene_id, BookSceneLink.book_id).where(
            BookSceneLink.scene_id.in_(scene_ids)
        )
    ).all()
    out: dict[str, list[str]] = {}
    for scene_id, book_id in rows:
        out.setdefault(scene_id, []).append(book_id)
    return out


def _book_ids_by_codex_entry(db: Session, entry_ids: list[str]) -> dict[str, list[str]]:
    if not entry_ids:
        return {}
    rows = db.execute(
        select(BookCodexLink.codex_entry_id, BookCodexLink.book_id).where(
            BookCodexLink.codex_entry_id.in_(entry_ids)
        )
    ).all()
    out: dict[str, list[str]] = {}
    for entry_id, book_id in rows:
        out.setdefault(entry_id, []).append(book_id)
    return out


def search(
    db: Session,
    query: str,
    limit: int = 20,
    entity_type: str | None = None,
) -> list[SearchResult]:
    """Hybrid FTS5 + vector search over `search_fts`/`embeddings`, fused via RRF, resolved
    back to the actual Scene/CodexEntry rows (title/snippet/linked Books) so the response is
    directly usable by a frontend result list.

    ``entity_type``, if given, must be ``"scene"`` or ``"codex_entry"`` — raises
    ``ValueError("INVALID_ENTITY_TYPE")`` otherwise (mirroring the ``ValueError`` + string-
    code convention `codex_service.py`'s `create_relationship`/`create_arc_state` use for
    route-mappable errors).

    An empty/whitespace-only ``query`` returns ``[]`` rather than erroring — both underlying
    legs (an empty FTS5 MATCH, an embedding of an empty string) are meaningless queries, not
    error conditions, so "no results" is the right answer for a search box a user hasn't
    typed into yet.
    """
    query = (query or "").strip()
    if entity_type is not None and entity_type not in VALID_ENTITY_TYPES:
        raise ValueError("INVALID_ENTITY_TYPE")
    if not query:
        return []

    fts_keys = _fts_ranked_keys(query, limit, entity_type)
    vector_keys = _vector_ranked_keys(query, limit, entity_type)
    ranked = _fuse(fts_keys, vector_keys)[:limit]
    if not ranked:
        return []

    scene_ids = [entity_id for (etype, entity_id), _ in ranked if etype == "scene"]
    entry_ids = [entity_id for (etype, entity_id), _ in ranked if etype == "codex_entry"]

    scenes_by_id = {
        scene.id: scene
        for scene in (
            db.execute(select(Scene).where(Scene.id.in_(scene_ids))).scalars()
            if scene_ids
            else []
        )
    }
    entries_by_id = {
        entry.id: entry
        for entry in (
            db.execute(select(CodexEntry).where(CodexEntry.id.in_(entry_ids))).scalars()
            if entry_ids
            else []
        )
    }
    scene_book_ids = _book_ids_by_scene(db, scene_ids)
    entry_book_ids = _book_ids_by_codex_entry(db, entry_ids)

    results: list[SearchResult] = []
    for (etype, entity_id), score in ranked:
        if etype == "scene":
            scene = scenes_by_id.get(entity_id)
            # A stale index row (e.g. indexed then the Scene was deleted through a path
            # that bypassed scene_service.delete_scene's search_index_service cleanup) —
            # skip rather than error; the next backfill re-syncs the index.
            if scene is None:
                continue
            results.append(
                SearchResult(
                    entity_type="scene",
                    entity_id=entity_id,
                    title=scene.title,
                    snippet=_snippet(scene.description),
                    score=score,
                    book_ids=scene_book_ids.get(entity_id, []),
                )
            )
        else:
            entry = entries_by_id.get(entity_id)
            if entry is None:
                continue
            results.append(
                SearchResult(
                    entity_type="codex_entry",
                    entity_id=entity_id,
                    title=entry.name,
                    snippet=_snippet(entry.summary),
                    score=score,
                    book_ids=entry_book_ids.get(entity_id, []),
                )
            )
    return results
