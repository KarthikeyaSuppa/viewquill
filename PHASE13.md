# Phase 13 — Character & Node-Editor Redesign

Status: In progress (started 2026-08-02)

## Why

Three Canvas/Codex rough edges plus a governance ask, all from a direct user
directive (see the approved plan `~/.claude/plans/purrfect-crunching-wave.md`):

1. The **Characters tab** shipped a Gantt "Timeline" view the user doesn't want,
   and its "Map" view could *show* character relationships but gave no way to
   *draw* them.
2. The **Canvas Codex** was a cramped floating bottom-left card overlapping nodes.
   The user wants it as a real left **sidebar drawer**, entries shown as **circles**.
3. The **node editor** should always show an auto-resizing Description with the
   screenplay elements *and* a new **circular character-chip strip** beneath it;
   Title should get an AI "generate-from-description" enhance; Description needs a
   read-only **version History** (GitHub-style); new nodes should appear **where the
   user last clicked**.
4. **Governance:** author a strict protected-features doc (`docs/16`) the user can
   only unlock with the keyword `spiderman`, plus a character-flow explainer
   (`docs/17`), and wire them into the repo Hard-rules.

Decisions locked with the user before build:
- Character chips live **in the node editor, under the description**.
- The screenplay **"Character" cue element is kept** — it's required for Fountain/FDX
  export and is a *different* concept from a Codex character (documented in `docs/17`).
- Node editor uses the unified **"Description always visible, rest beneath"** layout.
- History **reuses existing `scene_revisions`** snapshots — no new storage, read-only.

Model routing (CLAUDE.md): opus planned → `builder` (sonnet) implements scoped tasks →
`reviewer` (opus) gates the AI-seam / relationship-writer tasks → demo in main session.
LLM code is written ready-to-run and **stub-verified only** (`QUILLNIGHT_LLM_STUB=1`);
this machine never runs real models.

## Workstream A — Characters tab cleanup + editable Map

1. **Remove Timeline** (`components/codex/characters-panel.tsx`; delete
   `character-scene-timeline.tsx`) — drop the `'timeline'` view mode, its toggle, and
   the dead timeline data plumbing (`useCanvas`/`useTimeline`/`buildRows`/`orderedScenes`).
2. **Editable Map** (`character-relationship-graph.tsx`) — `nodesConnectable`, an
   `onConnect` → relationship-type picker → `useCreateRelationship`; `onEdgesDelete` →
   `useDeleteRelationship`; invalidate `['book-characters', bookId]` after writes. Reuse
   the `RELATIONSHIP_TYPES` list from `codex-entry-dialog.tsx` (exported, not duplicated).

## Workstream B — Canvas Codex → left sidebar drawer + circular chips

3. `components/canvas/codex-panel.tsx` — dock left, full-height, scrollable drawer;
   entries rendered as circular avatar/initials chips in a wrapping layout; link (to the
   selected node) / edit / delete preserved. Logic unchanged; presentation only.

## Workstream C — Node editor (`components/canvas/node-editor.tsx`)

4. **Unified body** — Description always visible + auto-resizing; screenplay elements
   (script books, "Character" cue kept) beneath; character chips beneath that. `bookType`
   forwarded `book-screen.tsx` → `CanvasPanel` → `NodeEditor`.
5. **Title Enhance** — Sparkles control fixed on the left of the Title field; new
   `'title'` enhance mode (`prompt_builder.py` + `schemas.py` + `enhance.ts`) turns the
   description into a title; Accept writes the Title field only (never auto-overwrites).
6. **Description Enhance + Undo/Redo** — keep the `EnhanceDiff` Accept/Reject seam; after
   Accept, surface `showUndoToast(undo, redo)` (the existing delete-flow pattern).
7. **Description History** — a History button opens a read-only, copyable, version-by-version
   diff view over `useSceneRevisions(sceneId)`, reusing the `enhance-diff.tsx` differ. No restore.
8. **Character chips** — circular chips (first 3 letters/avatar) from `useSceneCodex`
   filtered to `character`, wrapping into rows, with a circular **Add character** button
   after the last chip (link-existing via `useLinkCodexToScene` or create+link); click a
   chip → `CodexEntryDialog`; unlink via `useUnlinkCodexFromScene`.

## Workstream D — Node created at last click position

9. `components/canvas/canvas-panel.tsx` — `onPaneClick` stores
   `screenToFlowPosition(...)`; `handleAddNode`/`handleAddNodeWithFocus` use it for
   `canvas_x`/`canvas_y` (stagger fallback). Update the Scene entry in
   `docs/15-ENTITY-LIFECYCLES.md`.

## Governance (Workstream E)

10. `docs/16-PROTECTED-FEATURES.md` (strict, `spiderman`-locked), `docs/17-CHARACTER-FLOW.md`
    (explainer), Hard-rule bullets wired into `CLAUDE.md` + `PROJECT-MAP.md §9`.

## Reviewer gate

- Title mode + Title/Description Accept write paths — verify the never-silently-overwrite seam.
- Map relationship create/delete — verify from/to ids + cache invalidation.

## Verification

- Frontend `npm run dev --prefix apps/desktop` (:1420) demo per the plan; `npm run build`
  (tsc) + `oxlint` clean. Backend `QUILLNIGHT_LLM_STUB=1` + `pytest` (title-mode test).

## Follow-up iteration (2026-08-02) — user-directed, NOT yet `spiderman`-locked

Two further changes the user asked for after the first pass landed. Per the user these are
still being iterated and are only to be locked into `docs/16-PROTECTED-FEATURES.md` once the
user says the keyword `spiderman` (not said yet).

1. **Canvas node action row** (`components/canvas/nodes.tsx`) — removed the left-hand
   Enhance ✨ button; **Duplicate** now sits on the left, the **⋯** menu stays on the right.
   Enhancing still lives in the node editor's Title/Description fields (`node-editor.tsx`).

2. **Characters-tab Map → read-only D3-style graph** (`character-relationship-graph.tsx`) —
   the interactive React Flow map was replaced with a read-only, D3-style **circular
   node-link** visualization (curved swoosh edges, hover-highlight, tooltip, relationship-type
   controls, theme-token colors). Relationships are now created/edited **only** in each
   character's Relationships tab (`codex-entry-dialog.tsx` RelationshipsTab). Clicking a node
   opens that character's editor. `docs/17-CHARACTER-FLOW.md` updated to match.

   ✅ **RECONCILED (2026-08-02, unlocked with `spiderman`).** The user approved and locked
   these changes. `docs/16-PROTECTED-FEATURES.md` was updated: **P9** now describes the
   read-only D3-style relationship map, and two new entries were added — **P11** (character
   relationships are created/edited only in the Relationships tab, the single writer path) and
   **P12** (canvas node action row: Duplicate left / ⋯ right / no inline Enhance). No
   divergence remains; the earlier "do not self-heal" caveat no longer applies.
