# PHASE5.md — Phase 5 (Images system) Directive

Loaded for Phase 5. Supersedes CLAUDE.md only where noted (workflow rules carried from
Phase 3/4, user-confirmed). Keep < 100 lines.

## 1. Project & Phase Context

Stack unchanged (React 19 + Vite + Tailwind v4 + shadcn + React Flow + Zustand + TanStack
Query · FastAPI sidecar + SQLAlchemy 2 + Alembic + Pydantic v2 · SQLite). Phase 5 goals
(docs/06 §Phase 5, docs/03 §Images):
- Tables already EXIST: `Image` (bucket, description, width/height, checksum), `ImageTag`,
  `EntityImage` (polymorphic `entity_type IN book|scene|codex_entry`). Phase 3 shipped only a
  minimal `reference_pool` upload/serve. Phase 5 makes it a real subsystem.
- **Both buckets** (`finalized_scene` + `reference_pool`); upload/rename/tag/**search**;
  **Enhance-able** `description`; polymorphic **`entity_images` attach/detach**.
- **Book-scoped export-gather query** finalized here — the ONE query Phase 6/7 use to bundle
  "only images linked to THIS Book" (book + its scenes + its codex + cover). Wrong scope leaks
  another Book's images → data-integrity-critical.
- FE: tagged/searchable reference-pool gallery; attach finalized image to a canvas node; Book
  cover; export preview.

## 2. Strict Execution Protocol (carried, user-confirmed)

- PLAN in **main-session Plan Mode using Opus**. Explore→Plan→Implement→Verify. Present plan;
  wait for ExitPlanMode approval before ANY edit. (Done — plan approved.)
- IMPLEMENT via **builder (Sonnet) subagents, autonomous** — 1 scoped task (1–3 files) each,
  sequential where they share `schemas.py`/`main.py`.
- REVIEWER (Opus) gate before phase done on DATA-SENSITIVE parts: **BE-1** Pillow decode of
  untrusted bytes (decompression-bomb/corrupt handling) + thumbnail write + retained path/type
  guards; **BE-4** export-gather scope correctness. Per CLAUDE.md.
- Output: diffs + bullets, no pleasantries. Targeted edits only.

## 3. AI / environment constraint (IMPORTANT)

- **No models on this build laptop.** Everything Phase 5 is deterministic and fully testable
  here EXCEPT the Enhance-a-`description` flow (BE-5) → BUILD + STUB-verify only
  (`QUILLNIGHT_LLM_STUB=1` EchoProvider); real semantic quality tested on the ASUS TUF F15 —
  see memory [[quillnight-target-laptop-hw]]. Never fetch a model here.
- **Pillow** (new dep) is an image lib, NOT a model — fine to install/pin. Decodes untrusted
  bytes → set `Image.MAX_IMAGE_PIXELS`, wrap decode in try/except → `ValueError("BAD_IMAGE")`.

## 4. Token & Context Efficiency

- Targeted path searches only; reference doc sections by path (`docs/03 §Images`). No whole-dir
  reads. Fix bugs by editing the target function/lines. `/compact` when switching tasks.

## 5. Verification & Environment Commands

Backend (cwd `apps/sidecar`):
- Test: `QUILLNIGHT_LLM_STUB=1 QUILLNIGHT_STT_STUB=1 .venv/Scripts/python.exe -m pytest -q`
- Lint: `.venv/Scripts/python.exe -m ruff check app tests`
Frontend (cwd `apps/desktop`):
- Build/typecheck: `npm run build`   ·   Lint: `npm run lint`
- Type sync (backend running): `NODE_OPTIONS=--use-system-ca npm run gen:types`
New dep this phase: `Pillow` — pinned, official PyPI, in `pyproject.toml` + lockfile.

Self-verify: after edits run the relevant test + lint, confirm green, report the summary line.
Data-sensitive image bytes + export scope MUST have deterministic tests; Enhance via stub echo.

## 6. Process carry-over
Next phase: create `PHASE6.md` from this template; re-confirm any CLAUDE.md overlaps with the
user. Phase 6 (Final Draft + export) reuses Pillow (image embed) + the BE-4 export-gather query.
