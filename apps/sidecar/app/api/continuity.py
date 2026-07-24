"""/books/{book_id}/continuity and /continuity/flags — Continuity Checker v2, Tier 1 + Tier 2
(docs/11-AI-INTELLIGENCE.md §4, docs/06 Phase 4 tasks BE-4/BE-5).

``POST /books/{book_id}/continuity/check`` always recomputes the Book's deterministic flags
(pure SQL, zero LLM — see app/services/continuity_service.py's ``run_tier1``). Passing
``?include_ai=true`` additionally runs Tier 2 (semantic, LLM-guarded — ``run_tier2``) on the
same call. This is intentionally the single "run continuity checks" endpoint, with Tier 2
opt-in via a query flag rather than a separate route, so Tier 1's default cost stays zero-LLM
and callers choose when to pay for the (guarded) semantic pass.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import ContinuityFlagRead, FlagStatusUpdate
from app.services import continuity_service

router = APIRouter(tags=["continuity"])


def _handle_value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code == "BOOK_NOT_FOUND":
        return HTTPException(status_code=404, detail="Book not found")
    if code == "INVALID_STATUS":
        return HTTPException(status_code=422, detail="Invalid flag status")
    raise exc


@router.post("/books/{book_id}/continuity/check", response_model=list[ContinuityFlagRead])
async def run_continuity_check(
    book_id: str,
    include_ai: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[ContinuityFlagRead]:
    """Runs Tier-1 deterministic checks always (cheap, zero LLM). Tier-2 semantic checks
    (docs/11-AI-INTELLIGENCE.md §4 "Tier 2", task BE-5) only run when ``include_ai=true`` is
    passed — this keeps the default check free of any LLM call, with Tier 2 opt-in on this
    same route rather than a separate endpoint."""
    try:
        flags = continuity_service.run_tier1(db, book_id)
        if include_ai:
            flags = await continuity_service.run_tier2(db, book_id)
    except ValueError as exc:
        raise _handle_value_error(exc) from exc
    return [ContinuityFlagRead.model_validate(flag) for flag in flags]


@router.get("/books/{book_id}/continuity/flags", response_model=list[ContinuityFlagRead])
def list_continuity_flags(
    book_id: str, status: str | None = Query(default=None), db: Session = Depends(get_db)
) -> list[ContinuityFlagRead]:
    return [
        ContinuityFlagRead.model_validate(flag)
        for flag in continuity_service.list_flags(db, book_id, status=status)
    ]


@router.patch("/continuity/flags/{flag_id}", response_model=ContinuityFlagRead)
def update_continuity_flag_status(
    flag_id: str, payload: FlagStatusUpdate, db: Session = Depends(get_db)
) -> ContinuityFlagRead:
    try:
        flag = continuity_service.update_flag_status(db, flag_id, payload.status)
    except ValueError as exc:
        raise _handle_value_error(exc) from exc
    if flag is None:
        raise HTTPException(status_code=404, detail="Continuity flag not found")
    return ContinuityFlagRead.model_validate(flag)
