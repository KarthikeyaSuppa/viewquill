# LLM Integration

> **This document covers the local (Ollama) plumbing in depth.** Two sibling docs extend it: [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md) adds the optional cloud backend (GroqCloud) and Offline/Online/Hybrid provider selection; [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) adds the *intelligence* layer on top of this plumbing — retrieval (RAG/GraphRAG-lite), prefix caching, two-pass reasoning, and hallucination guardrails. Everything below applies identically regardless of which provider serves a call, because the provider abstraction (LiteLLM, wrapped in `llm_orchestrator.py`) normalizes both backends to the same request/response shape.

## Model & runtime

- **Local model (default)**: **`qwen3.5:4b`** — at ~3.4GB quantized it fits the RTX 3050's 4GB VRAM *entirely*, making it both faster and more consistent than a larger partially-offloaded model, with best-in-class instruction-following and JSON-schema adherence for its size. Optional alternates: **`gemma4:e4b`** (grammar specialist — the Gemma line tops ≤9B grammar-correction studies) and `qwen3.5:9b` (slower "quality" toggle). Full selection rationale, the Phase 0 bake-off that validates it, and the model-churn caveat live in [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §1. All model names are runtime settings (`app_settings.local_model_name`), never hardcoded.
  - *Historical note*: the original early-2026 plan chose Mistral-7B-Instruct for quality-over-speed; the mid-2026 4B class made that tradeoff obsolete — current small models beat it on both axes at lower memory cost.
- **Local runtime**: Ollama, bundled from the **official Ollama Windows release** (GitHub releases — satisfies the "official registries only" constraint), run as a Tauri sidecar process, not a system-wide install.
- **Embedding model** (v1.1 semantic layer): `qwen3-embedding:0.6b`, pinned to CPU so it never competes with the chat model for VRAM — see [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §2.
- **Cloud model (optional)**: GroqCloud free tier, for Online/Hybrid mode. Details, rate limits, and the fallback design are in [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md) — not duplicated here.
- **Auto-suggest is local-only in every mode**, regardless of the user's Offline/Online/Hybrid setting — see [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md) for why (Groq's free-tier quota is sized for on-demand actions, not continuous background traffic).

## Ollama bundling & lifecycle

> **Provisional, pending Phase 0 spike #2**: no known open-source Tauri app actually bundles/manages Ollama itself this way today (most just assume it's already running externally) — see [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md) for the fallback plan (require a separate Ollama install, or bundle llama.cpp directly instead) if this doesn't prove reliable.

1. Rust spawns `ollama.exe serve` with `OLLAMA_MODELS` pointed at the app-data directory on startup.
2. Health-check: poll `GET /` until it responds ("Ollama is running").
3. First run only: `POST /api/pull` for the target model, relaying Ollama's own progress fields (`total`/`completed`) to a UI progress bar — a multi-GB download (~3.4GB for the default `qwen3.5:4b`) the user is told about explicitly during onboarding, not left guessing why the app is idle.
4. **Keep-warm**: immediately after health-check passes, issue a warm-up generate call with a long `keep_alive` (e.g. `"30m"`), and run a periodic background ping (FastAPI background task) timed just under that window so the model never gets evicted mid-session. This is what makes flipping the auto-suggest toggle on later "cheap and responsive" instead of eating a multi-second cold-load penalty on the first request. Exposed as its own settings toggle ("keep AI model warm," default on) since it has a real RAM/VRAM residency cost.
5. Rust owns start/stop lifecycle for both Ollama and the Python sidecar; Python only ever talks to Ollama's HTTP API — the frontend never calls Ollama directly.

## Enhance call flow

