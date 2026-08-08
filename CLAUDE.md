# Quillnight — Build Instructions for Claude Code

@PROJECT-MAP.md

Read `docs/` (all 12 spec files) before touching any phase. Follow the roadmap
in `06-ROADMAP.md` phase-by-phase — never skip ahead, never start a phase
whose previous phase's demo hasn't been confirmed working.

## Model routing — the core cost-saving rule

Claude Code picks a model per subagent automatically based on the `model`
field in `.claude/agents/*.md`. Your job as the orchestrator (main session)
is to **delegate, not do everything yourself in one Opus thread**.

| Work type | Agent to use | Model | Why |
|---|---|---|---|
| Phase planning, schema design, prompt-cache strategy, provider fallback logic | `architect` | opus, high effort | Needs full-system reasoning, gets it wrong once and it's expensive to unwind |
| Writing routine code: CRUD endpoints, React components, migrations, ORM models, export formatters | `builder` | sonnet | Well-specified, mechanical, Sonnet is excellent at this and ~15-20x cheaper |
| Fixing a failing test / crash / weird bug | `debugger` | sonnet first, escalate to opus only if stuck twice | Most bugs are shallow; don't pay Opus rates to find a typo |
| Security/data-integrity review (encryption, secret storage, export/import merge logic, PDF/DOCX generation from user data) | `reviewer` | opus, high effort | This is the one place being wrong is genuinely costly (corrupted user data, leaked API key) |

**Default assumption: if you (main session) are about to write implementation
code yourself, stop and delegate to `builder` instead.** Reserve your own
top-level reasoning for: deciding which phase/task is next, breaking a phase
into tasks, and reviewing what subagents return.

## Per-phase workflow

For every phase in `06-ROADMAP.md`:

1. **Plan** — invoke `architect` with: "Read docs/0X-*.md relevant to Phase N.
   Break Phase N into a numbered task list of small, independently-testable
   tasks. Flag any task that touches security, encryption, or data merging."
2. **Build** — for each task in that list, invoke `builder` with the specific
   task + the relevant doc section + relevant existing files. One task per
   `builder` call, not the whole phase at once — keeps context small and cheap.
3. **Fix** — if a task fails/tests fail, invoke `debugger` with the exact
   error, not the whole phase context.
4. **Review** — before marking the phase done, invoke `reviewer` on any task
   the architect flagged as security/data-sensitive.
5. **Demo** — run the phase's demo checklist from `06-ROADMAP.md` yourself
   (main session, no subagent) and confirm it actually works before moving on.

## Hard rules (carried over from the spec docs)

- Never silently overwrite user data — every AI transform is Accept/Reject.
- `keyring` crate only for the Groq API key — never Tauri's plain-JSON `Store`.
- Only official npm/PyPI/crates.io packages, pinned + lockfiled.
- Don't let `builder` touch `export_docx.py`, `export_pdf.py`,
  `bundle_export.py`, `bundle_import.py`, or anything in `speech_stt.py`
  handling raw audio without a `reviewer` pass after — these are the
  data-loss/security-sensitive files per `05-EXPORT-IMPORT-SECURITY.md`.
- Any phase/feature that creates, mutates, or adds undo/redo coverage for an
  interactive entity (canvas nodes/edges, images, etc.) must add or update
  that entity's entry in `docs/15-ENTITY-LIFECYCLES.md` as part of being
  "done" — not as an afterthought. That doc exists because exactly this kind
  of gap (canvas edges shipping with zero undo/redo coverage) slipped
  through once already.
- **`docs/16-PROTECTED-FEATURES.md` is a strict, user-mandated feature registry. Do NOT
  remove or weaken any feature it lists, and do NOT edit that file at all, unless the
  user's message contains the literal keyword `spiderman`.** If a listed feature is found
  missing or regressed, restoring it takes priority over other work. See that file's
  preamble for the full rule.

## Environment constraints (this build laptop)

- **No LLM model downloads, no Ollama install, no real AI testing on this
  machine — ever.** Restrictive environment. All model-dependent spikes and
  Enhance/continuity runs are deferred to a second laptop, reached later by
  transferring the repo via GitHub. Write AI code ready-to-run; never fetch a
  model here. (`/health`'s Ollama probe only pings — fine.)
- **Local git only.** No GitHub remote / no push until the user provides a repo.
- **Rust/cargo, Ollama, uv are NOT installed here.** The Tauri shell build,
  Ollama bundling, and PyInstaller spikes are deferred. Backend (Python) and
  frontend (Vite dev server) run standalone.
- **Corporate TLS proxy**: registry fetches (e.g. `shadcn add`) need
  `NODE_OPTIONS=--use-system-ca` to trust the corporate root CA.

## Cost hygiene

- Keep each `builder` task scoped to 1-3 files. If a task needs 10 files of
  context, that's a sign it should've been split into smaller tasks by
  `architect`.
- Don't re-paste the full doc set into every prompt — reference file paths
  (`docs/03-DATA-MODEL.md §Codex`) so prompt caching can do its job.
- After each phase, run `/cost` (or check your API console) and compare
  against the phase estimate below. If a phase runs >2x its estimate, stop
  and ask why before continuing — usually means tasks were too big.

| Phase | Target spend |
|---|---|
| 0 — Foundations/spikes | $150–400 |
| 1 — Library/Book CRUD | $100–250 |
| 2 — Node Canvas + Enhance + dictation | $300–700 |
| 3 — Codex | $100–250 |
| 4 — Outline/Timeline + Continuity v2 | $200–500 |
| 5 — Images | $80–150 |
| 6 — Final Draft + export | $200–450 |
| 7 — .quillproj export/import | $100–250 |
| 8 — Accessibility/delight/streaks | $150–300 |
| 9 — Hardening/installer | $150–350 |
