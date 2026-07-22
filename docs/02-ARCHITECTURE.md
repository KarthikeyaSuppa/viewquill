# Architecture

## Tech stack at a glance

| Layer | Choice | Why |
|---|---|---|
| Desktop shell | **Tauri 2** (Rust) | ~20-40MB idle RAM vs Electron's 200-400MB, smaller installer, smaller attack surface (no bundled Chromium/Node runtime), native Windows installers (NSIS/MSI) out of the box. |
| Frontend | **React + TypeScript + shadcn/ui (Tailwind)** | shadcn/ui ships an official React Flow component/template set — a direct match for the node-canvas UI this app is built around. |
| Node editor | **React Flow (`@xyflow/react`)** | Purpose-built, large community, official npm package, official shadcn/ui integration — reusing a mature library instead of building a custom canvas from scratch. |
| Backend/logic | **Python 3 + FastAPI**, bundled as a Tauri sidecar (PyInstaller executable) | Best local-LLM tooling of the three language options considered (React/Python/Java-Spring Boot); owns all domain logic so Rust stays thin and OS-only. |
| Local LLM runtime | **Ollama**, bundled from the official Windows release | Handles model download, quantization, and serving via a simple local API automatically — least custom inference code to maintain. |
| Local model | **`qwen3.5:4b`** default; `gemma4:e4b` grammar alternate; `qwen3.5:9b` quality toggle | Fits the 4GB VRAM entirely — faster and more consistent than a partially-offloaded 7B. Config-driven, never hardcoded; Phase 0 bake-off validates. Full rationale in [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §1. |
| Semantic layer (v1.1) | **`sqlite-vec`** + SQLite FTS5 (RRF-fused hybrid retrieval) + **`qwen3-embedding:0.6b`** pinned to CPU | Vectors live inside the existing SQLite file — zero new services, one backup artifact; CPU-pinned embedder never evicts the chat model. See [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §2–3. |
| Speech-to-text (dictation) | **Parakeet-TDT 0.6B via `onnx-asr`** (PyPI) on CPU; Groq Whisper in Online mode | Real-time on CPU, zero VRAM contention, avoids the cuDNN packaging trap. See [12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md). |
| Text-to-speech (read-aloud) | **Web Speech API** (karaoke word-highlighting) + **Piper** (`piper1-gpl`, v1.1) | Piper is **GPL-3.0 → runs as an isolated standalone process, never linked** into app code. See [12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md) §2. |
| Spellcheck (v1.1) | Hunspell (PHONE table) / SymSpell + **LanguageTool** | Phonetic misspellings + real-word errors — what standard spellcheck misses for dyslexic writers. [10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md) §4. |
| Animation & delight | `motion`, `@formkit/auto-animate`, `@rive-app/react-canvas` (mascot), `canvas-confetti`, `use-sound`, `@number-flow/react`, Magic UI components, `dnd-kit`, `tw-animate-css`, native View Transitions API, GSAP (free) for rare set-pieces | All MIT/ISC (verified July 2026, official registries). Per-package notes + the chrome-not-manuscript rule in [10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md) §5. |
| Fonts | Fontsource packages: **Lexend** (default), Atkinson Hyperlegible Next, OpenDyslexic, Inter | Self-hosted via npm, zero CDN calls; chosen per-user via the onboarding font self-test ([10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md) §2). |
| Cloud LLM (optional) | **GroqCloud free tier**, via the user's own API key | Optional Online/Hybrid mode for heavier user-triggered actions. See [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md). |
| Provider abstraction | **LiteLLM** (`litellm`, official PyPI package), wrapped behind a project-owned `ProviderClient` interface | Both Ollama and Groq expose OpenAI-compatible endpoints, so LiteLLM talks to either with no custom request/response mapping; its `Router` also provides the fallback/cooldown behavior Hybrid mode needs (a built-in circuit breaker), so no separate breaker library is needed. Wrapped behind our own interface so LiteLLM itself stays swappable. |
| Secret storage | **`keyring` crate** (crates.io), Windows Credential Manager backend, Rust-only access | Stores the user's Groq API key encrypted via DPAPI. Deliberately *not* Tauri's `Store` plugin, which persists plain unencrypted JSON. See [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md). |
| Client state | **Zustand** | Selector-based store avoids the re-render storms Context/Redux broadcast models cause when dragging nodes at 60fps on a canvas this size. |
| Server-truth state | **TanStack Query** | Caching, invalidation, optimistic updates, and `AbortSignal` plumbing that pairs directly with the streaming-Enhance cancel logic. |
| ORM/migrations | **SQLAlchemy 2.0 + Alembic** | Versioned, reversible schema migrations — not optional for data this irreplaceable, evolving across a multi-phase build. |
| Validation | **Pydantic v2** | Native FastAPI pairing; also drives the OpenAPI schema used to generate TS types. |
| Type sync | **`openapi-typescript`** | Generates TS interfaces directly from FastAPI's OpenAPI schema so Pydantic models and TS types never drift apart. |

## Process architecture

Three processes run together, managed by Tauri:

1. **Tauri/Rust shell** — the native window + WebView, and process supervisor for the other two.
2. **Python/FastAPI sidecar** — `127.0.0.1:<dynamic-port>`, owns all domain logic, data, and AI orchestration.
3. **Ollama** — `127.0.0.1:11434` (or dynamically assigned), serves the local model over its own HTTP API. The Python sidecar is Ollama's only client; the frontend never talks to Ollama directly.

**Boundary rule**: Python/FastAPI over local HTTP owns everything domain-related. Tauri's Rust-side `#[tauri::command]` IPC is reserved for things only the OS shell can do — it does not duplicate business logic in two languages.

### Tauri shell responsibilities (kept intentionally thin)
- Spawn/health-poll/restart-on-crash/cleanly-terminate both sidecars (`externalBin` sidecar mechanism, `on_window_event`/`RunEvent::Exit`). **Do not rely on OS-level `process.kill()` to stop the Python sidecar** — if built with PyInstaller's one-file mode, Rust only holds the bootloader's PID, not the real Python process underneath, so killing it can leave an orphan running (see [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md)); use an explicit shutdown signal instead, or build with `--onedir`.
- Native file dialogs (`tauri-plugin-dialog`) for image upload and `.quillproj` export/import pickers.
- App-data path resolution (`tauri-plugin-fs`, `app_data_dir()`) — the single source of truth for where the SQLite DB, media files, and Ollama's model store live on disk.
- OS drag-and-drop of files from Explorer into the app.
- A small IPC surface: `get_backend_port()`, `get_app_data_dir()`, `open_file_dialog()`, `restart_sidecar()`.

## Frontend structure

```
apps/desktop/src
  /app/                     — routes: Library, Book/{id}/canvas, /outline, /draft, Settings
  /components/
    /ui/                    — shadcn/ui primitives
    /flow/                  — xyflow custom nodes (SceneNode, PlotPointNode, ThoughtNode, ScriptElementNode),
                              custom edges, node toolbar (Enhance button, image attach, codex-link picker)
    /codex/                 — entity list/detail, custom-field editor, relationship picker, arc-state timeline
    /outline/               — beat-board (columns/lanes) + timeline (horizontal sequencer), one shared data hook
    /draft/                 — compiled manuscript/script preview, export dialog
    /images/                — upload/tag/search grid for both buckets
    /accessibility/         — font/size/spacing controls, reading ruler, focus mode, read-aloud karaoke controls
    /delight/               — mascot host (Rive canvas + state wiring), confetti triggers, sound manager,
                              NumberFlow ticker + inkwell ring, ambient firefly, delight-level gate (10-DESIGN-SYSTEM.md)
    /voice/                 — push-to-talk button/hotkey handling, recording indicator, voice-notes review
    /onboarding/            — Reading Comfort Wizard (font self-test, spacing, theme, delight level)
  /stores/                  — Zustand: useCanvasStore, useSettingsStore, useLlmStreamStore, useMergeReportStore,
                              useDelightStore (level + per-feature toggles), useVoiceStore (recording state)
  /queries/                 — TanStack Query hooks per REST resource (books, scenes, codex, images, outline, exports, search, voice)
  /lib/                     — typed API client (generated types), fetch-stream helper with AbortController registry,
                              view-transitions helper (reduced-motion-aware)
  /styles/                  — Tailwind day/night theme tokens, Fontsource font imports (Lexend, Atkinson Next, OpenDyslexic, Inter)
```

## Backend structure

```
apps/sidecar/app
  main.py                   — app factory, CORS (localhost only), startup: run Alembic migrations, verify Ollama health
  /api/                     — routers: books.py, scenes.py, codex.py, images.py, outline.py, continuity.py,
                              llm.py, export.py, import_.py, settings.py, search.py (v1.1), voice.py, gamification.py
  /services/
    prompt_builder.py       — Enhance/continuity prompt assembly, Codex context injection, token-budget trimming,
                              prefix-cache prompt ordering (11-AI-INTELLIGENCE.md §5), deterministic codex serialization
    llm_orchestrator.py     — LiteLLM-backed ProviderClient (Ollama + Groq), streaming relay, keep-alive/keep-warm,
                              cancellation, Offline/Online/Hybrid routing and fallback (see 08-AI-PROVIDER-MODES.md)
    continuity_checker.py   — v2 two-tier scan: deterministic SQL checks + guarded LLM pass with quote verification
                              and (v1.1) self-consistency voting (11-AI-INTELLIGENCE.md §4)
    semantic_search.py      — (v1.1) embedding pipeline, sqlite-vec + FTS5 hybrid RRF retrieval,
                              GraphRAG-lite context assembly, auto-link + similar-scene suggestions
    speech_stt.py           — dictation: sounddevice capture, Silero VAD, Parakeet (onnx-asr) / Groq Whisper routing,
                              voice_notes persistence (12-VOICE-AND-SPEECH.md)
    speech_tts.py           — (v1.1) Piper process management (GPL-isolated standalone process, stdin/HTTP only)
    spellcheck.py           — (v1.1) Hunspell-phonetic/SymSpell + LanguageTool verifier, personal dictionary
    gamification.py         — writing_sessions tracking, streaks/goals, achievement unlocks
    export_docx.py / export_pdf.py / export_fountain_fdx.py
    bundle_export.py / bundle_import.py — .quillproj packaging, encryption, UUID-merge (embeddings excluded — derived)
    image_store.py          — file storage, checksum, thumbnailing
  /models/                  — SQLAlchemy 2.0 ORM models + Pydantic v2 schemas
  /db/                      — Alembic migrations, schema.sql snapshot
```

## Repo/folder structure

```
quillnight/
├── apps/
│   ├── desktop/                    # Tauri app
│   │   ├── src/                    # React frontend
│   │   ├── src-tauri/
│   │   │   ├── src/                # main.rs, sidecar lifecycle commands
│   │   │   ├── binaries/           # PyInstaller sidecar exe per target triple (gitignored)
│   │   │   ├── resources/ollama/   # bundled official Ollama Windows release (gitignored, fetched by script)
│   │   │   └── tauri.conf.json
│   │   ├── components.json         # shadcn config
│   │   └── package.json
│   └── sidecar/                    # Python FastAPI backend
│       ├── pyproject.toml          # pinned deps
│       └── build_sidecar.py        # PyInstaller spec/build
├── packages/
│   └── api-types/                  # generated via openapi-typescript from FastAPI's OpenAPI schema
├── scripts/
│   ├── setup-ollama.ps1            # fetch official Ollama release into resources/
│   ├── dev.ps1                     # run frontend + sidecar concurrently in dev
│   └── audit.ps1                   # npm audit / pip-audit / cargo audit
├── docs/                            # this specification
└── .github/workflows/ci.yml        # windows-latest runner: lint/test/build
```

## Package/dependency security

- Only official registries: npm, PyPI, crates.io, and the official Ollama GitHub release / model library. This applies just as strictly to the new provider-abstraction/secret-storage dependencies (`litellm` on PyPI, `keyring` on crates.io) as to everything else — no unofficial forks, especially not for anything touching credentials.
- Pinned versions and committed lockfiles (`package-lock.json`, a locked `pyproject.toml`/`uv.lock` or `poetry.lock`, `Cargo.lock`).
- No unofficial forks/mirrors of well-known libraries, ever — if a library isn't on the official registry under its own name, it doesn't go in this project.
- Recurring dependency audits (`scripts/audit.ps1`: `npm audit`, `pip-audit`, `cargo audit`) — run in CI and periodically by hand, not just once at setup.
