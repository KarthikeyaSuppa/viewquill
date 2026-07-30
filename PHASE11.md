# Phase 11 — Canvas lifecycle overhaul + cross-cutting bug fixes

Status: Workstream A done (2026-07-30). Workstream B (git-tree ordering,
revision history, AI-assisted merge, undo/redo) designed, not yet built.

## Why

Live use of the app (Phase 10 / UI-Effects 1&2 built a lot of new surface
fast) surfaced real regressions and pre-existing gaps: missing cover images
on canvas nodes, a two-click delete bug, an un-scrollable node editor drawer,
zoom making node actions hard to click, a leftover Phase-2 MVP Codex
quick-panel with no traits field duplicating the newer full editor, a
systemic dialog-height bug beyond just Help, and no way to reuse a character
across Books despite the backend already supporting it. The user also asked
for a much bigger idea: treat the canvas like a git tree (ordered lineage,
commit-like history per scene, AI-assisted multi-node merge, undo/redo for
merges and deletions). Full plan, root-cause detail, and the Opus design for
Workstream B: see the plan this phase was built from (superseded by this
file once done — see git history if needed) and the task list below.

Their earlier project (VIBE, github.com/KarthikeyaSuppa/VIBE) was checked
for reusable concepts before designing Workstream B: it has a character-
relationship graph (NetworkX) but no git-like history, ordering system, or
undo/redo — nothing structural to port, Workstream B is a from-scratch
design for this app.

## Workstream A — bug fixes (done)

1. **Node cover-image loading state** (`nodes.tsx`) — `BaseNode` now
   handles `isLoading`/`isError` from `useEntityImages` (shows a `Skeleton`
   while loading instead of jumping straight to the empty placeholder,
   which previously made nodes with real images look like they had none
   during a cold load or transient error).
2. **Delete-reopens-panel bug** (`nodes.tsx`) — the in-card delete
   `AlertDialogAction` now calls `event.stopPropagation()`, matching the
   existing pattern on Duplicate/the `⋯` trigger, so deleting a node no
   longer bubbles into React Flow's `onNodeClick` and reopens the
   NodeEditor drawer mid-deletion.
3. **Dialog height — systemic fix for the two worst offenders**
   (`codex-entry-dialog.tsx`, `reading-comfort-wizard.tsx`) — both had
   zero vertical bound on `DialogContent` (only width). Applied the same
   `max-h-[85vh] overflow-y-auto` pattern already proven in
   `image-detail.tsx`. `help-guide.tsx`/`continuity-panel.tsx` were a
   separate, already-partially-bounded pattern, handled next.
4. **`help-guide.tsx`'s inner scroll region** — its `ScrollArea` was
   hardcoded to `h-[52vh]`, sized independently of how much space the
   header/tabslist actually consumed, able to overflow the dialog's own
   `max-h-[85vh]` cap on short viewports. Changed to `h-full` so it fills
   exactly the remaining space in its already-correctly-bounded
   `TabsContent` parent. (`continuity-panel.tsx` was checked and found
   already correct — no `Tabs` structure, its `ScrollArea` was already
   `min-h-0 flex-1` — no change needed there.)
5. **NodeEditor drawer couldn't scroll to see all elements** — confirmed
   root cause: the classic flexbox `min-h-0` footgun. `node-editor.tsx`'s
   `<ScrollArea className="flex-1">` had no `min-h-0`, so its default
   content-based `min-height: auto` let it grow to fit everything instead
   of clamping to the drawer's bounds and scrolling internally — content
   (including the Save button and delete footer) overflowed invisibly
   instead of being reachable via scroll. Fixed: `flex-1 min-h-0`.
6. **Canvas zoom + hit targets** (`canvas-panel.tsx`, `nodes.tsx`) — added
   explicit `minZoom={0.4}`/`maxZoom={1.5}` (tighter than xyflow's 0.5–2
   default) and bumped the node action-row buttons (Enhance/Duplicate/⋯)
   from the `icon` to the existing `icon-lg` shadcn size variant, so
   they're easier to hit at low zoom.
7. **Retired the old in-canvas Codex quick-panel's inline forms**
   (`codex-panel.tsx`) — this bottom-left floating panel was still the
   Phase-2 MVP version (name + summary only, no traits field at all, per
   its own docstring), and was found to actually have **three parallel
   create/edit paths** (a bespoke inline create form, a bespoke inline
   edit mode, and a partially-wired path to the full `CodexEntryDialog`).
   Consolidated to one: "+ New" and "Edit" (Pencil) now both open the same
   full `CodexEntryDialog` used by the Characters tab (traits,
   relationships, custom fields, images, arc states) — no more
   name+summary-only dead-end anywhere in the app. This is very likely
   also the fix for the reported "characters overlapping, can't add more
   traits" screenshot, since that panel's traits field never existed at
   all until now (there's simply no bespoke narrow form left to overlap).
   Kept unchanged: the scene link/unlink toggle and delete action, which
   are genuinely canvas-specific and useful.
8. **Cross-book character library / attach-existing flow**
   (`characters-panel.tsx`) — the backend already fully supported reusing
   a character across Books (`CodexEntry` has no `book_id`, `GET /codex`
   already returns every entry ever created, `POST /codex/{id}/books/{id}`
   already links an existing entry to a Book) but the frontend never
   exposed either. Added an "Attach existing" button next to "Add
   character" opening a searchable dialog (same primitive as the global
   `Ctrl+K` search) over every character ever created, excluding ones
   already linked to the current Book — selecting one attaches it with no
   backend changes needed.

## Workstream B — canvas node lifecycle overhaul (designed, not built)

Full design (Opus pass) covers: no third ordering concept (canvas edges
stay free-form, chronological order stays in `BookSceneOrder`, only a new
nullable `SceneConnection.sequence_weight` for lineage-styled edges); a
lightweight append-only `scene_revisions` + `scene_merges` history (not
literal git — pre-image snapshots + merge-provenance rows, enough to render
a per-node commit list); AI-assisted merge reusing the Enhance seam exactly
(`build_merge_prompt`, `POST /llm/merge-scenes`, `enhance-diff.tsx` reused
verbatim for Accept/Reject, never silent); and scoped (not global) undo/redo
via one `undo_log` table + `BookSceneLink.archived_at` soft-delete, surfaced
as an undo-toast after any delete or merge-accept — which also subsumes both
known delete-consistency bugs (keyboard-delete currently only unlinks
instead of permanently deleting, unlike the confirmed-dialog path). 17-task
backend→frontend build list, not started — next up.

## Verification (Workstream A)

- Backend: `QUILLNIGHT_LLM_STUB=1 QUILLNIGHT_STT_STUB=1 pytest -q` (cwd
  `apps/sidecar`) — 351 passed, 2 failed (both the known pre-existing
  cross-module test-ordering failures documented since Phase 10, unrelated
  — Workstream A made no backend changes).
- Frontend: `npm run build` / `npm run lint` (cwd `apps/desktop`) — both
  clean, only pre-existing warnings.
- Manual/live confirmation of each fix is still pending from the user
  directly in the running app (dev server localhost:1420, sidecar
  127.0.0.1:8756) — this session's Browser tool can't reliably screenshot
  or simulate every click here, so live confirmation continues to depend
  on the user checking the app themselves, per the established pattern
  this session.
