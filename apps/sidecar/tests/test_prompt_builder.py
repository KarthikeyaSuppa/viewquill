"""Tests for app.services.prompt_builder — pure string assembly, NO model involved.

Verifies the prefix-cache discipline (docs/11-AI-INTELLIGENCE.md §5) and the anti-spoiler
point-in-time arc-state rule (module docstring in prompt_builder.py):

1. Two `build_enhance_prompt` calls with identical inputs produce a BYTE-IDENTICAL prefix
   (system + codex messages).
2. Changing only the scene `text` changes ONLY the tail message, not the prefix.
3. For the EARLIER scene, a later arc-state is EXCLUDED; for the LATER scene it's included.

Uses a fresh, temp-directory SQLite DB (via `QUILLNIGHT_DATA_DIR`) migrated to head with
Alembic — the same startup path the real sidecar uses — so this exercises the real schema,
not a hand-rolled one.
"""

from __future__ import annotations

import os
import shutil
import tempfile

# `QUILLNIGHT_DATA_DIR` must be set BEFORE any `app.*` module is imported, because
# `app.config.get_settings()` is `@lru_cache`-d and `app.db.base` builds the engine at
# import time from whatever it returns.
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight_prompt_builder_test_")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

import pytest  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.db.migrate import run_migrations  # noqa: E402
from app.models.orm import (  # noqa: E402
    Book,
    BookSceneOrder,
    CodexArcState,
    CodexEntry,
    CodexSceneLink,
    Scene,
)
from app.services import prompt_builder  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _fresh_db():
    run_migrations()
    yield
    shutil.rmtree(_TMP_DATA_DIR, ignore_errors=True)


@pytest.fixture(scope="module")
def seeded():
    """Book with two ordered scenes and a character with two arc-states, one before each
    scene's outline position."""
    db = SessionLocal()
    try:
        book = Book(title="Test Book", book_type="story_book")
        db.add(book)

        scene_early = Scene(node_type="scene", title="Early Scene", description="Nothing much happens yet.")
        scene_late = Scene(node_type="scene", title="Late Scene", description="Everything comes to a head.")
        db.add_all([scene_early, scene_late])
        db.flush()

        order_early = BookSceneOrder(
            book_id=book.id, scene_id=scene_early.id, outline_order_index=0
        )
        order_late = BookSceneOrder(
            book_id=book.id, scene_id=scene_late.id, outline_order_index=10
        )
        db.add_all([order_early, order_late])

        character = CodexEntry(
            entry_type="character",
            name="Elena",
            summary="A quietly determined blacksmith's apprentice.",
            custom_fields={"eye_color": "green", "role": "protagonist"},
        )
        db.add(character)
        db.flush()

        link_early = CodexSceneLink(codex_entry_id=character.id, scene_id=scene_early.id)
        link_late = CodexSceneLink(codex_entry_id=character.id, scene_id=scene_late.id)
        db.add_all([link_early, link_late])

        # Arc state BEFORE the early scene (as_of 0 <= 0 -> visible to early scene too).
        arc_before_early = CodexArcState(
            codex_entry_id=character.id,
            book_id=book.id,
            as_of_outline_order_index=0,
            status_summary="Still an apprentice, unaware of her true heritage.",
        )
        # Arc state AFTER the early scene but AT/BEFORE the late scene (as_of 5).
        # Must be EXCLUDED for the early scene (0 < 5) and INCLUDED for the late scene (5 <= 10).
        arc_after_early = CodexArcState(
            codex_entry_id=character.id,
            book_id=book.id,
            as_of_outline_order_index=5,
            status_summary="Has discovered she is the last heir of House Ashgate.",
        )
        db.add_all([arc_before_early, arc_after_early])
        db.commit()

        return {
            "book_id": book.id,
            "scene_early_id": scene_early.id,
            "scene_late_id": scene_late.id,
            "character_id": character.id,
        }
    finally:
        db.close()


def test_identical_calls_produce_byte_identical_prefix(seeded):
    db = SessionLocal()
    try:
        msgs_a = prompt_builder.build_enhance_prompt(
            db,
            mode="prose",
            text="She lifted the hammer.",
            scene_id=seeded["scene_early_id"],
            book_id=seeded["book_id"],
        )
        msgs_b = prompt_builder.build_enhance_prompt(
            db,
            mode="prose",
            text="She lifted the hammer.",
            scene_id=seeded["scene_early_id"],
            book_id=seeded["book_id"],
        )
        # Prefix = system prompt + codex block (messages[0], messages[1]).
        assert msgs_a[0] == msgs_b[0]
        assert msgs_a[1] == msgs_b[1]
        assert msgs_a[0]["content"] == prompt_builder.SYSTEM_PROMPT
        assert "## CODEX CONTEXT ##" in msgs_a[1]["content"]
        # Whole-message-list equality too, since text/mode are identical here.
        assert msgs_a == msgs_b
    finally:
        db.close()


