"""app_settings read/merge/update.

Every user preference from docs/03, docs/08, docs/10, docs/12 has a built-in default here,
so a fresh database (no rows yet) still returns a complete, sane settings object. Stored rows
override these. Secrets are never among them — the Groq API key lives only in the OS vault.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import new_uuid
from app.models.orm import AppSetting
from app.services import groq_key

_cfg = get_settings()

# Defaults are the single source of truth for "what settings exist". Keep ordered by concern.
DEFAULT_SETTINGS: dict[str, Any] = {
    # ── AI models (names are settings, not constants — docs/09 #9) ──
    "local_model_name": _cfg.default_local_model,
    "grammar_model_name": _cfg.default_grammar_model,
    "embedding_model_name": _cfg.default_embedding_model,
    # ── AI provider mode (docs/08) ──
    "ai_mode": "offline",  # offline | online | hybrid
    "groq_model_name": None,
    "groq_zdr_enabled": True,
    # ── reading environment (docs/10 §1–2, evidence-tuned; manuscript surface) ──
    "theme_mode": "day",  # day | night | auto
    "bg_tint": "cream",
    "font_family": "Lexend",
    "font_size": 18,
    "line_height": 1.5,
    "letter_spacing": 0.035,
    "line_length_ch": 65,
    "reading_ruler": "off",  # off | grey_bar | shade
    # ── delight (docs/10 §5, §8) ──
    "delight_level": "playful",  # calm | standard | playful
    "sounds_enabled": True,
    "mascot_enabled": True,
    # ── voice (docs/12) ──
    "dictation_hotkey": "CmdOrCtrl+Shift+Space",
    "stt_engine": "parakeet",  # parakeet | groq_whisper
    "tts_voice": None,
    "tts_rate": 1.0,
    # ── gamification (docs/10 §9) ──
    "daily_word_goal": 500,
    # ── per-profile onboarding (docs/13 §Data model additions) ──
    "onboarding_complete": False,
}

# The PERSONAL settings (docs/13-PROFILES-AND-AUTH.md §"Data model additions"): reading
# typography, theme, delight/sounds/mascot, and per-profile onboarding. Writes to these keys
# route to the current user's row (``user_id`` = that user) instead of the global row.
# Everything else (AI provider/model settings, dictation/STT/TTS, daily_word_goal) stays
# GLOBAL/shared across profiles.
PER_USER_KEYS = frozenset(
    {
        "theme_mode",
        "bg_tint",
        "font_family",
        "font_size",
        "line_height",
        "letter_spacing",
        "line_length_ch",
        "reading_ruler",
        "delight_level",
        "sounds_enabled",
        "mascot_enabled",
        "onboarding_complete",
    }
)


def get_all_settings(db: Session, user_id: str | None = None) -> dict[str, Any]:
    """Defaults overlaid with stored *global* overrides (``user_id IS NULL``), then — if a
    ``user_id`` is given — that user's personal overrides on top, plus a computed,
    safe-to-expose ``groq_key_present`` flag.

    Merge order (docs/13 §"Data model additions"): ``DEFAULT_SETTINGS`` -> global rows ->
    the current user's rows. When ``user_id`` is None this is byte-for-byte the pre-auth,
    global-only behavior (existing callers/tests are unaffected).

    The flag is NEVER stored — it's read fresh from the in-memory `groq_key` seam (docs
    seam, see app/services/groq_key.py) on every call, and deliberately excluded from
    ``DEFAULT_SETTINGS``/the DB so there is no code path that could persist it (or the key
    itself)."""
    merged = dict(DEFAULT_SETTINGS)
    stmt = select(AppSetting).where(AppSetting.user_id.is_(None))
    for row in db.execute(stmt).scalars():
        merged[row.key] = row.value
    if user_id is not None:
        user_stmt = select(AppSetting).where(AppSetting.user_id == user_id)
        for row in db.execute(user_stmt).scalars():
            merged[row.key] = row.value
    merged["groq_key_present"] = groq_key.is_present()
    return merged


def update_settings(
    db: Session, values: dict[str, Any], user_id: str | None = None
) -> dict[str, Any]:
    """Upsert each provided key, scoped by ``PER_USER_KEYS``: a personal key with a
    ``user_id`` present routes to that user's row; everything else (and every key when
    ``user_id`` is None) routes to the *global* (``user_id IS NULL``) row, exactly as
    before per-user scoping existed. Unknown keys are allowed (forward-compat) but callers
    should stick to the documented set."""
    for key, value in values.items():
        scope_user_id = user_id if (user_id is not None and key in PER_USER_KEYS) else None
        row = db.execute(
            select(AppSetting).where(AppSetting.user_id == scope_user_id, AppSetting.key == key)
        ).scalar_one_or_none()
        if row is None:
            db.add(AppSetting(id=new_uuid(), user_id=scope_user_id, key=key, value=value))
        else:
            row.value = value
    db.commit()
    return get_all_settings(db, user_id)
