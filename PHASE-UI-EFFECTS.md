# PHASE-UI-EFFECTS.md — freefrontend.com effects + Characters tab

Loaded ad-hoc (not a roadmap phase). Status: **In progress (started 2026-07-30)**.

## 1. Context

User asked for 9 UI effects from freefrontend.com evaluated for use in this
app, plus a new Characters tab (searchable list + relationship "map") driven
by a real gap: too many Codex characters to track via the existing
scene-scoped Codex panel alone. Researched (sonnet) then placement-planned
(opus) per this project's usual model routing.

## 2. Placement decisions

| # | Effect | Decision |
|---|---|---|
| 1 | Curved SVG border-radius scrollbar | **Skip** — no long custom-scroll rounded container needs a bespoke thumb; native scroll is the deliberate dyslexia-first choice |
| 2 | Glowing bell | **Skip** — no notification system exists to justify one; don't force it |
| 3 | Sliding radio pill (CSS Anchor) | `book-screen.tsx`'s rectangle/square card-style toggle |
| 4 | Holographic project cards | `library-screen.tsx` Book cards |
| 5 | GSAP draggable/zoom gallery | New optional gallery-view mode on `images-panel.tsx` |
| 6 | Arc time slider | **Skip** — nothing in this app is time-of-day-scoped (streaks/daily-goal already cut in Phase 8) |
| 7 | Image drop-shadow cards | `image-card.tsx` / Library Book cards, pure CSS |
| 8 | Drag-and-drop table | **Skip** — no table UI exists anywhere to attach it to; revisit if a future feature needs tabular reorder |
| 9 | Wobbly underline menu | `app-shell.tsx` sidebar nav + `book-screen.tsx` tab bar |

Every decorative/animated item routes through the existing `useDelight()`
gate — no new competing gate, per Phase 8's zero-bypass audit.

## 3. Characters feature

- New Book-screen tab (Codex entries are Book-scoped via `book_codex_links`;
  Characters sits alongside Canvas/Outline/Images/Draft, not in the
  cross-book top-level nav).
