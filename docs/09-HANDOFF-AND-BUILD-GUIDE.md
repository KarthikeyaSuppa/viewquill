# Handoff & Build Guide

## Purpose

This document exists so that **anyone or anything picking up this project cold** — a different Claude session with zero memory of how these docs were produced, another AI coding tool, or a human developer — can start building Quillnight correctly on day one, without re-deriving decisions that have already been made and without the original author having to re-explain any of it. If you are that fresh reader: start here, then follow the reading order below. Do not skip the "why" sentences in the other docs — they exist specifically so you can judge edge cases the docs don't literally spell out.

## Current project state (read this first, it will save you a mistake)

- **No code has been written yet.** This repository/folder currently contains only the 12 markdown files in `docs/` plus this `README.md`. If you find yourself about to run `npm create tauri-app` or `git init`, that's correct — that's the actual next step, not something someone else already did.
- **There is no git repository yet.** The very first implementation action should be `git init` in the project root, followed by a first commit of the docs themselves, so the project's history starts clean with the specification as commit #1.
- **All product and architecture decisions below were reached through extensive back-and-forth with the actual end user** (a single, personal, non-technical-by-trade user who is dyslexic and wants a trustworthy local tool). They are not arbitrary defaults — treat everything in `01` through `12` as **settled** unless [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md) explicitly lists it as open or unvalidated.

## Reading order

1. [README.md](../README.md) — orientation, doc index.
2. [01-PRODUCT-VISION.md](01-PRODUCT-VISION.md) — what you're building and why each piece exists. Read this fully before touching architecture; the "why" here explains constraints that aren't repeated elsewhere.
3. [02-ARCHITECTURE.md](02-ARCHITECTURE.md) — tech stack, module breakdown, folder structure.
4. [03-DATA-MODEL.md](03-DATA-MODEL.md) — the schema. Treat this as the first Alembic migration's target, not a suggestion.
5. [04-LLM-INTEGRATION.md](04-LLM-INTEGRATION.md), [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md), and [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) — read these three together: `04` is the plumbing, `08` adds cloud/provider modes, `11` adds the intelligence layer (model choice, retrieval, caching, reasoning patterns, guardrails). `11` supersedes `04` wherever they touch the same topic.
6. [10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md) — themes, typography, reading aids, the delight stack, the mascot, and the chrome-not-manuscript rule. Read before building any UI surface.
7. [12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md) — dictation (STT) and read-aloud (TTS), both directions.
8. [05-EXPORT-IMPORT-SECURITY.md](05-EXPORT-IMPORT-SECURITY.md) — storage/backup/encryption model.
9. [06-ROADMAP.md](06-ROADMAP.md) — release trains (v1.0/v1.1/v2.0), MoSCoW priorities, phase-by-phase build order and demo criteria. This is your actual task list.
10. [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md) — check this **before** making any decision that feels underspecified; it's a living document, keep it that way.

## Non-negotiable cross-cutting principles

These apply everywhere, across every phase, even in places the docs don't call them out explicitly. If a new feature or edge case isn't covered by the specific docs, fall back to these:

