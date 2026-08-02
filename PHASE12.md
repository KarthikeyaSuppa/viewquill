# Phase 12 — Node shapes, connection discoverability, persistent undo/redo, image-attach gap, suggestions removal

Status: Done (2026-07-31).

## Why

After using the app live post-Phase 11, the user reported five concrete
problems plus a general UI/UX ask. Investigation (3 parallel Explore agents)
confirmed each maps to a real root cause — but two of them ("connections
don't work," "no image attach option") turned out to be discoverability/
gating gaps rather than broken code, not the functional regressions they
first appeared to be:

1. Node shape was a single global rectangle/square toggle applied to every
   node regardless of type — the user wanted shape to communicate node TYPE.
2. "Connections don't work" — they did. `onConnect→createEdge→backend→
   refetch` was fully wired and multiple edges into/out of one node were
   already unrestricted. The actual problem: xyflow's default handles are
   10px and invisible until hover, with zero on-screen cue.
3. "No undo/redo button" — confirmed real gap. Undo/redo only existed as a
   toast that auto-dismisses; no persistent control existed anywhere.
4. "No image attach/reorder option" — the feature was fully built but
   silently never rendered at all for script-type Books (movie_script/
   short_film_script) — a real, confirmed gating bug.
5. "Don't give suggestions inside node" — asked twice; `SuggestionPanel`
   rendered unconditionally with no way to turn it off.

A design pass (Sonnet at high effort — Opus was transiently unavailable for
this call) turned each into a scoped fix, plus a bounded UI/UX audit of the
canvas + node editor (this round's theme, not a full-app pass).

## What shipped

1. **Shape communicates node type**: Scene keeps the existing user-facing
   toggle (relabeled "Scene shape," unchanged mechanism/store). Plot Point
   now always renders a fixed vertical rectangle (`aspect-[3/4]`) regardless
   of the toggle. Thought now always renders a fixed square with visibly
   rounder corners (`rounded-[2rem]` vs the shared `rounded-2xl`). Only
   Scene reads the global store — implemented via a new aspect-source field
   on each node type's `BaseNodeConfig`, keeping the existing "one BaseNode,
   three thin wrappers" structure unchanged.
2. **Connection discoverability**: handles bumped 10px→14px with a
   permanent low-opacity visible state (not hover-only), a hover/focus state
   that grows further and recolors to that node type's own accent color, and
   a one-time (per-profile) tooltip hint on the two source handles ("Drag to
   connect to another node") shown once, then never again. `Shift+C`
   keyboard-connect is untouched. No new connection capability was added —
   multiple edges into/out of one node already worked.
3. **Persistent Undo/Redo**: a real button pair (not just the toast) now
   lives in the canvas chrome, wired to the already-built undo/redo
   mutations. This needed one small backend addition —
   `GET /books/{id}/undo-status` (`{can_undo, can_redo}`) — since no
   "is anything undoable" signal existed before. Bundled a real correctness
   fix found during design: `can_redo` now also verifies no *newer* action
   has happened since the undo (via the existing `sequence` column), so a
   persistent Redo button can't silently resurrect a stale action the way a
   several-seconds-lived toast never had the chance to.
4. **Script-book image attach fixed**: `SceneImagesSection` (multi-select
   attach, upload, reorder, make-cover — already fully built) now renders
   alongside the screenplay `ElementsEditor` for Movie Script / Short Film
   Script scenes too, instead of never rendering at all. Also added a
   tooltip on the "Attach existing" button explaining why it's disabled when
   no finalized images exist yet (previously disabled with zero explanation).
5. **SuggestionPanel removed from the node editor**: render call + import
   deleted from `node-editor.tsx`. The underlying feature
   (`suggestion-panel.tsx`, Phase 10's hybrid-search suggestions) is left in
   the tree, dormant — a real working capability, just no longer surfaced
   inside the node editor per explicit repeated request.
6. **Scoped UI/UX audit fixes**: image-load-error now shows a distinct
   `ImageOff` icon instead of looking identical to zero-images-attached;
   side-strip thumbnails are now clickable to open the node editor (traced
   xyflow's click/drag internals first — confirmed `stopPropagation` would
   have been the wrong fix here, since it would've broken the existing
   single-click-opens-editor and Shift-click-multi-select behavior; used
   `draggable={false}` instead to prevent the browser's native image-drag
   gesture from occasionally eating the click); an "or add nodes one at a
   time" caption links the empty-canvas templates to the manual "Add node"
   entry point; an accepted-image-format caption ("PNG, JPEG, WebP, or GIF")
   sits under the upload button; and the canvas dropdown's "Delete
   permanently"/"Remove from canvas" items now carry explanatory tooltips.
   Also caught and fixed a staleness bug while touching this copy: both
   delete-confirmation dialogs (the canvas card's and the node editor
   drawer's) still said "This cannot be undone" — stale as of Phase 11's
   undo/redo work — corrected to accurately describe the new Undo-based
   recovery window in both places.

One audit finding — shrinking each node's icon+label header row now that
shape also communicates type — was deliberately left as a noted follow-up
rather than forced into this round; it's a bigger visual change than the
"scoped, low-risk" bar the rest of this round held to.

## Verification

- Backend: `QUILLNIGHT_LLM_STUB=1 QUILLNIGHT_STT_STUB=1 pytest -q` (cwd
  `apps/sidecar`) — 390 passed, 2 failed (both the known pre-existing
  cross-module test-ordering failures, unrelated, unchanged since Phase 10).
- Frontend: `npm run build` / `npm run lint` (cwd `apps/desktop`) — both
  clean throughout, only pre-existing warnings.
- Manual/live confirmation of every visual/interaction change (shapes,
  handle styling, undo/redo buttons, script-book images, removed
  suggestions) is still pending from the user directly in the running app
  (dev server localhost:1420, sidecar 127.0.0.1:8756) — this session's
  Browser tool can't reliably screenshot or simulate every click here.
