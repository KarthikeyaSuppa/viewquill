# Entity Lifecycles

This doc exists because undocumented lifecycle gaps in interactive canvas/data entities
(creation, mutation, deletion, what else depends on them, undo/redo coverage) have slipped
through before — e.g. canvas edges (`SceneConnection`) shipped in Phase 2 with zero
undo/redo coverage despite node delete and node merge already having full coverage by
Phase 11, and it took a dedicated pass to even notice the gap. A per-entity reference that's
kept current is cheaper than re-deriving "what actually happens when this gets deleted" from
scratch every time a new feature touches it.

**Process rule: every phase or feature that creates, mutates, or adds undo/redo coverage
for an interactive entity must add or update that entity's entry here as part of being
"done" — not as an afterthought.** If `architect` scopes a task that touches an entity's
lifecycle, the task list should include updating this file; if `reviewer` is gating a
data-integrity-sensitive change, checking this file's "Known gaps" section for that entity
is part of the review.

---

## Template

Copy this shape for every new entity entry. Keep it bullet-scannable, not prose paragraphs.
Every claim must cite the actual file/line it was verified against — an unverified claim in
this doc defeats its purpose.

- **Creation**: which endpoint(s)/function(s) create it.
- **Mutation paths**: every function/endpoint that can change it after creation.
- **Deletion**: hard delete vs soft delete, which function, what happens to it physically.
- **Interactions & dependents**: what other tables/services/UI read or depend on this
  entity (FK relationships and their `ondelete` behavior, cascades, rendering, search
  index, etc.).
- **Undo/redo coverage**: which `UndoLog.action_type`(s) cover this entity's operations
  today, if any.
- **Known gaps**: anything genuinely missing or inconsistent — documented honestly, not
  smoothed over.

---

## Scene (canvas node)

The canonical node entity behind the Node Canvas (`apps/sidecar/app/models/orm.py:63-78`,
`Scene`). Canonical and shared across Books, same posture as Codex entries — a Book's
canvas only ever *links* to a Scene via `BookSceneLink`, it never owns one exclusively.

### Creation

- `POST /scenes` (`apps/sidecar/app/api/scenes.py:30-38`) → `scene_service.create_scene`
  (`apps/sidecar/app/services/scene_service.py:45-65`). Creates the bare `Scene` row
  (`node_type`, `title`, `description`, derived `word_count`) — not yet on any Book's
  canvas.
- `POST /books/{book_id}/scenes/{scene_id}` (`apps/sidecar/app/api/canvas.py:73-96`,
  "add scene to canvas") → `canvas_service.add_scene_to_canvas`
  (`apps/sidecar/app/services/canvas_service.py:62-91`). Doesn't create a `Scene` — links
  an *existing* one onto a Book's canvas via a new `BookSceneLink` row (idempotent: a
  second call for the same book/scene pair returns the existing link, per the
  `UNIQUE(book_id, scene_id)` constraint, `orm.py:104`).
