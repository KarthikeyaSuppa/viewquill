# Quillnight — API & Options Reference

> Every user-facing option and backend endpoint, side by side: the left
> column is what it does for the person using the app (frontend, plain
> language); the right column is what a frontend/backend engineer needs to
> touch it (endpoint, file, implementation notes). Rows tagged **(planned)**
> or **(deferred to v1.1/v2.0)** aren't built yet — see
> [PROJECT-MAP.md](PROJECT-MAP.md) §10 for the current gap list. Everything
> else below is implemented today. Base URL for all endpoints:
> `http://127.0.0.1:8756`.

## Profiles & Auth

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Profile picker | Netflix-style picker at launch; pick one of up to 2 local profiles (username + avatar) | `GET /profiles` (public, no auth) → `components/auth/profile-gate.tsx`, `api/profiles.py` |
| Create profile | "Add profile" — set a username, password, avatar; capped at 2 profiles total | `POST /profiles` → `api/profiles.py` → `services/profiles_service.py` (argon2-cffi hash via `services/password_service.py`) |
| Log in | Enter password for the selected profile | `POST /auth/login` → `api/auth.py` → returns an in-memory session token (no JWT, no persisted sessions table) |
| Stay logged in this session | App remembers who's active while running | `GET /auth/me` (bearer token) → `services/sessions_service.py` |
| Log out / switch profile | "Switch profile" control returns to the picker | `POST /auth/logout` → invalidates the in-memory token |
| Shared Story Library | All profiles see the same Books/Scenes/Codex — only personal settings (typography, theme, delight, onboarding) differ per profile | Library endpoints (`/books`, `/scenes`, etc.) are unauthenticated server-side; `profile-gate.tsx` enforces the "must be logged in" UX client-side only |

## Settings

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Load/save settings | Settings screen reads and writes theme, AI mode, delight level, voice prefs, etc. | `GET /settings` / `PATCH /settings` (bearer) → `api/settings.py` → `services/settings_service.py`; merges per-user + global rows. Frontend: `queries/settings.ts`, `routes/settings-screen.tsx` |
| AI/provider settings are global | Changing AI mode affects every profile, not just yours | Enforced in `settings_service.py` — only typography/theme/delight/mascot/onboarding are per-profile |

## Books

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Create a Book | "New Book" — pick a title, book type (novel/movie script/short film/single scene), logline | `POST /books` → `api/books.py` → `services/book_service.py` |
| Browse Library | See all Books as cards on the Library screen | `GET /books` (list) / `GET /books/:id` (detail) → `routes/library-screen.tsx` |
| Edit Book metadata | Rename, change logline, etc. | `PATCH /books/:id` |
| Convert Book type | E.g. turn a Single Scene into a Movie Script | `POST /books/:id/convert` — **additive only**, never deletes existing fields (e.g. adds `screenplay_elements`, keeps `description`) |
| Delete a Book | Remove a Book from the Library | `DELETE /books/:id` |
| Chapters (book-length works) | Group scenes into chapters for novel-type Books | `api/chapters.py` (60 ln) |

## Scenes & Screenplay

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Create/edit/delete a Scene | Write or dictate a scene's content | `POST`/`GET`/`PATCH`/`DELETE /scenes`, `/scenes/:id` → `api/scenes.py` → `services/scene_service.py` |
| Screenplay elements | For script-type Books: scene headings, dialogue, action lines as distinct typed elements | `GET/POST /scenes/:id/elements`, `PATCH /scenes/elements/:elid` → `services/screenplay_service.py` |
| Reorder screenplay elements | Drag elements within a scene | `POST /scenes/:id/elements/reorder` |

