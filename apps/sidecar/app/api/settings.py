"""/settings — read and patch the app_settings key/value store.

The frontend hydrates its theme, fonts, spacing, delight level, and AI mode from here on
launch. Secrets never pass through this endpoint (docs/03, docs/08).

Per docs/13-PROFILES-AND-AUTH.md §Endpoints, this router is now BEARER-protected: personal
keys (``settings_service.PER_USER_KEYS``) route to the current profile, everything else
stays global/shared.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.base import get_db
from app.models.orm import User
from app.models.schemas import SettingsResponse, SettingsUpdate
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(
    db: Session = Depends(get_db), current: User = Depends(get_current_user)
) -> SettingsResponse:
    return SettingsResponse(values=settings_service.get_all_settings(db, user_id=current.id))


@router.patch("", response_model=SettingsResponse)
def patch_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> SettingsResponse:
    return SettingsResponse(
        values=settings_service.update_settings(db, payload.values, user_id=current.id)
    )
