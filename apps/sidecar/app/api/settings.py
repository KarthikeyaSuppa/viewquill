"""/settings — read and patch the app_settings key/value store.

The frontend hydrates its theme, fonts, spacing, delight level, and AI mode from here on
launch. Secrets never pass through this endpoint (docs/03, docs/08).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import SettingsResponse, SettingsUpdate
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)) -> SettingsResponse:
    return SettingsResponse(values=settings_service.get_all_settings(db))


@router.patch("", response_model=SettingsResponse)
def patch_settings(payload: SettingsUpdate, db: Session = Depends(get_db)) -> SettingsResponse:
    return SettingsResponse(values=settings_service.update_settings(db, payload.values))
