# PHASE6.md — Phase 6 (Final Draft tab + export pipeline) Directive

Loaded for Phase 6. Supersedes CLAUDE.md only where noted (workflow rules carried from
Phase 3/4/5, user-confirmed). Keep < 100 lines.

## 1. Project & Phase Context

Stack unchanged (React 19 + Vite + Tailwind v4 + shadcn + React Flow + Zustand + TanStack
Query · FastAPI sidecar + SQLAlchemy 2 + Alembic + Pydantic v2 · SQLite). Phase 6 goals
(docs/06 §Phase 6, docs/05 §Export formats, docs/03 §draft_versions):
- **Draft compiler**: prose path via Scene `description` (chapters/scenes in `book_scene_order`),
  script path via `screenplay_elements`. Front-matter editor (`Book.front_matter` JSON — title
  page, dedication, preface).
- **Export formats**: Markdown (Jinja2) + DOCX (python-docx) + PDF (see §3 below) for ALL Book
  types; Fountain + Final Draft `.fdx` (screenplay-tools) gated to `movie_script`/
  `short_film_script` only.
- **`draft_versions` snapshots**: every compile writes a versioned row + on-disk file
  (`file_path`, `format_settings`, `is_current`, `generated_at`); never overwrite a prior
  snapshot.
- Reuses Phase 5's Pillow (image embed in DOCX/PDF) + the BE-4 book-scoped export-gather query
  (which images belong in this Book's export).
- Reading environment on this tab uses the FULL evidence-tuned defaults (65ch, spacing, cream)
  unconditionally — chrome-not-manuscript rule, no exceptions here.

## 2. Strict Execution Protocol (carried, user-confirmed)

- PLAN in **main-session Plan Mode using Opus**. Explore→Plan→Implement→Verify. Present plan;
  wait for ExitPlanMode approval before ANY edit.
- IMPLEMENT via **builder (Sonnet) subagents, autonomous** — 1 scoped task (1–3 files) each,
  sequential where they share `schemas.py`/`main.py`/the export module.
- REVIEWER (Opus) gate before phase done, per CLAUDE.md hard rule: builder MAY write
  `export_docx.py`/`export_pdf.py`/the Fountain/FDX writer, but reviewer MUST pass on them
  before commit — user-content-driven file generation, correctness + injection/resource-limit
  concerns (e.g. Jinja2 autoescape, XML injection in FDX, huge-input DoS on PDF render).
- Output: diffs + bullets, no pleasantries. Targeted edits only.

## 3. PDF library decision (user-confirmed 2026-07-27)

- **Try WeasyPrint first** on this machine (pip install + GTK3/Pango/cairo runtime). If it
  fails to install or import here, **fall back to ReportLab** (pure-Python, no native deps) —
  do NOT block the phase on it.
- **Outcome (BE-1, this session):** `pip install weasyprint` succeeded but `import weasyprint`
  raised `OSError: cannot load library 'libgobject-2.0-0'` — no GTK runtime on this machine, as
  expected. Removed weasyprint + its transitive deps; **ReportLab `5.0.0` is the active PDF
  engine here.** `export_pdf.py` (BE-5) still isolates the renderer behind one interface so
  activating WeasyPrint is a localized change on the ASUS laptop.
- Either way, **isolate the PDF renderer behind one interface** (`render_pdf(html, css) -> bytes`
  or similar) so swapping/upgrading to WeasyPrint on the ASUS laptop later is a localized change,
  not a rewrite. Keep both code paths honest: whichever isn't the active renderer here should
  still be structurally complete and readable, ready to activate there.
- Markdown/DOCX/Fountain/FDX are unaffected by this — all pure-Python, install cleanly here.

## 4. AI / environment constraint (carried)

- **No models on this build laptop, ever.** Phase 6 has no new LLM surface (export is
  deterministic compilation of existing text) — nothing here is stub-gated for that reason.
- FDX round-trip fidelity is flagged unproven at scale (docs/07) and its real check needs an
  actual Final Draft/Highland viewer we don't have here — verify structurally (parses back,
  scene numbering/dual-dialogue/title-page present) here; real-viewer round-trip check is
  deferred, same posture as Enhance-quality in Phase 4/5 — see [[quillnight-target-laptop-hw]].

## 5. Token & Context Efficiency

- Targeted path searches only; reference doc sections by path. No whole-dir reads. `/compact`
  when switching tasks.

## 6. Verification & Environment Commands

Backend (cwd `apps/sidecar`):
- Test: `QUILLNIGHT_LLM_STUB=1 QUILLNIGHT_STT_STUB=1 .venv/Scripts/python.exe -m pytest -q`
- Lint: `.venv/Scripts/python.exe -m ruff check app tests`
Frontend (cwd `apps/desktop`):
- Build/typecheck: `npm run build`   ·   Lint: `npm run lint`
- Type sync (backend running): `NODE_OPTIONS=--use-system-ca npm run gen:types`
New deps this phase: `jinja2`, `python-docx`, `weasyprint` (try) / `reportlab` (fallback),
`screenplay-tools` — all official PyPI, pinned, in `pyproject.toml` + lockfile.

Self-verify: after edits run the relevant test + lint, confirm green, report the summary line.
Export/generation files (§2) MUST get a reviewer pass before phase done.

## 7. Process carry-over
Next phase: create `PHASE7.md` from this template; re-confirm any CLAUDE.md overlaps with the
user. Phase 7 (`.quillproj` export/import) reuses `draft_versions` + the BE-4 gather query +
adds `pyrage` encryption.
