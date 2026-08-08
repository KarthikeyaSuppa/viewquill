# Deferred Enhancements ("On-Tab" ideas)

Non-blocking ideas parked here so they don't disturb the phase roadmap (`06-ROADMAP.md`).
Each entry says **what**, **why it's deferred**, and **where it would slot in**. Nothing here
is committed to a phase yet — promote an item into a phase only when its prerequisites land.

---

## A. bento (github.com/nyblnet/bento) — what it actually is

**Reality check first.** bento is **not** a canvas/node-graph library and **not** a "bento-grid"
CSS layout kit (a reasonable assumption from the name). It is a **local-first presentation app** —
a single-file `.bento.html` that bundles editor + viewer + presenter (a PowerPoint alternative),
built on Reveal.js with in-house animation/chart/collaboration engines. **License: MIT**
(patterns/code reusable with attribution — verify per-file before copying).

So it does **not** upgrade the React Flow story canvas. But several of its ideas map cleanly onto
Quillnight's **export / presentation / offline-first** surfaces. Feasible borrows, by phase:

| bento idea | Where it fits in Quillnight | Feasibility |
|---|---|---|
| **Single-file, self-contained export** (deck travels in one HTML) | Phase 6 (Final Draft/export) or Phase 7 (`.quillproj`) — a "share my story as one openable file" export | High — aligns with the offline-first, no-cloud ethos; MIT patterns reusable |
| **"Morph" transitions** (shared-id elements animate between slides) | A future **"Present your story" mode** — step through scenes/beats like slides for a read-through or pitch | Medium — nice delight feature (Phase 8-ish), not core writing |
| **Plain-JSON document format, agent-editable** | Reinforces the `.quillproj` design (Phase 7) — keep the export a clean, inspectable JSON/bundle | High — already the direction; bento validates it |
| **Dependency-free charts** | Low relevance (writing app, not analytics) — only if a "story stats" view is ever wanted | Low |
| **E2E-encrypted CRDT collaboration + blind relay** | Explicitly **out of scope** — Quillnight is single-user, local, offline (docs/02, docs/08). Do NOT pull this in | N/A — conflicts with the offline/local premise |

**Recommendation:** treat bento as a **reference for the export/"present" side (Phases 6-8)**, not the
canvas. If a "present your story" slideshow mode is wanted, that's the strongest borrow. Revisit when
Phase 6 begins; nothing to do now.

---

## B. Canvas UX polish (React Flow — the actual node canvas)

The canvas is `@xyflow/react` (`apps/desktop/src/components/canvas/`). Genuine canvas upgrades
(independent of bento) to consider later, most already feasible with React Flow built-ins:

- **Node grouping / frames** — visually box a set of scenes into an act/chapter (React Flow parent
  nodes or a group node). Slots near Phase 4 (Outline/Timeline).
- **Auto-layout** — one-click tidy of the graph (e.g. dagre/elk layout). Phase 4.
- **Node-level Codex badges** — show attached Codex entries as pills on a node (was listed optional in
  Phase 3, deferred). Small, do when convenient.
- **Edge labels / typed connections** — label connections (leads-to, flashback, causes). Phase 4.
- **Canvas templates** — starter layouts (three-act, hero's journey) as pre-seeded nodes. Phase 8 delight.
- **Keyboard-first node creation** — add/connect nodes without the mouse (accessibility). Phase 8.

None block current work; pull into the phase noted when its groundwork exists.

---

## B2. Periodic (timer-based) local backup rotation

**What:** a during-session timer that runs `backup_service.run_rotation()` on a cadence (e.g.
hourly), not just at startup + manual trigger. **Why deferred:** Phase 7 shipped startup +
manual rotation, which covers the "never lose data" need for an app that restarts regularly; a
background asyncio timer adds test surface for marginal value. docs/05 §"Additional backup safety
net" implies a periodic cadence — this closes that gap. **Where it slots:** Phase 9 (hardening),
alongside idle RAM/`keep_alive` perf tuning. Decision recorded 2026-07-28.

## D. Continuity "detective dashboard" (relationship view)

**What:** a separate view (not the main node canvas) that surfaces how scenes and
characters interact across a whole Book — a relationship graph/matrix, not a ranked
list — so a writer working with scattered, non-linearly-written scenes can spot
continuity flaws at a glance. **Why deferred:** raised 2026-08-02 while scoping a canvas
node-linking upgrade (directional/undirected edges, handle hit-area, multi-image upload —
see PHASE-adjacent working notes); it's a genuinely separate, larger initiative, not a
task that fits inside that upgrade. It would consume `continuity_service.py`'s existing
flag detection (Phase 4) and Phase 10's embeddings/FTS5/RRF hybrid search + auto
codex-link/similar-scene suggestions as its data sources — the canvas node/scene data is
effectively the RAG corpus this dashboard would visualize relationships over, with an eye
toward eventually helping merge scattered scenes into one coherent story (Phase 11's
AI-assisted multi-node merge already exists as the merge mechanism; this dashboard would
be the discovery layer surfacing *which* scenes are candidates). **Where it slots:** its
own future phase, planned fresh with `architect` once picked up — don't retrofit it into
an unrelated task. Note: a D3.js "bump/rank chart" (categories ranked across fixed year
snapshots) was floated as visual inspiration during scoping but explicitly doesn't fit —
this dashboard is about relationships, not rankings — don't resurrect that chart shape
for it.

## D2. Hugging Face model-fetch tooling (for Phase 10's real-embedding half)

**What:** write (but don't run) the actual model-download code for Phase 10's still-stub
`embedding_service._embed_real` — e.g. via `huggingface_hub` — so it's ready-to-run
rather than needing to be written from scratch once real embeddings are tackled.
**Why deferred:** this build machine's hard constraint (CLAUDE.md: "no LLM model
downloads... ever") means writing it now would mean writing untested code with no way to
verify it works here; it's cheaper to write it together with the rest of Phase 10's
real-embedding work, on whichever machine actually runs it. **Where it slots:** Phase 10's
deferred real-embedding half (see `HANDOFF-ASUS-TUF.md` §4c) — pick up there, don't start
early.

## C. Recently shipped (moved off this list)

- Toolbar tidy: **Add node** relocated to the Canvas/Outline/Draft tab row; **zoom controls** moved
  under the word-count pill; word label renamed **"penned"**.
- **In-app Help & Guide** (sidebar → Help): getting-started steps, canvas + minimap, Codex, reading
  comfort, profiles, examples.
