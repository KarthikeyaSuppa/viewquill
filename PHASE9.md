# PHASE9.md — Phase 9 (Hardening & v1.0 release) Directive

Loaded for Phase 9. Status: **In progress (started 2026-07-30)**.

## 1. Scope — this-machine-buildable only

Literal spec (`docs/06-ROADMAP.md` Phase 9): MSI/NSIS installer bundling
Tauri+sidecar+Ollama+fonts, first-run onboarding (disk-space/model-pull +
Reading Comfort Wizard), `npm audit`/`pip-audit`/`cargo audit` clean pass,
backup-nudge UI, `keep_alive` idle/perf tuning. Also inherits two items
deferred from Phase 8 (`docs/14-DEFERRED-ENHANCEMENTS.md`): true periodic
backup timer (§B2), canvas templates + keyboard-first node creation.

**Hard constraint**: no `src-tauri/` exists anywhere, no Rust/cargo, no
Ollama on this machine (`CLAUDE.md` Environment constraints). The
installer/Tauri-bundling half of the spec is **not buildable or testable
here** — deferred to the ASUS TUF F15 target machine, same pattern as
Phase 0's spikes. This phase covers only what's genuinely buildable on this
Python+Node-only machine.

## 2. In-scope task list

1. Periodic asyncio backup timer in FastAPI lifespan (`main.py`,
   `config.py`) — **reviewer-gated** (changes live DB snapshot cadence).
2. Expose `last_backup_at`/`next_backup_at` (`backups.py`,
   `backup_service.py`).
3. Frontend backup-nudge banner (`backup-nudge.tsx`, `queries/backups.ts`).
4. Canvas template seed + apply endpoint (`canvas_template_service.py`,
   `canvas.py`, `schemas.py`) — additive-only, 409 if canvas non-empty.
5. Frontend "start from a template" entry point (`canvas-panel.tsx`,
   `queries/canvas-templates.ts`).
6. Keyboard shortcut to add a node with focus moved to it
   (`canvas-panel.tsx`).
7. Keyboard-driven edge creation between two focused nodes
   (`canvas-panel.tsx`, `nodes.tsx`) — the genuine missing a11y capability.
8. `npm audit --audit-level=high` clean pass.
9. `pip-audit -r requirements.lock.txt` clean pass.
10. `scripts/run-audits.ps1` wiring both + roadmap note (recurring).
11. Configurable `ollama_keep_alive` threaded into the Ollama LiteLLM call
    (`config.py`, `llm_orchestrator.py`).

## 3. Deferred to target machine (ASUS TUF F15)

`src-tauri/` scaffolding, MSI/NSIS installer, Ollama bundling, onboarding
disk-space/model-pull step, `cargo audit`, the literal clean-install demo.

## 4. Execution protocol

Per `CLAUDE.md`: `builder` (sonnet) per task, 1-3 files, parallel where
files don't overlap; `reviewer` (opus) on task 1; `debugger` (sonnet) on any
first-pass failure. Full plan:
`C:\Users\2430171\.claude\plans\c-users-2430171-downloads-initiataion-r-swirling-pebble.md`.

## 5. Outcome

**Status: done for the this-machine-buildable scope (2026-07-30).**

11 builder tasks + 1 architect-level dependency fix + 1 opus reviewer gate,
all via sonnet builder subagents except the reviewer pass:

- **Periodic backup timer**: asyncio background task in the FastAPI
  lifespan, `backup_interval_minutes` (default 60, floored to 5), shielded
  rotation so shutdown always joins an in-flight `VACUUM INTO` rather than
  truncating it. Reviewer found one real gap — no lock between the timer and
  the manual `POST /backups/run` endpoint, relying only on microsecond
  filename uniqueness — fixed with a `threading.Lock` around `run_rotation()`
  plus clean error handling on the manual endpoint. `GET /backups/status`
  exposes `last_backup_at`/`next_backup_at`.
- **Backup-nudge UI**: `<BackupNudge>` banner mounted in `app-shell.tsx`,
  shows when the backup is stale (>24h) or has never run, one-click
  "Back up now".
- **Canvas templates**: `POST /books/{book_id}/canvas/apply-template`
  (three-act, hero's journey — real Scene rows + sequential edges, 409 if
  the canvas isn't empty), plus a frontend entry point on the empty-canvas
  state.
- **Keyboard-first canvas**: `Shift+N` adds a node with focus moved to it;
  `Shift+C` starts/confirms keyboard-driven edge creation between two
  focused nodes (the genuine missing capability — edge creation was
  mouse-drag-only before this), with an ARIA-live announcer and `Escape` to
  cancel. Reuses the exact same create-node/create-edge calls the mouse path
  already used.
- **`ollama_keep_alive`**: configurable setting threaded into the Ollama-leg
  LiteLLM call only, proven via the existing stub/mock test seam.
- **Dependency audits**: `pip-audit` found 4 known CVEs in `cryptography`
  46.0.3 (the Phase 7 bundle-encryption library) — bumped to **48.0.1**,
  full backend test suite re-run clean including all bundle export/import
  tests, `pip-audit` now reports zero known vulnerabilities. `npm audit`
  fixed `js-yaml` non-breaking; two findings left as documented accepted
  risk rather than forced: `brace-expansion` (dev-only, via
  `openapi-typescript`, never shipped to users) and `react-router` (the
  flagged CVE is RSC-Mode-specific; this app is a plain client-side SPA via
  `createBrowserRouter`, not React Server Components — a 7-minor-version
  downgrade to "fix" a vulnerability class this app doesn't use was judged
  higher-risk than the finding itself). `scripts/audit.ps1` already existed
  and covers all three ecosystems (npm/pip/cargo, cargo gracefully skipped
  when absent); `docs/06-ROADMAP.md`'s Phase 9 line already said "recurring,
  not one-time" — no doc changes needed.

Backend: 302 passed, 1 pre-existing unrelated failure
(`test_continuity_flags_migration.py`, a migration-downgrade check-constraint
assertion, confirmed unrelated to any Phase 9 change). Frontend: clean
`npm run build` + `npm run lint` (only pre-existing warnings).

## 6. Not done here — genuinely deferred to the ASUS TUF F15

`src-tauri/` scaffolding, MSI/NSIS installer, Ollama bundling, onboarding
disk-space/model-pull step, `cargo audit`, and the literal Phase 9 demo
("full end-to-end walkthrough from a clean install") remain untouched —
this machine has no Rust/cargo/Ollama and none should be installed here.
These are the first things to pick up once the repo reaches the target
machine.

## 7. Process carry-over

Next: Phase 10 (v1.1 — semantic layer: sqlite-vec + FTS5 + RRF hybrid
search, GraphRAG-lite context assembly, auto codex-link suggestions,
similar-scene detection). Note Phase 10 also has real model-dependent work
(embeddings) that is subject to the same no-LLM-on-this-machine constraint —
expect a similar split between what's buildable here (schema, API surface,
deterministic parts) and what's deferred to the target machine.