def test_changing_text_changes_only_the_tail_message(seeded):
    db = SessionLocal()
    try:
        msgs_a = prompt_builder.build_enhance_prompt(
            db,
            mode="prose",
            text="She lifted the hammer.",
            scene_id=seeded["scene_early_id"],
            book_id=seeded["book_id"],
        )
        msgs_b = prompt_builder.build_enhance_prompt(
            db,
            mode="prose",
            text="She lifted the hammer and swung it in one clean arc.",
            scene_id=seeded["scene_early_id"],
            book_id=seeded["book_id"],
        )
        # Prefix (system, codex) untouched.
        assert msgs_a[0] == msgs_b[0]
        assert msgs_a[1] == msgs_b[1]
        # Task instruction (static per mode) untouched too.
        assert msgs_a[3] == msgs_b[3]
        # Only the variable scene-text message differs.
        assert msgs_a[2] != msgs_b[2]
        assert msgs_a[2]["content"] == "She lifted the hammer."
        assert msgs_b[2]["content"] == "She lifted the hammer and swung it in one clean arc."
    finally:
        db.close()


def test_anti_spoiler_arc_state_excluded_for_earlier_scene(seeded):
    db = SessionLocal()
    try:
        early_entries = prompt_builder.build_codex_context(
            db, scene_id=seeded["scene_early_id"], book_id=seeded["book_id"]
        )
        assert len(early_entries) == 1
        early_custom = early_entries[0]["custom_fields"]
        assert early_custom.get("arc_status_summary") == (
            "Still an apprentice, unaware of her true heritage."
        )
        # The later (spoiler) arc-state must NOT leak into the earlier scene's context.
        assert "Ashgate" not in str(early_custom)
    finally:
        db.close()


def test_anti_spoiler_arc_state_included_for_later_scene(seeded):
    db = SessionLocal()
    try:
        late_entries = prompt_builder.build_codex_context(
            db, scene_id=seeded["scene_late_id"], book_id=seeded["book_id"]
        )
        assert len(late_entries) == 1
        late_custom = late_entries[0]["custom_fields"]
        # The later scene sees the latest applicable arc-state (as_of 5 <= 10).
        assert late_custom.get("arc_status_summary") == (
            "Has discovered she is the last heir of House Ashgate."
        )
    finally:
        db.close()


def test_serialize_codex_block_is_deterministic_regardless_of_input_order():
    entries = [
        {"id": "b-id", "name": "Bram", "entry_type": "character", "summary": "s2", "custom_fields": {"z": 1, "a": 2}},
        {"id": "a-id", "name": "Anya", "entry_type": "character", "summary": "s1", "custom_fields": {}},
    ]
    block_1 = prompt_builder.serialize_codex_block(entries)
    block_2 = prompt_builder.serialize_codex_block(list(reversed(entries)))
    assert block_1 == block_2


def test_serialize_codex_block_empty():
    assert prompt_builder.serialize_codex_block([]) == prompt_builder._EMPTY_CODEX_BLOCK


def test_token_budget_trim_preserves_prefix_and_drops_from_the_end():
    entries = [
        {"id": "1", "name": "Alpha", "entry_type": "character", "summary": "first", "custom_fields": {}},
        {"id": "2", "name": "Beta", "entry_type": "character", "summary": "second", "custom_fields": {}},
        {"id": "3", "name": "Gamma", "entry_type": "character", "summary": "third", "custom_fields": {}},
    ]
    full_block = prompt_builder.serialize_codex_block(entries)
    trimmed = prompt_builder.token_budget_trim(full_block, max_chars=len(full_block) - 5)
    assert len(trimmed) <= len(full_block) - 5
    assert full_block.startswith(trimmed.rstrip()) or trimmed in full_block
    # Untrimmed content fits as-is.
    assert prompt_builder.token_budget_trim(full_block, max_chars=len(full_block)) == full_block


def test_temperature_for():
    assert prompt_builder.temperature_for("grammar") == 0.3
    assert prompt_builder.temperature_for("continuity") == 0.3
    assert prompt_builder.temperature_for("prose") == 0.7
    with pytest.raises(ValueError):
        prompt_builder.temperature_for("not_a_mode")  # type: ignore[arg-type]
