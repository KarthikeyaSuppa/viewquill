"""/search — Phase 10 semantic layer: bulk backfill (task 3) + hybrid RRF search (task 4),
PHASE10.md, docs/11-AI-INTELLIGENCE.md §2.

Scene/CodexEntry create/update/delete already keep `search_fts`/`embeddings` current via
scene_service.py/codex_service.py's embed-on-save hooks into
app/services/search_index_service.py — the backfill endpoint exists only to catch up rows
that predate those hooks (or to re-derive every row from scratch, e.g. after a future
embedding model swap on the ASUS TUF F15).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import SceneSuggestionsResponse, SearchBackfillResponse, SearchResult
from app.services import hybrid_search_service, search_index_service, suggestion_service

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/backfill", response_model=SearchBackfillResponse)
def backfill(db: Session = Depends(get_db)) -> SearchBackfillResponse:
    counts = search_index_service.backfill_all(db)
    return SearchBackfillResponse(**counts)


@router.get("", response_model=list[SearchResult])
def search(
    q: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
    entity_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[SearchResult]:
    """Hybrid FTS5 + vector search (app/services/hybrid_search_service.py) over Scene/
    CodexEntry rows, fused via Reciprocal Rank Fusion. Not Book-scoped — see that module's
    docstring for why. ``q=""`` (or omitted) returns ``[]`` rather than erroring, matching
    a search box with nothing typed into it yet."""
    try:
        return hybrid_search_service.search(db, q, limit=limit, entity_type=entity_type)
    except ValueError as exc:
        if str(exc) == "INVALID_ENTITY_TYPE":
            raise HTTPException(
                status_code=422,
                detail="entity_type must be 'scene' or 'codex_entry'",
            ) from exc
        raise


@router.get("/scenes/{scene_id}/suggestions", response_model=SceneSuggestionsResponse)
def scene_suggestions(
    scene_id: str,
    codex_limit: int = Query(default=5, ge=1, le=50),
    similar_scene_limit: int = Query(default=3, ge=1, le=50),
    db: Session = Depends(get_db),
) -> SceneSuggestionsResponse:
    """Read-only suggestions for one Scene (Phase 10 task 5): Codex entries it mentions/
    resembles but isn't linked to yet, and other Scenes it closely resembles (possible
    near-duplicates). Kept in `search.py` rather than `scenes.py` since both lists are built
    entirely on `hybrid_search_service`/`suggestion_service` — no other scene-route
    dependency — and this is where the rest of the Phase 10 search surface already lives.

    Suggestions only, never auto-applied — see `suggestion_service`'s module docstring.
    """
    try:
        codex_link_suggestions = suggestion_service.suggest_codex_links(
            db, scene_id, limit=codex_limit
        )
        similar_scenes = suggestion_service.suggest_similar_scenes(
            db, scene_id, limit=similar_scene_limit
        )
    except ValueError as exc:
        if str(exc) == "SCENE_NOT_FOUND":
            raise HTTPException(status_code=404, detail="Scene not found") from exc
        raise
    return SceneSuggestionsResponse(
        codex_link_suggestions=codex_link_suggestions,
        similar_scenes=similar_scenes,
    )
