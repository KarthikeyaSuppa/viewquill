# Phase 14 — Prebaked Sample Library

Status: In progress (started 2026-08-08)

## Why

Quillnight's library starts empty (`library-screen.tsx` empty state — sleeping-firefly
Lottie, "No books yet"). A new user, or the user demoing the app, has to hand-build a
Book, a canvas, a Codex, an outline, a timeline and images before a single feature is
visible. Meanwhile this build machine's DB had accumulated 12 throwaway dev Books
("New", "Demo story_book", "Canvas Demo", "Node Card Demo") and 20 scenes across
Phases 2–12.

Direct user directive: wipe the accumulated dev data, and ship four example Books —
one per `book_type` — prebaked with canvas, characters, maps, timelines and "almost
every possible combination or edge case", visible on a fresh launch of the library.

Decisions locked with the user before build:

- **Trigger** — auto-seed at startup when the library is empty. Real product
  behavior, not a one-off script.
- **Wipe scope** — story data only. Profiles and settings survive, so the user stays
  logged in with their typography intact. A backup snapshot is taken first.
- **Labeling** — sample Books carry a visible "Sample" badge and are freely
  deletable; a seeded marker stops them resurrecting after deletion.

Model routing (CLAUDE.md + explicit user cost directive): `builder` (**sonnet**)
implements every task; `reviewer` (opus) gates only the destructive wipe script;
demo in the main session. No LLM is ever called by the seeder — this machine never
runs real models.

## Non-negotiables carried in

- **`docs/16-PROTECTED-FEATURES.md` is NOT edited** — the user's message did not
  contain `spiderman`. Nothing here removes or weakens P1–P12; the sample data is
  purely additive and in fact exercises P1 (node fields), P4 (Description History),
  P7 (character chips), P9 (Characters Map) and P10 (Canvas Codex drawer).
- `docs/15-ENTITY-LIFECYCLES.md` gains a **Sample Library** entry (six-section
  template) as part of "done".

## Key architectural findings driving the design

1. `scenes` and `codex_entries` are **global/canonical**, not owned by a Book
   (`orm.py`). A Book references them via `book_scene_links` (canvas + x/y),
   `book_scene_order` (outline/timeline) and `book_codex_links` (roster). The seeder
   must write all three or panels look empty.
2. **Canvas membership ≠ outline membership.** `canvas_service.add_scene_to_canvas`
   writes only a `BookSceneLink`. BeatBoard, Timeline *and* the Draft manuscript
   reader all read `book_scene_order`.
3. `canvas_service.create_edge` **writes an `UndoLog` row**. Seeding through it would
   arm the canvas Undo button to delete sample content → the seeder writes
   `SceneConnection` rows **directly via ORM**, leaving the undo stack clean.
4. `scene_service.update_scene` always stamps revisions `manual_edit` and fires on any
   status change → set `status` directly on the ORM object and hand-build
   `SceneRevision` chains so all four `change_source` values are exercised.
5. **Front matter is printed verbatim into every export** (`export_pdf.py`,
   `export_docx.py`, `export_markdown.py` all iterate its keys) → the sample marker
   must NOT live in `front_matter`, or exported title pages would print it.
6. `settings_service.get_all_settings` merges **every** global row, not just known
   keys → a global `sample_library` row is readable through the existing
   `GET /settings` with zero backend/API change. One mechanism serves as both the
   idempotency marker and the badge source.
7. `DELETE /books/{id}` deliberately leaves canonical scenes/codex/images behind, so
   the wipe must delete those explicitly — a per-book delete loop is insufficient.
8. `search_index_service.upsert_entity` never raises, so seeding through
   `scene_service.create_scene` / `codex_service.create_entry` gives free FTS
   indexing; the embedding half fails and is swallowed without Ollama.

## Design

**Marker** — one global `app_settings` row (`user_id IS NULL`), key `sample_library`:

```json
{ "version": 1, "seeded_at": "<iso>", "book_ids": ["…"] }
```

Plus a test opt-out, `QUILLNIGHT_SKIP_SAMPLE_SEED=1`, read at call time and set for the
whole pytest session in `tests/conftest.py`. The suite shares one SQLite DB that starts
empty — precisely the "fresh install" condition — so without the flag the first module to
enter `TestClient(app)` seeded 4 Books into everyone's database. That regression was caught
by the full-suite run (6 failures) and fixed before landing.

Seed only when the marker is absent **and** `books` is empty. The marker prevents
resurrection after the user deletes the samples; the empty check additionally
protects a restored-from-backup library that lost the marker. Deliberately not added
to `DEFAULT_SETTINGS`/`PER_USER_KEYS` — it is per-install, not per-profile, so
`settings_service.py` needs no edit.

