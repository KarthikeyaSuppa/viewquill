"""llm_request_log read/write — the trust/audit trail for every LLM call (docs/03-DATA-MODEL.md
`llm_request_log`, docs/06 Phase 2 task D2).

Every Enhance call gets exactly one row: created (accepted=None) before the stream starts,
finished (provider/model_name/latency_ms filled in) once the stream completes or errors, and
optionally flipped to accepted=True/False by a later, separate client action (Accept/Reject —
never implied by this module). This module performs NO writes to `scenes` or
`screenplay_elements` — it only ever touches `llm_request_log`.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.base import new_uuid
from app.models.orm import LlmRequestLog


def start_log(
    db: Session,
    *,
    request_type: str | None,
    entity_type: str | None,
    entity_id: str | None,
    book_id: str | None,
    provider: str | None = None,
    model_name: str | None = None,
) -> str:
    """Create the audit row before the stream starts. ``accepted`` starts as None — it is
    only ever set later via :func:`set_accepted`, driven by an explicit client action."""
    log = LlmRequestLog(
        id=new_uuid(),
        request_type=request_type,
        entity_type=entity_type,
        entity_id=entity_id,
        book_id=book_id,
        provider=provider,
        model_name=model_name,
        accepted=None,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log.id


def finish_log(
    db: Session,
    log_id: str,
    *,
    provider: str | None,
    model_name: str | None,
    latency_ms: int,
) -> LlmRequestLog | None:
    """Fill in the outcome fields once the stream has completed (successfully or not)."""
    log = db.get(LlmRequestLog, log_id)
    if log is None:
        return None
    log.provider = provider
    log.model_name = model_name
    log.latency_ms = latency_ms
    db.commit()
    db.refresh(log)
    return log


def get_log(db: Session, log_id: str) -> LlmRequestLog | None:
    return db.get(LlmRequestLog, log_id)


def set_accepted(db: Session, log_id: str, accepted: bool) -> LlmRequestLog | None:
    """Record the author's Accept/Reject decision. This is the ONLY place `accepted` is
    ever set — it is always driven by an explicit client call, never inferred."""
    log = db.get(LlmRequestLog, log_id)
    if log is None:
        return None
    log.accepted = int(accepted)
    db.commit()
    db.refresh(log)
    return log
