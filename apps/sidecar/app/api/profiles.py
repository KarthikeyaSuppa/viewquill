"""/profiles — local profile picker (docs/13-PROFILES-AND-AUTH.md §Endpoints).

Both endpoints are PUBLIC (no auth): the picker needs to list profiles before anyone is
logged in, and profile creation is how the very first profile gets made. This is a
UI/profile LOCK, not encryption — see the doc for the full rationale.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import ProfileCreate, ProfilePublic
from app.services import profiles_service

router = APIRouter(prefix="/profiles", tags=["profiles"])

_ERROR_DETAILS = {
    "MAX_PROFILES": (status.HTTP_409_CONFLICT, "Maximum of 2 profiles reached."),
    "DUPLICATE_USERNAME": (status.HTTP_409_CONFLICT, "That username is already taken."),
    "INVALID": (status.HTTP_422_UNPROCESSABLE_ENTITY, "Username and password are required."),
}


@router.get("", response_model=list[ProfilePublic])
def list_profiles(db: Session = Depends(get_db)) -> list[ProfilePublic]:
    return [ProfilePublic.model_validate(user) for user in profiles_service.list_profiles(db)]


@router.post("", response_model=ProfilePublic, status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfileCreate, db: Session = Depends(get_db)) -> ProfilePublic:
    try:
        user = profiles_service.create_profile(
            db,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            avatar=payload.avatar,
        )
    except ValueError as exc:
        status_code, detail = _ERROR_DETAILS[str(exc)]
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return ProfilePublic.model_validate(user)
