# PHASE7.md — Phase 7 (`.quillproj` export/import) Directive

Loaded for Phase 7. Supersedes CLAUDE.md only where noted. Status: **DONE (2026-07-28)** —
reviewer-gated, demo-verified. Kept as historical record.

## 1. Project & Phase Context

Stack unchanged (React 19 + Vite + Tailwind v4 + shadcn + React Flow + Zustand + TanStack
Query · FastAPI sidecar + SQLAlchemy 2 + Alembic + Pydantic v2 · SQLite). Phase 7 goals
(docs/06 §Phase 7, docs/05 §Export bundle encryption):
- **Gather → zip → encrypt** `.quillproj` bundles (per-Book, UUID-scoped).
- **Decrypt → merge-by-UUID** with review dialog on conflicts (no silent overwrite).
- **Local backup rotation** (VACUUM INTO snapshots, keep-N, WAL-aware restore).
- **Embeddings excluded** from bundles (derived data, regenerated post-import).

## 2. Strict Execution Protocol (carried, user-confirmed)

- PLAN in main-session Plan Mode (Opus). Present plan; wait for ExitPlanMode approval.
- IMPLEMENT via builder (Sonnet) subagents, 1 scoped task (1–3 files) each, sequential where
  they share a file.
- REVIEWER (Opus) gate before phase done on `bundle_crypto.py`/`bundle_export.py`/
  `bundle_import.py`/`api/import_export.py`/`backup_service.py` — export/import merge + encryption.
- Output: diffs + bullets, no pleasantries.

## 3. Encryption library decision (resolved)

- **`cryptography` 46.0.3 (AES-256-GCM) + `argon2-cffi` (Argon2id)** is the active engine.
  `pyrage` (roadmap default) was dropped — single-maintainer native wheel; `cryptography`
  installed cleanly on the corporate proxy and gives real, testable crypto here (same posture as
  Phase 6's WeasyPrint→ReportLab). Isolated behind `encrypt_bundle`/`decrypt_bundle`. docs/05 §28
  explicitly sanctions this fallback.

## 4. Data-integrity hard rules

- Never silently overwrite. UUID conflict → explicit resolution; **default keep_local**.
- Embeddings excluded; regen is a post-import log stub (real impl Phase 10).
- Bundle manifest carries `schema_version`, validated before any data is read.

## 5. AI / environment constraint (carried)

- No models on this build laptop. Phase 7 has no LLM surface (deterministic serialize/merge).

## 6. Verification & Environment Commands

Backend (cwd `apps/sidecar`):
- Test: `QUILLNIGHT_LLM_STUB=1 QUILLNIGHT_STT_STUB=1 .venv/Scripts/python.exe -m pytest -q`
- Lint: `.venv/Scripts/python.exe -m ruff check app tests`
Frontend (cwd `apps/desktop`): `npm run build` · `npm run lint` · `gen:types` (backend running).
Deps added: `cryptography==46.0.3` (pinned, in pyproject + requirements.lock.txt).

## 7. Outcome

9 builder tasks + Opus reviewer gate (no MUST-FIX; 3 SHOULD-FIX applied: WAL-aware restore,
`book_scene_order` natural-key dedup, zip-slip regression test). Backend 279 passed (1 pre-existing
unrelated failure). Demo checklist 5/5 PASS via real HTTP stack, isolated from live library.

## 7b. Resolved deviations from docs/05 (user-approved 2026-07-28)

- **Conflict modes = keep-local / take-imported / merge** (NOT the spec's literal
  keep-mine / take-theirs / *keep-both*). `keep-both` for a same-UUID conflict would require
  minting a new UUID, breaking the UUID-identity model the merge relies on and risking confusing
  duplicates; `merge` (imported fills local NULL/empty fields only) is strictly more useful.
  Built + tested; deviation is intentional.
- **Backup rotation = startup + manual trigger only** (NOT a during-session periodic timer).
  Covers the data-safety need for a frequently-restarted app; true periodic timer deferred to
  Phase 9 hardening — logged in docs/14 §B2.

## 8. Process carry-over

Next phase: create `PHASE8.md` (Design/accessibility deep pass + reading aids + streaks; includes
the deferred full responsive/all-screen-size QA pass). Prioritize token/cost savings — delegate
mechanical work to Sonnet builders, keep Opus for planning/review only.
