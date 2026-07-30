# PHASE10.md — Phase 10 (Semantic layer) Directive — this-machine slice only

Loaded for Phase 10. Status: **In progress (started 2026-07-30)** — this
covers only the part of Phase 10 buildable on this Python+Node-only,
no-Ollama machine. Full spec: `docs/06-ROADMAP.md` Phase 10,
`docs/11-AI-INTELLIGENCE.md`.

## 1. Scope — this-machine-buildable only

`sqlite-vec` (PyPI, Windows wheel, no model involved — confirmed installable
here) and FTS5 (built into SQLite) need no real model. The only genuinely
model-dependent piece is the actual `qwen3-embedding:0.6b` call (1024-dim,
CPU-pinned via Ollama, per `docs/11-AI-INTELLIGENCE.md` §2). Everything
else — schema, storage, hybrid search, embed-on-save plumbing, auto-link
suggestions, similar-scene detection, the frontend search UI — is buildable
and testable here behind a stub embedding function, same
`QUILLNIGHT_LLM_STUB=1` pattern used everywhere else in this codebase.

## 2. In-scope task list (sequential, one at a time)

1. Alembic migration: FTS5 virtual table (scenes+codex text) + sqlite-vec
   `vec0` table (1024-dim embeddings, scene/codex-entry scoped). Add
   `sqlite-vec` to `pyproject.toml`/`requirements.lock.txt`.
2. Embedding service: a real interface (`embed(text) -> list[float]`) with
   a deterministic stub implementation for this machine (config-gated,
   same seam as `QUILLNIGHT_LLM_STUB`), ready for the real Ollama call to
   drop in on the target machine.
3. Embed-on-save trigger (scene/codex entry create/update enqueues a
   re-embed) + a bulk backfill endpoint for existing rows.
4. Hybrid RRF search service (FTS5 keyword rank + vector cosine rank fused
   via reciprocal rank fusion) + search API endpoint.
5. Auto codex-link suggestion + similar-scene detection, built on the
   search service from task 4.
6. Frontend: search UI + `queries/search.ts`.
7. Frontend: surfacing auto-link-suggestion / similar-scene hints in the
   canvas/codex UI.

Embeddings are derived data — never included in `.quillproj` export
bundles (already true per Phase 7; this phase doesn't change that),
rebuildable at any time via the backfill endpoint.

## 3. Deferred to the target machine (ASUS TUF F15)

The real `qwen3-embedding:0.6b` Ollama call (swap into task 2's interface),
re-running the bulk backfill against real embeddings, and the actual
"semantic search finds a scene by meaning" / "auto-link suggestion" /
"near-duplicate surfaces its twin" demo criteria from `docs/06-ROADMAP.md`
— all need a real embedding model, not the stub. See `HANDOFF-ASUS-TUF.md`
§4c, updated once this slice lands to reflect what's already built here.

## 4. Outcome

**Status: this-machine-buildable slice done (2026-07-30).**

7 builder tasks, all sonnet, no reviewer pass needed (additive-only, no
encryption/export/import/generated-document code touched):

- **Schema**: `search_fts` (FTS5) + `embeddings` (`sqlite-vec` `vec0`,
  1024-dim) virtual tables, polymorphic over `entity_type IN ('scene',
  'codex_entry')` + `entity_id`. `sqlite-vec` confirmed installable here
  (pure-extension PyPI package, Windows wheel, no model involved) — the
  extension is loaded via a `connect` event listener in `app/db/base.py` so
  every application connection can see `vec0` tables, plus Alembic's own
  migration runner loads it independently.
- **Embedding service**: `embed(text) -> list[float]` with a deterministic
  stub (hash-seeded, L2-normalized) under `QUILLNIGHT_LLM_STUB=1`; the real
  `qwen3-embedding:0.6b` call is a documented drop-in, not built here.
- **Embed-on-save + backfill**: `search_index_service.py` keeps both tables
  in sync on Scene/CodexEntry create/update/delete (never blocks the actual
  save if indexing fails — derived data, not source of truth); `POST
  /search/backfill` indexes pre-existing rows.
- **Hybrid RRF search**: FTS5 keyword rank + vector KNN rank fused via
  Reciprocal Rank Fusion (`RRF_K=60`, per docs/11 §2), `GET /search`.
  Deliberately **not** Book-scoped — Scenes/CodexEntries are canonical and
  shared across Books in this app's data model; each result reports every
  Book it's linked to instead.
- **Auto-link + similar-scene suggestions**: `GET
  /search/scenes/{scene_id}/suggestions`. A real bug was caught and fixed
  here — FTS5's implicit-AND `MATCH` semantics meant passing a scene's full
  text straight through never matched anything; fixed by extracting
  distinctive words and joining them as an OR query. Suggestions-only, never
  auto-applied (same Accept/Reject posture as every AI-adjacent feature).
- **Frontend**: a `Ctrl+K` search dialog (debounced, keyboard-navigable,
  navigates to the first linked Book) and a suggestion panel in the Scene
  node editor reusing the existing manual codex-link mutation (no parallel
  link-creation path added).

Backend: 342 passed, 2 pre-existing failures — both the same known
cross-module shared-test-database ordering issue already present before
this phase (`test_continuity_flags_migration.py`; the new
`test_semantic_search_migration.py` round-trip test joined the same known
class, not a new bug — confirmed by comparing against the older test's
identical failure signature). Frontend: clean build + lint.

**Everything here was proven against a stub embedding, not real semantics**
— the mechanism (schema, indexing, RRF fusion, suggestion filtering,
frontend wiring) is real and tested; whether it actually finds
conceptually-related-but-differently-worded content is unproven until the
real `qwen3-embedding:0.6b` model runs on the target machine. Don't mistake
this slice for the finished Phase 10 demo criteria in `docs/06-ROADMAP.md`
— those still require real embeddings.

## 5. What's left — deferred to the target machine

Swap `embedding_service._embed_real` from `NotImplementedError` to the real
`litellm.embedding(model=f"ollama/{settings.default_embedding_model}", ...)`
call; re-run `POST /search/backfill` against real embeddings; verify the
actual Phase 10 demo criteria (semantic search by meaning, real auto-link
suggestions, real near-duplicate detection) per `docs/06-ROADMAP.md`. See
`HANDOFF-ASUS-TUF.md` §4c, updated below.
