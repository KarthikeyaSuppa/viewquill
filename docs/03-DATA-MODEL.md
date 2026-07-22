# Data Model

SQLite via SQLAlchemy 2.0 + Alembic migrations. This document is the schema of record — implementation should treat it as the starting migration, then evolve it through further Alembic revisions rather than hand-edited `ALTER TABLE` scripts.

## Design principle

**Scenes and Codex entries are canonical, decoupled from any single Book via join tables.** This is the single most important structural decision in the schema: it's what lets a scene (or a character) be dragged between Books without duplication, while each Book still keeps its own independent canvas layout, connections, and outline/timeline order. Everywhere you see a `book_*_links` or `*_scene_links` table, that's this pattern.

Images and compiled drafts are stored as **files on disk** under the app-data directory; the database holds metadata/paths only — keeps SQLite lean, matches how Tauri serves local images to the WebView, and simplifies `.quillproj` packaging.

## Schema

```sql
-- Books
CREATE TABLE books (
  id TEXT PRIMARY KEY,                 -- UUID
  title TEXT NOT NULL,
  book_type TEXT NOT NULL CHECK(book_type IN ('story_book','movie_script','short_film_script','single_scene')),
  structure_template_id TEXT REFERENCES structure_templates(id),
  logline TEXT,
  front_matter JSON,                   -- title page, dedication, preface fields
  cover_image_id TEXT REFERENCES images(id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- Canonical node/scene entity (shared across Books)
CREATE TABLE scenes (
  id TEXT PRIMARY KEY,
  node_type TEXT NOT NULL CHECK(node_type IN ('scene','plot_point','thought')),
  title TEXT NOT NULL,                 -- mandatory per spec
  description TEXT,                    -- optional freeform prose/notes body — NEVER deleted by conversion
  status TEXT DEFAULT 'draft',
  word_count INTEGER DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- Structured screenplay content for script-type Books. Coexists with `description` —
-- converting a scene to/from script form ADDS this representation, never removes the other.
CREATE TABLE screenplay_elements (
  id TEXT PRIMARY KEY,
  scene_id TEXT NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
  order_index INTEGER NOT NULL,
  element_type TEXT NOT NULL CHECK(element_type IN
    ('scene_heading','action','character','dialogue','parenthetical','transition','shot','dual_dialogue')),
  text TEXT NOT NULL
);

-- Per-Book canvas membership + layout (many-to-many: scene <-> book)
CREATE TABLE book_scene_links (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  scene_id TEXT NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
  canvas_x REAL, canvas_y REAL, color TEXT,
  added_at TEXT NOT NULL,
  UNIQUE(book_id, scene_id)
);

-- Node-graph edges, scoped per Book (the same two scenes can be connected differently in different Books)
CREATE TABLE scene_connections (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  source_scene_id TEXT NOT NULL REFERENCES scenes(id),
  target_scene_id TEXT NOT NULL REFERENCES scenes(id),
  source_handle TEXT, target_handle TEXT,
  connection_type TEXT CHECK(connection_type IN ('sequence','causal','reference','contradiction','custom')),
  label TEXT
);

CREATE TABLE chapters (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  title TEXT NOT NULL, order_index INTEGER NOT NULL
);

CREATE TABLE structure_templates (
  id TEXT PRIMARY KEY, name TEXT NOT NULL,          -- 'Three-Act', "Hero's Journey", 'Freeform'
  applicable_book_types JSON, beats JSON             -- [{name, order_index, description}]
);

-- The Outline/Timeline "mediator" tab — ONE table backs BOTH views (beat-board and sequencer)
CREATE TABLE book_scene_order (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  scene_id TEXT NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
  chapter_id TEXT REFERENCES chapters(id),
  outline_order_index INTEGER,          -- narrative/reveal order (beat-board view)
  structure_beat TEXT,                  -- e.g. "Inciting Incident"
  timeline_order_index INTEGER,         -- chronological in-story order (timeline view)
  in_story_time_label TEXT,             -- e.g. "Day 3, dawn" (display)
  in_story_time_sort_key REAL,          -- numeric sort for chronological view
  UNIQUE(book_id, scene_id)
);

-- Codex (canonical, shared across Books like scenes)
CREATE TABLE codex_entries (
  id TEXT PRIMARY KEY,
  entry_type TEXT NOT NULL CHECK(entry_type IN ('character','location','faction','object_lore')),
  name TEXT NOT NULL, summary TEXT,
  custom_fields JSON,                                 -- flexible/arbitrary fields per entry
  primary_image_id TEXT REFERENCES images(id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE codex_relationships (
  id TEXT PRIMARY KEY,
  from_entry_id TEXT NOT NULL REFERENCES codex_entries(id) ON DELETE CASCADE,
  to_entry_id TEXT NOT NULL REFERENCES codex_entries(id) ON DELETE CASCADE,
  relationship_type TEXT NOT NULL, description TEXT
);

-- Point-in-time status snapshots — prevents Enhance calls on an EARLY scene from being "spoiled"
-- by a LATER plot development (resolved via as_of_outline_order_index <= current scene's order)
CREATE TABLE codex_arc_states (
  id TEXT PRIMARY KEY,
  codex_entry_id TEXT NOT NULL REFERENCES codex_entries(id) ON DELETE CASCADE,
  book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  as_of_outline_order_index INTEGER NOT NULL,
  status_summary TEXT, traits_snapshot JSON, created_at TEXT NOT NULL
);

CREATE TABLE book_codex_links (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  codex_entry_id TEXT NOT NULL REFERENCES codex_entries(id) ON DELETE CASCADE,
  role_note TEXT, UNIQUE(book_id, codex_entry_id)
);

CREATE TABLE codex_scene_links (
  id TEXT PRIMARY KEY,
  codex_entry_id TEXT NOT NULL REFERENCES codex_entries(id) ON DELETE CASCADE,
  scene_id TEXT NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
  note TEXT, UNIQUE(codex_entry_id, scene_id)
);

-- Images (two buckets: finalized_scene, reference_pool)
CREATE TABLE images (
  id TEXT PRIMARY KEY,
  bucket TEXT NOT NULL CHECK(bucket IN ('finalized_scene','reference_pool')),
  storage_path TEXT NOT NULL,          -- relative path under app-data/media/
  display_name TEXT NOT NULL, original_filename TEXT,
  description TEXT,                    -- Enhance-able free text ("why I have this / what to use from it")
  width INTEGER, height INTEGER, checksum_sha256 TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE image_tags (image_id TEXT REFERENCES images(id) ON DELETE CASCADE, tag TEXT, PRIMARY KEY(image_id, tag));

-- Polymorphic attach — this single table drives "only images linked to THIS Book get exported"
CREATE TABLE entity_images (
  id TEXT PRIMARY KEY,
  image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  entity_type TEXT NOT NULL CHECK(entity_type IN ('book','scene','codex_entry')),
  entity_id TEXT NOT NULL, role TEXT
);

-- `severity` added per prior-art finding in 07-RISKS-AND-OPEN-QUESTIONS.md (91zgaoge/StoryForge's
-- validated pattern: audit results as severity-tagged issues, not a flat list) — drives which flags
-- render as blocking vs. informational annotations in the Outline/Timeline tab.
CREATE TABLE continuity_flags (
  id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  scene_id TEXT REFERENCES scenes(id), codex_entry_id TEXT REFERENCES codex_entries(id),
  flag_type TEXT CHECK(flag_type IN ('early_appearance','trait_contradiction','timeline_conflict','custom')),
  severity TEXT DEFAULT 'warning' CHECK(severity IN ('critical','warning','hint')),
  description TEXT NOT NULL, status TEXT DEFAULT 'open' CHECK(status IN ('open','dismissed','resolved')),
  source TEXT CHECK(source IN ('ai','manual')), created_at TEXT NOT NULL
);

CREATE TABLE draft_versions (
  id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  version_number INTEGER NOT NULL, file_path TEXT NOT NULL,  -- compiled snapshot stored on disk, not in DB
  format_settings JSON, is_current INTEGER DEFAULT 0, generated_at TEXT NOT NULL, notes TEXT
);

-- Trust/audit trail: every LLM call, whether accepted or rejected
-- `provider` added per 08-AI-PROVIDER-MODES.md: which backend ('ollama'|'groq') actually served this call,
-- distinct from `model_name` (e.g. provider='groq', model_name='openai/gpt-oss-120b')
CREATE TABLE llm_request_log (
  id TEXT PRIMARY KEY, request_type TEXT, entity_type TEXT, entity_id TEXT, book_id TEXT,
  provider TEXT CHECK(provider IN ('ollama','groq')), model_name TEXT,
  latency_ms INTEGER, accepted INTEGER, created_at TEXT NOT NULL
);

CREATE TABLE app_settings (key TEXT PRIMARY KEY, value JSON);

-- ============================================================
-- Voice, delight & personalization (per docs 10 and 12)
-- ============================================================

-- Every dictation keeps its raw audio (file on disk) + transcript — never-lose-data applies to voice.
-- A mis-transcription can be re-listened and re-transcribed later, even by a better future engine.
CREATE TABLE voice_notes (
  id TEXT PRIMARY KEY,
  audio_path TEXT NOT NULL,            -- relative path under app-data/audio/
  transcript TEXT,
  engine TEXT,                          -- 'parakeet' | 'groq_whisper' | future engines
  duration_ms INTEGER,
  attached_entity_type TEXT, attached_entity_id TEXT,  -- where the transcript landed (nullable)
  status TEXT DEFAULT 'transcribed' CHECK(status IN ('recorded','transcribed','attached','discarded')),
  created_at TEXT NOT NULL
);

-- Writing streaks / daily word goals (10-DESIGN-SYSTEM.md §9). One row per app session with writing activity.
CREATE TABLE writing_sessions (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL, ended_at TEXT,
  words_added INTEGER DEFAULT 0,
  book_id TEXT REFERENCES books(id)     -- nullable; a session can touch many books, this records the primary one
);

-- Badges (v1.1). Definitions live in code; this records unlocks only.
CREATE TABLE achievements (
  key TEXT PRIMARY KEY,                 -- e.g. 'first_chapter', 'night_owl'
  unlocked_at TEXT NOT NULL
);

-- Dyslexia-aware spellcheck personal dictionary (10-DESIGN-SYSTEM.md §4):
-- character names and invented lore words, exempt from squiggles and offered in suggestions.
CREATE TABLE personal_dictionary (
  word TEXT PRIMARY KEY,
  added_at TEXT NOT NULL,
  source TEXT CHECK(source IN ('user','codex_auto'))  -- codex entity names can be auto-added
);
```

