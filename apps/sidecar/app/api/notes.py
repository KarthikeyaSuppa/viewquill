"""/notes/{channel} — the local (127.0.0.1-only) side of the LAN Notes shared scratch-note
(docs/03-DATA-MODEL.md `notes`; app/services/notes_service.py).

``channel`` is a path param today ('lan' is the only value in use) so a later LAN server can
reuse the exact same `notes_service.apply_note` merge rule against additional channels without
a schema change here. No networking/binding beyond this app's existing 127.0.0.1 host lives in
this module — that's a later task.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import NoteRead, NoteWrite
from app.services import notes_service

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("/{channel}", response_model=NoteRead)
def get_note(channel: str, db: Session = Depends(get_db)) -> NoteRead:
    return NoteRead.model_validate(notes_service.get_note(db, channel))


@router.put("/{channel}", response_model=NoteRead)
def put_note(channel: str, payload: NoteWrite, db: Session = Depends(get_db)) -> NoteRead:
    return NoteRead.model_validate(notes_service.apply_note(db, channel, payload))
