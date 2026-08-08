# Character Flow (Codex characters end-to-end)

> **Why this doc exists.** The character/Codex surfaces span several UIs (Characters
> tab, the Canvas Codex drawer, the node editor's character chips, the relationship
> map) all backed by one shared canonical entity. A future session asked to "modify
> the character flow" needs one place that explains how those surfaces connect so a
> change in one doesn't silently break another. Written for Phase 13; keep it current
> when the flow changes. Feature-level guarantees for these surfaces are in
> `docs/16-PROTECTED-FEATURES.md` — do not weaken them without the `spiderman` unlock.

## 1. The entity: `CodexEntry`

A `CodexEntry` (`apps/sidecar/app/models/orm.py`, table `codex_entries`) is **canonical
and shared across the whole Story Library** — it has no `book_id` column. `entry_type`
is one of `character | location | faction | object_lore`. Only `entry_type ==
'character'` participates in the character-specific surfaces below; the others still
exist in the Codex.

Frontend hooks (all in `apps/desktop/src/queries/codex.ts`):
- `useCodexEntries(entryType?)` → `GET /codex[?entry_type=…]` — every entry of a type,
  any Book (the library-wide pool).
- `useCreateCodex()` / `useUpdateCodex()` / `useDeleteCodex()` → `POST/PATCH/DELETE /codex`.

## 2. Two independent kinds of "link"

A character is attached at **two** independent levels — do not conflate them:

- **Book link** (`book_codex_links`): `useLinkCodexToBook(bookId)` →
  `POST /codex/{entryId}/books/{bookId}`. Puts the character on a Book's roster; this is
  what the **Characters tab** lists via `useBookCharacters(bookId)` →
  `GET /books/{bookId}/characters` (returns `{ entries, relationships, scene_links }`).
- **Scene link** (`codex_scene_links`): `useLinkCodexToScene(sceneId)` /
  `useUnlinkCodexFromScene(sceneId)` → `POST/DELETE /codex/{entryId}/scenes/{sceneId}`;
  read with `useSceneCodex(sceneId)` → `GET /scenes/{sceneId}/codex`. This is what the
  **node editor character chips** and the **Canvas Codex drawer link toggle** use.

Deleting the `CodexEntry` cascades away both link kinds; unlinking either level never
deletes the entry.

## 3. Where characters are rendered (the surfaces)

| Surface | File | Reads | Writes |
|---|---|---|---|
| **Characters tab — List** | `components/codex/characters-panel.tsx` | `useBookCharacters` | create + `useLinkCodexToBook` (add/attach-existing) |
| **Characters tab — Map** | `components/codex/character-relationship-graph.tsx` | `useBookCharacters` (`.entries` + `.relationships`) | **read-only** D3-style circular node-link viz (Phase 13 follow-up) — relationships are created/edited in the Relationships tab, not on the map; clicking a node opens that character's editor |
| **Canvas Codex drawer** | `components/canvas/codex-panel.tsx` | `useCodexEntries` + `useSceneCodex` | `useLinkCodexToScene` / `useUnlinkCodexFromScene`; edit via `CodexEntryDialog` |
| **Node editor character chips** | `components/canvas/node-editor.tsx` | `useSceneCodex(sceneId)` filtered to `character` | `useLinkCodexToScene` / `useUnlinkCodexFromScene`; create via `useCreateCodex` |
| **Full entry editor** | `components/codex/codex-entry-dialog.tsx` | per-entry fields/relationships/arc/image | all Codex field/relationship/arc mutations |

As of the Phase 13 follow-up (2026-08-08) the entry editor is a **wide (`max-w-4xl`)
two-column dialog**: the standalone Relationships and Arc tabs were folded into the
Details view (left column = Name, Description, Role/Kind, Traits; right column =
Relationships + Arc over time), leaving three tabs (Details / Custom Fields / Image).
"Summary" is labelled **Description** in the UI (the API field is still `summary`).
Role/Kind is a **creatable combobox** (curated suggestions from `lib/vocab.ts`, but any
typed value is accepted — stored in `custom_fields.role`/`.kind`), and Traits accept
custom values alongside the presets. None of this changed the schema — role/kind/traits
still live in the `custom_fields` JSON blob.

The node-editor chips and the Canvas drawer both act on the **scene link** of the
**currently-selected canvas node** (`sceneId`). Clicking a chip opens the same
`CodexEntryDialog` every other surface uses — there is intentionally only one entry
editor.

## 4. Relationships (the Map's edges)

`codex_relationships` rows are directional: `from_entry_id` → `to_entry_id` with a
free-text `relationship_type` (+ optional `description`). Hooks:
`useCodexRelationships(entryId)` (`GET /codex/{entryId}/relationships`),
`useCreateRelationship()` (`POST /codex/{entryId}/relationships`, body `{ to_entry_id,
relationship_type, description? }` — the *from* side is the URL entry), and
`useDeleteRelationship()` (`DELETE /codex/relationships/{relId}`). There is **no** update
hook — edit = delete + recreate. As of the Phase 13 follow-up the entry dialog's
Relationships tab (`RELATIONSHIP_TYPES`) is the **single writer path** — the Map is now a
read-only visualization of these rows (it no longer creates/deletes edges via drag). Keep
the Relationships tab as the one place relationships are mutated.

The target-entry picker is a **searchable, type-to-filter combobox** (built from the
existing `Popover` + `Input`, not `cmdk`) over **all** codex entries except self — a
character can relate to any entry type (another character, a location, a faction, an
object/lore), so the picker deliberately does not filter by `entry_type`; each result row
shows the entry name plus a small type badge. This replaced a plain `<Select>` that listed
every entry with no filter (the "scroll endlessly" problem when a library has many
characters).

## 4a. "Arc over time" — the spoiler-safe character timeline

The Arc section (formerly "Arc States", `codex_arc_states`) is **not** a generic notes
field — it is the mechanism that lets the AI know how a character *changes* without leaking
the future. Each arc row pins a `status_summary` (and optional `traits_snapshot`) to a
`(book_id, as_of_outline_order_index)` — i.e. a point in the story. When
`prompt_builder.build_codex_context` assembles the codex block for a scene, it folds in
**only** the latest arc row whose `as_of_outline_order_index <= that scene's outline
position** (`prompt_builder.py` anti-spoiler filter). So a Chapter-20 betrayal noted in an
arc row never reaches the model while it is helping with a Chapter-2 scene. This is why the
feature is load-bearing (it feeds Enhance/continuity context) and `spiderman`-protected —
do not remove or bypass the outline-position filter. The UI relabel to "Arc over time" +
the plain-language explainer (2026-08-08) is presentational only; the data model and filter
are unchanged.

## 5. The screenplay "Character" element is NOT a Codex character

In a script Book's node editor, `ElementsEditor` offers a **"Character"** screenplay
element (`ELEMENT_TYPE_LABELS.character` in `node-editor.tsx`). That is a **Fountain cue
line** — the UPPERCASE speaker name printed above dialogue — required by the Fountain/FDX
export pipeline (`apps/sidecar/app/services/export_fountain.py`). It has **nothing** to do
with a `CodexEntry` of `entry_type='character'`. Do not merge, alias, or remove one in
terms of the other. The node editor's circular character chips manage Codex character
scene-links; the "Character" element formats a script line. Both coexist by design.