- Search: simple client-side filter (per-Book character count is small;
  Phase 10's hybrid search is overkill at this scale).
- Map: a character-relationship graph via React Flow (already a
  dependency), nodes = characters, edges = `codex_relationships` — not a
  geographic map, this app has no location data model.
- One new backend endpoint needed: `GET /books/{book_id}/characters`
  (entries + relationships in one call) — the only backend work in this
  phase, scoped exactly to unblocking the frontend per the user's
  frontend-first instruction.

## 4. Task list (sequential, one at a time)

1. Backend: `GET /books/{book_id}/characters` aggregation endpoint. **Done.**
2. Frontend: regenerate types + `useBookCharacters` query hook. **Done.**
3. Frontend: Characters tab — searchable list view. **Done.**
4. Frontend: Characters tab — relationship graph view. **Done (2026-07-30)** — new
   `components/codex/character-relationship-graph.tsx`: one `character` React Flow node per
   `CodexEntry` (name + icon, `glass glass-edge` styling matching `nodes.tsx`'s card
   conventions), one `ink`-typed edge per `CodexRelationship` labeled with `relationship_type`
   (reuses Canvas's `InkEdge` component as-is), deterministic circular layout by array index.
   `characters-panel.tsx` gained a keyboard-operable List/Map `role="tablist"` toggle (same
   pattern as `outline-panel.tsx`'s Outline/Timeline toggle) and both view branches share the
   same `filtered` entries + `editingEntry`/`CodexEntryDialog` state — clicking a map node
   opens the identical dialog the list cards do.
5. Frontend: wobbly underline on nav + book tabs.
6. Frontend: sliding pill selector for card-style toggle. **Done (2026-07-30)** —
   `book-screen.tsx`'s rectangle/square card-style toggle is now a real `<fieldset>` +
   two `<input type="radio">`/`<label>` pairs (native keyboard/SR accessibility, not
   ARIA-patched divs). The sliding pill (`.card-style-pill` in `index.css`) uses CSS
   Anchor Positioning: each label gets a unique `anchor-name` keyed off
   `data-card-style`, and the pill's `position-anchor` swaps via className
   (`--rectangle`/`--square`) driven by the `card-style.ts` store value, then `anchor()`
   pins all four edges to size/position it — no DOM measurement, unlike
   `WobblyIndicator`. Gated through `useDelight().motionOk` exactly like
   `wobbly-indicator.tsx` (`.card-style-pill--instant` removes the transition at
   Calm/reduced-motion). Same `useCardStyleStore` setter/value as before — visual/a11y
   upgrade only, no behavior change.
7. Frontend: holographic hover + drop-shadow cards (Library/Images).
8. Frontend: GSAP zoom/pan gallery view for Images panel. **Done (2026-07-30)** —
   pinned `gsap` 3.15.0 exact in `apps/desktop/package.json` (matching the no-caret style
   `@dnd-kit/*`/`lottie-react` already use). New `components/images/gallery-zoom-view.tsx`:
   a GSAP `Draggable` "stage" (pan) + button/keyboard-driven `scale` (zoom, 30%-100%)
   wrapped around the *same* `<ImageCard/>` grid `images-panel.tsx`'s plain grid already
   renders — clicking a card opens the identical `<ImageDetail/>` dialog, no second
   open-detail path. `images-panel.tsx` gained a second keyboard-operable Grid/Gallery
   `role="tablist"` toggle (same pattern as Outline's Outline/Timeline and Characters'
   List/Map) alongside the existing Reference-pool/In-this-Book toggle, orthogonal to it —
   both views can render either layout. `useDelight().motionOk` gates only *feel*: GSAP
   `InertiaPlugin` momentum on drag-release and eased zoom tweens are `motionOk`-only; the
   pan/zoom mechanism itself is never disabled at Calm/reduced-motion since it's real
   navigation, not decoration — drag becomes a dead-stop 1:1 move and zoom becomes an
   instant jump instead. Explicit keyboard fallback (arrow keys pan, `+`/`=`/`-`/`_` zoom)
   writes through the same `Draggable` instance via `.update(true)`/`.applyBounds()` so
   pointer and keyboard input can't desync. One `Draggable.create` per mount, killed
   (`.kill()` + `gsap.killTweensOf`) in the mount effect's cleanup — verified no
   double-create/leak across the mount → `motionOk`-flip-recreate → unmount lifecycle.
9. Frontend: Help page — hotkeys/usage section (Ctrl+K search, Shift+N,
   Shift+C, R/F reading shortcuts, etc.) — separate small ask, done first.

No reviewer pass needed for any task (no encryption/merge/generated-document
code touched).

## 5. Outcome

**Status: done (2026-07-30).** All 9 tasks landed, sonnet builders, no
reviewer pass needed.

- **Characters feature**: `GET /books/{book_id}/characters` aggregation
  endpoint (entries+relationships, book-scoped, character-filtered), a new
  Book-screen "Characters" tab with a searchable list view
  (`characters-panel.tsx`) and a relationship-graph "map" view
  (`character-relationship-graph.tsx`, React Flow, deterministic circular
  layout, reuses Canvas's `InkEdge`), both sharing the same
  `CodexEntryDialog` open-state — no duplicated entry-editing UI.
- **Wobbly underline** (`wobbly-indicator.tsx`) on sidebar nav + Book-screen
  tabs — single indicator per surface (no competing pill+underline),
  overshoot cubic-bezier, gated through `useDelight().motionOk`.
- **Sliding pill selector** for the card-style toggle — real
  `<input type="radio">`+`<label>` (accessible by construction), CSS Anchor
  Positioning (safe, this app's WebView2 shell is Chromium ≥125), same
  motion gating.
- **Holographic Book cards** + **image drop-shadow cards** — pure CSS,
  theme-token-based (no hardcoded colors), hover **and** `:focus-visible`
  parity on the holographic effect, only the hue-shift animation gated
  (static gradient always visible).
- **GSAP gallery view** for Images panel — `gsap@3.15.0` pinned, draggable
  + 30%-100% zoom, full keyboard fallback (arrow-key pan, +/- zoom,
  independent of mouse drag), inertia/easing gated through `motionOk`
  (panning itself never disabled — it's navigation, not decoration), no
  instance leaks on unmount (traced), reuses the existing `ImageCard`
  click-to-open-detail path directly rather than a second handler.
- **Help page hotkeys section** — verified against actual source before
  listing (Ctrl+K global; Shift+N/Shift+C/Enter/Escape canvas-scoped;
  R/F Draft-tab-scoped only, not global).

**Skipped, with reasons** (per the user's own instruction: don't force a fit
that isn't there): curved SVG scrollbar (no long custom-scroll rounded
container needing it — native scroll is the deliberate dyslexia-first
choice), glowing bell (no notification system exists to attach it to), arc
time slider (nothing in this app is time-of-day-scoped — streaks/daily-goal
were cut in Phase 8), drag-and-drop table (no table UI exists anywhere;
this app already uses accessible `dnd-kit` for reordering, would not have
used the inaccessible native HTML5 DnD the original demo relies on anyway).

Backend: 344 passed, same 2 pre-existing known cross-module test-ordering
failures (unrelated). Frontend: clean build + lint throughout, every task
verified individually before moving to the next.