## Canvas (node graph)

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Visual node canvas | Blender-style graph of Scene nodes you can drag around, connect, and edit inline | `GET /books/:id/canvas` → `components/canvas/node-editor.tsx` (805 ln, largest file in repo), built on React Flow (`@xyflow/react`) |
| Add/move/unlink a node | Drop a new scene node, drag it, or remove it from the canvas without deleting the scene | `POST`/`PATCH`/`DELETE /books/:id/scenes/:id` (canvas-scoped) → `services/canvas_service.py` |
| Connect two scenes | Draw an edge between nodes to show story flow | `GET/POST /books/:id/edges`, `DELETE /edges/:id` → `components/canvas/ink-edge.tsx` (animated "ink flow" via Magic UI's Animated Beam) |
| Move a scene between Books | Drag a scene node out of one Book into another | `POST /books/:id/scenes/:id/move?from_book_id=` |
| Copy a scene into a Book | Reuse an existing scene without moving the original | `POST /books/:id/scenes/:id/copy` |
| Accept/Reject AI edits inline | Every Enhance suggestion shows as a diff you must approve, reject, or edit further before it touches your text | `components/canvas/enhance-diff.tsx` — this is the canonical trust-rule UI pattern used everywhere AI writes text |

## Codex

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Create a Codex entry | Add a character, location, or other lore entry, reusable across every Book | `POST /codex` → `api/codex.py` → `services/codex_service.py`. Frontend: `components/codex/codex-entry-dialog.tsx` (698 ln) |
| Browse/filter Codex | Filter by entry type (character/location/etc.) | `GET /codex?entry_type=` |
| Edit/delete a Codex entry | Update or remove lore | `PATCH`/`DELETE /codex/:id` |
| Link a Codex entry to a Scene | Tag which characters/locations appear in a scene | `POST /codex/:id/scenes/:id`, `GET /scenes/:id/codex` |
| Point-in-time character state | Enhance calls only "know" what a character knows as of that scene — no spoilers from later reveals | Backed by `codex_arc_states` table (see `docs/03-DATA-MODEL.md`), consumed by `prompt_builder.py` |

## Outline & Continuity

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Beat-board (Outline view) | Drag-and-drop scene cards to reorder your story's beats | `components/outline/beat-board.tsx` (354 ln, `dnd-kit`) → `api/outline.py` → `services/outline_service.py` |
| Timeline view | Same scenes, chronological-order view instead of beat order | `components/outline/timeline-view.tsx` — both views share the one `book_scene_order` table |
| Continuity Checker | Flags inconsistencies (e.g. a character described alive after being killed off) for you to review | `api/continuity.py` → `services/continuity_service.py` (585 ln, largest service file). Frontend: `components/outline/continuity-panel.tsx` |
| Dismiss/resolve a continuity flag | Mark a flag as "not an issue" or "fixed" | Continuity flag endpoints in `api/continuity.py` |
| Verbatim-quote guardrail | Continuity flags are dropped if the AI's supporting quote isn't an exact literal match in your text — prevents false "gotchas" | Enforced in `continuity_service.py` |
| Tier-1 continuity checks | Instant, always-correct checks (early character appearance, timeline inversions) — deterministic, not AI | Plain SQL queries in `continuity_service.py` — no model involved, fully tested on this build machine |
| Tier-2 continuity checks | Deeper "does this contradict something earlier" semantic pass | Two-pass CoT→JSON via the LLM path; **built and stub-verified only on this build machine** (`QUILLNIGHT_LLM_STUB=1` EchoProvider) — real semantic quality is checked later on the ASUS TUF F15 target laptop |
| 3-vote self-consistency check (deferred to v1.1) | *(planned)* Higher-confidence continuity checks by having the model vote 3 times before flagging | v1.0 ships single-pass Tier-2 only |

## LLM / Enhance / AI provider modes

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Enhance (grammar/prose fix) | Select text, click Enhance, review a streaming diff, Accept/Reject | `POST /llm/enhance` (SSE stream, `mode: grammar\|prose\|continuity_flag`) → `api/llm.py` → `services/prompt_builder.py` + `services/llm_orchestrator.py` |
| Record Accept/Reject outcome | Every decision is logged for audit/analysis | `POST /llm/log/:id/accept` → `services/llm_log_service.py` writes to `llm_request_log` |
| **Offline mode** | AI runs 100% locally via Ollama — nothing leaves your machine | Settings → AI Mode = Offline. `llm_orchestrator.py` routes to local Ollama only (`qwen3.5:4b` default, `gemma4:e4b` grammar-alt, `qwen3.5:9b` quality toggle) |
| **Online mode** | AI runs on GroqCloud using your own free API key — faster, needs internet | Settings → AI Mode = Online. Routes to GroqCloud only via LiteLLM |
| **Hybrid mode** | Prefers Groq for speed, silently falls back to local Ollama if Groq fails/times out/hits rate limits | Settings → AI Mode = Hybrid (default recommended). Fallback logic lives in `llm_orchestrator.py` |
| Set/clear/test Groq API key | Paste your Groq key (masked field), or clear it; "Test connection" confirms it works | `POST`/`DELETE /llm/groq-key`, `POST /llm/test-connection` → `services/groq_key.py` — **key is never written to SQLite or Tauri's Store; stored only via the Rust `keyring` crate (Windows Credential Manager/DPAPI), passed to the sidecar in-memory per session** |
| Keep AI model warm | Toggle to keep the local model loaded in memory for faster responses | Settings toggle → passed through to Ollama sidecar lifecycle management |
| Auto-suggest | Background, debounced Enhance suggestions as you type (off by default) | Settings toggle, default **off**. **Hard rule: auto-suggest always uses the local model, never Groq** — Groq's free tier isn't sized for continuous background traffic |
| Zero Data Retention (ZDR) setting | Signals you want providers that don't retain your data for training | Settings toggle → filters which provider/model options are offered |
| Per-task model routing (rejected as automatic) | You choose the model yourself; the app doesn't auto-pick per task | Explicit product decision — see `docs/07-RISKS-AND-OPEN-QUESTIONS.md` |
| Prompt structure | *(no user-facing control)* Prompts are always ordered `[static system] → [deterministic codex block] → [variable text] → [task]` for LLM prefix-cache efficiency | `services/prompt_builder.py` — don't reorder this without understanding the caching implications |

## Voice / Dictation & Read-Aloud

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Push-to-talk dictation | Hold `Ctrl+Space` or click the mic button to dictate a scene | `POST /voice/transcribe` (raw audio, max 100MB) → `api/voice.py` → `services/speech_stt.py`. Frontend: `components/voice/mic-button.tsx` — **currently stubbed, returns a fixed "stub transcript"** (real model deferred to the second/unrestricted build machine per `CLAUDE.md` environment constraints) |
| Voice notes list | See past dictations, retry or discard them | `GET /voice`, `POST /voice/:id/attach`, `/discard`, `/retranscribe` |
| Auto-stop on silence | Recording stops automatically when you stop talking | Silero VAD — sensitivity configurable in Settings → Voice |
| Local vs cloud transcription | Offline: Parakeet-TDT 0.6B (CPU, local, `onnx-asr`); Online/Hybrid: Groq `whisper-large-v3-turbo` | Same Offline/Online/Hybrid setting drives both Enhance and transcription routing |
| Read-aloud (karaoke highlighting) | Have the app read your Draft tab manuscript back, word-by-word highlight, from the read-aloud toolbar | `lib/speech.ts` (236 ln, Web Speech API wrapper) + `components/draft/read-aloud-bar.tsx` (165 ln). **Hard-filtered to `voice.localService === true` — never falls back to a remote voice**; if no local voices exist, shows a plain "no local voices" note instead. Reviewer-audited in Phase 8 specifically for this local-first guarantee (a remote voice would otherwise send your manuscript text off-device); Settings → Voice exposes the voice picker + speed |
| Read-aloud, neural voices **(deferred to v1.1)** | *(planned)* Higher-quality Piper TTS voices, paragraph-level highlighting | Isolated as a separate process for GPL license boundary reasons |
| Brain-dump mode **(deferred to v1.1)** | *(planned)* Ramble freely, have the AI split your rambling into multiple draft scene nodes | Not yet started |

## Images

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Upload an image | Attach a reference image to a Book, Scene, or Codex entry | `api/images.py` (316 ln, largest route file) → `services/images_service.py` (406 ln) |
| Tag an image | Add tags for organization/search | `components/images/tag-editor.tsx` |
| One image, many attachment points | An image can be linked to a book/scene/codex_entry via one consistent model | `entity_images` polymorphic join table → `services/entity_images_service.py` |
| Safe image decoding | Large/malicious images can't crash or exploit the app | Pillow `MAX_IMAGE_PIXELS` + decompression-bomb guards in `images_service.py` |

## Reading & Accessibility (Phase 8)

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Manuscript reader | The Draft tab now actually renders your compiled prose (it showed no text at all before Phase 8) | `GET /books/{book_id}/draft-preview` (read-only, reuses `export_service.build_compiled_document`, never touches the export write path) → `components/draft/manuscript-reader.tsx` (239 ln) — renders with globally-sequential `data-para-index`/`data-w`/`data-c` attributes every reading aid below positions against |
| Reading ruler | Toggle (`R` key) a highlighted bar that follows your reading position line-by-line | `components/reading-ruler.tsx` (94 ln) + `lib/reading-cursor.ts`'s `useReadingCursor` (243 ln — rewritten in Phase 8 after a perf audit found it re-measuring the whole DOM on every mousemove frame; now caches paragraph rects once and binary-searches them) |
| Focus mode | Toggle (`F` key) to dim every paragraph except the one you're reading | `components/reading-controls.tsx`, driven by the same cached reading-cursor position |
| Background tint presets | Pick from 4 background tint presets for the reading surface | Settings → new `BG_TINTS` picker (`stores/theme.ts`) |
| Auto theme re-evaluation | Day/Night auto-switch now re-checks on a timer and on tab focus, not just at app load | `theme_mode: 'auto'` handling in `stores/theme.ts` |
| Accessibility audit fixes | *(no direct toggle — these are baseline fixes, not options)* | Phase 8 found and fixed: a Night-theme WCAG AA contrast failure (button/badge text 3.39:1 → 5.49:1), a canvas keyboard dead-end (Enter did nothing on a focused node), and added a missing skip-to-main link + nav focus ring |
| ~~Streaks / daily word goal~~ **(cut, not shipped)** | *(not planned)* The roadmap originally listed streak/gamification tracking for Phase 8 — the user rejected this scope ("this is a storyboarding tool, not a habit-tracker") and it was replaced with the Lottie animation overhaul below instead | No backend/frontend work exists or is planned for this |
| Lottie animation overhaul | The firefly mascot, canvas/library empty states, the manuscript-reader loading spinner, and the onboarding header now use smooth Lottie animations instead of CSS/Motion effects | `lib/lottie.tsx`'s `<LottiePlayer>` (centralizes delight-level/reduced-motion gating), `assets/lottie/*.json` (4 curated CC0/free-tier assets, licenses in `assets/lottie/LICENSES.md`), `lib/delight-accent.tsx` (new Playful-only accent layer) |

## Export / Import (Final Draft — done in Phase 6; `.quillproj` bundles done in Phase 7)

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Export a Book | Pick a format and compile your Book into a downloadable file | One unified endpoint: `POST /books/{book_id}/export/{format}` → `api/export.py` → `services/export_service.py` (275 ln, dispatches by format, enforces script-only formats). `format` ∈ `markdown \| docx \| pdf \| fountain \| fdx`. Frontend: `queries/export.ts`, `components/draft/draft-panel.tsx` |
| — Markdown | Plain-text/Markdown export, any Book type | `services/export_markdown.py` (188 ln, Jinja2 templates in `app/templates/draft.md.j2`) |
| — DOCX | Word document export, any Book type | `services/export_docx.py` (197 ln, python-docx) |
| — PDF | Formatted PDF, any Book type | `services/export_pdf.py` (292 ln). Renderer isolated behind one `render_pdf(html, css) -> bytes` interface. **Active engine: ReportLab 5.0.0** — WeasyPrint was tried first (2026-07-27) but failed to import (`OSError: cannot load library 'libgobject-2.0-0'`, no GTK runtime here); reactivating WeasyPrint later on the ASUS TUF F15 is meant to be a localized swap behind that same interface, not a rewrite |
| — Fountain | Screenplay-format export — **script-type Books only** (`movie_script`/`short_film_script`) | `services/export_fountain.py` (186 ln), via `screenplay_tools.fdx.writer.Writer` |
| — Final Draft (`.fdx`) | Export as a `.fdx` file openable in Final Draft/Highland — **script-type Books only** | Same `services/export_fountain.py` file (`render_fdx()`) via `screenplay_tools.fdx.writer.Writer` — round-trip fidelity against a real Final Draft/Highland viewer is unverified here (no viewer on this build machine); checked structurally only (parses back, scene numbering/dual-dialogue/title-page present) until verified on the ASUS TUF F15 |
| Front matter / title page | Edit title page, dedication, preface before exporting | `Book.front_matter` JSON field (`models/orm.py`) ↔ `components/draft/front-matter-editor.tsx` |
| Draft version history | See past export versions, re-download any of them — exports never overwrite a prior version | `GET /books/{book_id}/draft-versions` (list), `GET /draft-versions/{id}/download` (file download) → `draft_versions` table (`is_current`, `format_settings`, `generated_at`). Frontend: `components/draft/version-list.tsx` |
| **`.quillproj` project export** | Export a Book as one encrypted, shareable/backup file — you set a passphrase | `POST /books/{book_id}/export/bundle` (raw octet-stream response) → `api/import_export.py` → `services/bundle_export.py` (282 ln, UUID-scoped gather of the Book + its scenes/codex/images → zip) → `services/bundle_crypto.py` (132 ln, **AES-256-GCM + Argon2id**, `encrypt_bundle`). Frontend: `components/bundle/export-dialog.tsx` (123 ln), `queries/bundle.ts` |
| **`.quillproj` project import** | Import a bundle — preview what will change, resolve any conflicts, then confirm | Two-step: `POST /import/quillproj/inspect` (dry-run, returns a diff) then `POST /import/quillproj/apply` (transactional) — both take the raw bundle body + an `X-Quillnight-Passphrase` header. → `services/bundle_import.py` (**652 ln, the largest service file in the repo**). Conflict resolution per row: **keep-local / take-imported / merge** (imported fills only local NULL/empty fields), default keep-local — note this is an intentional deviation from docs/05's original keep-mine/take-theirs/**keep-both** wording; `keep-both` was dropped because it would require minting a new UUID, breaking the UUID-identity model the merge relies on. Frontend: `components/bundle/import-review-dialog.tsx` (242 ln) |
| Local database backups | Automatic backup on app startup, or trigger one manually | `POST /backups/run`, `GET /backups`, `POST /backups/{name}/restore` → `services/backup_service.py` (140 ln, `VACUUM INTO` rotation, keep-N, WAL-aware restore). **Startup + manual trigger only** — a true periodic in-session timer is deferred to Phase 9 |
| Reviewer-gated files | *(no direct user option)* | `export_docx.py`, `export_pdf.py`, `bundle_export.py`, `bundle_import.py`, `bundle_crypto.py` all require an Opus reviewer pass before merging — data-loss/security-sensitive per `docs/05-EXPORT-IMPORT-SECURITY.md`. Phase 7's reviewer pass found no MUST-FIX; 3 SHOULD-FIX applied (WAL-aware restore, `book_scene_order` natural-key dedup, zip-slip regression test) |

## Health

| Option | User-facing (Frontend) | Developer (Backend/Frontend) |
|---|---|---|
| Sidecar/Ollama status | Small status indicator confirming the backend and local AI are running | `GET /`, `GET /health` → `api/health.py` → `services/ollama_health.py` — Ollama check is a ping only, never blocks startup |

## Not yet built at all (roadmap-level gaps)

| Feature | Status |
|---|---|
| Tauri desktop shell | Planned — no `src-tauri/` exists; app runs as a plain Vite web app today |
| Real voice dictation model | Backend stub only (`speech_stt.py` returns a fixed transcript) — real model runs on the ASUS TUF F15, never on this build machine |
| Piper neural read-aloud voices | Deferred to v1.1 — Web Speech (local-only) ships today, see Reading & Accessibility above |
| Semantic search / auto codex-link suggestions / similar-scene detection | Deferred to v1.1 (needs `sqlite-vec`, not installed) |
| Cross-encoder reranker | Deferred, only if v1.1 retrieval quality underperforms |
| True periodic backup timer | Deferred to **Phase 9** — Phase 7 shipped startup + manual-trigger rotation only |
| Canvas templates + keyboard-first node creation | Deferred to **Phase 9** (deliberately pushed out of Phase 8 to protect its budget) |
| Canvas node grouping/frames, auto-layout, edge labels, Codex badges on nodes | Deferred, see `docs/14-DEFERRED-ENHANCEMENTS.md` — no phase committed yet |
| Streaks / daily word goal / gamification | **Cut entirely, not planned** — was in the original Phase 8 roadmap scope, replaced by the Lottie animation overhaul instead |
| "Present your story" slideshow mode | Deferred, no phase committed yet |
| Real Final Draft/Highland viewer verification of `.fdx` round-trip fidelity | Checked structurally only on this build machine (no viewer available); real verification happens on the ASUS TUF F15 |

## Security & data-integrity notes (read before touching auth/export code)

- The **live SQLite database is unencrypted** (performance tradeoff, local
  disk only). Only `.quillproj` **export bundles** are encrypted — shipped in
  Phase 7 as **`cryptography` 46.0.3 AES-256-GCM keyed by Argon2id**, not the
  roadmap's original `pyrage`/age choice (`pyrage` was dropped: single-
  maintainer native wheel; `cryptography` is the most-audited option and
  installed cleanly through the corporate proxy — same posture as Phase 6's
  WeasyPrint→ReportLab fallback). A separate local backup rotation
  (`VACUUM INTO`, startup + manual trigger, keep-N) exists independent of
  exports; a true periodic in-session timer is deferred to Phase 9.
