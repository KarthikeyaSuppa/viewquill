# Quillnight — Project Map

> **Read this first.** This file replaces exploring `docs/` and `apps/`
> file-by-file at the start of a session — it tells you what exists, where it
> lives, roughly how big it is, and what it connects to. `docs/` (12 numbered
> spec files) still holds the full rationale/spec for anything you need
> deeper detail on; this file is the map, not the spec. See also
> [API-REFERENCE.md](API-REFERENCE.md) for every user option and backend
> endpoint, and [CLAUDE.md](CLAUDE.md) for the subagent/model workflow.
>
> This is a hand-written snapshot (line counts, phase status, file lists) —
> it is **not** auto-regenerated, so treat exact numbers as approximate once
> new phases land. Structure and locations are reliable; digits will drift.

## 1. What Quillnight is

A personal, fully local Windows desktop app for story generation and
storyboarding. Capture raw scene/plot/character ideas as a Blender-style
connected node graph (typed or spoken), use a locally-run LLM to fix grammar
and catch continuity holes, then compile into a finished book, movie script,
short film script, or single scene. All content (scenes, characters, images)
is canonical and reusable across every project in one shared local "Story
Library." Built dyslexia-first (evidence-based typography/reading aids) and
trust-first (AI never silently overwrites — every transform is
Accept/Reject).

## 2. Architecture at a glance

| Layer | Tech | Lives in | Talks to next layer via |
|---|---|---|---|
| Desktop shell | Tauri 2 (Rust) — **not yet wired**, no `src-tauri/` exists yet | (planned, not present) | OS-only concerns when built: sidecar lifecycle, file dialogs, app-data paths |
| Frontend | React 19 + TypeScript, Vite 8, Tailwind v4, shadcn/ui, React Flow (`@xyflow/react`) | `apps/desktop/` | Plain `fetch` REST calls over localhost to the sidecar (`src/lib/api.ts`) |
| Backend ("sidecar") | Python 3.13, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2 | `apps/sidecar/` | Owns all domain logic; runs on `127.0.0.1:8756` |
| Database | SQLite (single file) | `app-data/quillnight.sqlite` (created at runtime) | via SQLAlchemy ORM, no raw SQL in routes |
| LLM routing | LiteLLM via `llm_orchestrator.py` | `apps/sidecar/app/services/` | Local Ollama (`qwen3.5:4b` etc., port 11434) or GroqCloud (user's own key), per Offline/Online/Hybrid mode |
| Shared types | `openapi-typescript` generated from FastAPI's OpenAPI schema | `packages/api-types/schema.d.ts` (4839 lines, generated — don't hand-edit) | Frontend imports these for request/response typing |

The frontend **never** talks to Ollama or the Rust shell for business logic
— everything domain-related goes through the FastAPI sidecar.

## 3. Build status (roadmap phases)

Per `docs/06-ROADMAP.md` and the root `PHASE*.md` working directives:

