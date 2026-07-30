# PHASE-UI-EFFECTS-2.md — 10 more freefrontend.com effects + 2 image feature gaps

Loaded ad-hoc (not a roadmap phase), follow-on to `PHASE-UI-EFFECTS.md`.
Status: **Done (2026-07-30).**

## 0. Outcome

10 of 12 planned tasks built, 2 skipped honestly rather than forced:

- **Part B (real feature gaps) — both done**: `EntityImage.order_index`
  (nullable int, additive migration), `POST /entities/{type}/{id}/images/
  reorder`, `nodes.tsx`'s cover-image selection now uses real user-set order
  instead of the old `bucket === 'finalized_scene'` heuristic, up/down-arrow
  reorder + "Make cover" quick-action in `SceneImagesSection` (reused this
  app's own existing screenplay-elements reorder convention rather than
  adding a second mechanism), and multi-select checkbox attach (`Promise.all`
  over the existing single-attach mutation, one invalidation, no new bulk
  endpoint — not worth the speculative surface at this scale).
- **Characters Timeline (Gantt view)**: built as recommended in §3 below —
  explicitly not a bump chart (no orderable per-scene value exists in this
  app's data) or a storyline/braided diagram (redundant with the
  already-shipped relationship graph, harder D3). One new dependency,
  `d3-scale@4.0.2`, for x-axis math only.
- **A-Z scroll index rail** on the Characters List view — used
  `IntersectionObserver`, not CSS `view-timeline`, since character-list
  length is fully dynamic per Book (a stable scroll-timeline range doesn't
  suit that).
- **Context-aware canvas cursor** — implemented as a pure CSS `cursor`
  property swap on React Flow's own already-hover-managed classes, **zero
  JS, zero re-renders** — a materially better outcome than the tracking-
  element approach the research described, caught and fixed a placement
  error in this doc (`node-editor.tsx` → actually `canvas-panel.tsx`).
- **Skipped, with reasons**: hamburger-to-X toggle (confirmed via grep — no
  collapsible/mobile nav exists anywhere in this desktop-only app; inventing
  one just to host the effect was rejected, matching this batch's own
  no-forced-fits convention); tactile range-slider reskin (the actual
  "Speaking rate" control is Radix's accessible `Slider` primitive, not a
  native `<input type="range">` — a one-off native variant just for this
  reskin would fragment the design system for a purely decorative gain, so
  the builder halted and reported rather than forcing it — correct call).

Backend: 351 passed, same 2 known pre-existing cross-module test-ordering
failures (unrelated, unchanged in count). Frontend: clean build + lint
throughout, every task verified individually.

## 1. Context

Same convention as round 1: research done (sonnet, already supplied), this
doc is the opus placement/feasibility pass, task list is builder-assignable.
Two tracks: Part A (10 decorative effects, frontend-only, `useDelight()`-gated)
and Part B (2 real feature gaps — multi-select image attach + image ordering
— which need backend changes, per the user's explicit "fix the backend"
instruction).

## 2. Part A — placement decisions

