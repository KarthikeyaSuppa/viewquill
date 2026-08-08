"""LAN Notes — a shared scratch-note per ``channel``, last-write-wins (docs/03-DATA-MODEL.md
`notes`; app/models/orm.py `Note`).

``apply_note`` is the single source of truth for the LWW merge rule and is deliberately kept
pure of any HTTP concerns (session in, ORM row out) — it will later be called from BOTH the
local route (app/api/notes.py) and a separate LAN server that isn't built yet, and both must
resolve conflicts identically.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orm import Note
from app.models.schemas import NoteWrite

DESKTOP_DEVICE_ID = "desktop-local"


def get_note(db: Session, channel: str) -> Note:
    """Returns the ``channel`` row, creating an empty one on first read.

    The empty row's own ``updated_at`` starts at 0 (the oldest possible LWW clock value) so
    the very first real write — whatever its timestamp — is always newer and always applies.
    """
    note = db.execute(select(Note).where(Note.channel == channel)).scalar_one_or_none()
    if note is None:
        note = Note(channel=channel, content="", updated_at=0, updated_by=DESKTOP_DEVICE_ID, rev=0)
        db.add(note)
        db.commit()
    return note


def apply_note(db: Session, channel: str, payload: NoteWrite) -> Note:
    """Last-write-wins: applies ``payload`` only if its clock is strictly newer than the
    row's current ``updated_at``. A tie or an older clock is a no-op — the existing row is
    returned unchanged (never silently overwritten by a stale/out-of-order write)."""
    note = get_note(db, channel)
    if payload.updated_at > note.updated_at:
        note.content = payload.content
        note.updated_at = payload.updated_at
        note.updated_by = payload.updated_by
        note.rev += 1
        db.commit()
    return note
