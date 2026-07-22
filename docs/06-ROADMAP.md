# Roadmap

Each phase ends in an independently demoable milestone — nothing ships as "trust me, it's wired up," everything has a concrete thing to look at or click.

The roadmap is organized agile-style into **release trains**: **v1.0** (Phases 0–9) is the core product — everything needed to trust Quillnight with real creative work daily. **v1.1** (Phases 10–11) is the first improvement iteration — the semantic/AI power features and the full delight package. **v2.0** (Phase 12) is the ideas backlog. Build order inside each phase is Must-first.

## Release trains & MoSCoW priority map

| Priority | Feature | Train / Phase |
|---|---|---|
| **Must** | Everything in Phases 0–9 below: Library/Books, Node Canvas + Enhance, Codex, Outline/Timeline + continuity checks (deterministic SQL + guarded LLM), Images, Final Draft + all export formats, `.quillproj` backup/import, AI provider modes, security | v1.0 |
| **Must** | Model switch to `qwen3.5:4b` default (+ `gemma4:e4b` alternate) + prefix-cache prompt discipline ([11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md)) | v1.0 / Ph 0–2 |
| **Must** | Design-system foundations: Day/Night themes, font system + self-test, BDA spacing defaults, Reading Comfort Wizard, reading ruler, TTS karaoke proofreading ([10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md)) | v1.0 / Ph 1, 8 |
| **Must** | Dictation MVP: push-to-talk into any text field, local Parakeet + Groq online ([12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md)) | v1.0 / Ph 2 |
| **Must** | Delight base: Motion + View Transitions, confetti moments, UI sounds, NumberFlow word ticker, ambient firefly, Delight-level setting (Playful default) | v1.0 / Ph 2, 8 |
| **Must** | Streaks + daily word goal + inkwell ring (`writing_sessions`) | v1.0 / Ph 8 |
| **Should** | Semantic layer: sqlite-vec + FTS5 + RRF hybrid search, GraphRAG-lite context assembly, auto codex-link suggestions, similar-scene detection | v1.1 / Ph 10 |
| **Should** | Full Rive firefly mascot (ambient firefly ships in v1.0; the state-machine companion is v1.1) | v1.1 / Ph 11 |
| **Should** | 3-vote self-consistency on continuity checks (single-pass + quote guardrail ships in v1.0) | v1.1 / Ph 11 |
| **Should** | Piper TTS quality voice (GPL-isolated sidecar); Web Speech karaoke ships in v1.0 | v1.1 / Ph 11 |
| **Should** | Phonetic spellcheck (Hunspell PHONE/SymSpell) + LanguageTool verifier loop + personal dictionary | v1.1 / Ph 11 |
| **Should** | Brain-dump mode (long ramble → multiple draft nodes, reviewed) | v1.1 / Ph 11 |
| **Should** | Achievements/badges | v1.1 / Ph 11 |
| **Could** | Style anchors (few-shot from your accepted texts so Enhance keeps your voice); writer's-room multi-persona brainstorm; reranker (only if v1.1 retrieval disappoints); propagation-debt review lists ("this codex change may affect these N scenes"); word prediction with phonetic support; CLIP image search | v2.0 / Ph 12 |
| **Won't** (recorded rejections) | Bionic Reading; unaided self-refine loops; thinking-mode+JSON in one call; heavyweight GraphRAG frameworks — see [10](10-DESIGN-SYSTEM.md)/[11](11-AI-INTELLIGENCE.md) for the evidence | — |

---

# v1.0 — Core (Phases 0–9)

## Phase 0 — Foundations & de-risking spikes

Repo skeleton; Tauri + React + Tailwind + shadcn init; FastAPI + SQLAlchemy + Alembic wired to an app-data SQLite file.

Eight spikes, each producing a checkable artifact in [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md):
1. PyInstaller-built FastAPI sidecar spawned/monitored/killed by Tauri (explicit-shutdown pattern, not `process.kill()`).
2. Bundled Ollama process: spawn + health-check + model pull + a real generate call on the actual target hardware.
3. WeasyPrint-on-Windows PDF render via the packaged sidecar (GTK DLL bundling pass/fail).
4. `pyrage` encrypt/decrypt round-trip + `screenplay-tools` Fountain round-trip.
5. **Groq/LiteLLM connectivity spike** (see [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md)): one code path against local and `groq/<model>`; forced-failure triggers Router fallback to local; Groq API key round-trips through the `keyring` crate without touching disk; Zero Data Retention flag confirmed on requests.
6. **Model bake-off + cache measurement** ([11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md)): `qwen3.5:4b` vs `gemma4:e4b` vs `mistral:7b-instruct` — measured tok/s each, plus a 10-sentence grammar-correction quality eval scored by hand; verify the chosen tags exist on Ollama's library; measure prefix-cache TTFT (cold vs byte-identical-prefix warm) to confirm the CAG win is real on this machine.
7. **Dictation spike** ([12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md)): Parakeet via `onnx-asr` transcribes a 30s clip real-time-or-better on this CPU; survives PyInstaller packaging; `sounddevice` capture works from the packaged sidecar. Fallback documented: whisper.cpp Vulkan.
8. **Semantic-layer smoke test** ([11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md)): sqlite-vec Windows wheel loads into the app DB; `qwen3-embedding:0.6b` runs CPU-pinned (`num_gpu: 0`) without evicting the chat model; one hybrid FTS5+vector+RRF query returns sane results. (Feature ships in v1.1 — the spike just proves the stack now, while changing course is cheap.)

