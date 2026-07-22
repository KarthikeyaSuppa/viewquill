# AI Provider Modes: Offline / Online / Hybrid

## Why this exists

The local model (`qwen3.5:4b` by default — see [04-LLM-INTEGRATION.md](04-LLM-INTEGRATION.md) and [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md)) guarantees privacy and offline availability, but it's a 4B-class model on a 4GB-VRAM laptop — real quality ceilings apply for the heaviest reasoning tasks. **GroqCloud's free tier** offers access to meaningfully larger, faster-inference models (up to 120B-class) for on-demand, user-triggered actions, at no cost, using the user's own free API key. This doc adds a third axis to the app: the user chooses whether AI actions run **Offline** (local only), **Online** (cloud only), or **Hybrid** (cloud when available, seamless fallback to local otherwise) — without ever changing where the *data* lives. The Story Library (SQLite) is always local, always the source of truth, regardless of which mode generates the text that goes into it. Cloud, when used, is a stateless text-in/text-out helper — never a data store.

## The three modes

| Mode | Behavior | When to use |
|---|---|---|
| **Offline** | All AI calls go to local Ollama only. Zero network calls, ever. | Default. Sensitive/personal manuscripts, no internet, or simply "I don't want this leaving my machine." |
| **Online** | All AI calls go to GroqCloud using the user's own free API key. | Fast, high-quality passes when you have internet and don't mind cloud processing for that session. |
| **Hybrid** (recommended default once configured) | Prefer cloud for **user-triggered, heavier actions** (full Enhance pass, continuity check, draft/export generation) when online and within quota; **automatically fall back to local** the instant the cloud call fails, times out, or is rate-limited — no user action required, no lost work. | The "best of both" — most of the time you get Groq's extra power; when you're offline or hit a limit, you don't notice, you just get the local model instead. |

**One rule that applies in every mode, without exception**: background **auto-suggest** (the tab-switch/node-blur feature from [01-PRODUCT-VISION.md](01-PRODUCT-VISION.md)) always uses the **local model only**, regardless of the configured mode. Reasoning: Groq's free tier is generous for on-demand passes (see limits below) but not designed for continuous per-keystroke-adjacent traffic — burning the daily quota on background suggestions would starve the manual Enhance/continuity/draft actions that benefit far more from the larger cloud models. Auto-suggest is deliberately the "cheap and frequent" tier; manual actions are the "occasional and heavy" tier that gets the cloud upgrade.

## Architecture: provider abstraction via LiteLLM

- **Client library**: `litellm` (official PyPI package, `BerriAI/litellm`). Both Ollama and Groq already expose OpenAI-compatible `/v1/chat/completions` endpoints, so LiteLLM talks to both with **zero custom request/response mapping** — `litellm.completion(model="ollama/qwen3.5:4b", ...)` and `litellm.completion(model="groq/openai/gpt-oss-120b", ...)` return an identical `ModelResponse` shape, streaming or not.
- **Own interface on top**: LiteLLM is wrapped behind Quillnight's own `ProviderClient` interface inside `services/llm_orchestrator.py` (extending the module already described in [04-LLM-INTEGRATION.md](04-LLM-INTEGRATION.md)) — LiteLLM is never called directly from route handlers. This means if LiteLLM ever becomes a liability (it's a fast-moving, fairly large dependency — see open issue `BerriAI/litellm#19985` on fallback/retry interaction as an example of the kind of bug class to watch for), it can be swapped without touching call sites.
- **Fallback/circuit-breaker**: LiteLLM's `Router` supports exactly the hybrid behavior needed out of the box — a prioritized `fallbacks=[...]` list (`groq/...` → `ollama/<local model>`), `num_retries`, and `cooldown_time` after N failures in a window (a de facto circuit breaker, including rate-limit-aware cooldown). No need to layer a separate breaker library on top.
- **Architecture references** (prior art for this exact local+cloud shape, not for direct reuse): `askalf/hybrid` (minimal local-first router that escalates hard queries to a frontier endpoint) and `thushan/olla` (Go proxy with health-checked failover across local/cloud endpoints) — useful for validating the "connectivity mode" shape described here.
- **Streaming + cancellation stay provider-agnostic**: LiteLLM's `stream=True` yields identical chunks regardless of backend, so the SSE relay and the `fetch`+`AbortController`+`request.is_disconnected()` cancellation pattern from [04-LLM-INTEGRATION.md](04-LLM-INTEGRATION.md) needs no per-provider branching.

## Model selection on Groq

- Groq's free-tier lineup **changes over time** (it deprecated several models in a single wave in June 2026) — the model name must be a **configurable setting** (`app_settings`), never hardcoded, so a lineup change doesn't require a new release.
- Recommended default for the "online heavy-lift" tasks (Enhance full pass, continuity-check, draft generation): a large general model such as `openai/gpt-oss-120b` or `moonshotai/kimi-k2-instruct` — meaningfully stronger than the local 7B for reasoning-heavy continuity work.
- **Structured output caveat**: Groq's API currently makes `stream=True` and `response_format` (JSON-schema-constrained output) **mutually exclusive**, and strict JSON-schema compliance is only certified for the `gpt-oss` family — other models are "best-effort" and can still emit invalid JSON. Since the continuity-checker (see [04-LLM-INTEGRATION.md](04-LLM-INTEGRATION.md)) already uses non-streaming structured output, this isn't a conflict, but the JSON-parsing step must stay defensive (validate-and-retry) for any Groq model, not just assume Ollama-level reliability.

