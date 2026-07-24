# PHASE4.md — Phase 4 (Outline/Timeline + Continuity Checker v2) Directive

Loaded for Phase 4. Supersedes CLAUDE.md only where noted (rules carried from Phase 3,
user-confirmed). Keep < 100 lines.

## 1. Project & Phase Context

Stack unchanged (React 19 + Vite + Tailwind v4 + shadcn + React Flow + Zustand + TanStack
Query · FastAPI sidecar + SQLAlchemy 2 + Alembic + Pydantic v2 · SQLite). Phase 4 goals
(docs/06 §Phase 4, docs/11 §4):
- Data: `book_scene_order` (EXISTS: outline_order_index + timeline_order_index) + new
  `chapters` + `structure_templates` (seed Three-Act, Hero's Journey). ONE model backs
  BOTH the Outline (beat-board) and Timeline views.
- Beat-board UI (dnd-kit, color-coded structure lanes) + Timeline UI (reorder) as two views.
- **Continuity Checker v2** (docs/11 §4): Tier-1 deterministic SQL checks (early appearance,
  timeline inversions — instant, never wrong); Tier-2 LLM semantic pass, two-pass CoT→JSON
  with the **verbatim-quote guardrail** (a flag whose quote isn't a string-match in the source
  is DROPPED). Severity-tagged flags (`continuity_flags` table exists).
- Wire the VIBE story-level vocab here: genre/tone/pacing/character-focus (defined in
  `lib/vocab.ts` in Phase 3) now drive real controls + feed the continuity/enhance prompt.

## 2. Strict Execution Protocol (carried from Phase 3, user-confirmed)

- PLAN in **main-session Plan Mode using Opus** (effort tuned to task). Explore→Plan→
  Implement→Verify. Present plan; wait for ExitPlanMode approval before ANY edit.
- IMPLEMENT via **builder (Sonnet) subagents, autonomous** — 1 scoped task (1–3 files) each.
- REVIEWER (Opus) gate before phase done on the DATA-SENSITIVE parts: continuity merge/flag
  persistence, the verbatim-quote guardrail (fabricated-quote drop), Tier-1 SQL correctness,
  structure_template seed integrity. Per CLAUDE.md.
- Output: diffs + bullets, no pleasantries. Targeted edits only.

## 3. AI / environment constraint (IMPORTANT for this phase)

- **No models on this build laptop.** Tier-1 SQL continuity checks are deterministic → BUILD
  + TEST fully here. Tier-2 LLM semantic pass → BUILD + STUB-verify only (`QUILLNIGHT_LLM_STUB=1`
  EchoProvider); its real semantic behavior is tested later on the ASUS TUF F15 (RTX 3050 4GB) —
  see memory [[quillnight-target-laptop-hw]]. Write Tier-2 ready-to-run; never fetch a model here.

## 4. Token & Context Efficiency

- Targeted path searches only; reference doc sections by path (`docs/11 §4`). No whole-dir reads.
- Fix bugs by editing the target function/lines. Run `/compact` or `/clear` when switching tasks.

## 5. Verification & Environment Commands

Backend (cwd `apps/sidecar`):
- Test: `QUILLNIGHT_LLM_STUB=1 QUILLNIGHT_STT_STUB=1 .venv/Scripts/python.exe -m pytest -q`
- Lint: `.venv/Scripts/python.exe -m ruff check app tests`
Frontend (cwd `apps/desktop`):
- Build/typecheck: `npm run build`   ·   Lint: `npm run lint`
- Type sync (backend running): `NODE_OPTIONS=--use-system-ca npm run gen:types`
New dep this phase: `@dnd-kit/core` (+ `@dnd-kit/sortable`) — pinned, official npm.

Self-verify: after edits run the relevant test + lint, confirm green, report the summary line.
Tier-1 continuity MUST have deterministic tests; Tier-2 verified via the stub echo path.

## 6. Process carry-over
Next phase: create `PHASE5.md` from this template; re-confirm any CLAUDE.md overlaps with the user.
