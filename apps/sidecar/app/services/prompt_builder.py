"""Enhance/continuity prompt assembler — the prefix-cache-disciplined context builder
(docs/11-AI-INTELLIGENCE.md §5, docs/04-LLM-INTEGRATION.md "Enhance call flow").

This module does ONLY string/message assembly. It never calls an LLM (no `litellm`, no
`httpx` to Ollama) — that lives in the later `llm_orchestrator.py` (task D1) and the
`/llm/enhance` endpoint (task C2), which are explicitly out of scope here.

## The hard, cache-friendly message order (docs/09 principle #7, docs/11 §5)

    [static system prompt] -> [deterministically-serialized codex block]
        -> [variable scene text] -> [task instruction]

Ollama/llama.cpp reuse the KV cache when a request's token *prefix* is byte-identical to
the previous request in that slot. So:

* Nothing volatile (timestamps, UUIDs, request IDs) may appear before the variable scene
  text — one early differing token forfeits the whole cached prefix.
* The codex block must be serialized **deterministically**: stable entity ordering, stable
  field order, so an unchanged codex state produces a byte-identical block across calls.

## Anti-spoiler rule (DATA-SENSITIVE — read before touching `build_codex_context`)

`codex_arc_states` rows are point-in-time snapshots of a Codex entry (e.g. a character's
current status/traits) *as of* a given position in a Book's outline
(`as_of_outline_order_index`). When assembling context for a scene, only the **latest**
arc-state whose `as_of_outline_order_index <= this scene's outline_order_index` may be
included. A LATER arc-state (something that hasn't happened yet from this scene's point of
view) must be EXCLUDED — including it would leak a future plot fact into an earlier scene's
AI suggestion. If the scene isn't placed in the Book's outline yet (no `book_scene_order`
row, or a null `outline_order_index`), we cannot safely resolve "as of where" — the fallback
is to skip arc-state resolution entirely rather than guess, since omitting point-in-time
detail can never leak a spoiler (it just falls back to the entry's evergreen summary).

Note: Codex *relationship* `description` text (from `codex_relationships`) is ALWAYS
visible to the model regardless of scene position — relationships are NOT arc-scoped like
`codex_arc_states` rows are; only `status_summary`/`traits_snapshot` are filtered by
`as_of_outline_order_index`. Do not assume relationship descriptions are spoiler-filtered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orm import (
    BookSceneOrder,
    CodexArcState,
    CodexEntry,
    CodexRelationship,
    CodexSceneLink,
    Scene,
)

Mode = Literal["grammar", "prose", "continuity", "title"]

# ── Static system prompt — NEVER interpolated with volatile data ──────────────────────────
SYSTEM_PROMPT = (
    "You are a careful developmental editor and continuity assistant embedded in "
    "Quillnight, a fiction-writing application. You preserve the author's voice, "
    "structure, and intent. You NEVER invent new plot facts, characters, relationships, "
    "or events beyond what is already established in the provided story-bible context or "
    "the author's own text. When asked to revise text, output only the revised text — no "
    "commentary, preamble, or explanation."
)

# ── Mode-specific task instructions (static per mode; sit AFTER the variable text) ────────
_TASK_INSTRUCTIONS: dict[Mode, str] = {
    "grammar": (
        "Task: correct grammar, spelling, and punctuation errors in the text above only. "
        "Preserve the author's voice, word choice, and sentence structure wherever "
        "possible. Output only the corrected text."
    ),
    "prose": (
        "Task: improve the prose quality, flow, and clarity of the text above. Preserve "
        "the author's voice and every plot fact already established in the codex context "
        "and the text itself. Output only the revised text."
    ),
    "continuity": (
        "Task: check the text above for continuity issues against the codex context "
        "provided earlier (contradicted traits, timeline inconsistencies, or facts "
        "inconsistent with the story bible). Cite the exact contradicting text verbatim."
    ),
    "title": (
        "Task: the text above is a scene description. Read it and generate ONE concise, "
        "evocative scene title that captures its central action or image — a short noun "
        "phrase, at most 8 words, no quotation marks, no trailing punctuation. Do not "
        "invent plot facts beyond what is in the text above or the codex context provided "
        "earlier. Output only the title — nothing else, no commentary or preamble."
    ),
}

_TEMPERATURE_BY_MODE: dict[Mode, float] = {
    "grammar": 0.3,
    "continuity": 0.3,
    "prose": 0.7,
    "title": 0.3,
}

_ENTRY_SEPARATOR = "\n---\n"
_EMPTY_CODEX_BLOCK = "## CODEX CONTEXT ##\n(no codex entries linked)"

# ── Merge task instruction — static, sits AFTER the variable (labeled multi-scene) text ───
# Output shape mirrors the plain-text convention of `_TASK_INSTRUCTIONS` above (no JSON,
# just a predictable delimited plain-text shape) so a later response parser can split on
# the "TITLE:"/"DESCRIPTION:" markers the same way callers already just take the model's
# raw text for grammar/prose/continuity.
_MERGE_TASK_INSTRUCTION = (
    "Task: the text above contains multiple source scenes, each introduced by a "
    "'--- Scene: <title> ---' label, in story order. Combine ALL of them into ONE "
    "coherent merged scene. Preserve every plot-relevant detail from every source scene "
    "above and the codex context provided earlier — do not invent new plot facts, "
    "characters, or events. Do not simply concatenate the source text; rewrite it into "
    "one continuous scene. Output only the merged result, in exactly this format, with "
    "no additional commentary:\n\n"
    "TITLE: <merged scene title>\n"
    "DESCRIPTION:\n"
    "<merged scene description>"
)

_SCENE_LABEL_TEMPLATE = "--- Scene: {title} ---\n{description}"


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


def temperature_for(mode: Mode) -> float:
    """Sampling temperature per mode (docs/04 "Enhance call flow"): 0.3 favors precision
    for grammar/continuity/title, 0.7 gives more latitude for prose phrasing."""
    if mode not in _TEMPERATURE_BY_MODE:
        raise ValueError(f"Unknown Enhance mode: {mode!r}")
    return _TEMPERATURE_BY_MODE[mode]


def _render_value(value: Any, indent: int) -> str:
    """Deterministic rendering for nested dict/list custom-field values. Dict keys are
    sorted (recursively); list order is preserved as given (assumed already deterministic)."""
    pad = " " * indent
    if isinstance(value, dict):
        lines = []
        for key in sorted(value.keys()):
            sub = value[key]
            if isinstance(sub, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.append(_render_value(sub, indent + 2))
            else:
                lines.append(f"{pad}{key}: {sub}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.append(_render_value(item, indent + 2))
            else:
                lines.append(f"{pad}- {item}")
        return "\n".join(lines)
    return f"{pad}{value}"


def _render_entry(entry: dict[str, Any]) -> str:
    """Stable per-entry field order: name, type, summary, then custom_fields keys sorted
    alphabetically, then relationships (if any) sorted deterministically. No id, no
    timestamps — nothing volatile-positioned."""
    lines = [
        f"name: {entry['name']}",
        f"type: {entry['entry_type']}",
        f"summary: {entry.get('summary') or ''}",
    ]
    custom_fields = entry.get("custom_fields") or {}
    if custom_fields:
        lines.append("custom_fields:")
        for key in sorted(custom_fields.keys()):
            value = custom_fields[key]
            if isinstance(value, (dict, list)):
                lines.append(f"  {key}:")
                lines.append(_render_value(value, 4))
            else:
                lines.append(f"  {key}: {value}")
    relationships = entry.get("relationships") or []
    if relationships:
        lines.append("relationships:")
        ordered_rels = sorted(
            relationships,
            key=lambda r: (r["type"], r["with"], r.get("description") or ""),
        )
        for rel in ordered_rels:
            line = f"  - {rel['type']}: {rel['with']}"
            description = rel.get("description") or ""
            if description:
                line += f" — {description}"
            lines.append(line)
    return "\n".join(lines)


def serialize_codex_block(entries: list[dict[str, Any]]) -> str:
    """Deterministic serialization of resolved codex entries into a single prefix-cacheable
    block. Byte-identical across calls given the same logical input, because:

    * entries are sorted by a stable key (``id`` then ``name``) rather than input order,
    * each entry's fields are always emitted in the same order,
    * custom_fields keys are sorted alphabetically,
    * nothing volatile (timestamps, request-varying UUID positions) is emitted.

    ``entries`` items are dicts with keys: ``id``, ``name``, ``entry_type``, ``summary``,
    ``custom_fields``, ``relationships`` — the shape returned by :func:`build_codex_context`.
    """
    if not entries:
        return _EMPTY_CODEX_BLOCK
    ordered = sorted(entries, key=lambda e: (e["id"], e["name"]))
    blocks = [_render_entry(e) for e in ordered]
    return "## CODEX CONTEXT ##\n" + _ENTRY_SEPARATOR.join(blocks)


def token_budget_trim(codex_block: str, max_chars: int) -> str:
    """Trim a serialized codex block to fit ``max_chars`` by dropping lowest-priority
    entries from the END of the block — never reordering or rewriting survivors — so the
    resulting string's PREFIX (the entries that remain) is byte-identical to what it would
    have been without trimming. This is what keeps the KV-cache prefix stable even as the
    budget forces some low-priority entries out on a given call.
    """
    if len(codex_block) <= max_chars:
        return codex_block
    if codex_block == _EMPTY_CODEX_BLOCK:
        return codex_block[:max_chars]

    header, _, rest = codex_block.partition("\n")
    entry_blocks = rest.split(_ENTRY_SEPARATOR)
    survivors = list(entry_blocks)
    while survivors:
        candidate = header + "\n" + _ENTRY_SEPARATOR.join(survivors)
        if len(candidate) <= max_chars:
            return candidate
        survivors.pop()  # drop the lowest-priority (last) entry; keep the prefix stable
    return header[:max_chars]


def build_codex_context(db: Session, scene_id: str, book_id: str) -> list[dict[str, Any]]:
    """Resolve the codex entries relevant to ``scene_id`` within ``book_id``:

    1. SEED   — entries directly linked to the scene via ``codex_scene_links``.
    2. EXPAND — one hop out through ``codex_relationships`` (either direction).
    3. RESOLVE-TIME — apply the point-in-time ``codex_arc_states`` filter (anti-spoiler
       rule, see module docstring): only the latest arc-state with
       ``as_of_outline_order_index <= this scene's outline_order_index`` is folded into the
       entry's ``custom_fields``. If the scene has no outline placement in this Book yet,
       arc-state resolution is skipped entirely (safe fallback — omission can't spoil).

    Returns a list of plain dicts (id, name, entry_type, summary, custom_fields,
    relationships) ready for :func:`serialize_codex_block`. Order is NOT meaningful here —
    serialization re-sorts. ``relationships`` contains only edges whose OTHER endpoint is
    also present in the resolved set (self-contained — no dangling references), rendered as
    ``{"type", "with", "description"}`` with the other entry's name resolved.
    """
    seed_ids: set[str] = set(
        db.execute(
            select(CodexSceneLink.codex_entry_id).where(CodexSceneLink.scene_id == scene_id)
        ).scalars()
    )

    hop_ids: set[str] = set()
    if seed_ids:
        rel_rows = db.execute(
            select(CodexRelationship.from_entry_id, CodexRelationship.to_entry_id).where(
                CodexRelationship.from_entry_id.in_(seed_ids)
                | CodexRelationship.to_entry_id.in_(seed_ids)
            )
        ).all()
        for from_id, to_id in rel_rows:
            if from_id in seed_ids:
                hop_ids.add(to_id)
            if to_id in seed_ids:
                hop_ids.add(from_id)

    all_ids = seed_ids | hop_ids
    if not all_ids:
        return []

    entries = list(db.execute(select(CodexEntry).where(CodexEntry.id.in_(all_ids))).scalars())

    # Full relationship rows (type + description) between entries both present in the
    # resolved set — used to render the "relationships" list on each entry below.
    full_rel_rows = list(
        db.execute(
            select(CodexRelationship).where(
                CodexRelationship.from_entry_id.in_(all_ids),
                CodexRelationship.to_entry_id.in_(all_ids),
            )
        ).scalars()
    )
    name_by_id = {entry.id: entry.name for entry in entries}
    relationships_by_id: dict[str, list[dict[str, Any]]] = {entry_id: [] for entry_id in all_ids}
    for rel in full_rel_rows:
        if rel.from_entry_id not in name_by_id or rel.to_entry_id not in name_by_id:
            continue
        relationships_by_id[rel.from_entry_id].append(
            {
                "type": rel.relationship_type,
                "with": name_by_id[rel.to_entry_id],
                "description": rel.description or "",
            }
        )
        relationships_by_id[rel.to_entry_id].append(
            {
                "type": rel.relationship_type,
                "with": name_by_id[rel.from_entry_id],
                "description": rel.description or "",
            }
        )

    scene_outline_index = db.execute(
        select(BookSceneOrder.outline_order_index).where(
            BookSceneOrder.book_id == book_id, BookSceneOrder.scene_id == scene_id
        )
    ).scalar_one_or_none()

    resolved: list[dict[str, Any]] = []
    for entry in entries:
        custom_fields = dict(entry.custom_fields or {})

        if scene_outline_index is not None:
            arc_state = db.execute(
                select(CodexArcState)
                .where(
                    CodexArcState.codex_entry_id == entry.id,
                    CodexArcState.book_id == book_id,
                    CodexArcState.as_of_outline_order_index <= scene_outline_index,
                )
                .order_by(
                    CodexArcState.as_of_outline_order_index.desc(),
                    CodexArcState.created_at.desc(),
                    CodexArcState.id.desc(),
                )
                .limit(1)
            ).scalar_one_or_none()
            if arc_state is not None:
                if arc_state.status_summary:
                    custom_fields["arc_status_summary"] = arc_state.status_summary
                if arc_state.traits_snapshot:
                    custom_fields["arc_traits_snapshot"] = arc_state.traits_snapshot

        resolved.append(
            {
                "id": entry.id,
                "name": entry.name,
                "entry_type": entry.entry_type,
                "summary": entry.summary,
                "custom_fields": custom_fields,
                "relationships": relationships_by_id.get(entry.id, []),
            }
        )
    return resolved


def build_enhance_prompt(
    db: Session,
    *,
    mode: Mode,
    text: str,
    scene_id: str | None = None,
    book_id: str | None = None,
) -> list[dict[str, str]]:
    """Assemble the ordered chat-message list for an Enhance/continuity call.

    Hard order (see module docstring): [static system] -> [codex block] ->
    [variable scene text] -> [task instruction]. Returns plain ``{"role","content"}`` dicts
    (the shape LiteLLM/`litellm.completion(messages=...)` expects) so the later
    orchestrator (task D1) can pass this straight through.
    """
    if mode not in _TASK_INSTRUCTIONS:
        raise ValueError(f"Unknown Enhance mode: {mode!r}")

    entries: list[dict[str, Any]] = []
    if scene_id is not None and book_id is not None:
        entries = build_codex_context(db, scene_id=scene_id, book_id=book_id)
    codex_block = serialize_codex_block(entries)

    messages = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="system", content=codex_block),
        ChatMessage(role="user", content=text),
        ChatMessage(role="user", content=_TASK_INSTRUCTIONS[mode]),
    ]
    return [m.as_dict() for m in messages]


def _resolve_merge_order(
    db: Session, *, book_id: str, scenes: list[Scene]
) -> list[Scene]:
    """Deterministic source-scene order for a merge (PHASE11.md Workstream B task 8):
    ``book_scene_order.timeline_order_index`` when EVERY given scene has one recorded
    for this Book, else fall back to ``Scene.created_at``. This is an all-or-nothing
    choice (not a per-scene mixed key) so the ordering signal is never half-trusted —
    either the whole group has a reliable chronological placement, or none of it does.
    """
    order_rows = db.execute(
        select(BookSceneOrder.scene_id, BookSceneOrder.timeline_order_index).where(
            BookSceneOrder.book_id == book_id,
            BookSceneOrder.scene_id.in_([s.id for s in scenes]),
        )
    ).all()
    timeline_index_by_scene_id = {
        scene_id: index for scene_id, index in order_rows if index is not None
    }

    if len(timeline_index_by_scene_id) == len(scenes):
        return sorted(scenes, key=lambda s: timeline_index_by_scene_id[s.id])
    return sorted(scenes, key=lambda s: (s.created_at, s.id))


def build_merge_prompt(
    db: Session,
    scene_ids: list[str],
    *,
    book_id: str,
) -> list[dict[str, str]]:
    """Assemble the ordered chat-message list for an AI-assisted multi-scene merge
    (PHASE11.md Workstream B, "AI-assisted merge reusing the Enhance seam exactly").

    Same hard order as :func:`build_enhance_prompt` (module docstring): [static system]
    -> [codex block] -> [variable multi-scene text] -> [task instruction]. Returns the
    same plain ``{"role","content"}`` dict shape so `llm_orchestrator.py`/the future
    ``POST /llm/merge-scenes`` route can pass this straight through unchanged.

    ``scene_ids`` must all resolve to existing ``Scene`` rows — raises
    ``ValueError("SCENE_NOT_FOUND")`` (same sentinel `outline_service.py` uses) the
    moment any id doesn't. ``book_id`` scopes both the codex context and the
    ``book_scene_order`` lookup used for deterministic source ordering — merging is a
    per-Book canvas operation, the same way `build_enhance_prompt`'s codex context is
    scoped to one (scene_id, book_id) pair.
    """
    if not scene_ids:
        raise ValueError("SCENE_IDS_REQUIRED")

    scenes_by_id = {
        scene.id: scene
        for scene in db.execute(select(Scene).where(Scene.id.in_(scene_ids))).scalars()
    }
    missing = [scene_id for scene_id in scene_ids if scene_id not in scenes_by_id]
    if missing:
        raise ValueError("SCENE_NOT_FOUND")

    # De-duplicate while preserving first-seen order, in case a caller passes the same
    # scene_id twice — a merge should never absorb the same source scene's text twice.
    unique_scenes = list({scene_id: scenes_by_id[scene_id] for scene_id in scene_ids}.values())
    ordered_scenes = _resolve_merge_order(db, book_id=book_id, scenes=unique_scenes)

    # Codex context: union across all source scenes, each resolved via the SAME
    # anti-spoiler-aware `build_codex_context` Enhance uses (module docstring "Anti-spoiler
    # rule") — no new scoping rule invented here. Scenes are walked in the deterministic
    # (earliest-first) order just established, and an entry id is kept from the FIRST
    # (earliest) scene it's resolved for — the conservative choice, since a later scene's
    # arc-state resolution could otherwise leak a fact that hasn't happened yet from an
    # earlier source scene's point of view into the merged block.
    codex_entries_by_id: dict[str, dict[str, Any]] = {}
    for scene in ordered_scenes:
        for entry in build_codex_context(db, scene_id=scene.id, book_id=book_id):
            codex_entries_by_id.setdefault(entry["id"], entry)
    codex_block = serialize_codex_block(list(codex_entries_by_id.values()))

    labeled_scenes = [
        _SCENE_LABEL_TEMPLATE.format(title=scene.title, description=scene.description or "")
        for scene in ordered_scenes
    ]
    combined_scene_text = "\n\n".join(labeled_scenes)

    messages = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="system", content=codex_block),
        ChatMessage(role="user", content=combined_scene_text),
        ChatMessage(role="user", content=_MERGE_TASK_INSTRUCTION),
    ]
    return [m.as_dict() for m in messages]