- **Passwords**: hashed with `argon2-cffi`. Sessions are in-memory token maps
  only — no persisted sessions table, no JWT. Profile "login" is a UI lock
  for a shared local machine, not disk-level encryption; it does not protect
  against someone with direct file-system access.
- **Groq API key**: never stored in `app_settings` or SQLite. Lives only in
  the OS credential store via the Rust `keyring` crate, passed to the Python
  sidecar in-memory per session.
- **Import merge semantics** (shipped Phase 7): every entity has a UUID
  primary key specifically so imports can merge by ID — existing UUID never
  silently overwritten (conflict resolution is **keep-local / take-imported /
  merge**, an intentional deviation from docs/05's original keep-mine/
  take-theirs/keep-both wording — see Export/Import table above for why),
  new UUID always inserted, with a structured report shown to the user
  either way. Bundle manifests carry a `schema_version`, validated before any
  data is read; the bundle-import path was reviewer-gated (no MUST-FIX, 3
  SHOULD-FIX applied) and has a zip-slip regression test.
- **Read-aloud is local-voice-only, no exceptions**: `lib/speech.ts` hard-
  filters to `voice.localService === true` and never falls back to a remote
  voice — reviewer-audited in Phase 8 specifically because a remote voice
  would otherwise send manuscript text off-device via WebView2.
- **Audit trail**: `llm_request_log` records every AI call (entity, mode,
  latency, accepted/rejected, which provider actually served it).
- **Dependency policy**: only official npm/PyPI/crates.io packages, pinned
  and lockfiled — applies with extra weight to anything touching crypto or
  export.
- **This build machine never runs real models.** Anything LLM-dependent
  (Enhance quality, Tier-2 continuity semantic pass, FDX round-trip fidelity)
  is built and stub-verified here via `QUILLNIGHT_LLM_STUB=1
  QUILLNIGHT_STT_STUB=1` (an EchoProvider stub, set before running
  `pytest`) — real quality/fidelity is only ever confirmed later on the
  **ASUS TUF F15 (RTX 3050 4GB)**, the designated target laptop, once the
  repo is transferred there via GitHub. Never fetch or install a model here.
