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
from app.models.orm import AppSetting

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
}


def get_all_settings(db: Session) -> dict[str, Any]:
    """Defaults overlaid with any stored overrides."""
    merged = dict(DEFAULT_SETTINGS)
    for row in db.execute(select(AppSetting)).scalars():
        merged[row.key] = row.value
    return merged


def update_settings(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    """Upsert each provided key. Unknown keys are allowed (forward-compat) but callers
    should stick to the documented set."""
    for key, value in values.items():
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return get_all_settings(db)
