# HANDOFF-ASUS-TUF.md — What's left, for the target-machine Claude Code session

> **Read this file first, in a fresh Claude Code session, before touching anything.**
> This machine (ASUS TUF F15, i5-11400H, RTX 3050 4GB, 16GB RAM) is where every
> model-dependent, Rust/Tauri-dependent, and hardware-dependent piece of Quillnight
> gets built and verified — none of it was possible on the corporate build laptop
> that produced everything up through Phase 9. This doc is the punch list: what's
> left, why it's left, where it lives, and in what order to do it. It does **not**
> replace `docs/` or `PROJECT-MAP.md` — read those too (index below) — it's the
> bridge document specific to *this* handover.

## 0. How to use this doc, and how to set up your team

Introduce yourself to this session as the **senior software developer /
orchestrator**, then bring in role-scoped teammates the same way `CLAUDE.md`
already defines subagents (`.claude/agents/*.md`: `architect`/`builder`/
`debugger`/`reviewer`, opus/sonnet-routed). Map your new team roles onto that
existing convention plus the domain split below — don't invent a parallel
process, extend the one already in place:

| Your team role | Maps to | Owns (by file area) | Model |
|---|---|---|---|
| **Backend engineer** | `builder` (scoped to backend tasks) | `apps/sidecar/app/**`, Alembic migrations, `pyproject.toml`/`requirements.lock.txt` | sonnet |
| **Frontend engineer** | `builder` (scoped to frontend tasks) | `apps/desktop/src/**`, `packages/api-types/` | sonnet |
| **Database/schema owner** | `architect` for schema decisions, `builder` for migrations | `apps/sidecar/app/models/orm.py`, `db/migrations/versions/`, `docs/03-DATA-MODEL.md` | opus for design, sonnet for the migration itself |
| **UI/UX reviewer** | a `reviewer`-style pass, but for design/accessibility not security | `docs/10-DESIGN-SYSTEM.md` compliance, WCAG/keyboard audits (Phase 8's pattern), delight-matrix bypass checks | opus, high effort |
| **Security/data-integrity reviewer** | `reviewer` (as already defined) | encryption, keyring, export/import merge, generated documents, Tauri↔sidecar boundary | opus, high effort |
| **You (orchestrator)** | `architect` + main-session judgment calls | phase planning, task breakdown, deciding what's next, reading subagent output | opus, high effort |

Per-phase workflow stays exactly what `CLAUDE.md` already specifies: architect
plans → builder implements one 1-3-file task at a time → reviewer gates
anything security/data-sensitive → debugger fixes failures → you run the
phase's demo yourself before moving on. Nothing about that process changes
here — only the environment does.

## 1. Why this handover exists (read once, don't re-litigate)

The build laptop this project was developed on through Phase 9 has, by
deliberate corporate-device policy: **no Rust/cargo, no Tauri shell, no
Ollama, and an explicit standing rule to never download or run real LLM
models there.** Every phase up to now was built and tested with that
constraint honored — model-dependent code was written stub-verified
(`QUILLNIGHT_LLM_STUB=1 QUILLNIGHT_STT_STUB=1`) and real verification was
always deferred to this machine. That's not a shortcut being cleaned up now
— it's the plan working as designed. See `docs/06-ROADMAP.md`'s "How to use
this roadmap" and `CLAUDE.md`'s "Environment constraints" section for the
original framing.

## 2. Get oriented first (in this order)

1. `PROJECT-MAP.md` (repo root) — the full codebase map, auto-loaded via
   `CLAUDE.md`'s `@PROJECT-MAP.md` import. Read this before exploring
   anything file-by-file.
2. `API-REFERENCE.md` (repo root) — every user option/endpoint, user-facing
   vs developer detail, implemented vs planned.
3. `CLAUDE.md` (repo root) — the subagent/model-routing workflow (§0 above
   extends it, doesn't replace it).
4. `PHASE7.md` / `PHASE8.md` / `PHASE9.md` (repo root) — the three most
   recent phase directives, kept as historical record of what actually
   shipped and why, including deviations from the original spec docs.
5. `docs/06-ROADMAP.md` — the authoritative phase-by-phase plan; `docs/07-
   RISKS-AND-OPEN-QUESTIONS.md` — **read this in full before Phase 0
   verification below**, it lists every unresolved risk item with a specific
   `Action:` line, most of them gated on exactly this machine.
6. `git log --oneline` — recent commits map 1:1 to phases; `git status` —
   confirm the working tree is clean before starting (Phase 9's work should
   already be committed and pushed to `origin/master` by the time you read
   this on this machine — if not, that's the very first thing to resolve,
   see §8).

## 3. What's already done (v1.0 core, Phases 0–9)

Phases 0–9 are functionally complete per `PROJECT-MAP.md`'s build-status
table, **except** the parts that structurally require this machine (listed
in §4 immediately below — these aren't separate phases, they're the
undone slice of phases already "done" everywhere else). Don't re-plan or
re-litigate anything already decided in Phases 0-9 — `docs/09-HANDOFF-AND-
BUILD-GUIDE.md`'s "What NOT to do" applies here specifically.

## 4. What's left — in the order to actually do it

### 4a. First: re-run the Phase 0 spikes for real (do this before anything else)

Every one of these was deferred, not skipped — `docs/07-RISKS-AND-OPEN-
QUESTIONS.md` §"Unresolved — gated by Phase 0 spikes" has the full list with
specific `Action:` lines. The ones that need **real hardware/model
measurement** (as opposed to the ones already resolved by a documented
fallback decision — WeasyPrint→ReportLab, pyrage→cryptography, both already
shipped and don't need redoing):

| Spike | What to actually do | Why it's gated here | Source |
|---|---|---|---|
| Model bake-off | Install Ollama, pull `qwen3.5:4b` + `gemma4:e4b` + `mistral:7b-instruct` (verify exact current tags on Ollama's library first — they may have moved since July 2026), measure tok/s each + hand-score a 10-sentence grammar-correction eval + measure prefix-cache cold-vs-warm TTFT delta | Needs the actual RTX 3050 4GB + 16GB@2400MHz RAM this machine has; no number has ever been measured | `docs/06-ROADMAP.md` Phase 0 spike #6, `docs/11-AI-INTELLIGENCE.md` §1 |
| Ollama bundling | Test whether Rust-managed `ollama.exe serve` spawn/health-check/kill is reliable as a Tauri sidecar | No Rust/Tauri/Ollama existed on the build laptop at all | `docs/06-ROADMAP.md` Phase 0 spike #2, `docs/07-RISKS-AND-OPEN-QUESTIONS.md` (the "no known project bundles Ollama as a Tauri sidecar" finding — fallback is prompt-user-to-install-Ollama-themselves, or bundle llama.cpp directly if this proves fragile) |
| PyInstaller sidecar packaging | Verify the explicit-shutdown pattern (not `process.kill()`) actually prevents orphaned processes; build the `.spec` file incrementally, testing each dependency | Needs PyInstaller + Rust, neither installed on the build laptop | `docs/07-RISKS-AND-OPEN-QUESTIONS.md` items #1-2 (`dieharders/example-tauri-python-server-sidecar` etc. are the cited real-world gotchas) |
| Dictation (STT) spike | Install `onnx-asr[cpu,hub]` + `sounddevice` + `silero-vad`, verify Parakeet transcribes real-time-or-better on this CPU, survives PyInstaller packaging | `speech_stt.py` is still a stub (`[MODEL-DEFERRED]`) — this is real, un-simulated dictation | `docs/06-ROADMAP.md` Phase 0 spike #7, `docs/12-VOICE-AND-SPEECH.md`, `docs/07-RISKS-AND-OPEN-QUESTIONS.md` (fallback: whisper.cpp Vulkan) |
| Semantic-layer smoke test | Install `sqlite-vec`, confirm the Windows wheel loads, run `qwen3-embedding:0.6b` CPU-pinned (`num_gpu: 0`), one hybrid FTS5+vector+RRF query | Feeds Phase 10 (§4c below); needs a real embedding model | `docs/06-ROADMAP.md` Phase 0 spike #8, `docs/11-AI-INTELLIGENCE.md` |
| Ollama cancel-on-disconnect | Confirm closing the httpx stream to Ollama actually stops its generation loop (not just cosmetic on the frontend) | Needs a live Ollama call, first exercised for real when Enhance is used for real | `docs/07-RISKS-AND-OPEN-QUESTIONS.md` (affects whether auto-suggest is viable at all) |

Update `docs/07-RISKS-AND-OPEN-QUESTIONS.md` with the **actual measured
numbers** for each, not just a checkmark — that document explicitly asks for
this ("the number itself is what later phases need").

### 4b. Phase 9's deferred half — installer + real onboarding

These were explicitly scoped out of Phase 9 on the build laptop (see
`PHASE9.md` §3/§6) because there was no Tauri project to bundle at all:

| Task | Where | Why now, not before |
|---|---|---|
| Scaffold `src-tauri/` (Tauri 2 shell) | new `apps/desktop/src-tauri/` per `docs/02-ARCHITECTURE.md`'s folder layout | Nothing to bundle without this; also gates the two spikes above |
| MSI/NSIS installer bundling Tauri + sidecar (PyInstaller) + Ollama + fonts | Tauri's bundler config once `src-tauri/` exists | Needs Rust/cargo + a packaged sidecar + a bundled Ollama binary, all of which are this-machine-only |
| First-run onboarding: disk-space check + model-pull flow | new onboarding step, wraps around the already-built `reading-comfort-wizard.tsx` (don't rebuild that — it shipped in Phase 8) | Needs real OS disk APIs (via Tauri) + a real Ollama model-pull call |
| `cargo audit` clean pass | once `src-tauri/Cargo.lock` exists | No Rust project existed to audit |
| The literal Phase 9 demo: "full end-to-end walkthrough from a clean install on the target machine" | — | This is the actual v1.0 ship gate — run it here, first, before considering v1.0 done |

Do this **after** §4a's spikes resolve the Ollama-bundling and PyInstaller
risk items — those spikes directly inform how the installer step is built,
not the other way around.

### 4c. Phase 10 — Semantic layer (v1.1, `docs/06-ROADMAP.md`)

**Most of this already landed on the build laptop (2026-07-30) — see
`PHASE10.md`.** `sqlite-vec` turned out to need no model at all (pure PyPI
extension package), so the schema, hybrid search, suggestion mechanisms, and
frontend UI are already built and tested here, behind a deterministic stub
embedding. What's actually left is narrow:

- **Swap the real embedding call in.** `apps/sidecar/app/services/
  embedding_service.py`'s `_embed_real()` currently raises
  `NotImplementedError` with the exact drop-in documented in its module
  docstring: `litellm.embedding(model=f"ollama/{settings.
  default_embedding_model}", ...)`. Wire that in once Ollama + the
  `qwen3-embedding:0.6b` model are actually available (§4a's semantic-layer
  smoke test should run first to confirm the model/wheel combination works
  on this hardware before wiring it into the real service).
- **Re-run `POST /search/backfill`** against real embeddings once the swap
  above lands — the stub-embedded backfill from the build laptop needs
  redoing for real semantic quality (the schema/rows are already correct
  structurally, only the vectors themselves are placeholders).
- **Verify the actual Phase 10 demo criteria** from `docs/06-ROADMAP.md`:
  semantic search finds a scene by meaning not just shared keywords; an
  auto-link suggestion is genuinely conceptually relevant, not just
  FTS5-keyword-driven; a near-duplicate scene surfaces its twin even when
  worded differently. None of this is provable with the stub — it's the
  first real thing to check once the swap lands.
- **GraphRAG-lite context assembly** (replacing the flat context builder
  for Enhance calls) was **not** started on the build laptop — it's
  genuinely new work, not a stub-to-real swap. Source:
  `docs/11-AI-INTELLIGENCE.md` (retrieval/RAG design). Touch:
  `apps/sidecar/app/services/prompt_builder.py` (the current flat context
  builder — read it first), building on the now-existing
  `hybrid_search_service.py`.
- Already-built files worth knowing about before touching this phase
  further: `apps/sidecar/app/services/embedding_service.py`,
  `search_index_service.py`, `hybrid_search_service.py`,
  `suggestion_service.py`, `apps/sidecar/app/api/search.py`,
  `apps/sidecar/app/db/migrations/versions/
  e51867fcdc66_semantic_search_fts5_and_vec0.py`,
  `apps/desktop/src/queries/search.ts`+`suggestions.ts`,
  `apps/desktop/src/components/search/search-dialog.tsx`,
  `apps/desktop/src/components/canvas/suggestion-panel.tsx`.
- Team split: backend engineer does the embedding-service swap + backfill
  re-run + GraphRAG-lite context assembly; UI/UX or security reviewer isn't
  needed here (no new encryption/export-import/generated-document surface);
  you (orchestrator) verify the actual demo criteria yourself once real
  embeddings are in, per this project's own "demo is the only quality gate"
  rule.

### 4d. Phase 11 — Full delight + voice + verification iteration (v1.1)

Rive firefly mascot (idle/thinking/celebrating/sleeping states — **requires
a paid Rive export tier, ~$9 for one month**, budget it or use the
documented layered-SVG+Motion fallback per `docs/07`); achievements/badges;
**Piper TTS** listen-through voice (`piper1-gpl`, GPL-3.0 — **hard rule**:
must run as a fully separate standalone process, never imported/linked into
Quillnight's own executables, see `docs/07`'s Piper item); phonetic
spellcheck (Hunspell PHONE/SymSpell) + LanguageTool verifier loop + personal
dictionary; brain-dump mode (ramble → reviewed draft nodes); 3-vote
self-consistency on continuity checks (budget-gated on 4a's model bake-off
numbers).

- Source: `docs/12-VOICE-AND-SPEECH.md` §2 (Piper isolation design),
  `docs/10-DESIGN-SYSTEM.md` §6 (mascot state machine), `docs/11-AI-
  INTELLIGENCE.md` §7 (self-consistency voting), `docs/06-ROADMAP.md`
  Phase 11 section.
- Touch: new `apps/sidecar/app/services/piper_process_manager.py` (process
  boundary is the security-sensitive part — **needs a reviewer pass**), new
  `apps/desktop/src/components/mascot/` (Rive integration or SVG
  fallback), `services/continuity_service.py` (extend for 3-vote), new
  spellcheck service + personal-dictionary table (another schema owner
  call).
- **This phase needs a UI/UX reviewer pass** on the mascot's
  delight-matrix compliance (Calm/Standard/Playful + `prefers-reduced-
  motion`), same audit discipline Phase 8 already established — don't
  let a new animated surface bypass the existing `useDelight()` gate.

### 4e. Phase 12 — Backlog (v2.0, unscheduled)

Style anchors (few-shot from accepted prose), writer's-room multi-persona
brainstorm, CPU reranker (only if v1.1 retrieval quality warrants it),
propagation-debt review lists (`docs/07`'s `autonovel` reference — "these N
scenes may need review" after a Codex arc-state change), word prediction
with phonetic support, CLIP image search, community/theme packs. No fixed
order — MoSCoW-lowest, per `docs/06-ROADMAP.md`'s own framing ("Coulds wait
indefinitely"). Don't start this before v1.1 (Phases 10-11) is genuinely
done.

## 5. Hard rules that don't change on this machine

Everything in `CLAUDE.md`'s "Hard rules" and `docs/09-HANDOFF-AND-BUILD-
GUIDE.md`'s "Non-negotiable cross-cutting principles" still applies exactly
as-is: never silently overwrite user data, `keyring` crate only for the Groq
key, official-registry-only pinned packages, reviewer-gated files stay
reviewer-gated (now also including anything in the new Piper process
boundary and the Tauri↔sidecar shutdown handshake), playfulness stays in
chrome not manuscript, prompt-cache ordering discipline in
`prompt_builder.py`.

**New rule specific to this machine**: this is the *only* place real models
run. Don't let that turn into "move fast, it's fine now" — the same
Accept/Reject trust contract, the same never-silently-overwrite rule, and
the same demo-before-next-phase discipline apply with real models exactly
as they did with stubs. If anything, be more careful here, not less — this
is where a wrong assumption gets discovered in production behavior instead
of a stub returning a fixed string.

## 6. Sources checklist (have these open)

- `docs/01` through `docs/14` (all 14 spec files — `docs/13` covers
  Profiles/Auth, `docs/14` is the deferred-enhancements list §4b/§4c/§4d
  pull from)
- `PROJECT-MAP.md`, `API-REFERENCE.md`, `CLAUDE.md` (repo root)
- `PHASE7.md`, `PHASE8.md`, `PHASE9.md` (repo root — historical record of
  the most recent three phases' actual decisions/deviations)
- This file, `HANDOFF-ASUS-TUF.md` — update or delete sections as each
  item above actually gets done, the same way `PHASE*.md` files get
  superseded; don't let it go stale while claiming to be the source of
  truth for what's left.

## 7. Environment setup checklist (do once, before §4a)

- Install Rust/cargo (`rustup`), Ollama (official Windows release), `uv`
  (or confirm whichever Python env manager this repo's `apps/sidecar`
  actually uses — check `pyproject.toml`/lockfile tooling before assuming).
- Pull the model tags from §4a's bake-off row (verify current tags on
  Ollama's library first, they may have moved).
- `git clone`/`git pull` from `origin` (`https://github.com/KarthikeyaSuppa/
  viewquill.git`) — confirm you're on `master`, working tree clean, and
  `git log --oneline` shows Phase 9's commits before starting anything new.
- Re-run the full backend/frontend test suites once here
  (`QUILLNIGHT_LLM_STUB=1 QUILLNIGHT_STT_STUB=1 pytest -q` in
  `apps/sidecar`; `npm run build && npm run lint` in `apps/desktop`) to
  confirm nothing broke in transit before starting new work.

## 8. If the repo isn't already pushed/pulled cleanly

If `git log` on this machine doesn't show Phase 9's commits yet: on the
build laptop, confirm `git status` is clean and Phase 9's changes are
committed and pushed to `origin/master` (`git push -u origin master` if not
already done) **before** treating this handoff doc as current — everything
above assumes Phase 9's actual code, not just this planning document, has
already crossed over.
