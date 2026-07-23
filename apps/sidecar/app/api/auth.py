"""/auth — login/session for local profiles (docs/13-PROFILES-AND-AUTH.md §Auth mechanics,
§Endpoints).

This is a UI/profile LOCK, not encryption. Sessions are an in-memory ``{token: user_id}``
map (``app/services/sessions_service.py``) — never persisted, never logged. The frontend
sends ``Authorization: Bearer <token>``.

``get_current_user`` is the shared dependency other routers (e.g. ``/settings``, BE-C) use
to require a bearer session: ``from app.api.auth import get_current_user``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.orm import User
from app.models.schemas import LoginRequest, LoginResponse, ProfilePublic
from app.services import profiles_service, sessions_service

router = APIRouter(prefix="/auth", tags=["auth"])

_NOT_AUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated."
)
_INVALID_SESSION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session."
)


def _extract_token(authorization: str | None) -> str:
    """Parses a ``Bearer <token>`` header (case-insensitive scheme). Raises 401 if missing
    or malformed. Never logs the token."""
    if not authorization:
        raise _NOT_AUTHENTICATED
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise _NOT_AUTHENTICATED
    return parts[1].strip()


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Shared bearer-auth dependency. Resolves the token to a session, then to a live
    profile row; 401s if either lookup fails."""
    token = _extract_token(authorization)
    user_id = sessions_service.resolve(token)
    if user_id is None:
        raise _INVALID_SESSION
    user = profiles_service.get_by_id(db, user_id)
    if user is None:
        raise _INVALID_SESSION
    return user


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = profiles_service.authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
        )
    token = sessions_service.create_session(user.id)
    return LoginResponse(token=token, user=ProfilePublic.model_validate(user))


@router.get("/me", response_model=ProfilePublic)
def me(current_user: User = Depends(get_current_user)) -> ProfilePublic:
    return ProfilePublic.model_validate(current_user)


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    token = _extract_token(authorization)
    sessions_service.revoke(token)
    return {"ok": True}