| # | Effect | Decision |
|---|---|---|
| 1 | Scroll-driven CSS alphabet index rail | `characters-panel.tsx`'s List view — this is the one screen in the app with a plain alphabetized entity list long enough to justify an A-Z rail (Book cards on Library aren't alphabetized; Codex-in-Canvas is scene-scoped, not a long flat list). `view-timeline` native CSS, WebView2/Chromium ≥115 is fine. Gate the highlight-transition animation through `useDelight().motionOk`; the rail itself (a nav, not decoration) stays always-interactive/keyboard-focusable regardless of motion setting. |
| 2 | Tactile CSS variable range slider | `image-detail.tsx` if it has a slider control (crop/zoom); more concretely: `read-aloud-bar.tsx`'s speed control and the GSAP gallery's zoom control (`gallery-zoom-view.tsx`, 30%-100%) are both currently button/keyboard-driven, not sliders — **skip forcing a slider where buttons already work well**; the one real fit is **Settings → Voice → read-aloud speed**, which likely already renders as a native range input (`settings-screen.tsx`) — reskin that one input, trivial, no new interaction model. |
| 3 | Animated SVG hamburger-to-X toggle | `app-shell.tsx` — if the shell has any collapsible mobile/narrow-width nav trigger use it there; if `app-shell.tsx`'s nav is always-expanded (desktop-only app, per `PROJECT-MAP.md` there's no responsive/mobile nav collapse mentioned), **skip** — don't invent a hamburger menu that doesn't otherwise exist just to host this effect. Confirm which case applies before assigning the task. |
| 4 | Hyperspace warp canvas button | **Skip** — no button in this app is a "fun/major moment trigger" button (e.g. a big one-shot "Compile" or "Export" button) that would suit a canvas warp flourish without looking out of place next to the app's calmer glass/holographic aesthetic; forcing it onto e.g. the Export button competes with the existing holographic-card language from round 1. Revisit only if a future "ship it" moment is designed. |
| 5 | Interactive 3D credit-card form | **Skip, hard** — this app has zero payment/billing surface anywhere (local desktop app, no purchases, no subscriptions). Nothing to attach it to. |
| 6 | Ribbon-hover CSS leaderboard widget | **Skip** — hover-only with no keyboard/touch path fails this app's accessibility bar outright (Phase 8's WCAG-AA audit specifically chased down hover-dependent-only interactions), and there's no ranked/leaderboard data anywhere in the model (no gamification — streaks were cut in Phase 8 on explicit user instruction: "not a habit-tracker"). Doubly disqualified. |
| 7 | Smart-home glassmorphic dashboard | **Skip** — no smart-home/device-control domain exists in this app, and the site's own note about glass-panel contrast risk is a real concern for an app that just passed a WCAG-AA contrast audit (Phase 8 fixed a 3.39:1 failure); adopting a translucent-panel-heavy pattern here without redoing that audit isn't worth it for an effect with no real placement anyway. |
| 8 | Scroll-driven particle WebGL image matrix | **Skip** — no page in this app has a hero/portfolio-style single-image scroll moment to justify a Three.js dependency + 50k-particle scene; also a vestibular-trigger risk this app's reduced-motion posture would need to gate hard, for a benefit (a photo assembling from particles) that doesn't map to any real screen (Library cards, Image cards, and node cards are all small-thumbnail grids, not full-bleed scroll heroes). |
| 9 | Bump-curve D3 chart | **Build — but not as a bump chart.** See §3, dedicated analysis below. |
| 10 | Context-aware CSS custom cursor | `node-editor.tsx` canvas surface only (cursor morphs between "select"/"pan"/"connect" states while hovering nodes vs. background vs. a connection handle) — genuinely useful affordance there since React Flow already has distinct interaction modes. **Must not be the only signal**: every one of those modes already has (per Phase 8's canvas keyboard audit) a real focus ring / keyboard path, so the cursor is additive, never load-bearing. Gate the cursor-shape *transition* animation through `useDelight().motionOk`; the shape itself (an affordance, like effect #10 in the general framing) stays on regardless of motion setting — only the smoothing/morph animation is decorative. |

Every animated/decorative item routes through `useDelight()` — no new
competing gate, per Phase 8's zero-bypass audit. Items 4, 5, 6, 7, 8 are
skipped outright (5 of 10) — more skips than round 1's 3 of 9, because this
batch's remaining effects lean harder into "needs a domain this app doesn't
have" (payments, leaderboards, smart-home, hero scroll) rather than
generically-portable chrome.

## 3. Part A #9 — the consequential one: bump chart vs. storyline vs. Gantt

**Checked the actual data model** (`apps/sidecar/app/models/orm.py`):

- `CodexSceneLink` (`codex_scene_links` table, orm.py line 234): columns are
  `codex_entry_id`, `scene_id`, `note` (free text). **Binary presence only —
  no orderable per-scene value** (no line-count, no word-count, no manually
  assigned rank/prominence field anywhere on this table or on `CodexEntry`).
- `BookSceneOrder` (`book_scene_order`, orm.py line 157): has
  `outline_order_index` and `timeline_order_index` — a real, already-shipped
  chronological/beat ordering of scenes per Book. This is the x-axis
  Characters-over-scenes needs, and it already exists.
- `CodexRelationship` (`codex_relationships`): character-to-character edges
  with a `relationship_type`, already visualized in round 1's
  `character-relationship-graph.tsx` — a separate, already-solved concern
  (who-knows-whom), not what #9 is asked to solve (who's-in-which-scene).

**Recommendation: a Gantt-style presence timeline, not a bump chart, not a
storyline/braided diagram.**

Reasoning: a bump chart needs one *orderable* value per
character-per-scene (rank = who's "most prominent" at that time-step) — this
app tracks zero such value today, only binary presence via
`codex_scene_links`. Inventing a manual "prominence" field just to unlock a
bump chart is exactly the kind of new-data-tracking cost the brief says to
avoid unless truly needed — and it isn't needed, because binary
presence-over-ordered-scenes is precisely what a Gantt/timeline chart is
built for natively, no new field required. A storyline diagram (braided
lines merging when characters share a scene) is the "correct" visualization
for binary presence in the academic sense, but it's a materially harder D3
pattern (dynamic vertical ordering/collision-avoidance to minimize crossings)
for a benefit — "these two characters are in scenes together" — that the
existing relationship-map (`character-relationship-graph.tsx`) already shows
more directly via edges. Gantt gets the user 90% of "storyline timeline"
value (visually: which characters appear across which stretch of the story,
gaps where a character disappears, overlaps where several share a run of
scenes) for a fraction of the implementation risk, using data that exists
today.

**Concrete design**: new third view on `characters-panel.tsx` (`List / Map /
Timeline` tri-state, same `role="tablist"` pattern as Outline's
List/Timeline and round 1's Characters List/Map and Images Grid/Gallery). One
horizontal row per `CodexEntry` (character), x-axis = scenes in
`book_scene_order.timeline_order_index` order (reuse the same ordering
`timeline-view.tsx` already renders in the Outline tab — don't re-derive it),
a filled bar/dot rendered at each scene where a `codex_scene_links` row
exists for that character. D3 (`d3-scale` for the x-axis positioning only)
+ React for the SVG rows — same "D3 for math, React for render" split the
original research called out as well-trodden. Click a bar → opens the same
scene (jump to Canvas or open a scene-detail popover, builder's call which
is cheaper given existing navigation). Hover → tooltip with scene title.
**No backend changes needed for this — it's a read composed entirely from
existing `GET /books/{id}/characters` (round 1) + `codex_scene_links` (needs
one new endpoint or field addition, see task list) + existing
`book_scene_order` data.**

One gap to close: confirm `GET /books/{book_id}/characters` (round 1) already
returns each character's linked scene IDs — if it only returns entries +
relationships (per `PHASE-UI-EFFECTS.md` §3's description: "entries +
relationships in one call"), it does **not** currently include
`codex_scene_links` membership, so a small backend addition is needed (task
1 below) — this is the one piece of "new data" this recommendation actually
requires, and it's additive to an existing endpoint, not a new table/column.

## 4. Part B — the two real feature gaps

### B1: Multi-select images → attach to a Scene node in one action

**Current state** (`apps/sidecar/app/services/entity_images_service.py`,
`apps/desktop/src/components/canvas/node-editor.tsx`'s `SceneImagesSection`,
~line 451-520): attach is genuinely one-at-a-time today. `SceneImagesSection`
renders a popover ("add existing") listing pickable pool images
(`pickable.map(...)`, line 506), each with `onSelect={() =>
handlePickExisting(image.id)}` (line 475) — selecting one calls
`attachImage.mutate({...})` for that single image and (implicitly, since
it's a `<Command>`-style popover) closes/re-triggers per click. There is no
selection state, no checkbox, no "attach N at once."

**Design — frontend-only, no new backend endpoint:**
`entity_images_service.attach()` is already idempotent per-call and cheap
(one `SELECT` + one `INSERT`, no heavy work) — a bulk endpoint would only
save round-trips, and this popover realistically attaches single-digit to
low-double-digit images at a time (a Book's whole reference pool, not
thousands), so N sequential/`Promise.all`'d calls to the existing `POST
/images/{image_id}/links` is the right call, not new backend surface.
Building a bulk endpoint here would be speculative generality for a cost
(new route + service function + schema + tests + reviewer consideration)
that buys nothing a `Promise.all` loop doesn't already give for free.

Concretely: turn `SceneImagesSection`'s "add existing" popover from
single-select-and-close into a multi-select list (checkbox per row, keep
popover open, footer shows "Attach N images" button, `Promise.all` of
`attachImage.mutateAsync(...)` per checked image on confirm, single query
invalidation after all resolve, then close). Same pattern is reusable
verbatim for Codex-entry image attach if that popover exists elsewhere —
check `codex-entry-dialog.tsx` for a parallel single-attach flow before
assuming `node-editor.tsx` is the only place this pattern lives.

### B2: Which image displays as a node's cover / reordering multiple attached images

**Confirmed** (`apps/sidecar/app/models/orm.py` line 279-291): `EntityImage`
has **no ordering column at all** — only `id`, `image_id`, `entity_type`,
`entity_id`, `role` (a free-text purpose tag like `'finalized'`, not an
order). `entity_images_service.list_for_entity()` (line 122-141) orders
results by `created_at DESC, id DESC` — most-recently-attached first, not
user-controlled.

**Confirmed current node-card behavior** (`apps/desktop/src/components/
canvas/nodes.tsx` lines 83-95): `mainImage = images?.find(image =>
image.bucket === 'finalized_scene') ?? images?.[0] ?? null` — it picks the
first image (by the above `created_at DESC` ordering) whose *bucket* is
`finalized_scene`, falling back to whatever's first overall. This is an
implicit heuristic, not a real "primary image" concept — there is no way for
a user to say "no, show *this* one" if multiple finalized images are
attached to the same scene. The thumbnail strip below it
(`thumbnails = (images ?? []).slice(0, 4)`, line 95) has the same problem:
its order is just attachment-recency, not anything the user chose.

**Design — one new nullable `order_index` column on `EntityImage` (not
`is_primary`)**: an int, not a boolean, because it solves *both* halves of
the ask in one field — "which one is primary" (order_index 0 = cover) *and*
"reorder the thumbnail strip" (nodes.tsx already renders up to 4 thumbnails
whose order currently means nothing) — a boolean would only solve the first
half and leave the strip's ordering permanently arbitrary. Additive/safe
migration: new nullable column, existing rows get `NULL`, `list_for_entity`'s
`ORDER BY` becomes `order_index IS NULL, order_index ASC, created_at DESC,
id DESC` (SQLite sorts `NULL` first ascending by default position, so state
the explicit `IS NULL` sort key rather than relying on default NULL
placement — verify SQLite's actual default and make it explicit either way,
don't guess) — so behavior for every existing row is **unchanged** until a
user explicitly reorders. New endpoint: `POST
/entity-images/reorder` (or nested under `/images/links/reorder`, builder's
call on REST shape) taking `{entity_type, entity_id, image_ids: [ordered
list]}`, service function `entity_images_service.reorder_for_entity(...)`
that sets `order_index = index` for each `EntityImage` row matching that
`(entity_type, entity_id)` pair whose `image_id` is in the list (images not
in the list keep their existing `order_index`, or get pushed to `NULL`/end —
builder's call, but must be explicit and tested either way). Frontend:
`nodes.tsx`'s `mainImage` becomes simply "first item of `useEntityImages(
'scene', sceneId)` once that list is ordered by the new column" — **drop the
bucket-based `finalized_scene` heuristic entirely**, since explicit
`order_index` is a strictly better and user-controllable signal; add a
small drag-reorder or up/down-arrow control to `SceneImagesSection`'s
attached-images list (`node-editor.tsx` ~line 544-561) that calls the new
reorder endpoint, and a lightweight "make cover" affordance (sets this image
to `order_index: 0`, shifting others down) as the fast path for the common
case of just picking one primary without manually reordering everything.

Neither B1 nor B2 needs a reviewer pass — no encryption, export, or
merge-import logic touched (`entity_images_service.py` isn't on the
reviewer-gated file list in `CLAUDE.md`/`PROJECT-MAP.md` §9).

## 5. Task list (backend before dependent frontend, sequential)

1. **Backend**: extend `GET /books/{book_id}/characters` (round 1's
   endpoint, `api/codex.py`/`codex_service.py`) to also include each
   character's linked `scene_id`s from `codex_scene_links`, so the new
   Timeline view (§3) has presence data in the same call it already uses for
   List/Map. 1-2 files (`services/codex_service.py`, `models/schemas.py`).
   Done when: response includes scene-membership per character, existing
   List/Map consumers unaffected (additive field only).
2. **Backend**: add `order_index` (nullable `Integer`) column to
   `EntityImage` (`models/orm.py`) + new Alembic migration. 1 file + 1
   migration. Done when: migration applies cleanly on top of existing data,
   existing `list_for_entity` ordering behavior is unchanged for rows with
   `NULL` order_index (regression test against current fixture ordering).
3. **Backend**: `entity_images_service.reorder_for_entity()` + `POST
   /entity-images/reorder` route + `EntityImageReorderRequest`/response
   schema. 2-3 files (`services/entity_images_service.py`, `api/images.py`
   or new small route file, `models/schemas.py`). Depends on task 2. Done
   when: reordering a scene's attached images persists and
   `list_for_entity` reflects the new order; unit test covers partial
   reorder (some images omitted from the list).
4. **Backend**: regenerate `packages/api-types/schema.d.ts` after tasks
   1 and 3 (one command, not a builder task — run after both land).
5. **Frontend**: `nodes.tsx` — switch `mainImage`/`thumbnails` from the
   bucket-based heuristic to `order_index`-first ordering (drop the
   `bucket === 'finalized_scene'` fallback logic). 1 file. Depends on task
   3+4. Done when: a scene with multiple attached images shows the
   user-ordered one as cover, no visual regression for scenes with a single
   image or with `order_index` all-`NULL`.
6. **Frontend**: `node-editor.tsx`'s `SceneImagesSection` — add reorder
   controls (drag or up/down arrows) + a "make cover" quick action wired to
   the new reorder endpoint. 1 file. Depends on task 5.
7. **Frontend**: `node-editor.tsx`'s `SceneImagesSection` "add existing"
   popover — convert single-select-and-attach into multi-select (checkboxes,
   "Attach N images" confirm, `Promise.all` over the existing single-attach
   mutation, one invalidation). 1 file. No backend dependency, can run
   parallel to tasks 1-6.
8. **Frontend**: `characters-panel.tsx` — add Timeline tri-state view (D3
   scale math + React SVG rows) alongside existing List/Map, reusing
   `book_scene_order.timeline_order_index` (same ordering
   `timeline-view.tsx` already uses — check that file for the exact sort
   before re-deriving it) + task 1's scene-membership data. 1-2 files
   (`characters-panel.tsx`, possibly a new
   `character-scene-timeline.tsx`). Depends on tasks 1+4.
9. **Frontend**: scroll-driven A-Z index rail on `characters-panel.tsx`'s
   List view (Part A #1). 1 file. Independent of tasks 1-8.
10. **Frontend**: confirm whether `app-shell.tsx` has any collapsible nav
    (Part A #3) before assigning — if yes, hamburger-to-X morph, 1 file; if
    no, mark #3 skipped and don't file a task.
11. **Frontend**: reskin the read-aloud speed control (Settings → Voice,
    `settings-screen.tsx`) as the tactile CSS-variable range slider (Part A
    #2). 1 file.
12. **Frontend**: context-aware cursor morph on `node-editor.tsx`'s canvas
    surface (Part A #10), motion-gated transition only, cursor shape itself
    always on. 1 file.

Tasks 9, 11, 12 (and 10 if applicable) have no backend dependency and can be
dispatched to `builder` immediately/in parallel with tasks 1-8. Tasks 4-8
and 3 form the one real dependency chain in this batch.

No task in this phase needs an Opus `reviewer` pass — confirmed against
`CLAUDE.md`'s reviewer-gated file list (`export_docx.py`, `export_pdf.py`,
`bundle_export.py`, `bundle_import.py`, `bundle_crypto.py`,
`speech_stt.py`): none of tasks 1-12 touch any of them.
