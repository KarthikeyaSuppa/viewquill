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
    CodexRelationship,
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


@pytest.fixture(scope="module")
def seeded_with_relationships():
    """Two Codex entries, both linked to the same scene, connected by one relationship
    edge, to exercise the relationships-rendering path in build_codex_context."""
    db = SessionLocal()
    try:
        book = Book(title="Relationship Test Book", book_type="story_book")
        db.add(book)

        scene = Scene(node_type="scene", title="Shared Scene", description="A and B meet.")
        db.add(scene)
        db.flush()

        entry_a = CodexEntry(entry_type="character", name="Anya", summary="A blacksmith.")
        entry_b = CodexEntry(entry_type="character", name="Boris", summary="A rival smith.")
        db.add_all([entry_a, entry_b])
        db.flush()

        db.add_all(
            [
                CodexSceneLink(codex_entry_id=entry_a.id, scene_id=scene.id),
                CodexSceneLink(codex_entry_id=entry_b.id, scene_id=scene.id),
            ]
        )
        db.add(
            CodexRelationship(
                from_entry_id=entry_a.id,
                to_entry_id=entry_b.id,
                relationship_type="rival",
                description="childhood friends turned enemies",
            )
        )
        db.commit()

        return {"book_id": book.id, "scene_id": scene.id, "a_id": entry_a.id, "b_id": entry_b.id}
    finally:
        db.close()


def test_relationships_rendered_for_both_endpoints_and_are_byte_identical_on_rebuild(
    seeded_with_relationships,
):
    db = SessionLocal()
    try:
        entries_1 = prompt_builder.build_codex_context(
            db,
            scene_id=seeded_with_relationships["scene_id"],
            book_id=seeded_with_relationships["book_id"],
        )
        block_1 = prompt_builder.serialize_codex_block(entries_1)

        entries_2 = prompt_builder.build_codex_context(
            db,
            scene_id=seeded_with_relationships["scene_id"],
            book_id=seeded_with_relationships["book_id"],
        )
        block_2 = prompt_builder.serialize_codex_block(entries_2)

        assert block_1 == block_2

        # Both entries carry the edge, from their own perspective.
        assert "relationships:" in block_1
        assert "  - rival: Boris — childhood friends turned enemies" in block_1
        assert "  - rival: Anya — childhood friends turned enemies" in block_1
    finally:
        db.close()


def test_entry_with_no_relationships_matches_pre_relationships_format():
    """Guards against accidental format drift: an entry dict with no relationships (either
    key omitted, or explicit empty list) must render EXACTLY as it did before this feature
    was added — no 'relationships:' line, no extra blank lines."""
    entry = {
        "id": "x-id",
        "name": "Nobody",
        "entry_type": "character",
        "summary": "Has no connections.",
        "custom_fields": {"eye_color": "brown"},
    }
    expected = "name: Nobody\ntype: character\nsummary: Has no connections.\ncustom_fields:\n  eye_color: brown"
    assert prompt_builder._render_entry(entry) == expected

    # Explicit empty relationships list must render identically to the key being absent.
    entry_with_empty_rels = dict(entry, relationships=[])
    assert prompt_builder._render_entry(entry_with_empty_rels) == expected


def test_relationships_render_deterministically_regardless_of_insertion_order():
    base_entry = {
        "id": "c-id",
        "name": "Cora",
        "entry_type": "character",
        "summary": "s",
        "custom_fields": {},
    }
    rels_order_1 = [
        {"type": "ally", "with": "Dax", "description": ""},
        {"type": "rival", "with": "Boris", "description": "childhood friends turned enemies"},
    ]
    rels_order_2 = list(reversed(rels_order_1))

    rendered_1 = prompt_builder._render_entry(dict(base_entry, relationships=rels_order_1))
    rendered_2 = prompt_builder._render_entry(dict(base_entry, relationships=rels_order_2))
    assert rendered_1 == rendered_2


