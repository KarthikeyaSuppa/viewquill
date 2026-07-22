# Quillnight

A personal, fully local Windows desktop application for story generation and storyboarding — capture raw scene/plot/character ideas as a Blender-style connected node graph (typed **or spoken**), use a locally-run LLM to fix grammar and catch continuity holes, then compile everything into a finished book, movie script, short film script, or single scene. Content (scenes, characters, images) is reusable across every project you create. Dressed in a dyslexia-first, evidence-based reading environment with a genuinely playful heart — Day/Night themes and a firefly companion included.

This repository currently contains only the specification — no code has been written yet. Read the docs below in order before writing any code; they are the source of truth for every design decision.

## Why this exists

The author is dyslexic and wants a trustworthy, permanent, offline home for creative work: something that helps correct grammar/vocabulary, keeps continuity consistent across long projects, and never loses or silently overwrites anything — with an interface good enough to actually want to open every day.

## Documentation index

| Doc | Contents |
|---|---|
| [01-PRODUCT-VISION.md](docs/01-PRODUCT-VISION.md) | What the app does: the Story Library, the 3 tabs per Book, node types, the Codex, images, book-type conversion, auto-suggest behavior |
| [02-ARCHITECTURE.md](docs/02-ARCHITECTURE.md) | Tech stack and why, module/component breakdown (Tauri/React/Python), state management, repo/folder structure |
| [03-DATA-MODEL.md](docs/03-DATA-MODEL.md) | Full SQLite schema (all tables), with column-level notes on why each design choice exists |
| [04-LLM-INTEGRATION.md](docs/04-LLM-INTEGRATION.md) | How Enhance/continuity-check calls are built, Ollama bundling, debounce/cancel/keep-warm design |
| [05-EXPORT-IMPORT-SECURITY.md](docs/05-EXPORT-IMPORT-SECURITY.md) | `.quillproj` bundle format, encryption approach, per-format exporters, backup strategy |
| [06-ROADMAP.md](docs/06-ROADMAP.md) | Phased build plan, each phase with a concrete demo/acceptance criterion |
| [07-RISKS-AND-OPEN-QUESTIONS.md](docs/07-RISKS-AND-OPEN-QUESTIONS.md) | Known risks/unvalidated assumptions, updated as Phase 0 spikes resolve them |
| [08-AI-PROVIDER-MODES.md](docs/08-AI-PROVIDER-MODES.md) | Offline/Online/Hybrid AI modes — optional GroqCloud backend, fallback design, secure key storage, privacy |
| [09-HANDOFF-AND-BUILD-GUIDE.md](docs/09-HANDOFF-AND-BUILD-GUIDE.md) | Operational guide for picking this project up cold (a different Claude session, or a human dev) and building Phase 0 onward |
| [10-DESIGN-SYSTEM.md](docs/10-DESIGN-SYSTEM.md) | Day/Night themes, evidence-based dyslexia typography + reading aids, the delight stack (animation/sounds/confetti), the firefly mascot, Reading Comfort Wizard, gamification |
| [11-AI-INTELLIGENCE.md](docs/11-AI-INTELLIGENCE.md) | Model selection (`qwen3.5:4b` default), local RAG (sqlite-vec + FTS5 hybrid retrieval), GraphRAG-lite, prefix caching (local CAG), two-pass reasoning, hallucination guardrails, rejected patterns |
| [12-VOICE-AND-SPEECH.md](docs/12-VOICE-AND-SPEECH.md) | Dictation (push-to-talk, local Parakeet + Groq Whisper) and read-aloud (Web Speech karaoke + Piper), audio capture design |

## Quick facts

- **Platform**: Windows desktop, Tauri + React + shadcn/ui frontend, Python/FastAPI sidecar backend.
- **AI**: Local-first — `qwen3.5:4b` via Ollama by default, fully resident in the 4GB GPU (Offline mode: no cloud calls, no accounts, no telemetry), upgraded with local retrieval (RAG) over your own library and mechanically-verified continuity checking. Optionally, GroqCloud's free tier adds extra power via Online or Hybrid mode, with automatic fallback to local when offline or rate-limited — see [08-AI-PROVIDER-MODES.md](docs/08-AI-PROVIDER-MODES.md) and [11-AI-INTELLIGENCE.md](docs/11-AI-INTELLIGENCE.md).
- **Voice**: push-to-talk dictation into any field (local speech-to-text on CPU; Groq Whisper in Online mode) and read-aloud proofreading with word-by-word highlighting — see [12-VOICE-AND-SPEECH.md](docs/12-VOICE-AND-SPEECH.md).
- **Design**: dyslexia-first and evidence-based (font self-test onboarding, BDA spacing defaults, reading ruler, warm cream/dark themes) with a playful layer that never touches the manuscript text — see [10-DESIGN-SYSTEM.md](docs/10-DESIGN-SYSTEM.md).
- **Storage**: One shared local SQLite "Story Library" (all books/scenes/characters), plus one-click encrypted portable backups per book. AI providers never store or see this library — they only ever process one request's worth of text at a time.
- **Releases**: v1.0 = core (Phases 0–9), v1.1 = semantic search + full mascot + voice extras (Phases 10–11), v2.0 = backlog — see the MoSCoW map in [06-ROADMAP.md](docs/06-ROADMAP.md).
- **Status**: Specification complete (12 docs), Phase 0 (foundations & 8 de-risking spikes) next.

See [06-ROADMAP.md](docs/06-ROADMAP.md) for what "next" means concretely, and [07-RISKS-AND-OPEN-QUESTIONS.md](docs/07-RISKS-AND-OPEN-QUESTIONS.md) for the handful of technical unknowns Phase 0 exists to resolve before the rest of the roadmap is trusted.
