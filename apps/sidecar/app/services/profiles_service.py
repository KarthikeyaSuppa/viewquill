"""Profile CRUD over the ``users`` table (docs/13-PROFILES-AND-AUTH.md).

This is a UI/profile LOCK, not encryption — the SQLite database stays plaintext on disk.
Up to two local profiles share one Story Library; see the doc for the full rationale.
Passwords are always hashed via ``app/services/password_service.py`` — never handled here
in the clear beyond the function argument itself, and never logged.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import new_uuid
from app.models.orm import User
from app.services import password_service

MAX_PROFILES = 2


def list_profiles(db: Session) -> list[User]:
    stmt = (
        select(User)
        .where(User.is_active == 1)
        .order_by(User.created_at.asc())
    )
    return list(db.execute(stmt).scalars())


def count_profiles(db: Session) -> int:
    stmt = select(func.count()).select_from(User).where(User.is_active == 1)
    return db.execute(stmt).scalar_one()


def get_by_username(db: Session, username: str) -> User | None:
    normalized = username.strip().lower()
    stmt = select(User).where(func.lower(User.username) == normalized)
    return db.execute(stmt).scalar_one_or_none()


def get_by_id(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def create_profile(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    avatar: str | None = None,
) -> User:
    """Creates a new local profile.

    Raises ``ValueError`` with one of: ``"INVALID"`` (empty username/password),
    ``"MAX_PROFILES"`` (already at the 2-profile cap), ``"DUPLICATE_USERNAME"`` (case-
    insensitive collision).
    """
    username = username.strip()
    if not username or not password:
        raise ValueError("INVALID")
    if count_profiles(db) >= MAX_PROFILES:
        raise ValueError("MAX_PROFILES")
    if get_by_username(db, username) is not None:
        raise ValueError("DUPLICATE_USERNAME")

    user = User(
        id=new_uuid(),
        username=username,
        password_hash=password_service.hash_password(password),
        display_name=display_name,
        avatar=avatar,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Returns the matching active ``User`` on success, else ``None``. Never raises."""
    user = get_by_username(db, username)
    if user is None or not user.is_active:
        return None
    if not password_service.verify_password(password, user.password_hash):
        return None
    return user