1. **Never silently overwrite user text.** Every AI action (Enhance, continuity-check, book-type conversion) is a proposal shown as a diff with Accept/Reject/Edit-further. If you're implementing a new AI-touching feature and you find yourself writing code that applies a model's output directly to the database without a review step, stop — that's a violation of the app's core trust contract.
2. **Never lose data as a side effect.** Conversions are additive, not destructive (a scene's prose and its generated screenplay elements coexist). Deletions are user-initiated and explicit, never a cleanup side effect of some other action.
3. **Local-first, cloud-optional.** The SQLite Story Library is always the sole source of truth. Cloud (Groq) is a stateless text-in/text-out helper, never a place any persistent data lives, regardless of which AI Mode is active.
4. **Official registries only, pinned versions.** npm, PyPI, crates.io, and Ollama's own model library — nothing else, ever, especially not for anything touching cryptography or credentials.
5. **Every phase ends in something you can actually look at or click**, per [06-ROADMAP.md](06-ROADMAP.md). Don't start the next phase until the current one's demo criterion has actually been exercised, not just "the code compiles."
6. **Playfulness lives in the chrome, never inside the manuscript.** The user's actual text always renders in the calm, evidence-tuned reading environment ([10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md)); mascots/confetti/sounds happen around it. Every delight element respects `prefers-reduced-motion` and is individually toggleable.
7. **Prompt order is [static system] → [deterministic codex block] → [variable text] → [task], with nothing volatile early.** This is the prefix-cache (local CAG) discipline in [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §5 — break it in one place and every repeat call pays full prompt-processing cost again.
8. **GPL stays at the process boundary.** Piper TTS (`piper1-gpl`, GPL-3.0) runs as a separate standalone process only — never imported, linked, or bundled into Quillnight's own executables ([12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md) §2).
9. **Model names are settings, not constants.** The local default (`qwen3.5:4b`), grammar alternate, embedding model, and Groq model all live in `app_settings` — the landscape churns too fast for hardcoding (this project has already retired one hardcoded-in-spirit default).

## Phase 0 kickoff checklist (concrete first commands)

This is deliberately concrete — these are close to the actual commands, not just a description of what to do. Adjust exact versions/flags as current tool releases require, but the sequence and structure should match [02-ARCHITECTURE.md](02-ARCHITECTURE.md)'s folder layout.

```powershell
# 1. Repo root and version control
mkdir quillnight; cd quillnight   # if not already created
git init

# 2. Tauri + React + shadcn frontend
npm create tauri-app@latest apps/desktop -- --template react-ts
cd apps/desktop
npx shadcn@latest init
npx shadcn@latest add button dialog dropdown-menu tabs   # add more components as each phase needs them
npm install @xyflow/react zustand @tanstack/react-query
npm install motion @formkit/auto-animate canvas-confetti @number-flow/react use-sound @dnd-kit/core @dnd-kit/sortable
npm install @fontsource/lexend @fontsource-variable/atkinson-hyperlegible-next @fontsource/opendyslexic @fontsource/inter
cd ../..

# 3. Python/FastAPI sidecar
cd apps/sidecar
# use uv or poetry per your preference — either is fine, just pin the lockfile
uv init
uv add fastapi "uvicorn[standard]" sqlalchemy alembic pydantic litellm
uv add sounddevice "onnx-asr[cpu,hub]" silero-vad     # dictation (12-VOICE-AND-SPEECH.md); sqlite-vec arrives with Phase 10
alembic init db
cd ../..

# 4. Type sync tooling
npm install -D openapi-typescript --workspace apps/desktop   # adjust if not using workspaces

# 5. Ollama (Phase 0 spike #2)
# Download the official Windows release from https://github.com/ollama/ollama/releases
# into apps/desktop/src-tauri/resources/ollama/ per the folder structure in 02-ARCHITECTURE.md

# 6. First commit
git add README.md docs/ apps/
git commit -m "Initial scaffolding: Tauri+React+shadcn frontend, FastAPI+SQLAlchemy+Alembic sidecar"
```

Then work through [06-ROADMAP.md](06-ROADMAP.md) Phase 0's **eight spikes** in order, checking each off in [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md) with the **actual measured result**, not just a checkmark.

## Where to look for X (quick lookup)

| If you're wondering about... | Go to |
|---|---|
| What a feature is supposed to do or why it exists | [01-PRODUCT-VISION.md](01-PRODUCT-VISION.md) |
| Which library/framework to use for something | [02-ARCHITECTURE.md](02-ARCHITECTURE.md) |
| A table, column, or relationship | [03-DATA-MODEL.md](03-DATA-MODEL.md) |
| How an Enhance/continuity-check call is built, or debounce/cancel behavior | [04-LLM-INTEGRATION.md](04-LLM-INTEGRATION.md) |
| Which local model, retrieval/RAG, prompt caching, reasoning patterns, hallucination guardrails | [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) |
| Anything involving Groq, online/offline/hybrid mode, or API keys | [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md) |
| Themes, fonts, spacing, reading aids, animation packages, the mascot, sounds, gamification | [10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md) |
| Dictation, read-aloud, audio capture, Piper/Parakeet | [12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md) |
| Backup, `.quillproj` bundles, encryption, or export formats | [05-EXPORT-IMPORT-SECURITY.md](05-EXPORT-IMPORT-SECURITY.md) |
| "What should I build next / is this phase done?" or "is this v1.0 or later?" | [06-ROADMAP.md](06-ROADMAP.md) — MoSCoW map + release trains |
| "Is this already decided, or still open?" | [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md) — check here **before** assuming something is undecided |

## How to keep these docs alive while building

The docs are a living specification, not a one-time artifact you build against and then ignore:

- When a Phase 0 spike (or any later phase) produces a real measurement (tok/s, whether Ollama actually cancels on disconnect, whether WeasyPrint's DLL bundling worked), **update [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md) with the actual result**, not just a checkmark. The next person (or your own future context) needs the number, not just "tested, works."
- If you hit a genuinely new decision point not covered by any doc, don't silently pick something and move on — add it to [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md) under a new "Open questions" entry with your reasoning, the same way prior decisions in that doc are recorded with their rationale. If the decision is reversible and low-stakes, make your best call and record it; if it's irreversible or changes something the user explicitly specified (any of the principles above, or anything in `01-PRODUCT-VISION.md`), stop and ask rather than guessing.
- If new external research changes something (e.g. Groq's model lineup shifts again, a new version of a chosen library breaks something), update the relevant doc directly rather than leaving it stale — these docs should always reflect current reality, not a frozen snapshot of when they were written.

## What NOT to do

- Don't re-litigate settled decisions (tech stack, node editor library, encryption approach, workspace model, provider modes) without a concrete new fact that invalidates the original reasoning — each decision in these docs has a "why," documented specifically so it doesn't get casually second-guessed later.
- Don't build ahead of the roadmap's phase order "because it's easy to do now" — the phases are ordered so each is independently demoable and so risk gets retired early (Phase 0's spikes exist specifically to de-risk the riskiest unknowns before anything depends on them).
- Don't skip the demo/verification step at the end of a phase, even when working solo with no other reviewer — for this project, that step is the only quality gate that exists.