@pytest.fixture(scope="module")
def seeded_with_tied_arc_states():
    """One Book, one Codex entry linked to one Scene placed at outline index 3, with TWO
    arc-states sharing the SAME `as_of_outline_order_index` (3) but different `created_at`
    values — locks FIX B.2's total-order tiebreak (newest-created wins, id as final
    tiebreak) so arc-state resolution is deterministic even when indexes tie."""
    db = SessionLocal()
    try:
        book = Book(title="Tiebreak Test Book", book_type="story_book")
        db.add(book)

        scene = Scene(node_type="scene", title="Tiebreak Scene", description="Something happens.")
        db.add(scene)
        db.flush()

        order = BookSceneOrder(book_id=book.id, scene_id=scene.id, outline_order_index=3)
        db.add(order)

        entry = CodexEntry(entry_type="character", name="Tessa", summary="A wandering scholar.")
        db.add(entry)
        db.flush()

        db.add(CodexSceneLink(codex_entry_id=entry.id, scene_id=scene.id))

        # Both arc-states share as_of_outline_order_index == 3 (<= scene's index of 3).
        # created_at is set explicitly (String column) so ordering is unambiguous.
        arc_older = CodexArcState(
            codex_entry_id=entry.id,
            book_id=book.id,
            as_of_outline_order_index=3,
            status_summary="OLDER — should be excluded by the tiebreak.",
            created_at="2026-01-01T00:00:00Z",
        )
        arc_newer = CodexArcState(
            codex_entry_id=entry.id,
            book_id=book.id,
            as_of_outline_order_index=3,
            status_summary="NEWER — must win the tiebreak.",
            created_at="2026-01-02T00:00:00Z",
        )
        db.add_all([arc_older, arc_newer])
        db.commit()

        return {"book_id": book.id, "scene_id": scene.id, "entry_id": entry.id}
    finally:
        db.close()


def test_tied_arc_state_index_resolves_deterministically_to_newest_created(
    seeded_with_tied_arc_states,
):
    """FIX B.2: when two arc-states share the max qualifying `as_of_outline_order_index`,
    resolution must be a TOTAL order (index desc, created_at desc, id desc) — not
    nondeterministic LIMIT 1 — so the newest-created row always wins and repeated calls
    produce byte-identical output (KV-cache-prefix safe)."""
    db = SessionLocal()
    try:
        results = [
            prompt_builder.build_codex_context(
                db,
                scene_id=seeded_with_tied_arc_states["scene_id"],
                book_id=seeded_with_tied_arc_states["book_id"],
            )
            for _ in range(5)
        ]

        for entries in results:
            assert len(entries) == 1
            summary = entries[0]["custom_fields"].get("arc_status_summary")
            assert summary == "NEWER — must win the tiebreak."
            assert "OLDER" not in str(entries[0]["custom_fields"])

        # Byte-identical serialized blocks across every call.
        blocks = [prompt_builder.serialize_codex_block(entries) for entries in results]
        assert all(block == blocks[0] for block in blocks)
    finally:
        db.close()


def test_temperature_for():
    assert prompt_builder.temperature_for("grammar") == 0.3
    assert prompt_builder.temperature_for("continuity") == 0.3
    assert prompt_builder.temperature_for("prose") == 0.7
    with pytest.raises(ValueError):
        prompt_builder.temperature_for("not_a_mode")  # type: ignore[arg-type]


# ── build_merge_prompt (PHASE11.md Workstream B task 8) ───────────────────────────────────


@pytest.fixture(scope="module")
def seeded_for_merge():
    """One Book with three scenes placed out of insertion order on the timeline
    (``timeline_order_index`` 2, 0, 1 for scene_a/b/c respectively) plus a Codex character
    linked to two of the three scenes, so both the ordering and codex-union logic have
    something non-trivial to prove."""
    db = SessionLocal()
    try:
        book = Book(title="Merge Test Book", book_type="story_book")
        db.add(book)

        scene_a = Scene(node_type="scene", title="Scene A", description="A happens.")
        scene_b = Scene(node_type="scene", title="Scene B", description="B happens.")
        scene_c = Scene(node_type="scene", title="Scene C", description="C happens.")
        db.add_all([scene_a, scene_b, scene_c])
        db.flush()

        # Insertion order is A, B, C but timeline order is B(0), C(1), A(2).
        db.add_all(
            [
                prompt_builder.BookSceneOrder(
                    book_id=book.id, scene_id=scene_a.id, timeline_order_index=2
                ),
                prompt_builder.BookSceneOrder(
                    book_id=book.id, scene_id=scene_b.id, timeline_order_index=0
                ),
                prompt_builder.BookSceneOrder(
                    book_id=book.id, scene_id=scene_c.id, timeline_order_index=1
                ),
            ]
        )

        character = CodexEntry(
            entry_type="character", name="Nia", summary="A wandering cartographer."
        )
        db.add(character)
        db.flush()
        db.add_all(
            [
                CodexSceneLink(codex_entry_id=character.id, scene_id=scene_a.id),
                CodexSceneLink(codex_entry_id=character.id, scene_id=scene_b.id),
            ]
        )
        db.commit()

        return {
            "book_id": book.id,
            "scene_a_id": scene_a.id,
            "scene_b_id": scene_b.id,
            "scene_c_id": scene_c.id,
            "character_id": character.id,
        }
    finally:
        db.close()