**Demo**: blank dual-themed window; sidecar `/health` OK; streamed tokens visible; sample encrypted blob + PDF; Groq call + forced-fallback both logged with correct `provider`; a table of measured numbers (tok/s ×3 models, cache TTFT delta, STT real-time factor) checked into doc 07.

## Phase 1 — Story Library & Book CRUD

`books`/`scenes`/`book_scene_links` schema + first Alembic migration; Library screen (create/rename/delete/convert-type Books); empty 3-tab Book shell; Zustand + TanStack Query wiring. **Design-system foundations land here**: Day/Night theme tokens, font system (Lexend default, full picker), BDA spacing defaults with live sliders, and the **Reading Comfort Wizard** as the first-run experience (font self-test, spacing, theme, delight level — [10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md) §7).

**Demo**: create Books of each type, convert Single Scene → Story Book; run the wizard end-to-end and watch every choice apply live; toggle Day/Night.

## Phase 2 — Node Canvas tab

xyflow custom nodes (Scene/PlotPoint/Thought + structured screenplay-element node for script types) with mandatory title, optional description, Enhance button wired to a real streaming LLM call with Accept/Reject span diff, image slot, connectors persisted to `scene_connections`; Characters panel MVP + `codex_scene_links`; debounce/cancel + keep-warm plumbing (auto-suggest off by default, always local); cross-Book scene move/copy. Settings gains the AI Mode picker + Groq key entry with provider indicator. **New in this phase**: prompt-prefix cache discipline in `prompt_builder.py` from day one ([11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §5); **dictation MVP** (push-to-talk into any field, Parakeet local / Groq online, `voice_notes` storage); **delight base** — Motion layout animations, View Transitions on tab switches, canvas "ink flow" edges, confetti on first node, UI sounds (Playful), NumberFlow ticker, ambient firefly on the Night canvas.

**Demo**: build a graph with animated ink edges; dictate a thought into a node and Enhance it; streamed Enhance with Accept/Reject + provider tag; drag a scene into a second Book; Hybrid-mode network-unplug fallback; confetti fires once, delightfully.

## Phase 3 — Full Codex system

All 4 entity types, custom-fields JSON editor, `codex_relationships` cross-linking UI, `codex_arc_states` entry, single-image attach. Codex serialization is **deterministic** (stable ordering) so the prompt-cache prefix stays byte-identical between codex edits.

**Demo**: populated Codex with cross-links, linked from canvas nodes, visibly informing an Enhance call's context.

## Phase 4 — Outline/Timeline tab + Continuity Checker v2

`book_scene_order`, `chapters`, `structure_templates` (Three-Act, Hero's Journey seed data); beat-board UI (dnd-kit, color-coded structure lanes) and timeline UI as two views over one shared data model. **Continuity Checker v2** per [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §4: Tier-1 deterministic SQL checks (early appearance, timeline inversions — instant, never wrong) + Tier-2 LLM semantic pass with two-pass CoT→JSON and the **verbatim-quote guardrail** (string-match or the flag is dropped); severity-tagged flags rendered per severity.

**Demo**: arrange a Three-Act outline; toggle to Timeline and reorder; seed a "character speaks before being introduced" error and watch the SQL tier catch it instantly with zero LLM call; seed a trait contradiction and watch the LLM tier flag it *with the exact quote highlighted*; a fabricated-quote flag (simulated) gets auto-dropped.

## Phase 5 — Images system

Both buckets, `entity_images` polymorphic linking, upload/rename/tag/search, Enhance-able descriptions, export-scoping query finalized.

**Demo**: tagged/searchable reference pool; finalized-scene images attached to nodes; Book-scoped export preview shows only linked images.

## Phase 6 — Final Draft tab + export pipeline

Draft compiler (prose path via `description`, script path via `screenplay_elements`); front-matter editor; Markdown/DOCX/PDF via Jinja2/python-docx/WeasyPrint (ReportLab fallback); Fountain/FDX via `screenplay-tools`, gated to script types; `draft_versions` snapshots. Reading environment in this tab uses the full evidence-tuned defaults (65ch, spacing, cream) — the manuscript surface obeys the chrome-not-manuscript rule absolutely.

**Demo**: compile and export every applicable format for one Story Book and one Short Film Script; visually verify each file.

## Phase 7 — `.quillproj` export/import

Full gather → zip → pyrage-encrypt flow; decrypt → merge-by-UUID with review dialog; periodic local backup rotation. Embeddings excluded from bundles (derived data — regenerated after import, [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §2).

**Demo**: export a populated Book, delete it, re-import → full restore; re-import without deleting → zero duplication; rotated local backup exists and restores.

## Phase 8 — Design/accessibility deep pass + reading aids + streaks

Full Day/Night polish across every screen; WCAG AA contrast/keyboard audit; long-text soak test of dyslexia settings; **reading ruler** (Grey Bar + Shade, `R` toggle) and **focus mode**; **read-aloud karaoke** (Web Speech word-boundary highlighting, local voices, per [12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md) §2); **streaks + daily word goal + inkwell ring** with milestone confetti; delight-level matrix fully honored including `prefers-reduced-motion`.

**Demo**: live font/spacing changes on the Final Draft view; ruler follows the caret through a full chapter; read-aloud highlights word-by-word; a streak milestone celebrates; switching to Calm silences everything instantly.

## Phase 9 — Hardening & v1.0 release

MSI/NSIS installer bundling Tauri + sidecar + Ollama + fonts; first-run onboarding = disk-space/model-pull flow + Reading Comfort Wizard; `npm audit`/`pip-audit`/`cargo audit` clean pass (recurring, not one-time); backup-nudge UI; idle RAM/perf tuning of `keep_alive` defaults.

**Demo**: full end-to-end walkthrough from a clean install on the target machine. **This is v1.0 — daily-drivable.**

---

# v1.1 — First iteration (Phases 10–11)

## Phase 10 — Semantic layer

sqlite-vec vec0 tables + FTS5 index + embedding pipeline (CPU-pinned `qwen3-embedding:0.6b`, background embed-on-save, bulk backfill job); hybrid RRF search API + search UI ("find scenes where…"); GraphRAG-lite context assembly replacing the flat context builder; **auto codex-link suggestions** on node save; **similar-scene detection** surfaced when creating new nodes.

**Demo**: semantic search finds a scene by meaning, not keywords; typing a scene mentioning an existing character pops a one-click link suggestion; a near-duplicate thought surfaces its March twin.

## Phase 11 — Full delight + voice + verification iteration

**Rive firefly mascot** (idle/thinking/celebrating/sleeping, provider tag, draggable/hideable — asset produced in Rive editor, one month of the export tier, SVG+Motion fallback documented); **achievements/badges**; **Piper TTS** listen-through voice (GPL-isolated sidecar process); **phonetic spellcheck + LanguageTool** verifier loop + personal dictionary; **brain-dump mode** (ramble → reviewed draft nodes); **3-vote self-consistency** on continuity checks (budget confirmed by Phase 0 numbers).

**Demo**: the firefly scribbles during an Enhance and celebrates an Accept; a phonetic misspelling ("fizishan") gets the right suggestion; a 90-second ramble becomes four draft nodes awaiting review; a previously flaky continuity flag stops appearing (voted out 1-of-3).

---

# v2.0 — Backlog (Phase 12, unscheduled)

Style anchors (retrieval of your accepted prose as few-shot examples so Enhance preserves your voice) · writer's-room multi-persona brainstorm (3 alternative takes on a twist, different lenses) · CPU reranker over top-20 if retrieval quality warrants · propagation-debt review lists (codex arc change → "these N scenes may need review", the `autonovel` idea from doc 07) · word prediction with phonetic support · CLIP-based image search · community/theme packs for the delight layer.

---

## How to use this roadmap

- Don't start a phase until the previous phase's demo has actually been run and confirmed — the demo step is the only quality gate this solo project has.
- Phase 0's eight spikes gate everything after them: model default, PDF library, encryption library, STT engine, semantic stack, and expected latencies are all provisional until their spike passes. Update [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md) with **measured numbers**, not checkmarks.
- v1.0 must stay shippable: nothing from v1.1/v2.0 gets pulled forward unless a v1.0 phase finishes early AND the pulled item doesn't add a new unvalidated dependency.
- MoSCoW rows above are the arbiter when time pressure hits: Musts never get cut, Shoulds slip trains, Coulds wait indefinitely.
