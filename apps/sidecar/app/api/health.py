"""/health — the readiness probe Tauri polls before showing the window (docs/06 Phase 0)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.db.base import get_db
from app.models.schemas import HealthResponse
from app.services.ollama_health import check_ollama

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001 — health must never raise
        database = "error"

    ollama = check_ollama()
    status = "ok" if database == "ok" else "degraded"
    return HealthResponse(
        status=status,
        version=__version__,
        database=database,
        ollama=ollama,
    )