### Derived search layer (virtual tables — rebuildable, never exported)

The semantic layer ([11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md), v1.1) adds **derived** structures to the same DB file. They are excluded from `.quillproj` bundles and regenerated from source text after import or whenever the embedding model changes — they are an index, not data:

```sql
-- sqlite-vec virtual table: one embedding row per scene / codex entry / image description
CREATE VIRTUAL TABLE embeddings USING vec0(
  embedding float[512],                 -- qwen3-embedding:0.6b, MRL-truncated to 512 dims
  entity_type TEXT,                     -- 'scene' | 'codex_entry' | 'image'
  entity_id TEXT,
  embedded_text_hash TEXT,              -- re-embed only when source text actually changed
  model TEXT                            -- embedding model versioning: bulk re-embed on model change
);

-- SQLite FTS5 keyword index over the same entities (BM25 leg of hybrid retrieval)
CREATE VIRTUAL TABLE search_fts USING fts5(
  entity_type UNINDEXED, entity_id UNINDEXED,
  title, body
);
```

## Notes on specific tables

- **`scenes` + `screenplay_elements`**: a scene can have *both* a `description` (prose) and a set of `screenplay_elements` (structured screenplay) at once. This is what makes Book-type conversion non-destructive — converting Single Scene → Movie Script generates `screenplay_elements` rows via an AI pass (reviewed/accepted like any Enhance call) without ever clearing `description`.
- **`book_scene_links` vs `scene_connections`**: membership (which Book a scene belongs to, and where it sits on that Book's canvas) is separate from graph edges (how scenes connect to each other within a specific Book's canvas). The same two scenes can be connected differently — or not at all — in two different Books.
- **`book_scene_order`**: deliberately one table for both Outline and Timeline views, per the product decision that they're "two views over the same underlying data," not two parallel systems that could drift out of sync.
- **`codex_arc_states`**: resolved by querying the latest snapshot where `as_of_outline_order_index <= scene's outline_order_index` for that Book — this is the mechanism behind "the AI won't spoil later plot facts into an earlier scene's Enhance call."
- **`entity_images`**: a single polymorphic join table (rather than three separate `book_images`/`scene_images`/`codex_images` tables) so the export-bundling query ("gather every image linked to any scene/codex-entry/cover used by this Book") is one consistent query shape instead of three.
- **UUID primary keys everywhere**: not just style — this is what makes `.quillproj` import able to match entities by stable ID and merge without duplication (see [05-EXPORT-IMPORT-SECURITY.md](05-EXPORT-IMPORT-SECURITY.md)).
- **`app_settings` and provider config**: gains `ai_mode` (`offline|online|hybrid`), `groq_model_name`, and `groq_zdr_enabled` keys per [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md). The Groq API key itself is deliberately **never** stored in this table (or anywhere in SQLite) — it lives only in the OS credential vault, accessed exclusively from the Rust shell.
- **`app_settings` design/voice keys** (per [10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md) and [12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md)): `local_model_name` (default `qwen3.5:4b`), `grammar_model_name` (optional `gemma4:e4b`), `delight_level` (`calm|standard|playful`, default playful), `theme_mode` (`day|night|auto`), `bg_tint`, `font_family`, `font_size`, `line_height`, `letter_spacing`, `line_length_ch`, `reading_ruler` (`off|grey_bar|shade`), `sounds_enabled`, `mascot_enabled`, `dictation_hotkey`, `stt_engine`, `tts_voice`, `tts_rate`, `daily_word_goal`. All plain settings, no secrets.
- **`voice_notes`**: raw dictation audio is data, not a temp file — kept on disk with the transcript so any note can be re-transcribed later (better engine, correction of a mis-hear). Audio files live under `app-data/audio/` and are included in `.quillproj` bundles only when attached to an exported Book's entity.
- **Derived search layer**: the `embeddings` (vec0) and `search_fts` (FTS5) virtual tables are indexes over source text, not source data — rebuildable at any time, excluded from exports, versioned by `model` so an embedding-model upgrade triggers a clean bulk re-embed rather than mixed-model search results.
