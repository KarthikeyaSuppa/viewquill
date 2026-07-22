"""Dictation (speech-to-text): audio storage + transcription + voice_notes CRUD
(docs/12-VOICE-AND-SPEECH.md §1, docs/03-DATA-MODEL.md `voice_notes`, docs/06 Phase 2
tasks E1/E2).

## Capture path — deliberately NOT the sounddevice design in docs/12

docs/12 describes native sidecar-side capture via `sounddevice`. That is deferred: this
build machine cannot install `sounddevice` (CLAUDE.md "Environment constraints"), and for
a Tauri WebView app the simpler, equally valid path is **browser-side capture**: the
frontend records with the browser's `MediaRecorder` and POSTs the resulting blob's raw
bytes as the request body. This module only ever receives already-recorded audio bytes —
it has no capture/VAD code of its own. `POST /voice/transcribe` (app/api/voice.py) is the
only caller of :func:`save_audio`.

## Never-lose-data

Raw audio is written to disk exactly once, in :func:`save_audio`, and this module never
deletes an audio file afterwards for ANY reason (failed transcription, discard, or
retranscribe) — see docs/12 "Raw audio is kept ... a mis-transcription can always be
re-listened and re-transcribed later". `discard_note` only flips `status`.

## [SECURITY-REVIEW] flag

This module reads raw, potentially-sensitive user audio bytes off the wire and writes them
unencrypted to `app-data/audio/`. Per CLAUDE.md, raw-audio-handling code in this file
should get a `reviewer` pass before this is considered production-ready (this task only
delivers/verifies it with the STT stub).

## [MODEL-DEFERRED] flag

The real engines below (Parakeet via `onnx-asr`, Groq's Whisper endpoint) are written and
wired but **never exercised on this machine** — CLAUDE.md forbids installing `onnx-asr` /
downloading any model here. Every import of a real engine is LAZY (inside the function
that needs it) so this module always imports cleanly with neither package installed.
Verification here uses ``QUILLNIGHT_STT_STUB=1``, which short-circuits before any of that
code runs. Real-engine testing happens later, on the second (AI) laptop.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import new_uuid, utcnow_iso
from app.models.orm import VoiceNote

# Env flag mirroring the QUILLNIGHT_LLM_STUB pattern in llm_orchestrator.py — lets the
# whole /voice/transcribe flow be exercised end-to-end without any real STT engine.
_STT_STUB_ENV_VAR = "QUILLNIGHT_STT_STUB"

# Groq's hosted Whisper model for the Online/Hybrid dictation leg (docs/12 §1 engine
# matrix: "Groq whisper-large-v3-turbo").
_DEFAULT_GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"

_CONTENT_TYPE_EXT: dict[str, str] = {
    "audio/webm": "webm",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/ogg": "ogg",
}


def _ext_for_content_type(content_type: str | None) -> str:
    """`audio/webm`, `audio/webm;codecs=opus`, missing/unknown header -> a safe extension.
    Falls back to ``bin`` rather than guessing, so an unrecognized MIME type never crashes
    the upload — the bytes are still saved (never-lose-data), just without a nice suffix.
    """
    if not content_type:
        return "bin"
    base = content_type.split(";", 1)[0].strip().lower()
    return _CONTENT_TYPE_EXT.get(base, "bin")


def _full_audio_path(relative_path: str) -> Path:
    """``voice_notes.audio_path`` is stored relative to the data dir (e.g.
    ``audio/<uuid>.webm``) so the DB stays portable across machines/data-dir moves."""
    return get_settings().data_dir / relative_path


def save_audio(data: bytes, content_type: str | None) -> str:
    """Writes raw uploaded audio bytes to ``app-data/audio/<uuid>.<ext>``. Returns the path
    RELATIVE to the data dir — what gets stored in ``voice_notes.audio_path``.

    This is the ONLY place audio bytes are written, and it never overwrites or deletes an
    existing file (each call gets a fresh UUID filename).
    """
    cfg = get_settings()
    cfg.ensure_dirs()
    ext = _ext_for_content_type(content_type)
    filename = f"{new_uuid()}.{ext}"
    full_path = cfg.audio_dir / filename
    full_path.write_bytes(data)
    return f"audio/{filename}"


def _transcribe_parakeet(full_path: Path) -> str:
    """Local/offline engine — NVIDIA Parakeet-TDT via `onnx-asr` (docs/12 §1). LAZY import:
    `onnx-asr` is not installed on this build machine and must never be imported at module
    load time. [MODEL-DEFERRED] — not exercised here; verified on the second laptop."""
    import onnx_asr  # noqa: PLC0415 — intentionally lazy, see module docstring

    model = onnx_asr.load_model("nvidia/parakeet-tdt-0.6b-v3")
    result = model.recognize(str(full_path))
    return str(result)


def _transcribe_groq(full_path: Path, groq_key: str) -> str:
    """Online engine — Groq's hosted Whisper transcription endpoint (docs/12 §1). LAZY
    import: only touches the network/`openai` client when actually invoked with a real
    key. [MODEL-DEFERRED] — not exercised here; verified on the second laptop."""
    from openai import OpenAI  # noqa: PLC0415 — intentionally lazy, see module docstring

    client = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
    with full_path.open("rb") as audio_file:
        response = client.audio.transcriptions.create(
            model=_DEFAULT_GROQ_WHISPER_MODEL,
            file=audio_file,
        )
    return response.text


def transcribe(
    audio_path: str,
    *,
    engine: str,
    ai_mode: str,
    groq_key: str | None = None,
) -> tuple[str, str]:
    """Transcribe the audio at ``audio_path`` (relative to the data dir). Returns
    ``(transcript, engine_used)``.

    Routing mirrors docs/08's Offline/Online/Hybrid semantics, same as text AI (docs/12
    §1 "Routing follows the exact same Offline/Online/Hybrid semantics"):
      - the caller's ``engine`` setting (``parakeet`` | ``groq_whisper``, from
        ``app_settings.stt_engine``) picks the *preferred* engine;
      - ``groq_whisper`` is only attempted when ``ai_mode`` allows it (``online``/
        ``hybrid``) AND a Groq key is present — same "missing key silently degrades to
        local" rule as ``llm_orchestrator.py``;
      - in ``hybrid`` mode a Groq failure falls back to Parakeet, matching the text-AI
        fallback behavior; in ``online`` mode with no key it also falls back to Parakeet
        (docs/08's "If absent, Online/Hybrid degrade to local" rule) rather than raising.

    Under ``QUILLNIGHT_STT_STUB=1`` this returns a fixed transcript and engine label
    ``"stub"`` immediately — no import of ``onnx_asr`` or the network client, no matter
    what ``engine``/``ai_mode``/``groq_key`` are passed. This is the ONLY path exercised
    on this build machine.
    """
    if os.environ.get(_STT_STUB_ENV_VAR) == "1":
        return "stub transcript", "stub"

    full_path = _full_audio_path(audio_path)
    want_groq = engine == "groq_whisper" and ai_mode in ("online", "hybrid")

    if want_groq and groq_key:
        try:
            return _transcribe_groq(full_path, groq_key), "groq_whisper"
        except Exception:  # noqa: BLE001 — provider-fallback boundary, mirrors llm_orchestrator.py
            if ai_mode != "hybrid":
                raise

    return _transcribe_parakeet(full_path), "parakeet"


def create_voice_note(
    db: Session,
    *,
    audio_path: str,
    transcript: str | None,
    engine: str | None,
    duration_ms: int | None = None,
    status: str = "transcribed",
) -> VoiceNote:
    note = VoiceNote(
        id=new_uuid(),
        audio_path=audio_path,
        transcript=transcript,
        engine=engine,
        duration_ms=duration_ms,
        status=status,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def list_notes(db: Session) -> list[VoiceNote]:
    return list(db.execute(select(VoiceNote).order_by(VoiceNote.created_at.desc())).scalars())


def get_note(db: Session, note_id: str) -> VoiceNote | None:
    return db.get(VoiceNote, note_id)


def attach_note(
    db: Session, note_id: str, entity_type: str, entity_id: str
) -> VoiceNote | None:
    """Records which field/entity this dictation ended up in. Never touches the audio
    file or the transcript text — attaching is metadata only."""
    note = db.get(VoiceNote, note_id)
    if note is None:
        return None
    note.attached_entity_type = entity_type
    note.attached_entity_id = entity_id
    note.status = "attached"
    db.commit()
    db.refresh(note)
    return note


def discard_note(db: Session, note_id: str) -> VoiceNote | None:
    """Marks a voice note as discarded. The audio file on disk is DELIBERATELY left in
    place — see module docstring "Never-lose-data". A discard is a UI/workflow state, not
    a deletion."""
    note = db.get(VoiceNote, note_id)
    if note is None:
        return None
    note.status = "discarded"
    db.commit()
    db.refresh(note)
    return note


def retranscribe(
    db: Session, note_id: str, engine: str, ai_mode: str, groq_key: str | None = None
) -> VoiceNote | None:
    """Re-runs transcription against the SAME stored ``audio_path`` — never re-records,
    never touches the audio file. Lets a mis-transcription be retried with a different
    engine/mode later (docs/12 §1), including after a future engine upgrade."""
    note = db.get(VoiceNote, note_id)
    if note is None:
        return None
    transcript, engine_used = transcribe(
        note.audio_path, engine=engine, ai_mode=ai_mode, groq_key=groq_key
    )
    note.transcript = transcript
    note.engine = engine_used
    note.status = "transcribed"
    db.commit()
    db.refresh(note)
    return note
