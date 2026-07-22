"""/voice — dictation intake + voice_notes lifecycle (docs/12-VOICE-AND-SPEECH.md §1,
docs/03-DATA-MODEL.md `voice_notes`, docs/06 Phase 2 tasks E1/E2).

DATA-SENSITIVE (flagged for a later `reviewer` pass, per CLAUDE.md): `POST
/voice/transcribe` reads and persists raw user audio to disk. See
`app/services/speech_stt.py` module docstring for the full [SECURITY-REVIEW] and
[MODEL-DEFERRED] notes.

No `python-multipart` here — the audio blob arrives as the RAW request body (the frontend
records via the browser's `MediaRecorder` and POSTs the blob directly), not a multipart
form field.

The Groq key used for the `groq_whisper` STT engine below is sourced the same way as
`app/api/llm.py` — the dev seam in `app/services/groq_key.py` (task F1/F2). Production
swaps this for a Rust-shell/OS-keyring value; the key never persists in the sidecar
either way.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import AttachRequest, VoiceNoteRead
from app.services import groq_key, speech_stt
from app.services.settings_service import get_all_settings

router = APIRouter(prefix="/voice", tags=["voice"])

# Hardening (reviewer finding): reading the whole request body into memory with no cap is
# an OOM risk for a malicious or buggy client. Reject anything over this size — fast via
# Content-Length when the client sends one, and always via a hard cap on the streamed read
# below (so a missing/lying Content-Length can't bypass the check).
MAX_AUDIO_BYTES = 100 * 1024 * 1024  # 100 MB


def _require_note(db: Session, note_id: str) -> None:
    if speech_stt.get_note(db, note_id) is None:
        raise HTTPException(status_code=404, detail="Voice note not found")


@router.post("/transcribe", response_model=VoiceNoteRead, status_code=status.HTTP_201_CREATED)
async def transcribe_voice_note(request: Request, db: Session = Depends(get_db)) -> VoiceNoteRead:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Audio body exceeds max size of {MAX_AUDIO_BYTES} bytes",
            )

    # Read via the stream (rather than request.body()) so a missing/lying Content-Length
    # header can't bypass the cap — we stop buffering the instant we exceed it, instead of
    # buffering the whole oversize body into memory first and rejecting after the fact.
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Audio body exceeds max size of {MAX_AUDIO_BYTES} bytes",
            )
        chunks.append(chunk)
    audio_bytes = b"".join(chunks)
    content_type = request.headers.get("content-type")

    # Raw audio is written to disk BEFORE transcription is attempted — never-lose-data
    # applies even if transcription itself fails below.
    audio_path = speech_stt.save_audio(audio_bytes, content_type)

    settings = get_all_settings(db)
    engine = settings.get("stt_engine", "parakeet")
    ai_mode = settings.get("ai_mode", "offline")

    # Dev seam (task F1/F2, same as app/api/llm.py) — see module docstring.
    resolved_groq_key = groq_key.get_key()

    transcript, engine_used = speech_stt.transcribe(
        audio_path, engine=engine, ai_mode=ai_mode, groq_key=resolved_groq_key
    )

    note = speech_stt.create_voice_note(
        db,
        audio_path=audio_path,
        transcript=transcript,
        engine=engine_used,
        status="transcribed",
    )
    return VoiceNoteRead.model_validate(note)


@router.get("", response_model=list[VoiceNoteRead])
def list_voice_notes(db: Session = Depends(get_db)) -> list[VoiceNoteRead]:
    return [VoiceNoteRead.model_validate(note) for note in speech_stt.list_notes(db)]


@router.post("/{note_id}/attach", response_model=VoiceNoteRead)
def attach_voice_note(
    note_id: str, payload: AttachRequest, db: Session = Depends(get_db)
) -> VoiceNoteRead:
    note = speech_stt.attach_note(
        db, note_id, payload.attached_entity_type, payload.attached_entity_id
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Voice note not found")
    return VoiceNoteRead.model_validate(note)


@router.post("/{note_id}/discard", response_model=VoiceNoteRead)
def discard_voice_note(note_id: str, db: Session = Depends(get_db)) -> VoiceNoteRead:
    note = speech_stt.discard_note(db, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Voice note not found")
    return VoiceNoteRead.model_validate(note)


@router.post("/{note_id}/retranscribe", response_model=VoiceNoteRead)
def retranscribe_voice_note(note_id: str, db: Session = Depends(get_db)) -> VoiceNoteRead:
    settings = get_all_settings(db)
    engine = settings.get("stt_engine", "parakeet")
    ai_mode = settings.get("ai_mode", "offline")

    # Dev seam (task F1/F2, same as above) — see module docstring.
    resolved_groq_key = groq_key.get_key()

    note = speech_stt.retranscribe(db, note_id, engine, ai_mode, groq_key=resolved_groq_key)
    if note is None:
        raise HTTPException(status_code=404, detail="Voice note not found")
    return VoiceNoteRead.model_validate(note)
