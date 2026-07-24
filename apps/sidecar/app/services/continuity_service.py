"""Continuity Checker v2 — Tier 1 (docs/11-AI-INTELLIGENCE.md §4 "Tier 1 — Deterministic",
docs/06 Phase 4 task BE-4).

Pure SQL, zero LLM. Two checks, both derived from the schema's own outline/timeline
positions and arc-state introduction markers — never wrong, never voted on:

* ``early_appearance`` (severity ``warning``) — an entity linked (``codex_scene_links``) to a
  scene that's placed (``book_scene_order.outline_order_index``) *before* the earliest
  outline position at which the entity is known to exist (``MIN`` of its
  ``codex_arc_states.as_of_outline_order_index`` for this Book).
* ``timeline_conflict`` (severity ``hint``) — an adjacent-in-outline pair of scenes whose
  in-story time goes backwards, i.e. story-time order disagrees with reading order,
  excluding pairs where either scene is labeled a flashback.

DATA-SENSITIVE (a wrong flag erodes user trust): both checks only ever flag facts the
database already states about itself — no heuristics, no guessing. An entity with no
arc-state in this Book has no known introduction point and is never flagged (skip, don't
guess). A scene with no outline position is never flagged (skip, don't guess).

REGENERATION SEMANTICS (known v1 limitation, intentional): :func:`run_tier1` is fully
re-derivable — each run DELETEs this Book's existing ``source='deterministic'`` flags and
re-inserts the freshly computed set with ``status='open'``. It never touches
``source='ai'`` or ``source='manual'`` flags. This means dismissing a deterministic flag
does NOT persist across a re-run (there is no identity linking an old deterministic flag to
its regenerated successor); this is acceptable for v1 since the flags are cheap and instant
to recompute, and a genuinely fixed continuity issue simply stops appearing next run.

## Tier 2 — Semantic (LLM, guarded) — docs/11-AI-INTELLIGENCE.md §4 "Tier 2", Phase 4 BE-5

:func:`run_tier2` adds the *genuinely* semantic checks (trait/fact contradictions) that pure
SQL can't express. v1.0 is SINGLE-PASS per scene — one reasoning call, one extraction call;
the 3-vote self-consistency pass described in docs/11 §4 point 3 is v1.1 and intentionally
NOT built here. It reuses the exact same LLM path Enhance uses
(``llm_orchestrator.get_provider_client``) — no new provider code, no network access on this
build machine (see CLAUDE.md "Environment constraints"); it is verified here only via the
``QUILLNIGHT_LLM_STUB=1`` ``EchoProvider``.

Two guards, both required by the spec, both implemented below:

1. **Two-pass CoT->JSON** (:func:`build_continuity_prompt` / :func:`build_continuity_extraction_messages`):
   PASS 1 asks the model to reason in free prose only; PASS 2 is a follow-up call on the same
   conversation asking it to convert that reasoning into a JSON array, with the schema
   ordering ``reasoning``/``evidence``/``quote`` FIRST and ``flag_type``/``severity`` LAST
   (answer-last — think before committing).
2. **Verbatim-quote guardrail** (:func:`apply_quote_guardrail`): a candidate flag is only ever
   persisted if its ``quote`` field is an exact (whitespace-normalized) substring of the
   scene's actual text. This is a plain, pure, standalone function — no DB, no model — see
   its docstring for the exact normalization rule. No match -> silently dropped, always.

CRASH-PROOF ON MODEL OUTPUT: PASS 2's output is untrusted text from a small model (or, under
the stub, an echoed instruction that is NOT JSON at all). :func:`run_tier2` must never raise
because of it — see :func:`_parse_candidates`, which treats any parse failure as zero
candidates rather than propagating an exception.

NEVER WRITES SCENE TEXT: :func:`run_tier2` and every helper it calls only ever READ
``Scene.description`` (to build prompts and to run the guardrail's substring check). There is
no ``db.add``/``setattr`` on a ``Scene`` row anywhere in this module — the only rows this
module ever writes are ``ContinuityFlag`` rows.

REGENERATION SEMANTICS mirror Tier 1, scoped to ``source='ai'``: each run DELETEs this Book's
existing ``source='ai'`` flags and re-inserts the freshly computed, guardrail-survived set.
``source='deterministic'``/``source='manual'`` flags are never touched by this function.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.db.base import new_uuid
from app.models.orm import (
    Book,
    BookSceneOrder,
    CodexArcState,
    CodexEntry,
    CodexSceneLink,
    ContinuityFlag,
    Scene,
)
from app.services import groq_key
from app.services.llm_orchestrator import ProviderClient, get_provider_client
from app.services.prompt_builder import (
    SYSTEM_PROMPT,
    ChatMessage,
    build_codex_context,
    serialize_codex_block,
    temperature_for,
)
from app.services.settings_service import get_all_settings

_VALID_STATUSES = {"open", "dismissed", "resolved"}
_VALID_FLAG_TYPES = {"early_appearance", "trait_contradiction", "timeline_conflict", "custom"}
_VALID_SEVERITIES = {"critical", "warning", "hint"}

_SEVERITY_RANK = case(
    (ContinuityFlag.severity == "critical", 0),
    (ContinuityFlag.severity == "warning", 1),
    (ContinuityFlag.severity == "hint", 2),
    else_=3,
)


def _require_book(db: Session, book_id: str) -> None:
    if db.get(Book, book_id) is None:
        raise ValueError("BOOK_NOT_FOUND")


# ── Check A — early_appearance ──────────────────────────────────────────────────


def _check_early_appearance(db: Session, book_id: str) -> list[ContinuityFlag]:
    """Entity linked to a scene ordered before its earliest arc-state introduction index
    in this Book. Entities with no arc-state in this Book (no known introduction point) and
    scenes with no outline position are skipped — never guessed at."""
    intro_subq = (
        select(
            CodexArcState.codex_entry_id.label("codex_entry_id"),
            func.min(CodexArcState.as_of_outline_order_index).label("intro_index"),
        )
        .where(CodexArcState.book_id == book_id)
        .group_by(CodexArcState.codex_entry_id)
        .subquery()
    )

    rows = db.execute(
        select(
            CodexEntry.id.label("codex_entry_id"),
            CodexEntry.name.label("entry_name"),
            CodexSceneLink.scene_id.label("scene_id"),
            BookSceneOrder.outline_order_index.label("scene_index"),
            intro_subq.c.intro_index.label("intro_index"),
        )
        .join(intro_subq, intro_subq.c.codex_entry_id == CodexEntry.id)
        .join(CodexSceneLink, CodexSceneLink.codex_entry_id == CodexEntry.id)
        .join(BookSceneOrder, BookSceneOrder.scene_id == CodexSceneLink.scene_id)
        .where(BookSceneOrder.book_id == book_id)
        .where(BookSceneOrder.outline_order_index.is_not(None))
        .where(BookSceneOrder.outline_order_index < intro_subq.c.intro_index)
    ).all()

    flags: list[ContinuityFlag] = []
    for row in rows:
        description = (
            f"'{row.entry_name}' appears in a scene at outline position {row.scene_index} "
            f"but isn't introduced until position {row.intro_index}."
        )
        flags.append(
            ContinuityFlag(
                id=new_uuid(),
                book_id=book_id,
                scene_id=row.scene_id,
                codex_entry_id=row.codex_entry_id,
                flag_type="early_appearance",
                severity="warning",
                description=description,
                status="open",
                source="deterministic",
            )
        )
    return flags


# ── Check B — timeline_conflict ─────────────────────────────────────────────────


def _is_flashback(label: str | None) -> bool:
    return label is not None and "flashback" in label.lower()


def _check_timeline_conflict(db: Session, book_id: str) -> list[ContinuityFlag]:
    """Adjacent-in-outline scene pairs (both outline-placed and timeline-placed) where
    story-time decreases relative to reading order, excluding flashback-labeled scenes.
    Flags only the ADJACENT inversion (one flag per inversion, on the later-in-outline
    scene) to avoid O(n^2) spam from a single misplaced scene."""
    rows = list(
        db.execute(
            select(
                BookSceneOrder.scene_id,
                BookSceneOrder.outline_order_index,
                BookSceneOrder.in_story_time_sort_key,
                BookSceneOrder.in_story_time_label,
            )
            .where(BookSceneOrder.book_id == book_id)
            .where(BookSceneOrder.outline_order_index.is_not(None))
            .where(BookSceneOrder.in_story_time_sort_key.is_not(None))
            .order_by(BookSceneOrder.outline_order_index, BookSceneOrder.scene_id)
        )
    )

    flags: list[ContinuityFlag] = []
    for prev, cur in zip(rows, rows[1:]):
        if cur.in_story_time_sort_key >= prev.in_story_time_sort_key:
            continue
        if _is_flashback(prev.in_story_time_label) or _is_flashback(cur.in_story_time_label):
            continue
        description = (
            f"Scene at outline position {cur.outline_order_index} occurs earlier in "
            "story-time than the preceding scene — possible timeline inversion."
        )
        flags.append(
            ContinuityFlag(
                id=new_uuid(),
                book_id=book_id,
                scene_id=cur.scene_id,
                codex_entry_id=None,
                flag_type="timeline_conflict",
                severity="hint",
                description=description,
                status="open",
                source="deterministic",
            )
        )
    return flags


# ── Public API ───────────────────────────────────────────────────────────────────


def run_tier1(db: Session, book_id: str) -> list[ContinuityFlag]:
    """Recompute all Tier-1 deterministic flags for ``book_id``.

    Raises ``ValueError("BOOK_NOT_FOUND")`` if the Book doesn't exist. Deletes this Book's
    existing ``source='deterministic'`` flags and inserts the freshly computed set — see
    the module docstring's REGENERATION SEMANTICS. ``source='ai'``/``source='manual'`` flags
    for this Book are never touched. Commits once. Returns the Book's current full flag
    list afterward (deterministic + any surviving ai/manual flags).
    """
    _require_book(db, book_id)

    new_flags = _check_early_appearance(db, book_id) + _check_timeline_conflict(db, book_id)

    db.execute(
        delete(ContinuityFlag).where(
            ContinuityFlag.book_id == book_id, ContinuityFlag.source == "deterministic"
        )
    )
    for flag in new_flags:
        db.add(flag)
    db.commit()

    return list_flags(db, book_id)


# ── Tier 2 — Semantic (LLM, guarded) ─────────────────────────────────────────────

# PASS 1 — free-prose reasoning only; deliberately asks for NO JSON (see module docstring
# "Two-pass CoT->JSON" / docs/11 §4 point 1: JSON-constrained decoding measurably degrades
# reasoning in small models).
_CONTINUITY_REASONING_TASK = (
    "Task: analyze the SCENE TEXT above against the CODEX CONTEXT provided earlier. Think "
    "step by step, in free prose, about whether anything stated or implied in the scene "
    "text contradicts an established trait, fact, or relationship from the codex context "
    "(for example: a described eye/hair color that differs, a stated location that "
    "conflicts, a relationship that's inconsistent with what's on record). Do not produce "
    "JSON yet — reason in plain prose only, and if you find nothing, say so."
)

# PASS 2 — extraction only, follow-up call on the SAME conversation (pass-1 messages +
# pass-1's own reasoning output, appended as an assistant turn, precede this task).
# Schema order is REQUIRED to be reasoning/evidence/quote first, flag_type/severity last —
# answer-last, per docs/11 §4 point 1.
_CONTINUITY_EXTRACTION_TASK = (
    "Task: convert your analysis above into a JSON array (and ONLY a JSON array — no "
    "markdown fences, no commentary). If you found no contradictions, output exactly []. "
    "Each element of the array must be a JSON object with EXACTLY these keys, in this "
    "order:\n"
    '  "reasoning": a short restatement of why this is a contradiction,\n'
    '  "evidence": the specific codex fact being contradicted,\n'
    '  "quote": the EXACT verbatim substring of the SCENE TEXT above that contains the '
    "contradiction — copy it character-for-character from the scene text, never paraphrase "
    "or summarize it,\n"
    '  "entity": the name of the codex entry involved, if any, else null,\n'
    '  "flag_type": one of "trait_contradiction", "early_appearance", "timeline_conflict", '
    '"custom",\n'
    '  "severity": one of "critical", "warning", "hint".\n'
    "Output ONLY the JSON array."
)


def build_continuity_prompt(
    db: Session, scene: Scene, codex_facts: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """PASS 1 (reasoning) message list for a single scene's Tier-2 pass.

    Mirrors ``prompt_builder.build_enhance_prompt``'s cache-friendly ordering — [static
    system] -> [codex facts block] -> [variable scene text] -> [task instruction] — and
    reuses ``prompt_builder.SYSTEM_PROMPT``/``serialize_codex_block`` verbatim so the codex
    block byte-matches Enhance's own serialization of the same facts. ``db`` is accepted (and
    currently unused directly) to match this module's other Session-taking helpers and leave
    room for a future DB-backed refinement without changing the call signature; ``codex_facts``
    is expected to already be resolved via ``prompt_builder.build_codex_context`` by the
    caller (:func:`run_tier2`), so this function itself makes no DB calls.
    """
    del db  # accepted for signature symmetry / future use; unused — see docstring
    codex_block = serialize_codex_block(codex_facts)
    messages = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="system", content=codex_block),
        ChatMessage(role="user", content=f"## SCENE TEXT ##\n{scene.description or ''}"),
        ChatMessage(role="user", content=_CONTINUITY_REASONING_TASK),
    ]
    return [m.as_dict() for m in messages]


def build_continuity_extraction_messages(
    pass1_messages: list[dict[str, str]], reasoning_text: str
) -> list[dict[str, str]]:
    """PASS 2 (extraction) message list — the PASS 1 messages, plus PASS 1's own reasoning
    output appended as an ``assistant`` turn, plus the JSON-extraction task instruction as
    the final ``user`` turn (so ``EchoProvider``/real providers alike see it as a normal
    follow-up turn in the same conversation)."""
    return [
        *pass1_messages,
        {"role": "assistant", "content": reasoning_text},
        {"role": "user", "content": _CONTINUITY_EXTRACTION_TASK},
    ]


async def _run_pass(
    provider_client: ProviderClient,
    messages: list[dict[str, str]],
    *,
    ai_mode: str,
    groq_model: str | None,
    groq_key_value: str | None,
    groq_zdr_enabled: bool,
    temperature: float,
) -> str:
    """Runs one LLM call through the shared orchestrator and collects the full text.

    Crash-proof against provider failures (e.g. every leg unavailable): returns "" rather
    than raising, so a single scene's Tier-2 pass failing never aborts the whole book's
    check — see :func:`run_tier2`'s "CRASH-PROOF" guarantee.
    """
    parts: list[str] = []
    try:
        async for chunk in provider_client.stream(
            messages,
            ai_mode=ai_mode,  # type: ignore[arg-type]
            groq_model=groq_model,
            groq_key=groq_key_value,
            groq_zdr_enabled=groq_zdr_enabled,
            temperature=temperature,
        ):
            parts.append(chunk["delta"])
    except Exception:  # noqa: BLE001 — provider-agnostic, must never crash Tier 2
        return "".join(parts)
    return "".join(parts)


def _try_parse_json_candidates(text: str) -> list[dict[str, Any]] | None:
    """Attempts one JSON parse of ``text``. Returns the candidate list on success (accepting
    either a bare JSON array, or a JSON object with a ``"flags"`` array — a common
    small-model wrapping quirk), or ``None`` on any failure/wrong shape. Never raises."""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        flags = parsed.get("flags")
        if isinstance(flags, list):
            return [item for item in flags if isinstance(item, dict)]
    return None


def _parse_candidates(text: str) -> list[dict[str, Any]]:
    """Robustly parses PASS 2's extraction output into a list of candidate flag dicts.

    Model output (real or, under test, the ``EchoProvider`` stub's echoed instruction text)
    is UNTRUSTED and may not be valid JSON at all — this NEVER raises. It first tries a
    direct parse of the whole string; failing that, it tries the substring between the
    first ``[`` and the last ``]`` (small models sometimes wrap the array in prose or
    markdown fences despite instructions not to). Any failure at either stage yields an
    empty list — this is what keeps :func:`run_tier2` crash-proof under the stub, which
    echoes plain instruction prose containing no ``[``/``]`` pair at all.
    """
    candidates = _try_parse_json_candidates(text)
    if candidates is not None:
        return candidates

    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidates = _try_parse_json_candidates(text[start : end + 1])
        if candidates is not None:
            return candidates

    return []


def _normalize_for_quote_match(text: str) -> str:
    """The guardrail's normalization rule, applied identically to BOTH the candidate's
    ``quote`` and the scene's actual text before the substring check: strip leading/trailing
    whitespace, then collapse every internal run of whitespace (spaces, tabs, newlines) to a
    single space. This tolerates a model reformatting incidental whitespace (e.g. a line
    wrap) inside an otherwise-verbatim quote, while still rejecting any quote that isn't
    actually present in the scene."""
    return " ".join(text.split())


def apply_quote_guardrail(
    candidates: list[dict[str, Any]], scene_text: str
) -> list[dict[str, Any]]:
    """The verbatim-quote guardrail (docs/11 §4 point 2) — pure, standalone, no DB/model.

    Keeps only candidates whose ``quote`` field, after :func:`_normalize_for_quote_match`
    normalization, is an exact substring of the similarly-normalized ``scene_text``. Any
    candidate that isn't a dict, has no non-empty string ``quote``, or whose (normalized)
    quote doesn't appear in the (normalized) scene text is DROPPED — silently, with no
    partial credit, no fuzzy matching. This is the mechanical hallucination filter: a
    fabricated quote can never survive this check no matter how plausible its surrounding
    ``reasoning``/``evidence`` text sounds.
    """
    normalized_scene = _normalize_for_quote_match(scene_text)
    kept: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        quote = candidate.get("quote")
        if not isinstance(quote, str):
            continue
        normalized_quote = _normalize_for_quote_match(quote)
        if not normalized_quote:
            continue
        if normalized_quote in normalized_scene:
            kept.append(candidate)
    return kept


def _resolve_entity_id(entity_name: Any, codex_facts: list[dict[str, Any]]) -> str | None:
    """Best-effort, case-insensitive match of a model-named ``entity`` string against the
    codex facts actually supplied for this scene. No match (including a missing/blank/
    non-string ``entity``) -> ``None`` — never guesses at a codex_entry_id."""
    if not isinstance(entity_name, str) or not entity_name.strip():
        return None
    target = entity_name.strip().lower()
    for entry in codex_facts:
        if str(entry.get("name", "")).strip().lower() == target:
            return entry.get("id")
    return None


def _build_ai_flag(
    candidate: dict[str, Any],
    *,
    book_id: str,
    scene_id: str,
    codex_facts: list[dict[str, Any]],
) -> ContinuityFlag:
    """Builds one ``source='ai'`` ContinuityFlag row from a guardrail-survived candidate.
    Validates ``flag_type``/``severity`` against the schema's allowed sets, defaulting to
    ``trait_contradiction``/``warning`` respectively when missing or invalid — never trusts
    the model to have stayed in-schema."""
    flag_type = candidate.get("flag_type")
    if flag_type not in _VALID_FLAG_TYPES:
        flag_type = "trait_contradiction"
    severity = candidate.get("severity")
    if severity not in _VALID_SEVERITIES:
        severity = "warning"

    reasoning = str(candidate.get("reasoning") or "").strip()
    evidence = str(candidate.get("evidence") or "").strip()
    quote = str(candidate.get("quote") or "").strip()
    description = " — ".join(part for part in (reasoning, evidence) if part)
    if not description:
        description = quote or "AI-flagged continuity issue (no description provided)."

    return ContinuityFlag(
        id=new_uuid(),
        book_id=book_id,
        scene_id=scene_id,
        codex_entry_id=_resolve_entity_id(candidate.get("entity"), codex_facts),
        flag_type=flag_type,
        severity=severity,
        description=description,
        status="open",
        source="ai",
    )


async def run_tier2(db: Session, book_id: str) -> list[ContinuityFlag]:
    """Recomputes all Tier-2 semantic (LLM-guarded) flags for ``book_id`` — see the module
    docstring's "Tier 2" section for the full guard/regeneration/never-writes-scene-text
    contract. Raises ``ValueError("BOOK_NOT_FOUND")`` if the Book doesn't exist. Reuses the
    exact orchestrator path Enhance uses (Router/EchoProvider under
    ``QUILLNIGHT_LLM_STUB=1``) — no new LLM plumbing, no network access on this build
    machine. Commits once. Returns the Book's current full flag list afterward.
    """
    _require_book(db, book_id)

    settings = get_all_settings(db)
    ai_mode = settings.get("ai_mode", "offline")
    groq_model = settings.get("groq_model_name")
    groq_zdr_enabled = settings.get("groq_zdr_enabled", True)
    resolved_groq_key = groq_key.get_key()
    temperature = temperature_for("continuity")
    provider_client = get_provider_client()

    # Scenes eligible for Tier 2: placed in this Book's outline (has a book_scene_order row)
    # AND has scene text — an unplaced or empty scene is skipped, never guessed at (same
    # "skip, don't guess" discipline as Tier 1). READ-ONLY: `Scene.description` is only ever
    # read below, never written — see module docstring "NEVER WRITES SCENE TEXT".
    scenes = list(
        db.execute(
            select(Scene)
            .join(BookSceneOrder, BookSceneOrder.scene_id == Scene.id)
            .where(BookSceneOrder.book_id == book_id)
            .where(Scene.description.is_not(None))
            .where(Scene.description != "")
            .order_by(BookSceneOrder.outline_order_index, Scene.id)
        ).scalars()
    )

    new_flags: list[ContinuityFlag] = []
    for scene in scenes:
        codex_facts = build_codex_context(db, scene_id=scene.id, book_id=book_id)

        pass1_messages = build_continuity_prompt(db, scene, codex_facts)
        reasoning_text = await _run_pass(
            provider_client,
            pass1_messages,
            ai_mode=ai_mode,
            groq_model=groq_model,
            groq_key_value=resolved_groq_key,
            groq_zdr_enabled=groq_zdr_enabled,
            temperature=temperature,
        )

        pass2_messages = build_continuity_extraction_messages(pass1_messages, reasoning_text)
        extraction_text = await _run_pass(
            provider_client,
            pass2_messages,
            ai_mode=ai_mode,
            groq_model=groq_model,
            groq_key_value=resolved_groq_key,
            groq_zdr_enabled=groq_zdr_enabled,
            temperature=temperature,
        )

        candidates = _parse_candidates(extraction_text)
        kept = apply_quote_guardrail(candidates, scene.description or "")
        for candidate in kept:
            new_flags.append(
                _build_ai_flag(candidate, book_id=book_id, scene_id=scene.id, codex_facts=codex_facts)
            )

    db.execute(
        delete(ContinuityFlag).where(ContinuityFlag.book_id == book_id, ContinuityFlag.source == "ai")
    )
    for flag in new_flags:
        db.add(flag)
    db.commit()

    return list_flags(db, book_id)


def list_flags(db: Session, book_id: str, status: str | None = None) -> list[ContinuityFlag]:
    """Flags for ``book_id``, optionally filtered by ``status``, ordered by severity
    (critical, warning, hint) then id for stable display order."""
    stmt = select(ContinuityFlag).where(ContinuityFlag.book_id == book_id)
    if status is not None:
        stmt = stmt.where(ContinuityFlag.status == status)
    stmt = stmt.order_by(_SEVERITY_RANK, ContinuityFlag.id)
    return list(db.execute(stmt).scalars())


def update_flag_status(db: Session, flag_id: str, status: str) -> ContinuityFlag | None:
    """Set an existing flag's ``status`` (open/dismissed/resolved).

    Raises ``ValueError("INVALID_STATUS")`` for any other value. Returns ``None`` if the
    flag doesn't exist.
    """
    if status not in _VALID_STATUSES:
        raise ValueError("INVALID_STATUS")
    flag = db.get(ContinuityFlag, flag_id)
    if flag is None:
        return None
    flag.status = status
    db.commit()
    db.refresh(flag)
    return flag
