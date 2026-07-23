# PHASE3.md — Phase 3 (Full Codex) Working Directive

Loaded into context for Phase 3. Supersedes CLAUDE.md only where noted below
(resolved with the user). Keep this file < 100 lines.

## 1. Project & Phase Context

Stack: Tauri 2 (deferred) · React 19 + TS + Vite + Tailwind v4 + shadcn/ui +
React Flow + Zustand + TanStack Query · Python 3.13 FastAPI sidecar (port 8756)
+ SQLAlchemy 2 + Alembic + Pydantic v2 · SQLite. Codex backend/FE stubs already
exist (`app/api/codex.py`, `codex_service.py`, `components/canvas/codex-panel.tsx`,
`queries/codex.ts`) from Phase 2 — Phase 3 COMPLETES them.

Phase 3 goals (docs/06 §Phase 3, docs/03 §Codex):
- All 4 Codex entity types (character / location / item / lore) with editors.
- Custom-fields JSON editor per entity (arbitrary user key/values).
- `codex_relationships` cross-linking UI (entity ↔ entity).
- `codex_arc_states` entry (per-scene entity state; feeds anti-spoiler filter).
- Single-image attach per entity.
- Deterministic Codex serialization (stable ordering) so the prompt-cache
  prefix stays byte-identical across edits.
- Demo: populated Codex w/ cross-links, linked from canvas nodes, visibly
  informing an Enhance call's context.

## 2. Strict Execution Protocol (user-resolved overrides)

- PLAN in **main-session Plan Mode using Opus** (not the architect subagent),
  effort tuned to task weight. Explore → Plan → Implement → Verify. Present the
  plan; wait for ExitPlanMode approval before ANY edit.
- IMPLEMENT via **`builder` (Sonnet) subagents, autonomous** — no per-edit
  confirmation. One scoped task (1–3 files) per builder call.
- Security/data-sensitive tasks (arc-state anti-spoiler filter, image bytes,
  deterministic serialization affecting prompt cache) get a `reviewer` (Opus)
  pass before the phase is marked done — carried over from CLAUDE.md.
- Output: code diffs + bullets only. No pleasantries. Targeted edits only —
  never rewrite a whole file to fix a block.

## 3. Token & Context Efficiency

- Search targeted paths only (Grep/Glob with a pattern). Never read whole dirs
  or unrequested files. Reference doc sections by path (e.g. `docs/03 §Codex`),
  don't re-paste.
- Fix bugs by editing the target function/lines, not the file.
- Run `/compact` or `/clear` when switching tasks to prune history.

## 4. Verification & Environment Commands

Backend (cwd `apps/sidecar`):
- Test: `QUILLNIGHT_LLM_STUB=1 QUILLNIGHT_STT_STUB=1 .venv/Scripts/python.exe -m pytest -q`
- Lint: `.venv/Scripts/python.exe -m ruff check app tests`

Frontend (cwd `apps/desktop`):
- Build/typecheck: `npm run build`   (tsc -b && vite build)
- Lint: `npm run lint`   (oxlint)
- Type sync (backend must be running): `NODE_OPTIONS=--use-system-ca npm run gen:types`

Run both: `./scripts/dev.ps1` (sidecar stub + Vite).

Self-verify rule: after edits, run the relevant test + lint above and confirm
green BEFORE declaring a task complete. Report the actual summary line.

## 5. Process carry-over

At the start of every new phase, create `PHASE<N>.md` in root following this
same template, resolving any CLAUDE.md overlaps with the user first.