## Rate limits (free tier) and what they mean for this app

- Typical free-tier shape: ~30-60 requests/minute, several-thousand tokens/minute, and a per-day cap that varies a lot by model (as low as ~250/day for some, closer to ~1,000+/day for current mid-size models). Limits are enforced **per model**, not globally.
- **Implication**: comfortably enough for on-demand, once-per-action calls (Enhance a node, run a continuity check, compile a draft) even across a long writing session — not enough for continuous background polling. This is the concrete reason auto-suggest is local-only in every mode (see above), and why Hybrid mode's fallback needs to trigger cleanly on a 429 rather than the app breaking or silently queuing.
- Health-check design: a `429` response includes an `error.type` (`rate_limit_exceeded` or `tokens`) plus a `Retry-After` header — the Router should treat this as "cool down and route this call to local now," not "retry the same provider a few times first." A `5xx` or timeout gets a small retry budget before falling back. Either way, the fallback is transparent to the user except for a small provider indicator (see UX below).

## Speech-to-text follows the same modes

Dictation ([12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md)) is a provider-routed AI action exactly like text calls:

| Mode | Dictation engine |
|---|---|
| Offline | **Parakeet-TDT 0.6B** locally on CPU — always available, zero network |
| Online | **Groq `whisper-large-v3-turbo`** (user's same API key; free tier ~2,000 requests/day, 7,200 audio-seconds/hour, 25MB/file) |
| Hybrid | Groq preferred, instant local fallback on failure/429 — identical semantics to text |

- The privacy disclosure below covers audio too: in Online/Hybrid mode, **your voice recording is uploaded to Groq** for transcription. The consent copy must say so explicitly, and Offline mode guarantees audio never leaves the machine.
- `llm_request_log`'s `provider` field and the provider indicator apply to transcriptions as well (`request_type='stt'`).
- Read-aloud (TTS) is **always local** (Web Speech / Piper) — there is no cloud TTS mode; nothing to route.

## Privacy & consent

- Per Groq's documentation: prompts/outputs are **not used for model training**, and a **Zero Data Retention (ZDR)** toggle is available on all tiers, including free — Quillnight should request ZDR by default in its Groq client configuration.
- Absent ZDR, brief abuse/troubleshooting logs may be retained (~30 days) — a policy commitment, not a technical guarantee.
- **Required UX**: the first time a user switches away from Offline mode, show a one-time, explicit disclosure: *"Online and Hybrid mode send the text you choose to enhance to GroqCloud, a third-party service. Groq states it doesn't train on this data. If you're working on something you don't want leaving this machine, stay in Offline mode."* This is not a one-time checkbox buried in Settings — it should be as clear as the Accept/Reject pattern used for every other AI action in this app.

## Secure API key storage (Windows)

- The user supplies **their own free Groq API key** — never bundled or shared by the app.
- **Do not** use Tauri's built-in `Store` plugin for this — it persists plain, unencrypted JSON on disk (confirmed in `tauri-apps/tauri` discussion #7846). That would put a live API credential in a readable file, contradicting the app's whole "secure against local access" posture.
- **Correct pattern**: the Rust shell stores the key in the **Windows Credential Manager** (DPAPI-encrypted) via the official `keyring` crate (crates.io). Only Rust ever touches the OS credential vault. The key is passed to the Python sidecar **in-memory, per session**, and is never written to the sidecar's own config or disk. If a future need arises for the Python side to independently manage a secret, the official `keyring` PyPI package (same Windows Credential Locker backend) is the equivalent, but the default design keeps vault access Rust-only to minimize the number of places that touch the credential.
- This is a **stricter rule than the live-database encryption tradeoff** in [05-EXPORT-IMPORT-SECURITY.md](05-EXPORT-IMPORT-SECURITY.md) (which deliberately leaves story text unencrypted for performance) — a third-party API credential is a different risk class than the user's own story text, and gets the stronger protection unconditionally.

## Settings & UX

- **Settings → AI Mode**: Offline / Online / Hybrid, plus (when Online/Hybrid is selected) a Groq API key field and a model picker for the "heavy-lift" tasks, defaulting to the recommendation above.
- **The API key field is fully editable at any time, not set-once**: add a key, replace it with a different one, or remove it entirely, all from the same Settings screen — switching Groq accounts or rotating a key never requires reinstalling or editing a config file by hand.
- **Masked by default with a show/hide toggle**: rendered as a standard password-style input (`type="password"`) with an eye-icon toggle to reveal it temporarily — the common pattern used by BYOK (bring-your-own-key) settings screens generally (e.g. VS Code's BYOK model picker stores the key in the OS credential manager behind exactly this kind of masked field).
- **"Test connection" button**: fires one cheap, minimal Groq call immediately after entering/changing a key and reports success/failure inline, so a typo or expired key is caught in Settings, not discovered later mid-Enhance.
- Under the hood, saving a new/changed key always goes through the same `keyring`-backed Rust-only vault write described above — the Settings UI never reads or displays the key from anywhere except that vault, and clearing the field removes it from the vault, not just from `app_settings`.
- **Provider indicator**: every Enhance/continuity/draft/transcription result subtly indicates which provider actually served it (e.g. a small "via Groq" / "via local model" tag next to the Accept/Reject diff — and beneath the mascot while it's in its thinking state, per [10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md) §6) — since Hybrid mode can fall back silently, the user should still always be able to see what happened, consistent with the app's broader trust/transparency principle (never hide what the AI did).

## Data model addendum (extends [03-DATA-MODEL.md](03-DATA-MODEL.md))

- `llm_request_log` gains a `provider` column (`'ollama' | 'groq'`) alongside its existing `model_name`, so the audit trail records not just *that* a call happened but *which* backend served it — needed for the provider indicator above and for diagnosing fallback behavior later.
- `app_settings` gains keys for `ai_mode` (`offline|online|hybrid`), `groq_model_name`, and `groq_zdr_enabled` — all plain settings, no secrets. The Groq API key itself is **never** stored in `app_settings`/SQLite — it lives only in the OS credential vault as described above.

## Roadmap & risk impact

- Adds a **Phase 0 spike #5** (see [06-ROADMAP.md](06-ROADMAP.md)): a Groq connectivity + LiteLLM fallback smoke test — real latency/quality comparison against the local model, confirming ZDR actually applies, and confirming the `keyring`-backed storage works end-to-end.
- Adds new risk items to [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md): Groq model-lineup churn, free-tier quota exhaustion during a heavy session, and LiteLLM as a fast-moving dependency to pin carefully.

## Settings-UI prior art

No open-source Tauri app was found with a fully polished BYOK settings screen, but the pattern above is validated by cross-stack reference implementations worth looking at directly during Phase 2 implementation: **`Mintplex-Labs/anything-llm`**'s `frontend/src/components/LLMSelection/` (a provider dropdown with a dedicated options component per provider — the cleanest real-world model for "provider switcher + per-provider settings panel"), **`chatboxai/chatbox`** (one settings screen: pick a provider, enter base URL + API key, stored locally only), and VS Code's own BYOK feature ([Oct 2025](https://code.visualstudio.com/blogs/2025/10/22/bring-your-own-key), [Jun 2026](https://code.visualstudio.com/blogs/2026/06/18/byok-vscode)), which documents the general contract (key goes to the OS credential manager, never plaintext) that this project's `keyring`-based design already follows.

## Sources consulted

- Groq docs: [rate limits](https://console.groq.com/docs/rate-limits), [models](https://console.groq.com/docs/models), [structured outputs](https://console.groq.com/docs/structured-outputs), [OpenAI compatibility](https://console.groq.com/docs/openai), [data usage](https://console.groq.com/docs/your-data), [errors](https://console.groq.com/docs/errors), [deprecations](https://console.groq.com/docs/deprecations)
- [Official Groq Python SDK](https://github.com/groq/groq-python) / [PyPI](https://pypi.org/project/groq/)
- [groqstatus.com](https://groqstatus.com/) (live status), third-party trackers: [Helicone](https://www.helicone.ai/status/provider/Groq), [StatusGator](https://statusgator.com/services/groq-cloud)
- Secure storage: [`keyring` crate](https://crates.io/crates/keyring), [`keyring-rs`](https://github.com/open-source-cooperative/keyring-rs), [`tauri-plugin-keyring`](https://github.com/HuakunShen/tauri-plugin-keyring), [Tauri Store plugin encryption discussion #7846](https://github.com/orgs/tauri-apps/discussions/7846), [`keyring` PyPI](https://pypi.org/project/keyring/)
- Provider abstraction: [LiteLLM](https://github.com/BerriAI/litellm) ([providers](https://docs.litellm.ai/docs/providers), [routing](https://docs.litellm.ai/docs/routing), [reliable completions](https://docs.litellm.ai/docs/completion/reliable_completions), [open issue #19985](https://github.com/BerriAI/litellm/issues/19985)), [aisuite](https://github.com/andrewyng/aisuite) (lighter alternative considered)
- Hybrid local/cloud router prior art: [`askalf/hybrid`](https://github.com/askalf/hybrid), [`thushan/olla`](https://github.com/thushan/olla), [`kcolemangt/llm-router`](https://github.com/kcolemangt/llm-router)
- Streaming/cancellation: [Ollama streaming docs](https://docs.ollama.com/api/streaming), [aborting requests](https://deepwiki.com/ollama/ollama-js/5.5-aborting-requests)