1. Frontend sends `POST /llm/enhance` with `{entity_type, entity_id, field, text, book_id, mode}`, where `mode` ∈ `grammar | prose | continuity_flag`.
2. `prompt_builder.py`:
   - Resolves Codex entries linked to the entity (via `codex_scene_links`/`book_codex_links`), plus one relationship-hop out via `codex_relationships`, capped by a token budget. (In v1.1 this flat resolution is replaced by the relevance-ranked GraphRAG-lite assembly in [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §3 — same inputs, better selection.)
   - For each Codex entry, resolves its **point-in-time state** via `codex_arc_states` — the latest snapshot where `as_of_outline_order_index <= this scene's outline_order_index` for that book — so the model doesn't leak later plot facts into an earlier scene's suggestion.
   - Assembles a system prompt ("careful developmental editor, preserve author voice, never invent new plot facts, output only the revised text") + a compact context block of relevant Codex facts + the target text + a mode-specific instruction.
   - **Prompt order is a hard rule** (prefix caching, [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §5): [static system] → [deterministically-serialized codex block] → [variable scene text] → [task]. Nothing volatile (timestamps, UUIDs) before the variable section — one early differing token forfeits the KV-cache reuse that makes repeat calls fast.
3. `llm_orchestrator.py` calls the active provider through LiteLLM (`litellm.completion(model=..., stream=True, ...)` — either `ollama/<local_model_name>` (default `qwen3.5:4b`) or `groq/<configured-model>` depending on the Offline/Online/Hybrid setting resolved per [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md)). Temperature is tuned per mode: **0.3** for grammar/continuity (favor precision, minimal invention), **0.7** for prose enhancement (more latitude for phrasing). Token chunks are relayed to the frontend as they arrive (NDJSON → SSE), identically regardless of which provider is serving the request, since LiteLLM normalizes the chunk shape.
4. **The UI never silently overwrites.** Every Enhance result renders as a side-by-side diff with **Accept / Reject / Edit further**. Every call is recorded in `llm_request_log` (entity, mode, latency, whether accepted) — a lightweight trust/audit trail, valuable specifically because the author needs to be able to trust what the AI changed, not just that it changed something.

## Continuity checks (v2 — full design in [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §4)

- Runs at the Book level, triggered from the Outline/Timeline tab. Two tiers:
  - **Tier 1, deterministic SQL** (no LLM, instant, never hallucinates): **early appearance** (character referenced before their introduction point — a JOIN over `codex_scene_links` × `book_scene_order`) and **timeline conflicts** (outline-vs-chronology inversions not marked as intentional flashbacks). Persisted with `source='deterministic'`.
  - **Tier 2, LLM semantic pass** (trait contradictions and subtle inconsistencies): **two-pass** — free-prose reasoning first, then a cheap JSON-extraction call (JSON-constrained decoding degrades small-model *reasoning*, so reasoning and formatting are separated); the extraction schema puts `reasoning`/`evidence` fields first and `verdict` last.
- **Verbatim-quote guardrail**: every Tier-2 flag must carry a `quote` field that the sidecar string-matches against the actual scene text — no match, the flag is dropped before the user sees it. This is the mechanical filter against hallucinated flags.
- Uses **Ollama's `format` parameter set to a JSON Schema** on the extraction pass (never combined with thinking mode — that combination is broken upstream, see [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) §7) so results persist directly into `continuity_flags` rows.
- **Each result is severity-tagged** (`critical | warning | hint`, stored on `continuity_flags.severity`) rather than returned as a flat list — a pattern validated by prior-art research (see [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md)) — so the Outline/Timeline tab can render critical issues as blocking and hints as easily-dismissible.
- **v1.1 adds 3-vote self-consistency** on Tier 2 (run 3× at temp>0, keep flags appearing ≥2/3) — affordable because the shared prompt prefix is KV-cached.
- **Book-relative semantics**: the same scene reused in two Books can legitimately get different continuity flags depending on each Book's own outline order. The UI labels flags as scoped to "this scene's use in Book X" to avoid confusing results when a shared scene is checked from two different Books.

## Auto-suggest: debounce, cancel, and keep-warm (engineering detail)

Regardless of whether the settings toggle defaults to on or off, the mechanism is built the same way so switching it later is free:

- A `useAutoEnhance(entityId, text)` hook resets a **2.5-second debounce timer** on every keystroke; on fire (or immediately on tab-switch/node-blur), it first calls `abortControllerRef.current?.abort()`, then issues a fresh request.
- Uses `fetch(url, { signal: controller.signal })` reading `response.body` as a `ReadableStream` — **not** `EventSource`, which cannot carry a POST body or a client-driven abort cleanly.
- On the FastAPI side, the streaming endpoint checks `await request.is_disconnected()` between forwarded chunks; on disconnect, it closes its own `httpx.AsyncClient().stream(...)` context to Ollama, which drops the TCP connection Ollama is writing to.
- **This needs empirical verification, not just cosmetic frontend cancellation**: whether Ollama actually stops computing when its client connection closes, or keeps burning GPU/CPU cycles for a response nobody will read, determines whether "auto-cancel" is a real performance win or just a UI illusion. This is one of the Phase 0 spikes — see [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md).

## API surface (sidecar routers relevant to LLM features)

- `llm.py` — `/llm/enhance` (streaming), `/llm/continuity-check` (structured JSON result)
- `continuity.py` — CRUD over `continuity_flags` (dismiss/resolve flags manually)
- `settings.py` — read/write `app_settings` (auto-suggest toggle, keep-warm toggle, model name, and the `ai_mode`/`groq_model_name`/`groq_zdr_enabled` keys from [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md) — the Groq API key itself is never read/written here, only in the OS credential vault)