| Phase | What it builds | Status |
|---|---|---|
| 0 | Foundations / spikes | Done |
| 1 | Library/Book CRUD + design-system foundations | Done |
| 2 | Node Canvas + Enhance + dictation | Done |
| 3 | Full Codex | Done |
| 4 | Outline/Timeline + Continuity Checker v2 | Done |
| 5 | Images | Done |
| 6 | Final Draft tab + export pipeline | Done. PDF engine resolved 2026-07-27: WeasyPrint failed to import (`OSError: cannot load library 'libgobject-2.0-0'`, no GTK runtime here); **ReportLab 5.0.0** is the active engine, isolated behind one `render_pdf(html, css) -> bytes` interface so WeasyPrint can be reactivated on the ASUS TUF F15 later |
| **7** | **`.quillproj` export/import** | **Done (2026-07-28)** — encrypted per-Book bundle export + merge-by-UUID import (never silent overwrite; keep-local/replace/merge resolution) + rotating local DB backups. **Encryption engine resolved:** `pyrage` (roadmap default, single-maintainer native wheel) dropped for **`cryptography` 46.0.3 AES-256-GCM + `argon2-cffi` Argon2id**, isolated behind `encrypt_bundle/decrypt_bundle` (same posture as Ph6's ReportLab swap). Opus reviewer gate passed (no MUST-FIX). See `PHASE7.md` |
| **8** | **Accessibility deep pass + reading aids + Lottie overhaul** | **Done (2026-07-28)** — scope changed mid-planning: streaks/daily-word-goal gamification **cut entirely**, replaced with a Lottie animation overhaul. Kept: WCAG AA audit, reading ruler, focus mode, read-aloud karaoke. See `PHASE8.md` §3 for the full shipped list |
| **9** | **Hardening + installer** | **Done for this-machine-buildable scope (2026-07-30)** — periodic backup timer + nudge UI, canvas templates (three-act/hero's journey), keyboard-first node+edge creation, `pip-audit`/`npm audit` clean pass (bumped `cryptography` 46.0.3→48.0.1 for 4 CVEs), configurable `ollama_keep_alive`. Installer/Tauri-bundling half (MSI/NSIS, Ollama bundling, `cargo audit`, onboarding disk-space/model-pull, the clean-install demo) explicitly deferred to the ASUS TUF F15 — no Tauri shell/Rust/Ollama exist on this machine. See `PHASE9.md` |
| **10** | **Semantic/RAG layer** | **This-machine slice done (2026-07-30)** — `search_fts`(FTS5)+`embeddings`(sqlite-vec vec0) schema, embed-on-save/backfill, hybrid RRF search (`GET /search`), auto codex-link + similar-scene suggestions, frontend search dialog (`Ctrl+K`) + suggestion panel — all proven against a deterministic stub embedding, not real semantics. Real `qwen3-embedding:0.6b` call, real backfill run, and the actual demo criteria remain on the ASUS TUF F15 (no Ollama here). See `PHASE10.md`, `HANDOFF-ASUS-TUF.md` §4c |
| 11 (v1.1) | Full delight/voice polish | Not started |
| 12 (v2.0) | Backlog | Not started |

Each `PHASE<N>.md` at repo root is a living working directive for the phase
currently in progress (created fresh per phase per `CLAUDE.md`'s process),
not a permanent spec — once a phase's demo is confirmed, the next
`PHASE<N+1>.md` is created and the old one becomes historical record.

## 4. Repo layout

```
initiataion/
├── apps/
│   ├── desktop/        React/Vite frontend (below)
│   └── sidecar/        FastAPI backend (below)
├── packages/
│   └── api-types/      Generated OpenAPI TS types — the only shared package
├── docs/                12 numbered spec files + Postman collection (full rationale, read for "why")
├── scripts/             Dev/audit/usage-tracking scripts (not part of the app itself)
├── ccusage-log/         Claude Code usage tracking output (unrelated to Quillnight product)
├── CLAUDE.md            Subagent/model routing rules + per-phase workflow
├── PHASE3.md … PHASE9.md  Current + recent phase working directives
├── PROJECT-MAP.md       This file
├── API-REFERENCE.md     Every user option + backend endpoint, user-friendly vs developer detail
├── HANDOFF-ASUS-TUF.md  What's left for the target machine (Tauri/Ollama/model-dependent work) — read this on the ASUS TUF F15 before starting Phase 9's deferred half or Phase 10+
└── README.md            Stale — predates real code, says "no code written yet" (it has been)
```

No root `package.json`/workspace file — `apps/desktop` and `apps/sidecar` are
independent projects (npm and pip/uv respectively), not an npm/pnpm
workspace.

## 5. Frontend map — `apps/desktop/`

**Config**: `package.json`, `tsconfig.json`/`tsconfig.app.json`/`tsconfig.node.json`,
`vite.config.ts` (dev server pinned to port **1420** — Tauri's default, so
the future Rust shell can wrap it without config changes), `components.json`
(shadcn/ui config), `.oxlintrc.json` (linter). No `.env.example` present.

**Entry chain**: `src/main.tsx` (18 ln, loads accessibility fonts — Inter,
Lexend, Atkinson Hyperlegible Next, OpenDyslexic — then calls `initTheme()`
and renders `App.tsx`) → `src/App.tsx` (35 ln) → `src/router.tsx` (17 ln,
`react-router-dom` v7 `createBrowserRouter`, wraps everything in
`app-shell.tsx`).

**Routes** (`src/routes/`):

| Path | File (lines) | Purpose |
|---|---|---|
| `/` | `library-screen.tsx` (452) | Story Library — list/create/open Books, largest route file |
| `/book/:bookId` | `book-screen.tsx` (183) | Book shell — hosts Canvas/Codex/Outline/Draft panels for one Book |
| `/settings` | `settings-screen.tsx` (417) | All Settings tabs (AI mode, voice, accessibility, theme, profile) |

**State management**: Zustand for client/UI state (`src/stores/`: `auth.ts`,
`canvas-actions.ts`, `card-style.ts`, `onboarding.ts`, `theme.ts` — all small,
17–45 ln each). TanStack Query for server state (`src/queries/`, one file per
API domain — `books.ts`, `bundle.ts` (Phase 7, `.quillproj` export/import),
`canvas.ts`, `codex.ts`, `continuity.ts`, `draft-preview.ts` (Phase 8,
manuscript reader), `enhance.ts`, `export.ts`, `health.ts`, `images.ts`,
`outline.ts`, `profiles.ts`, `screenplay.ts`, `settings.ts`, `voice.ts`, plus
`client.ts` for the shared QueryClient). Every mutation/query in the app goes
through one of these files — **check here first** before adding a new API
call.

**API client**: `src/lib/api.ts` (287 ln) — typed fetch wrapper used by every
`queries/*.ts` file, typed against `packages/api-types/schema.d.ts`.

**Components by feature area** (`src/components/`):

| Area | Files (lines) | Notes |
|---|---|---|
| Canvas (node graph) | `node-editor.tsx` (**805 — largest file in the repo**), `canvas-panel.tsx` (396), `codex-panel.tsx` (360), `nodes.tsx` (274), `enhance-diff.tsx` (145, Accept/Reject diff UI), `ink-edge.tsx` (77), `screenplay-node.tsx` (59) | Built on `@xyflow/react` (React Flow). Phase 8 fixed a keyboard dead-end here (Enter did nothing on a focused node) |
| Codex | `codex-entry-dialog.tsx` (698, 2nd largest) | Character/location/lore entry editor |
| Outline | `beat-board.tsx` (354, `dnd-kit`), `continuity-panel.tsx` (299), `timeline-view.tsx` (254), `outline-panel.tsx` (148) | `beat-board.tsx` backs the Outline view, `timeline-view.tsx` the chronological view — same underlying `book_scene_order` data |
| Images | `image-card.tsx` (277), `images-panel.tsx` (213), `image-detail.tsx` (210), `image-uploader.tsx` (79), `tag-editor.tsx` (61) | |
| Draft/export | `front-matter-editor.tsx` (131), `draft-panel.tsx` (157), `version-list.tsx` (78), `manuscript-reader.tsx` (239, Phase 8 keystone — Draft tab had **no rendered prose at all** before this; renders `.manuscript` with globally-sequential `data-para-index`/`data-w`/`data-c` attrs every reading-aid positions against), `read-aloud-bar.tsx` (165, karaoke toolbar) | |
| Bundle export/import | `bundle/export-dialog.tsx` (123), `bundle/import-review-dialog.tsx` (242, conflict review UI: keep-local/take-imported/merge per row) | Phase 7 `.quillproj` UI |
| Reading aids | `reading-ruler.tsx` (94, Grey Bar/Shade, `R` toggle) | Phase 8; pairs with `lib/reading-cursor.ts` + `reading-controls.tsx`'s focus mode (`F` toggle) |
| Auth/profiles | `profile-gate.tsx` (292), `avatars.ts` (32) | Client-side gate enforcing "must be logged in"; library endpoints themselves are unauthenticated |
| Voice | `mic-button.tsx` (236) | STT is stubbed server-side right now (see §10). Read-aloud (`lib/speech.ts`) is separate and fully implemented, see §9 |
| Onboarding | `reading-comfort-wizard.tsx` (280) | 60-second font/typography self-test |
| Help | `help-guide.tsx` (394) | In-app help/onboarding guide |
| Shell/chrome | `app-shell.tsx` (135, Phase 8 added a skip-to-main link + nav focus ring), `providers.tsx` (24), `settings-provider.tsx` (23), `status-screen.tsx` (83), `theme-toggle.tsx` (49), `reading-controls.tsx` (196), `firefly.tsx` (48, mascot — now Lottie-driven, see §8) | |
| UI primitives | `components/ui/*.tsx` (19 files: button, dialog, select, tabs, dropdown-menu, card, badge, input, switch, etc.) | shadcn/ui-style primitives, small, rarely need changes |

**Other `src/lib/` files**: `vocab.ts` (199, terminology/copy), `delight.ts`
(181, confetti/sound/animation triggers), `delight-accent.tsx` (47, Phase 8
Playful-only delight-moment layer), `lottie.tsx` (82, `<LottiePlayer>` —
centralizes delight-level/reduced-motion gating so every Lottie use freezes
correctly at Calm/reduced-motion instead of each caller re-implementing it),
`apply-settings.ts` (66), `keyring.ts` (29, frontend-side helper for the Groq
key flow), `reading-cursor.ts` (243, `useReadingCursor` — caches paragraph
rects once + `ResizeObserver`/`MutationObserver`, binary-searches the sorted
cache; rewritten in Phase 8 after a perf audit found the original re-measured
every `[data-para-index]` element on every mousemove frame), `reading-shortcuts.ts`
(37, `R`/`F` keybindings), `speech.ts` (236, Web Speech read-aloud wrapper —
see §9 for its local-voice-only guarantee), `tokenize-words.ts` (33, word/char
offset tokenization shared by the manuscript reader and read-aloud highlighting),
`utils.ts` (7, `cn()` class helper).

**`src/assets/lottie/`** (Phase 8): 4 curated CC0/free-tier Lottie JSON
animations (`mascot-idle.json`, `empty-state.json`, `delight-accent.json`,
`loading-loop.json`) + `LICENSES.md` recording each asset's license/source.

## 6. Backend map — `apps/sidecar/`

**Config**: `pyproject.toml` (fastapi 0.139.2, SQLAlchemy 2.0.51, alembic,
litellm, argon2-cffi, Pillow, python-docx, screenplay-tools, reportlab,
`cryptography` 46.0.3 (Phase 7 `.quillproj` AES-256-GCM encryption) — with
comments noting `onnx-asr`/`sounddevice` (voice) and `sqlite-vec` (Phase 10
semantic search) are deferred/not yet installed. `pyrage` was the roadmap's
export-encryption default but was dropped for `cryptography`, see §3 Phase 7).

**Entry point**: `app/main.py` (133 ln) — `create_app()` factory; on
startup runs Alembic migrations, seeds structure templates, probes Ollama
(non-fatal — `/health`'s Ollama check is a ping only); CORS locked to
localhost/`tauri://localhost` origins only.

**Folder roles**: `app/api/` = route handlers (thin), `app/services/` =
business logic (routes call these, never touch the ORM directly for
anything non-trivial), `app/models/` = `orm.py` (SQLAlchemy models) +
`schemas.py` (Pydantic request/response), `app/db/` = engine/session setup +
Alembic env, `app/templates/` = Jinja2 + CSS used by the export pipeline.

**Routes ↔ services** (`app/api/*.py` ↔ `app/services/*.py`):

| Route file (lines) | Service file(s) (lines) | Domain |
|---|---|---|
| `auth.py` (83) | `password_service.py` (31), `sessions_service.py` (34) | Login/logout, argon2 password check, in-memory session tokens |
| `profiles.py` (44) | `profiles_service.py` (87) | Local profile CRUD (max 2) |
| `settings.py` (40) | `settings_service.py` (122) | Per-user + global settings (theme, AI mode, delight level, etc.) |
| `books.py` (80) | `book_service.py` (84) | Book CRUD + type conversion |
| `chapters.py` (60) | — | Chapter grouping for book-length works |
| `scenes.py` (134) | `scene_service.py` (80), `screenplay_service.py` (109) | Scene CRUD + screenplay elements (scene_heading/dialogue/etc.) |
| `canvas.py` (177) | `canvas_service.py` (250) | Node positions, edges between scenes on the visual canvas |
| `codex.py` (245) | `codex_service.py` (314) | Character/location/lore entries + scene links |
| `outline.py` (121) | `outline_service.py` (267) | Beat-board + timeline ordering (`book_scene_order`) |
| `continuity.py` (72) | `continuity_service.py` (**585 — largest service file**) | Continuity-flag detection/dismiss/resolve |
| `llm.py` (204) | `llm_orchestrator.py` (283), `prompt_builder.py` (363), `groq_key.py` (45), `llm_log_service.py` (80) | Enhance (SSE streaming), Groq key set/clear/test, audit log |
| `voice.py` (135) | `speech_stt.py` (249, **stubbed** — see §10) | Dictation/transcription |
| `images.py` (316, largest route file) | `images_service.py` (406), `entity_images_service.py` (195) | Image upload/tagging, polymorphic linking to book/scene/codex_entry |
| `export.py` (167) | `export_service.py` (275, dispatches by format, enforces `fountain`/`fdx` are script-types-only), `export_docx.py` (197), `export_pdf.py` (292, ReportLab-backed, see §3), `export_markdown.py` (188), `export_fountain.py` (186, renders **both** Fountain text *and* Final Draft `.fdx` XML via `screenplay_tools.fdx.writer.Writer`) | Final Draft export (Phase 6, done). Single endpoint: `POST /books/{book_id}/export/{format}`, `format` ∈ `markdown\|docx\|pdf\|fountain\|fdx`; results are versioned `draft_versions` rows, never overwritten (`GET /books/{book_id}/draft-versions`, `GET /draft-versions/{id}/download`) |
| `draft_preview.py` (72, Phase 8) | reuses `export_service.build_compiled_document` (read-only, never touches `export.py`'s write path) | Backend keystone for the Draft tab's manuscript reader. `GET /books/{book_id}/draft-preview` — measured 66ms/472KB on an 80k-word/40-chapter soak test |
| `import_export.py` (194, Phase 7) | `bundle_schema.py` (73, manifest/payload Pydantic), `bundle_crypto.py` (132, **AES-256-GCM + Argon2id**, `encrypt_bundle`/`decrypt_bundle`), `bundle_export.py` (282, UUID-scoped gather → zip), `bundle_import.py` (**652 ln — now the largest service file**, dry-run `inspect_bundle` + transactional `apply_import`, merge-by-UUID, natural-key join dedup) | `.quillproj` encrypted backup. `POST /books/{book_id}/export/bundle` (→ octet-stream), `POST /import/quillproj/inspect` + `/apply` (raw body + `X-Quillnight-Passphrase` header). **Reviewer-gated files** — reviewer pass done, no MUST-FIX, 3 SHOULD-FIX applied (WAL-aware restore, `book_scene_order` natural-key dedup, zip-slip regression test) |
| `backups.py` (33, Phase 7) | `backup_service.py` (140, `VACUUM INTO` rotation, keep-N, WAL-aware `restore_backup`) | Rotating local full-DB snapshots. `POST /backups/run`, `GET /backups`, `POST /backups/{name}/restore`. **Startup + manual trigger only** — a true periodic timer was deliberately deferred to Phase 9 |
| `health.py` (32) | `ollama_health.py` (28) | Liveness probes |
| `structure_templates.py` (33) | `structure_templates.py` service (98) | Seeded book-structure templates (three-act, etc.) |

**Models**: `models/orm.py` (441 ln, all SQLAlchemy tables), `models/schemas.py`
(651 ln, all Pydantic request/response shapes — the single file to check for
"what fields does X accept/return").

**Database**: SQLite via SQLAlchemy, 3 Alembic migrations so far
(`app/db/migrations/versions/`): initial schema (matches `docs/03-DATA-MODEL.md`),
profiles + per-user settings, and a widen of the continuity-flags source
check constraint.

**Tests**: 26 test files under `apps/sidecar/tests/`, roughly one per
service/route — check here for expected behavior before changing a service.

## 7. Request flow (the two patterns that matter)

**Normal CRUD** (e.g. creating a Codex entry):
`codex-entry-dialog.tsx` → `queries/codex.ts` (TanStack mutation) →
`lib/api.ts` (typed fetch) → `POST /codex` in `api/codex.py` →
`services/codex_service.py` → `models/orm.py` via SQLAlchemy session → SQLite.

**AI call** (e.g. Enhance):
`enhance-diff.tsx` triggers → `queries/enhance.ts` → `lib/api.ts` →
`POST /llm/enhance` in `api/llm.py` → `services/prompt_builder.py` assembles
the prompt (fixed order: static system → deterministic codex block →
variable text → task, for prefix-cache efficiency) →
`services/llm_orchestrator.py` (LiteLLM) routes to local Ollama or GroqCloud
per the user's Offline/Online/Hybrid setting → response streamed back over
SSE → user sees a diff in `enhance-diff.tsx` and must Accept/Reject/Edit —
nothing is written back to the scene until they do → on decision,
`POST /llm/log/:id/accept` records the outcome in the `llm_request_log` audit
table.

## 8. Design system quick reference

Two themes — Day (cream `#FBF5E9`, warm amber/ink-blue) and Night (soft gray
`#1E1E24`, firefly-gold `#FFC94D` + cyan) — switchable manually or by time
(`theme_mode: 'auto'` re-evaluates on a timer/`visibilitychange` since Phase
8, not just at load), implemented via `stores/theme.ts` + `theme-toggle.tsx`.
Phase 8 also added 4 discrete `BG_TINTS` background presets and a `focus_mode`
setting. Typography is evidence-driven, not a single "dyslexia font": Lexend
(default), Atkinson Hyperlegible Next, OpenDyslexic (opt-in only, never
default), Inter — chosen via the onboarding self-test
(`reading-comfort-wizard.tsx`). Reading defaults: 18px, 1.5 line-height,
0.035em letter-spacing, 65ch line length, bold-only emphasis (no
italics/caps). Reading aids (Phase 8): reading ruler (`R` toggle), focus mode
(`F` toggle, dims non-current paragraphs), read-aloud karaoke — all built
against the manuscript reader's `data-para-index`/`data-w`/`data-c` offsets
(see §6 `draft_preview.py`).

**Delight stack** — note the roadmap's "streaks" plan for Phase 8 was **cut
entirely** mid-planning (user call: "this is a storyboarding tool, not a
habit-tracker") and replaced with a Lottie animation overhaul instead:
`lib/delight.ts` + `firefly.tsx` (now Lottie-driven, was CSS/Motion glow) +
`lib/lottie.tsx`'s `<LottiePlayer>` (centralizes delight-level/reduced-motion
gating — freezes at Calm/reduced-motion, one gate, never a competing second
one) + `lib/delight-accent.tsx` (new Playful-only accent layer) +
`assets/lottie/` (4 curated CC0/free-tier animations + `LICENSES.md`) +
`motion`, `@formkit/auto-animate`, `canvas-confetti`, `use-sound`,
`@number-flow/react`. Three levels (Calm/Standard/Playful, default Playful),
all respect `prefers-reduced-motion` — Phase 8's delight-matrix audit traced
every animated surface and found zero bypasses. **Hard rule: playfulness
stays in UI chrome, never inside manuscript text.** Full detail:
`docs/10-DESIGN-SYSTEM.md`.

**Accessibility audits (Phase 8)**: WCAG AA contrast audit found and fixed a
real Night-theme failure (default button/badge text 3.39:1 → 5.49:1); canvas
keyboard audit found and fixed a dead-end (Enter did nothing on a focused
node) plus added a missing focus ring; shell/dialog audit added a missing
skip-to-main link and one missing nav focus ring.

## 9. Hard rules / conventions to respect

- **Never silently overwrite user text** — every AI transform is
  Accept/Reject/Edit-further (`enhance-diff.tsx` is the canonical pattern).
- **Groq API key never touches SQLite or Tauri's plain-JSON Store** — Rust
  `keyring` crate (Windows Credential Manager/DPAPI) only, passed to the
  sidecar in-memory per session (`lib/keyring.ts` ↔ `services/groq_key.py`).
- **Import is merge-by-UUID, never silent overwrite** (shipped Phase 7) —
  existing UUID → explicit conflict resolution (**keep-local / take-imported /
  merge** — note this deviates intentionally from docs/05's original
  keep-mine/take-theirs/**keep-both** wording; `keep-both` was dropped because
  it would require minting a new UUID, breaking the UUID-identity model the
  merge relies on), new UUID → inserted.
- **Reviewer (Opus) pass required** before merging changes to:
  `services/export_docx.py`, `services/export_pdf.py`, `bundle_export.py`,
  `bundle_import.py`, `bundle_crypto.py`, plus `services/speech_stt.py`
  (raw audio handling) — per `CLAUDE.md`. Phase 7's reviewer pass on the
  bundle files found no MUST-FIX.
- **Read-aloud (`lib/speech.ts`) is hard-filtered to `voice.localService ===
  true` with no fallback to any remote voice, ever** — reviewer-audited in
  Phase 8 specifically for this local-first guarantee (WebView2 online voices
  could otherwise leak manuscript text off-device); if zero local voices are
  available it shows a "no local voices" note rather than falling back remote.
- **Only official npm/PyPI/crates.io packages, pinned + lockfiled.**
- **Auto-suggest always uses the local model only, never Groq** — Groq's
  free tier isn't sized for continuous background traffic.
- Conversions between book types are **additive, never destructive** — e.g.
  converting Single Scene → Movie Script adds `screenplay_elements` without
  deleting the original `description`.

## 10. Known gaps (documented but not yet built)

- **Tauri desktop shell** — no `src-tauri/` anywhere; the app currently runs
  as a plain Vite web app. Port 1420 is reserved for when this lands.
- **Voice/STT (input)** — `services/speech_stt.py` still returns a fixed stub
  transcript; `mic-button.tsx`/`queries/voice.ts` have `[MODEL-DEFERRED]`
  comments; real dictation model verification happens on the ASUS TUF F15.
  **Read-aloud (output) is fully implemented** as of Phase 8 (`lib/speech.ts`,
  Web Speech API, local-voices-only — see §9); Piper neural TTS remains
  deferred to v1.1.
- **Export bundle encryption** — **DONE in Phase 7** (`cryptography` AES-256-GCM
  + Argon2id, not `pyrage`). **Semantic search (`sqlite-vec`)** — not installed,
  deferred to Phase 10.
- **Periodic backup timer** — Phase 7 shipped startup + manual-trigger backup
  rotation only; a true during-session periodic timer is deferred to Phase 9.
- **Canvas UX polish** (templates, keyboard-first node creation) — deliberately
  pushed from Phase 8 to Phase 9 to protect that phase's budget.
- **This build machine never runs real models** (`CLAUDE.md` hard constraint)
  — LLM-dependent code (Enhance quality, Tier-2 continuity semantic pass,
  FDX round-trip fidelity against an actual Final Draft/Highland viewer) is
  built and stub-verified here only, via `QUILLNIGHT_LLM_STUB=1
  QUILLNIGHT_STT_STUB=1` env vars in the test command (see `PHASE3–6.md`).
  Real semantic/quality verification happens later on the **ASUS TUF F15
  (RTX 3050 4GB)**, the designated target laptop, once the repo is
  transferred there via GitHub.
- See [API-REFERENCE.md](API-REFERENCE.md) for the full implemented-vs-planned
  breakdown of every user-facing option.

## 11. "Where do I make this change?" quick index

| If the request is about... | Start here |
|---|---|
| Canvas node appearance/behavior | `components/canvas/node-editor.tsx`, `nodes.tsx` |
| Connecting scenes on canvas | `components/canvas/ink-edge.tsx`, `api/canvas.py` → `services/canvas_service.py` |
| A Codex field (character/location/etc.) | `components/codex/codex-entry-dialog.tsx`, `models/schemas.py`, `services/codex_service.py` |
| Outline/beat-board ordering | `components/outline/beat-board.tsx`, `services/outline_service.py` |
| Continuity flag logic | `services/continuity_service.py` (largest service — read carefully), `components/outline/continuity-panel.tsx` |
| Enhance/AI prompt behavior | `services/prompt_builder.py`, `services/llm_orchestrator.py` |
| Adding/changing an AI provider mode | `services/llm_orchestrator.py`, `queries/settings.ts`, `routes/settings-screen.tsx` |
| Export/Final Draft output | `api/export.py`, `services/export_pdf.py` / `export_docx.py` / `export_markdown.py` / `export_fountain.py`, `components/draft/*` — **needs reviewer pass** |
| `.quillproj` bundle export/import | `components/bundle/export-dialog.tsx` / `import-review-dialog.tsx`, `api/import_export.py` → `services/bundle_export.py` / `bundle_import.py` / `bundle_crypto.py` — **needs reviewer pass** |
| Local DB backups | `api/backups.py` → `services/backup_service.py` |
| Manuscript reader / reading aids (ruler, focus mode, karaoke) | `api/draft_preview.py`, `components/draft/manuscript-reader.tsx`, `components/reading-ruler.tsx`, `components/draft/read-aloud-bar.tsx`, `lib/reading-cursor.ts`, `lib/speech.ts` (read-aloud — **needs reviewer pass** if changing its local-voice-only guarantee) |
| Image upload/tagging | `components/images/*`, `services/images_service.py`, `services/entity_images_service.py` |
| Voice/dictation (input) | `components/voice/mic-button.tsx`, `services/speech_stt.py` (currently stubbed) |
| Themes/typography/delight/Lottie | `stores/theme.ts`, `lib/delight.ts`, `lib/lottie.tsx`, `assets/lottie/`, `docs/10-DESIGN-SYSTEM.md` |
| Auth/profiles | `components/auth/profile-gate.tsx`, `api/auth.py` / `profiles.py`, `services/password_service.py` / `sessions_service.py` |
| Adding a new API endpoint | Add route in `api/`, logic in matching `services/*.py` file, schema in `models/schemas.py`, then regenerate `packages/api-types/schema.d.ts` |
| Database schema changes | `models/orm.py` + new Alembic migration in `db/migrations/versions/` |