- `POST /books/{dest_book_id}/scenes/{scene_id}/copy` (`apps/sidecar/app/api/canvas.py:189-200`)
  → `canvas_service.copy_scene` (`canvas_service.py:233-276`). The one canvas-side path that
  creates a brand-new `Scene` row (new UUID) — deep-copies `node_type`/`title`/`description`/
  `status`/`word_count` and every `ScreenplayElement`, then links the new scene onto
  `dest_book_id`. Source scene is never touched (additive, per the app's "conversions are
  additive, never destructive" rule).
- `merge_service.accept_merge` (`apps/sidecar/app/services/merge_service.py:47-191`) also
  creates a new `Scene` (step 2, line 95) as the *merged* result of 2+ source scenes — its
  own path, not `scene_service.create_scene`, but functionally another creation route worth
  knowing about since it's reachable from the canvas UI's AI-assisted merge flow.
- **Canvas node placement (frontend, PHASE13 Workstream D)**: when the toolbar "Add node"
  action or the `Shift+N` keyboard shortcut (`handleAddNode`/`handleAddNodeWithFocus`,
  `apps/desktop/src/components/canvas/canvas-panel.tsx`) fires the create call above, the
  new node's `canvas_x`/`canvas_y` are taken from the user's last left-click on empty
  canvas — `onPaneClick` (`handlePaneClick`) records that click's position via xyflow's
  `screenToFlowPosition` into a ref, and both creators read it. If the ref is empty (no
  pane click yet this session), both fall back to the original staggered offset
  (`80 + nodeCount * 32` on each axis) so node creation never throws with no click on
  record.

### Mutation paths

- `PATCH /scenes/{scene_id}` (`scenes.py:54-60`) → `scene_service.update_scene`
  (`scene_service.py:106-129`). Partial update of `title`/`description`/`status`/etc.;
  recomputes `word_count` when `description` changes; snapshots the pre-update
  `title`/`description`/`status` into a new `SceneRevision` row first
  (`_record_revision_if_changed`, `scene_service.py:76-104`) if any of those three fields
  actually changed.
- `PATCH /books/{book_id}/scenes/{scene_id}` (`canvas.py:98-109`) →
  `canvas_service.update_link` (`canvas_service.py:94-105`). Mutates only the
  **`BookSceneLink`** row (`canvas_x`/`canvas_y`/`color`) — never touches the `Scene` row
  itself. Listed here because it's the canvas drag/reposition path a reader would otherwise
  expect under "Scene mutation."
- `POST /scenes/{scene_id}/elements`, `PATCH /scenes/elements/{element_id}`,
  `POST /scenes/{scene_id}/elements/reorder` (`scenes.py:98-128`, `screenplay_service.py`) —
  structured screenplay content nested under a Scene. Explicitly documented in `scenes.py`
  (line 80-81) as **never** allowed to modify `scenes.description` — the two content
  representations coexist deliberately.
- `POST /books/{dest_book_id}/scenes/{scene_id}/move` (`canvas.py:166-186`) →
  `canvas_service.move_scene` (`canvas_service.py:211-230`). Re-links the *same* canonical
  Scene onto a different Book's canvas (optionally unlinking the source Book too); creates
  zero new `scenes` rows and never edits the `Scene` row's own columns.
- `merge_service.accept_merge` (`merge_service.py:47-191`) doesn't mutate a pre-existing
  Scene's fields either — it only ever reads sources' current title/description into a
  frozen `SceneMerge` snapshot (step 4) before archiving their links (step 5). The one row
  it actually writes fresh content into is the newly created merged `Scene` (step 2).

### Deletion

- `DELETE /scenes/{scene_id}` (`scenes.py:63-66`) → `scene_service.delete_scene`
  (`scene_service.py:200-224`) — **hard delete** of the `Scene` row itself, everywhere it's
  linked. Before deleting, it builds a reconstruction snapshot
  (`_build_delete_undo_payload`, `scene_service.py:143-197`) of the `Scene` row, every
  `BookSceneLink` referencing it, its `ScreenplayElement` rows, its `SceneRevision` history,
  and any `SceneMerge` rows referencing it — and writes that as an `UndoLog` tombstone
  (`action_type="delete_scene"`) in the **same transaction** as the delete
  (`scene_service.py:207-219`), so a rollback undoes both together. If the scene has no
  `BookSceneLink` at all (not on any Book's canvas), no `book_id` exists to file the
  `UndoLog` under, so no tombstone is written (`scene_service.py:168-169`) — this is
  currently only reachable via a direct service call, not the API, since the API always
  creates a link on add-to-canvas.
- `DELETE /books/{book_id}/scenes/{scene_id}` ("remove scene from canvas",
  `canvas.py:112-115`) → `canvas_service.remove_from_canvas` (`canvas_service.py:108-120`) —
  **hard delete of the `BookSceneLink` row only**. The canonical `Scene` row and its
  `ScreenplayElement` rows are explicitly never touched (module docstring,
  `canvas_service.py:5-13`, reiterated in the function's own docstring). This is the
  "unlink, the scene survives" operation, distinct from the scene-service delete above.
- In the frontend, both are wired and kept visually/textually distinct
  (`apps/desktop/src/queries/screenplay.ts:128-153` docstring): `useDeleteScene`
  (`screenplay.ts:143-153`, hits `DELETE /scenes/{id}`) backs both the canvas's keyboard
  Delete (`apps/desktop/src/components/canvas/canvas-panel.tsx:300-320`, comment explains the
  keyboard path deliberately uses the permanent-delete mutation, not the unlink one) and the
  node menu's "Delete permanently" `AlertDialog` action
  (`apps/desktop/src/components/canvas/nodes.tsx:432`); `useRemoveFromCanvas`
  (`apps/desktop/src/queries/canvas.ts:85-95`) backs a separate, less-destructive "remove
  from canvas" menu item (`nodes.tsx:360`).

### Interactions & dependents

FK relationships onto `scenes.id` (`apps/sidecar/app/models/orm.py`), verified against a
live SQLite session (`PRAGMA foreign_keys=ON`, matching `app/db/base.py:4-5,77`):

| Table | `ondelete` | Verified behavior on `DELETE scenes` |
|---|---|---|
| `ScreenplayElement.scene_id` (`orm.py:93-95`) | `CASCADE` | Rows deleted with the scene. |
| `BookSceneLink.scene_id` (`orm.py:108-110`) | `CASCADE` | Rows deleted with the scene. |
| `BookSceneOrder.scene_id` (`orm.py:167-169`) | `CASCADE` | Rows deleted with the scene — this is the shared Outline/Timeline mediator table, so a scene delete also silently drops its outline/timeline placement. |
| `SceneRevision.scene_id` (`orm.py:360-362`) | `CASCADE` | History rows deleted with the scene (captured into the undo snapshot first, see Deletion above). |
| `SceneMerge.merged_scene_id` / `.source_scene_id` (`orm.py:392-397`) | `SET NULL` | Row survives; only the pointer column nulls out — the frozen snapshot columns (`source_snapshot_title`/`_description`) are what's meant to survive. |
| `SceneConnection.source_scene_id` / `.target_scene_id` (`orm.py:130-131`) | **none specified** | **Verified: raises `sqlite3.IntegrityError: FOREIGN KEY constraint failed`** — deleting a Scene that has any canvas edge referencing it as source or target currently fails outright rather than cascading or nulling. See Known gaps. |
| `ContinuityFlag.scene_id` (`orm.py:319`) | **none specified** | **Verified: same `IntegrityError`** — a Scene with any open/dismissed/resolved continuity flag referencing it also blocks the delete. See Known gaps. |

Other dependents, not FK-enforced:

- **Search index** (`apps/sidecar/app/services/search_index_service.py`) — `scene_service`
  calls `upsert_entity("scene", ...)` on create (`scene_service.py:64`) and update
  (`scene_service.py:128`), and `delete_entity("scene", scene_id)` on delete
  (`scene_service.py:223`). `search_fts`/`embeddings` are SQLite virtual tables with no real
  FK, so there is no DB-level cascade for them — the module's own docstring
  (`search_index_service.py:15-24`) states these calls never raise/block the real save,
  logging and swallowing failures instead; a temporarily-stale row is repaired by
  `POST /search/backfill`.
- **Canvas rendering** — `canvas_service.get_canvas` joins `BookSceneLink`+`Scene` filtered
  to `BookSceneLink.archived_at IS NULL` (`canvas_service.py:41-49`) — an archived link
  (from a merge, see below) simply stops rendering as a node without any Scene-side change.
- **Continuity checker** (`continuity_service.py`, not itself modified by Scene CRUD) reads
  `Scene` rows to detect flags but is a read-only dependent from Scene's point of view aside
  from the FK above.

### Undo/redo coverage

`UndoLog.action_type` is constrained to exactly two values
(`orm.py:413-415`, `CheckConstraint("action_type IN ('delete_scene','merge_scenes')")`):

- **`delete_scene`** — written by `scene_service.delete_scene` (`scene_service.py:207-219`).
  Reversed by `undo_service._restore_delete_scene`/`_redo_delete_scene`
  (`apps/sidecar/app/services/undo_service.py:113-174`) — full hard reinsert/re-delete of
  the `Scene` row plus its captured `BookSceneLink`/`ScreenplayElement`/`SceneRevision` rows;
  `SceneMerge` rows aren't reinserted (they were never deleted, only nulled) — only their
  `merged_scene_id`/`source_scene_id` columns are restored.
- **`merge_scenes`** — written by `merge_service.accept_merge` (`merge_service.py:173-182`).
  Reversed by `undo_service._restore_merge_scenes`/`_redo_merge_scenes`
  (`undo_service.py:177-252`) — deliberately "soft": undo only ever toggles
  `BookSceneLink.archived_at` on the merged scene's link and each source's link back to its
  exact pre-merge snapshot; the merged `Scene` row and its `SceneRevision`/`SceneMerge`
  history are never deleted by either direction.
- Both are surfaced via `POST /books/{book_id}/undo` / `/redo` (`canvas.py:220-251`) and a
  discoverability toast with an Undo button on delete
  (`apps/desktop/src/components/canvas/canvas-panel.tsx:311-320`,
  `apps/desktop/src/queries/undo.ts`).

**Not covered by `UndoLog` at all** (confirmed by the two-value CHECK constraint above —
there is no third `action_type`):

- `canvas_service.remove_from_canvas` (unlink from a Book's canvas) — no `UndoLog` row is
  written anywhere in that function (`canvas_service.py:108-120`).
- `scene_service.update_scene` (ordinary field edits) — captured in `SceneRevision` history
  (browsable, read-only, `scene_service.py:132-140`) but not reversible via undo/redo.
- `screenplay_service`'s element create/update/delete/reorder.
- `canvas_service.move_scene` / `copy_scene`.

### Known gaps

- **`remove_from_canvas` hard-deletes instead of soft-deleting, inconsistent with the
  column that exists for exactly this purpose.** `BookSceneLink.archived_at`
  (`orm.py:115`) exists specifically so a link can be "removed" reversibly — and
  `merge_service.accept_merge` uses it exactly that way (archives sources'
  `BookSceneLink` rows, step 5, `merge_service.py:138-142`, later restored by undo). But
  `canvas_service.remove_from_canvas` (the ordinary "remove from canvas" menu action) does
  a plain `db.delete(link)` (`canvas_service.py:118`), never touching `archived_at` — so the
  same table has two different "this link is gone" representations depending on which code
  path removed it, and the hard-delete one has zero undo coverage (see above). This wasn't
  smoothed over during Phase 11 — it's a real, current inconsistency.
- **Deleting a Scene with an attached canvas edge or continuity flag currently 500s.**
  Verified directly against `scene_service.delete_scene` with a real `SceneConnection` edge
  and, separately, a real `ContinuityFlag` both pointing at the scene being deleted — both
  raise an unhandled `sqlite3.IntegrityError: FOREIGN KEY constraint failed` because
  `SceneConnection.source_scene_id`/`target_scene_id` (`orm.py:130-131`) and
  `ContinuityFlag.scene_id` (`orm.py:319`) declare no `ondelete` clause, and this app runs
  with `PRAGMA foreign_keys=ON` (`app/db/base.py:77`), which enforces SQLite's default
  (effectively RESTRICT) immediately on the `DELETE FROM scenes` statement. No route or
  global handler in `app/main.py` catches `IntegrityError`, so this currently surfaces to
  the frontend as a bare 500, not a clean "can't delete, still connected" message — and it
  means the keyboard-Delete / "Delete permanently" path (which calls `delete_scene`
  directly, see Deletion above) can fail outright for any node that still has an edge or an
  open continuity flag on it, with no `UndoLog` row written since the transaction never
  commits.
- **No undo coverage for unlink, screenplay elements, move, or copy** — see the "Not covered"
  list above. Not necessarily wrong (unlink is explicitly the "safe" operation, and elements/
  move/copy are lower-stakes than a permanent delete or merge), but undocumented until now.

---

## SceneConnection (canvas edge)

The graph-edge entity behind the Node Canvas's connections between Scenes
(`apps/sidecar/app/models/orm.py:119-139`, `SceneConnection`, table `scene_connections`).
Scoped per Book (`book_id`, `ForeignKey("books.id", ondelete="CASCADE")`,
`orm.py:129`) — unlike `Scene`, it is not a canonical shared entity; an edge only ever
belongs to the one Book it was drawn on.

### Creation

- `POST /books/{book_id}/edges` (`apps/sidecar/app/api/canvas.py:127-145`) →
  `canvas_service.create_edge` (`apps/sidecar/app/services/canvas_service.py:158-206`).
  Requires both `source_scene_id`/`target_scene_id` to already exist (`_require_scene`,
  `canvas.py:132-133`). If `connection_type == "sequence"`, resolves `sequence_weight` via
  `_next_sequence_weight` (`canvas_service.py:147-155,170-173`) unless the caller supplied
  one explicitly; any other `connection_type` (or none) forces `sequence_weight` to `None`
  (`canvas_service.py:174-175`).
- **Drag direction (fixed 2026-08-08).** The canvas previously typed handles by position —
  `top`/`left` were `type="target"`, `bottom`/`right` `type="source"`
  (`components/canvas/nodes.tsx` `NodeHandles`, mirrored in `screenplay-node.tsx`) — with no
  `connectionMode` set. In xyflow, starting a drag at a *target* handle and dropping on a
  *source* handle emits the `Connection` **reversed** (`connection.source` = the node dropped
  on), so the stored direction only matched the user's gesture when they happened to start
  from bottom/right, and an arrow could never terminate on a node's bottom/right side. All
  four handles are now `type="source"` with `connectionMode={ConnectionMode.Loose}` on
  `<ReactFlow>`, so the drag gesture alone determines source→target. Handle **ids** were
  deliberately left as `top`/`left`/`bottom`/`right` because existing `scene_connections`
  rows store those strings. Loose mode makes same-node drags reachable, so an
  `isValidConnection` guard (`canvas-panel.tsx`) rejects `source === target` self-loops,
  which the DB has no CHECK against.
- Writes an `UndoLog` row (`action_type="create_edge"`, full `_row_to_dict(edge)` snapshot,
  `canvas_service.py:195-204`) — but verified this is **not** literally the same transaction
  as the edge insert: the edge is inserted and committed first (`db.add(edge)` /
  `db.commit()` / `db.refresh(edge)`, `canvas_service.py:187-189`), then the `UndoLog` row is
  added and committed separately (`canvas_service.py:205`). The function's own comment
  (`canvas_service.py:190-194`) explains why — the snapshot needs the edge's real
  DB-assigned `id` and resolved `sequence_weight`, which only exist after the first commit —
  and says it "mirrors `scene_service.delete_scene`'s 'same transaction as the mutation'
  precedent **as closely as possible**," i.e. deliberately not claiming full atomicity. In
  practice this leaves a narrow window where a crash between the two commits would leave a
  committed edge with no undo coverage for it.

### Mutation paths

- `PATCH /edges/{edge_id}` (`canvas.py:148-154`) → `canvas_service.update_edge`
  (`canvas_service.py:209-243`). Partial update — only keys present in the payload change.
  Special-cased side effect on `connection_type` (`canvas_service.py:214-218`): setting it to
  `"sequence"` auto-assigns a fresh `sequence_weight` via `_next_sequence_weight` unless the
  caller also supplied one (`values.setdefault(...)`); setting it to anything else forces
  `sequence_weight` back to `None`. This means a bare `{"connection_type": "reference"}`
  payload silently clears any existing `sequence_weight` too.
- Captures `before`/`after` dicts scoped to exactly the keys being changed
  (`canvas_service.py:220-228`) — which, per the comment there, includes `sequence_weight`
  even when the caller only passed `connection_type`, since it's set/cleared as that side
  effect. Writes an `UndoLog` row (`action_type="update_edge"`,
  `payload={"edge_id", "before", "after"}`, `canvas_service.py:232-241`) **only if
  `before != after`** (`canvas_service.py:231`) — a no-op update (every changed key
  round-tripping to its own current value) writes no undo row. Like `create_edge`, the row
  update and its conditional `UndoLog` write land in a **single** `db.commit()`
  (`canvas_service.py:245`) — re-verified 2026-08-08. (This bullet previously described two
  separate commits; that was fixed in the Phase 11 follow-up already recorded under
  SceneConnection › Known gaps, and the description here had gone stale.)
- **Reverse direction** (frontend, added 2026-08-08): the selected-edge toolbar in
  `components/canvas/canvas-panel.tsx` (`handleReverseEdge`) issues ONE `PATCH /edges/{id}`
  swapping `source_scene_id`↔`target_scene_id` **and** `source_handle`↔`target_handle`
  together. No new endpoint — `EdgeUpdate` (`schemas.py:277-286`) already accepted all four
  fields; the frontend's `UpdateEdgeInput` (`queries/canvas.ts`) was the only thing blocking
  it. Undo works because `_restore_update_edge` (`undo_service.py:340-354`) replays
  `payload["before"]` generically over whatever keys changed, so it is not limited to the
  `connection_type` toggle it was originally written for — verified live: reverse → undo
  restores the original source/target.
- **Label / comment** (frontend, added 2026-08-08): the same toolbar edits
  `scene_connections.label` via `PATCH /edges/{id}` on blur/Enter only (never per keystroke);
  an emptied field sends `null`. `ink-edge.tsx:89-103` already rendered the label through
  `EdgeLabelRenderer` — only the write path was missing. Also `UndoLog`-covered via the same
  `update_edge` before/after path above.

### Deletion

- `DELETE /edges/{edge_id}` (`canvas.py:157-160`) → `canvas_service.delete_edge`
  (`canvas_service.py:246-265`) — **hard delete**, `db.delete(edge)` (`canvas_service.py:263`).
  Confirmed `SceneConnection` has no soft-delete column at all (`orm.py:119-139`'s full
  column list — no `archived_at`, unlike `BookSceneLink.archived_at`, `orm.py:115`).
- Confirmed by grepping `apps/sidecar/app/models/orm.py` for any `ForeignKey` referencing
  `scene_connections.id` (zero matches — the only occurrences of `scene_connections` in the
  file are its own table's definition) that **no other table has a child FK onto a
  `SceneConnection` row**. `undo_service._restore_delete_edge`'s docstring states this
  explicitly: "simpler [than `_restore_delete_scene`] since no other table has a
  `ForeignKey` onto `scene_connections.id` (confirmed against `app/models/orm.py`), so
  there are no cascading children to reattach" (`undo_service.py:293-297`). This is what
  lets deletion use a plain snapshot-and-reinsert undo pattern with no parent-before-children
  ordering concerns, unlike `Scene`'s delete undo which must reinsert the `Scene` row first,
  then its `BookSceneLink`/`ScreenplayElement`/`SceneRevision` children (see Scene's Deletion
  section above).
- Unlike `create_edge`/`update_edge`, this one genuinely is a single transaction: the
  `UndoLog` row (full pre-delete `_row_to_dict(edge)` snapshot) is added *before* the delete,
  and both the add and the `db.delete(edge)` share one `db.commit()`
  (`canvas_service.py:253-264`) — matching the comment there ("both writes commit together
  in the single `db.commit()` below").

### Interactions & dependents

No FK dependents (see Deletion above) — every dependency here is rendering-only:

- `apps/desktop/src/components/canvas/ink-edge.tsx` — the `InkEdge` component's visual
  arrowhead/thickness are driven by `data?.sequenceWeight != null`
  (`ink-edge.tsx:51`): a non-null `sequenceWeight` renders a thicker stroke (`strokeWidth`
  2.5 vs 1.75), higher opacity (0.75 vs 0.55), and the `--chart-4` theme token instead of
  `--muted-foreground` (`ink-edge.tsx:69-74`). The component's own docstring
  (`ink-edge.tsx:24-33`) notes "Plain edges (the overwhelming majority today, since nothing
  writes `sequence_weight` yet) are completely unaffected."
- `apps/desktop/src/components/canvas/canvas-panel.tsx`'s edge-mapping — **verified this is
  a plain `useEffect`, not a `useMemo`** (`canvas-panel.tsx:248-271`), that reconciles local
  xyflow edge state from the server `canvas` query on every refetch. It sets `markerEnd` to
  `{ type: MarkerType.ArrowClosed, color: 'var(--chart-4)' }` when `edge.sequence_weight !=
  null`, else `undefined` (`canvas-panel.tsx:266-267`) — built here rather than inside
  `InkEdge` itself because, per the comment (`canvas-panel.tsx:260-265`), xyflow only accepts
  the marker *object* at the `Edge`-object level; by the time it reaches an edge component's
  props as `markerEnd` it's already a resolved marker-id string.
- **`sequence_weight` is explicitly NOT part of `BookSceneOrder`'s chronological ordering** —
  confirmed by the actual ORM column comment: `orm.py:136-138` reads verbatim: `"# Rendering/
  sort hint only: NULL = not part of the lineage view (default for all existing edges).
  Distinguishes lineage/sequence edges from free-form connections. Unrelated to
  BookSceneOrder's chronological ordering."` `_next_sequence_weight`'s own docstring
  (`canvas_service.py:147-151`) repeats this: "`sequence_weight` is intentionally independent
  of `BookSceneOrder`'s chronological ordering (Phase 11 decision) — this is purely a canvas
  edge-directionality marker." Two independent ordering systems by design, neither touches
  the other's storage or computation.

### Undo/redo coverage

`UndoLog.action_type`'s CHECK constraint (`orm.py:413-419`) was widened from the original
two values to five: `CheckConstraint("action_type IN ('delete_scene','merge_scenes',
'create_edge','delete_edge','update_edge')")`. The widening migration is
`apps/sidecar/app/db/migrations/versions/9694678ecc85_widen_undo_log_action_type_check_for_edges.py`
(revision `9694678ecc85`, `down_revision = 'c4c1f0a29f3a'`, dated 2026-08-02) — confirmed this
is the current alembic head for this lineage (no later revision revises it). Its `upgrade()`
rebuilds `undo_log` via `op.batch_alter_table(..., recreate='always')` to drop and recreate
the CHECK (SQLite can't `ALTER` a CHECK in place); its `downgrade()` explicitly deletes any
`'create_edge'`/`'delete_edge'`/`'update_edge'` rows first so the narrower constraint doesn't
fail on a dirty table.

- **`create_edge`** — written by `canvas_service.create_edge` (`canvas_service.py:195-204`,
  see the two-commit caveat under Creation above). Reversed by
  `undo_service._restore_create_edge`/`_redo_create_edge` (`undo_service.py:264-290`) — undo
  deletes the edge outright (it didn't exist before the action), redo re-inserts the exact
  captured row (`SceneConnection(**payload["edge"])`, `undo_service.py:289`) including its
  original `id` and resolved `sequence_weight`, never recomputed.
- **`delete_edge`** — written by `canvas_service.delete_edge` (`canvas_service.py:253-262`,
  true single-transaction case, see Deletion above). Reversed by
  `undo_service._restore_delete_edge`/`_redo_delete_edge` (`undo_service.py:293-315`) — undo
  re-inserts the exact pre-delete snapshot, redo deletes it again.
- **`update_edge`** — written by `canvas_service.update_edge` (`canvas_service.py:232-241`,
  only when `before != after`). Reversed by
  `undo_service._restore_update_edge`/`_redo_update_edge` (`undo_service.py:318-346`) — a
  before/after toggle on just the changed columns, the same shape
  `_restore_merge_scenes`/`_redo_merge_scenes` use for Scene merges.
- All three are dispatched from the same `undo_last_action`/`redo_last_action` entry points
  (`undo_service.py:349-398`) and surfaced via the same `POST /books/{book_id}/undo` /
  `/redo` endpoints Scene's `delete_scene`/`merge_scenes` coverage uses
  (`canvas.py:236-260`) — one shared undo/redo stack per Book across both entities, not a
  separate one for edges.

### Known gaps

Both gaps below were found during this doc's own drafting, then confirmed and fixed by the
mandatory Opus reviewer pass on this feature (2026-08-02) — kept here as resolved history
rather than deleted, since the doc's whole point is a durable record, not just a live-issue
tracker.

- **~~Missing FK-target guard on `_redo_create_edge`/`_restore_delete_edge`~~ — fixed.**
  Both now check `db.get(Scene, ...)` on the edge's `source_scene_id`/`target_scene_id`
  before writing, raising `ValueError(UNDO_TARGET_ROW_MISSING)` (the same pattern every
  other handler in this file already used) instead of letting a raw
  `sqlite3.IntegrityError` reach the API as an unhandled 500. The reviewer also traced a
  concretely reachable repro path through `redo_last_action` and found it didn't apply the
  same "a newer action exists ⇒ nothing to redo" staleness check `get_undo_status` already
  computed — fixed in the same pass (`undo_service.py`'s `redo_last_action` now applies that
  check before dispatching to any handler), which also closes the equivalent pre-existing
  gap for `delete_scene`/`merge_scenes` redo, not just edges.
- **~~`create_edge`/`update_edge` not single atomic transactions~~ — fixed.** Both now build
  the full row/diff values before a single `db.commit()`, matching `delete_edge`'s
  already-correct single-commit shape — no more window where a crash between two commits
  could leave a committed data change with no corresponding undo row.

---

## Sample Library (seeded demo content)

Not a table — a *provenance class* spanning ordinary rows in `books`, `scenes`,
`codex_entries`, `images` and every join table between them, written once by
`apps/sidecar/app/services/sample_library/seeder.py`'s `seed_sample_library`. It gets an
entry here because it is the only code path that creates a full multi-Book graph in one
shot, and because the rows it writes are otherwise **indistinguishable from user data** —
which is exactly the property that makes its guard and its non-participation in undo/redo
load-bearing. Established in Phase 14 (`PHASE14.md`).

The package is three files: `content.py` (pure frozen-dataclass data, no DB imports, with a
module-level `_validate()` that raises at import time on a bad key or illegal enum value),
`images.py` (deterministic Pillow placeholder art, pure functions returning PNG bytes), and
`seeder.py` (the only part that touches the DB).

### Creation

- `app/main.py`'s `lifespan`, immediately after `seed_structure_templates` — that ordering
  matters because each sample Book resolves its `structure_template_id` by template *name*.
  Wrapped in the same non-fatal `try/except` as the template seeder: a failed seed logs and
  leaves the app usable-but-empty, never blocking startup.
- **Test opt-out**: `QUILLNIGHT_SKIP_SAMPLE_SEED=1` makes `seed_sample_library` return `0`
  immediately, read at *call* time (not import time). `tests/conftest.py` sets it for the
  whole pytest session — the suite shares one SQLite DB that starts empty, which is exactly
  the "fresh install, please seed" condition, so without this the first module to enter
  `TestClient(app)` seeded 4 Books into everyone's database and broke every test asserting
  an empty library. Same `os.environ.get(...) == "1"` convention as `QUILLNIGHT_LLM_STUB`
  and `QUILLNIGHT_STT_STUB` rather than a third mechanism.
- **Guard (both conditions required)**: skips and returns `0` unless the global `AppSetting`
  row (`user_id IS NULL`) with `key == "sample_library"` is absent **and** the `books` table
  is empty. The marker is what stops the samples resurrecting after the user deletes them;
  the empty-table check is the belt-and-braces half that stops a seed landing in a real
  library whose marker was lost (e.g. after a `restore_backup`).
- **Marker written last**, only after every other write succeeds:
  `{"version": 1, "seeded_at": "<iso>", "book_ids": [...]}`. Deliberately *not* added to
  `settings_service.DEFAULT_SETTINGS` or `PER_USER_KEYS` — it is per-install, not
  per-profile, and `get_all_settings` already merges every global row, so the frontend reads
  it through the existing `GET /settings` with no API change (`library-screen.tsx` uses it
  to render the "Sample" badge).
- **Edges are written directly via ORM, NOT through `canvas_service.create_edge`** — that
  helper also writes an `UndoLog` row, which would arm the canvas Undo button to delete
  seeded content on a Book the user has never edited. Sample Books start with an empty undo
  stack by construction.
- **Scene `status` is set directly on the ORM object, NOT via `scene_service.update_scene`**
  — that function snapshots a `SceneRevision` stamped `manual_edit` on every status change,
  which would fabricate junk history. `SceneRevision` rows are instead hand-built from
  `content.REVISIONS` with `parent_revision_id` chained, which is also the only way to
  exercise the `enhance_accept`/`ai_merge`/`restore` change sources (`update_scene` can only
  ever produce `manual_edit`).
- Scenes and codex entries *are* created through `scene_service.create_scene` /
  `codex_service`, so `search_index_service.upsert_entity` populates `search_fts` for free.
  Its embedding half fails and is swallowed on this machine (no Ollama) — expected, non-fatal.

### Mutation paths

None of its own. Once seeded, every row is an ordinary row: the sample Books, scenes, codex
entries and images are edited, renamed, converted, enhanced and re-ordered through exactly
the same endpoints as user-created content. There is no "sample mode" branch anywhere in the
services — the marker is read-only metadata used for the badge and the seed guard, and is
never consulted on a write path.

### Deletion

- No dedicated deletion path. `DELETE /books/{book_id}` removes a sample Book like any
  other; because `scenes`/`codex_entries`/`images` are canonical and deliberately survive a
  Book delete (`api/books.py`'s module docstring), deleting all four sample Books leaves the
  seeded scenes, codex entries and images behind as orphans, same as it would for user data.
- The marker is **not** cleared on delete, and that is intentional: it is what makes deletion
  stick across restarts.
- `apps/sidecar/scripts/reset_library.py` is the full wipe (dev tool, `--yes` required,
  snapshots first, preserves `users`/`app_settings`/`structure_templates`). Note it preserves
  `app_settings`, so it also preserves the marker — a wipe alone will *not* cause a re-seed;
  the `sample_library` row must be deleted too.

### Interactions & dependents

Everything the four Books touch, which is close to the whole schema — that breadth is the
point of the phase. `books` (+ `cover_image_id` → `images`), `chapters`,
`book_scene_links` (canvas position, incl. one `archived_at` row), `book_scene_order`
(outline + timeline, incl. a deliberate flashback where the two orders disagree),
`scene_connections` (all five `connection_type`s plus one NULL), `screenplay_elements`
(all eight `element_type`s), `codex_entries` (all four `entry_type`s) with
`book_codex_links`/`codex_scene_links`/`codex_relationships`/`codex_arc_states`, `images`
(both buckets) with `image_tags`/`entity_images` (all three `entity_type`s),
`continuity_flags` (every enum value), `scene_revisions` (all four `change_source`s), and
`search_fts` via the create-path indexing above.

Two rows are intentionally shared to exercise the canonical-entity model: one `Scene` linked
to two Books' canvases at different `canvas_x/y`, and one `CodexEntry` in two Books'
rosters.

### Undo/redo coverage

**None, by design.** Seeding writes zero `UndoLog` rows (see the `create_edge` note above),
so the canvas Undo/Redo buttons are correctly disabled on a freshly-seeded Book. Once the
user edits a sample Book, its scenes and edges get normal undo coverage through the usual
`delete_scene`/`merge_scenes`/`create_edge`/`delete_edge`/`update_edge` action types — there
is nothing sample-specific about undo after the first user action.

### Known gaps

- **Seeding is not a single transaction.** `scene_service.create_scene` and
  `images_service.save_image` commit internally, so a failure partway cannot be rolled back
  cleanly. The seeder does best-effort cleanup (deleting Books created so far plus the
  global scenes/codex/images it made) and never writes the marker on failure, so a retry on
  the next boot is possible — but a crash at the wrong moment can leave orphaned canonical
  rows behind.
- **Orphaned canonical rows after Book deletion.** Deleting all four sample Books from the
  UI leaves their scenes, codex entries and image files on disk with no Book referencing
  them, and no UI surfaces them for cleanup. This is pre-existing canonical-entity behavior,
  not new — but sample content makes it easy to hit on a fresh install.
- **`reset_library.py` preserves the marker**, so "wipe and re-seed" is a two-step operation
  (documented in `PROJECT-MAP.md` §10). Arguably the script should offer a `--reseed` flag.
- Embeddings are not generated on this machine (no Ollama), so seeded content is findable by
  FTS keyword search but not by semantic similarity until `POST /search/backfill` is run on
  the ASUS TUF F15.