def test_build_merge_prompt_same_shape_as_enhance(seeded_for_merge):
    db = SessionLocal()
    try:
        merge_msgs = prompt_builder.build_merge_prompt(
            db,
            [seeded_for_merge["scene_a_id"], seeded_for_merge["scene_b_id"]],
            book_id=seeded_for_merge["book_id"],
        )
        enhance_msgs = prompt_builder.build_enhance_prompt(
            db,
            mode="prose",
            text="irrelevant",
            scene_id=seeded_for_merge["scene_a_id"],
            book_id=seeded_for_merge["book_id"],
        )
        # Same section count and same role sequence: system, system, user, user.
        assert len(merge_msgs) == len(enhance_msgs) == 4
        assert [m["role"] for m in merge_msgs] == [m["role"] for m in enhance_msgs]
        assert all(set(m.keys()) == {"role", "content"} for m in merge_msgs)
        # Static system prompt is reused verbatim.
        assert merge_msgs[0]["content"] == prompt_builder.SYSTEM_PROMPT
        assert merge_msgs[0] == enhance_msgs[0]
        # Codex block uses the same serialization/header.
        assert "## CODEX CONTEXT ##" in merge_msgs[1]["content"]
    finally:
        db.close()


def test_build_merge_prompt_respects_timeline_order_index(seeded_for_merge):
    db = SessionLocal()
    try:
        msgs = prompt_builder.build_merge_prompt(
            db,
            [
                seeded_for_merge["scene_a_id"],
                seeded_for_merge["scene_b_id"],
                seeded_for_merge["scene_c_id"],
            ],
            book_id=seeded_for_merge["book_id"],
        )
        combined_text = msgs[2]["content"]
        # Timeline order is B(0), C(1), A(2) — NOT the insertion/argument order (A, B, C).
        assert combined_text.index("--- Scene: Scene B ---") < combined_text.index(
            "--- Scene: Scene C ---"
        )
        assert combined_text.index("--- Scene: Scene C ---") < combined_text.index(
            "--- Scene: Scene A ---"
        )
        assert "B happens." in combined_text
        assert "C happens." in combined_text
        assert "A happens." in combined_text
    finally:
        db.close()


def test_build_merge_prompt_falls_back_to_created_at_when_order_missing():
    """When at least one source scene has no ``book_scene_order`` row (or a null
    ``timeline_order_index``), ordering must fall back to ``created_at`` for the WHOLE
    group — not a per-scene mixed key."""
    db = SessionLocal()
    try:
        book = Book(title="Merge Fallback Book", book_type="story_book")
        db.add(book)

        scene_first = Scene(
            node_type="scene",
            title="First Created",
            description="Created first.",
            created_at="2026-01-01T00:00:00Z",
        )
        scene_second = Scene(
            node_type="scene",
            title="Second Created",
            description="Created second.",
            created_at="2026-01-02T00:00:00Z",
        )
        db.add_all([scene_first, scene_second])
        db.flush()
        # Only scene_first gets a book_scene_order row -> the group is NOT fully ordered,
        # so both scenes must fall back to created_at.
        db.add(
            prompt_builder.BookSceneOrder(
                book_id=book.id, scene_id=scene_first.id, timeline_order_index=99
            )
        )
        db.commit()

        msgs = prompt_builder.build_merge_prompt(
            db, [scene_second.id, scene_first.id], book_id=book.id
        )
        combined_text = msgs[2]["content"]
        assert combined_text.index("--- Scene: First Created ---") < combined_text.index(
            "--- Scene: Second Created ---"
        )
    finally:
        db.close()


def test_build_merge_prompt_deterministic_across_calls(seeded_for_merge):
    db = SessionLocal()
    try:
        scene_ids = [seeded_for_merge["scene_a_id"], seeded_for_merge["scene_b_id"]]
        msgs_1 = prompt_builder.build_merge_prompt(
            db, scene_ids, book_id=seeded_for_merge["book_id"]
        )
        msgs_2 = prompt_builder.build_merge_prompt(
            db, scene_ids, book_id=seeded_for_merge["book_id"]
        )
        assert msgs_1 == msgs_2
    finally:
        db.close()


def test_build_merge_prompt_missing_scene_id_raises(seeded_for_merge):
    db = SessionLocal()
    try:
        with pytest.raises(ValueError, match="SCENE_NOT_FOUND"):
            prompt_builder.build_merge_prompt(
                db,
                [seeded_for_merge["scene_a_id"], "does-not-exist"],
                book_id=seeded_for_merge["book_id"],
            )
    finally:
        db.close()


def test_build_merge_prompt_task_instruction_is_static_and_last(seeded_for_merge):
    db = SessionLocal()
    try:
        msgs = prompt_builder.build_merge_prompt(
            db,
            [seeded_for_merge["scene_a_id"], seeded_for_merge["scene_b_id"]],
            book_id=seeded_for_merge["book_id"],
        )
        assert msgs[3]["content"] == prompt_builder._MERGE_TASK_INSTRUCTION
        assert "TITLE:" in msgs[3]["content"]
        assert "DESCRIPTION:" in msgs[3]["content"]
    finally:
        db.close()
