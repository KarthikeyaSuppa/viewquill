# Export, Import & Security

## Storage/workspace model: the hybrid

- **One shared local SQLite database** ("the Story Library") is the live source of truth for every Book, scene, Codex entry, image, and draft. This is what makes cross-Book drag-and-drop reuse instant, with no export/import step required for day-to-day work.
- **Every Book gets a one-click "Export Bundle"** producing a portable `.quillproj` file — this is the portability and disaster-recovery layer sitting on top of the shared library, resolving the tension between "instant shared reuse" and "single-file portability" without giving up either.
- Live database stays **unencrypted** (performance); `.quillproj` bundles are **encrypted** (see below) — this was an explicit, deliberate tradeoff, not an oversight.

## `.quillproj` bundle export

1. `POST /books/{id}/export/bundle {passphrase}` gathers, by UUID, everything the Book actually uses:
   - The book row itself.
   - All scenes via `book_scene_links` (+ `screenplay_elements` for script-type Books).
   - `scene_connections`, `book_scene_order`, `chapters`.
   - Codex entries via `book_codex_links` (+ their `codex_relationships` and scoped `codex_arc_states`).
   - Images via `entity_images`, resolved across all gathered scenes/codex-entries/the book cover — **only images actually linked to this Book**, not the whole global reference pool.
   - `draft_versions`, and `voice_notes` audio+transcripts whose transcript is attached to one of this Book's entities.
   - **Excluded: the derived search layer** (`embeddings` vec0 rows, `search_fts` index — see [03-DATA-MODEL.md](03-DATA-MODEL.md)). Embeddings are an index over the text, not data; they're regenerated automatically after import, which also keeps bundles small and immune to embedding-model version drift.
2. Serializes to `manifest.json` (schema_version, book UUID, exported_at, entity counts) + per-type JSON files, all entities keyed by their stable UUID primary keys — the same UUIDs used live in the database, which is exactly what makes UUID-matching on import possible.
3. Copies referenced image/draft files into a staging tree, zips with Python's stdlib `zipfile` (DEFLATE).
4. **Encrypts the whole zip as one blob** using **`pyrage`** (PyPI, pyO3/Rust bindings over the `age` encryption format), passphrase mode: `pyrage.passphrase.encrypt(zip_bytes, passphrase)`.

### Why `pyrage`/`age` over hand-rolled AES

- `age`'s spec is deliberately **non-agile** — one vetted primitive set, no algorithm-choice foot-guns, no DIY salt/nonce/KDF-parameter bugs to get subtly wrong.
- Ships from an **official PyPI package**, satisfying the project's "official registries only" constraint.
- Specifically valuable for a *disaster-recovery* format: the standalone `age` CLI (installable independently via winget/scoop) can decrypt the same file even in a scenario where this app itself is lost, broken, or years out of date. A backup format shouldn't depend on the app that made it still existing.
- **Documented fallback**: AES-256-GCM via `cryptography` (PyPI, pyca) + Argon2id key derivation via `argon2-cffi` (PyPI), used only if `pyrage`'s Windows wheel availability proves unreliable during the Phase 0 spike. Encryption itself is a hard requirement either way — only the specific library is conditional.

## Import / merge-by-UUID

1. `POST /import/storyproj` (multipart file + passphrase) → `pyrage.passphrase.decrypt` (a wrong passphrase surfaces as a clear, specific error, not a generic failure) → unzip → validate `manifest.json` schema_version.
2. For each entity in the bundle:
   - **UUID already exists locally** → never silently overwrite. Add an entry to a merge report and let the user choose keep-mine / take-theirs / keep-both in a review dialog (default: keep-mine).
   - **UUID doesn't exist locally** → insert as a new row, copy its asset files into the managed media directory.
3. Re-create the Book-scoped join rows (`book_scene_links`/`book_codex_links`/`entity_images`) for the target Book regardless of whether the referenced canonical rows were new or already existed — this is what makes both "restoring a deleted Book from its own backup" and "importing onto a fresh install" work correctly.
4. Return a structured merge report (`created` / `matched_existing` / `conflicts`, per entity type) rendered in the UI — the user always sees exactly what an import changed.

## Additional backup safety net

Beyond user-triggered `.quillproj` exports, a **periodic local unencrypted backup rotation** (`sqlite3 .backup()` or `VACUUM INTO`, keeping the last N snapshots) runs automatically against the live database. This exists because the live SQLite file is otherwise a single point of failure for a single personal user with an explicit "never lose data" requirement — the encrypted bundle is for portability/intentional backup, this rotation is for "the app crashed mid-write" or "I need to undo further back than my last manual export."

## Export formats (Final Draft tab)

| Format | Applies to | Library | Notes |
|---|---|---|---|
| Markdown | All Book types | `Jinja2` | Chapter/scene templates, optional YAML front matter |
| DOCX | All Book types | `python-docx` | Manuscript style (heading/body styles, page breaks, title page) for Story Books; Courier New + screenplay margins for script DOCX |
| PDF | All Book types | `WeasyPrint` (primary) / `ReportLab` (fallback) | Same Jinja2-rendered HTML feeds both a novel-manuscript CSS template and a dedicated screenplay CSS template (Courier Prime font, 1.5"/1" margins, per-element indentation). See packaging note below. |
| Fountain | Movie/Short Film Scripts only | `screenplay-tools` | Open-source, format-agnostic `Script` object with a Fountain `Parser`/`Writer` — reused rather than building a screenplay formatter from scratch. |
| Final Draft `.fdx` | Movie/Short Film Scripts only | `screenplay-tools` | Same `Script` object feeds an FDX XML writer. Round-trip fidelity at scale is flagged as unproven — see [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md). |

**WeasyPrint packaging note**: WeasyPrint depends on Pango/cairo/GDK-PixBuf (the GTK stack), which is not pip-installable on Windows and historically requires either the MSYS2 route or manually bundling GTK3 runtime DLLs next to the executable — this is a known pain point, not maintainer-supported out of the box for a PyInstaller build. Addressed as a Phase 0 pass/fail spike, with pure-Python `ReportLab` (no native dependencies) as the ready fallback.

## Package/dependency security (recap, applies here specifically)

Encryption and export libraries are held to the same standard as everything else in this project: official PyPI/npm/crates.io packages only, pinned versions, no unofficial forks — especially non-negotiable for a cryptography dependency.