**Content** — four Books in a loosely shared world:

| key | title | `book_type` | template | scale |
|---|---|---|---|---|
| `lantern` | The Lantern-Keeper's Debt | `story_book` | Three-Act | 3 chapters, ~12 scenes — flagship |
| `vespers` | Neon Vespers | `movie_script` | Hero's Journey | ~8 scenes, all 8 screenplay element types |
| `salt` | Salt | `short_film_script` | Three-Act | ~4 scenes, no chapters |
| `lastbus` | The Last Bus | `single_scene` | Freeform | 1 scene, no chapters |

**Images** — ~10 deterministic procedurally-generated PNGs (Pillow), pushed through
the existing `images_service.save_image` so `width`/`height`/`checksum_sha256` are
real and thumbnails generate. Fabricated `storage_path` rows are rejected: no `<img>`
consumer in the frontend has an `onError` handler, so a missing file renders a
broken-image glyph on canvas nodes, gallery cards and character chips.

## Coverage checklist (acceptance criteria)

Every enum value at least once: all 4 `book_type`; all 3 `node_type`; all 3 scene
`status`; all 5 `connection_type` **plus one NULL**; all 8 `element_type`; all 4
`entry_type`; both image `bucket`s; all 3 `entity_images.entity_type`; every
continuity `flag_type`/`severity`/`status`/`source`; all 4 revision `change_source`.

Structural edge cases: a scene on **two** Books' canvases at different x/y and a
character linked to **two** Books (the shared Story Library headline demo); a
**flashback** in `lantern` where outline order ≠ timeline order; an orphan node with
no edges; a `thought` and a `plot_point` node; a scene with `description=None`; an
archived canvas link; a `structure_beat` matching no template beat (→ "Unassigned"
lane); non-contiguous `sequence_weight` gaps; unicode/emoji in a title and one
~120-char title; a character with no portrait; an image with no tags; ≥4
relationships forming a connected graph; ≥2 arc states; `custom_fields` populated;
a canvas scene with no order row.

## Workstreams

- **A — Wipe.** `apps/sidecar/scripts/reset_library.py`: `--yes`/`--dry-run`, backup
  first (abort if it fails), delete story tables in FK order, clear
  `search_fts`/`embeddings`, purge `media/` + `drafts/` with containment guards,
  assert `users`/`app_settings` survive. **Reviewer (opus) gate.**
- **B — Content.** `app/services/sample_library/content.py` — pure frozen-dataclass
  data with an import-time `_validate()`; `images.py` — deterministic Pillow art;
  `__init__.py`.
- **C — Seeder.** `app/services/sample_library/seeder.py` —
  `seed_sample_library(db) -> int`, marker guard, ordering Book → chapters → images →
  scenes → canvas links → order rows → codex → links/relationships/arc states →
  edges (direct ORM) → screenplay elements → revisions → flags → marker.
- **D — Wiring.** One call in `main.py`'s `lifespan`, mirroring the
  `seed_structure_templates` block (own session, non-fatal try/except).
- **E — Frontend.** "Sample" badge in `library-screen.tsx`'s `BookCard`, driven by
  the settings marker. No new query or endpoint.
- **F — Tests.** `tests/test_sample_library.py` — idempotency, marker shape, no
  re-seed after deletion, table-driven enum coverage, zero `UndoLog` rows.
- **G — Docs.** This file, the `docs/15` entry, `PROJECT-MAP.md`.

## Reviewer gate

`scripts/reset_library.py` only — a mass-delete against the user's real DB. Verify:
nothing outside the intended table set is deleted; profiles and settings genuinely
survive; the backup is taken *before* any delete; no path traversal in the
media/drafts cleanup. No other reviewer-flagged file (`export_*`, `bundle_*`,
`speech_stt.py`, `images_service.py`) is modified.

## Verification

Backend, from `apps/sidecar`:
`QUILLNIGHT_LLM_STUB=1 QUILLNIGHT_STT_STUB=1 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Frontend: `npm run build --prefix apps/desktop` + `npm run lint --prefix apps/desktop`.

End-to-end demo: backup lands → `reset_library.py --yes` empties the library →
restart seeds 4 Books → each shows a Sample badge, profile still logged in → Book 1
canvas/characters/outline/**timeline reordered vs outline**/draft/images all populated
→ Book 2 exports Fountain → Book 4 renders with no chapters → node History shows a
revision chain → Ctrl+K finds a sample character → canvas Undo is disabled → deleting
a sample Book survives a restart.
