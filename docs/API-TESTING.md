# Quillnight Sidecar — API testing reference

Every HTTP endpoint the Python sidecar exposes as of Phase 2, with copy-paste `curl`.
The sidecar is local-only: **`http://127.0.0.1:8756`**.

## Running backend + frontend

Two processes: the **Python sidecar** (API, port **8756**) and the **Vite frontend** (UI, port **1420**). The Tauri desktop shell is deferred (no Rust on this laptop) — for now the UI runs in a normal browser tab.

### Both at once (easiest)

```powershell
./scripts/dev.ps1      # from repo root — starts the sidecar (stub mode) + the frontend, opens on :1420
```

Ctrl-C stops the frontend and tears down the sidecar job.

### Backend only (the API)

```powershell
cd apps/sidecar
# first time only:  python -m venv .venv ; ./.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
$env:QUILLNIGHT_DATA_DIR = "$PWD/app-data"   # dev DB/media/audio (gitignored)
$env:QUILLNIGHT_LLM_STUB = "1"               # Enhance echoes text instead of calling a model
$env:QUILLNIGHT_STT_STUB = "1"               # dictation returns a fixed transcript
./.venv/Scripts/python.exe -m app.main       # serves http://127.0.0.1:8756  (migrates the DB on startup)
```

Drop the two `*_STUB` vars on the AI laptop (with Ollama/models installed) to exercise real Enhance/dictation.

### Frontend only (the UI)

```powershell
cd apps/desktop
# first time only:  npm install
npm run dev            # serves http://localhost:1420  (expects the sidecar on :8756)
```

The frontend talks to the sidecar at `http://127.0.0.1:8756` by default; override with a `VITE_SIDECAR_URL` env var if needed. CORS already allows localhost + the Tauri origins.

## Interactive docs

- **Swagger UI (easiest, zero setup):** open <http://127.0.0.1:8756/docs> — try every endpoint in the browser.
- OpenAPI JSON: <http://127.0.0.1:8756/openapi.json>

## Postman

Two ways — the import gives you the complete, always-current set; the committed collection is offline and pre-wired with variables.

**A. Import the committed collection (recommended for quick start)**
1. Postman → **Import** → **File** → select `docs/quillnight.postman_collection.json`.
2. Open the collection's **Variables** tab: `base_url` is pre-filled (`http://127.0.0.1:8756`); paste `book_id` / `scene_id` / `codex_id` / etc. from earlier responses (or grab them in Swagger).
3. Folders mirror this doc (Health, Settings, Books, Scenes, Canvas, Codex, LLM, Voice). Run the sidecar in **stub mode** first.

**B. Import straight from OpenAPI (always in sync with the running server)**
1. Start the sidecar. Postman → **Import** → **Link** → `http://127.0.0.1:8756/openapi.json` → Import.
2. Postman generates a full collection from the live schema — nothing to hand-maintain as endpoints grow.

**Postman notes**
- **Enhance** (`POST /llm/enhance`) streams **Server-Sent Events** — Postman shows the streamed body as it arrives; add header `Accept: text/event-stream`.
- **Voice** (`POST /voice/transcribe`) takes **raw audio bytes**, not form-data: Body → **binary** → pick an audio file, and set `Content-Type: audio/webm` (or `audio/wav`).
- Path IDs are collection **variables** (`{{book_id}}` …) — set them once and every request in the folder uses them.

Notes: all IDs are UUID strings. Timestamps are ISO-8601 UTC text. `DELETE` returns `204`.
Missing resources return `404`. Bodies are JSON unless stated (voice upload is raw bytes).

---

## Health & settings

```bash
curl http://127.0.0.1:8756/health
curl http://127.0.0.1:8756/settings
# patch any subset of settings (theme, fonts, ai_mode, delight, etc.)
curl -X PATCH http://127.0.0.1:8756/settings \
  -H "Content-Type: application/json" \
  -d '{"values":{"theme_mode":"night","delight_level":"playful","ai_mode":"offline"}}'
```

## Books

```bash
# create (book_type: story_book | movie_script | short_film_script | single_scene)
curl -X POST http://127.0.0.1:8756/books -H "Content-Type: application/json" \
  -d '{"title":"My Novel","book_type":"story_book","logline":"a test"}'
curl http://127.0.0.1:8756/books                         # list
curl http://127.0.0.1:8756/books/<BOOK_ID>               # get one
curl -X PATCH http://127.0.0.1:8756/books/<BOOK_ID> -H "Content-Type: application/json" \
  -d '{"title":"Renamed"}'
curl -X POST http://127.0.0.1:8756/books/<BOOK_ID>/convert -H "Content-Type: application/json" \
  -d '{"book_type":"movie_script"}'                       # non-destructive type change
curl -X DELETE http://127.0.0.1:8756/books/<BOOK_ID>      # 204
```

## Scenes (canonical nodes, shared across books)

```bash
# node_type: scene | plot_point | thought ; title required
curl -X POST http://127.0.0.1:8756/scenes -H "Content-Type: application/json" \
  -d '{"node_type":"scene","title":"Opening","description":"the hero wakes"}'
curl http://127.0.0.1:8756/scenes
curl http://127.0.0.1:8756/scenes/<SCENE_ID>
curl -X PATCH http://127.0.0.1:8756/scenes/<SCENE_ID> -H "Content-Type: application/json" \
  -d '{"title":"Opening (rev)","description":"the hero wakes at dawn"}'   # word_count recomputes
curl -X DELETE http://127.0.0.1:8756/scenes/<SCENE_ID>    # 204
```

### Screenplay elements (script-type books; coexist with description, never clear it)

```bash
# element_type: scene_heading|action|character|dialogue|parenthetical|transition|shot|dual_dialogue
curl http://127.0.0.1:8756/scenes/<SCENE_ID>/elements
curl -X POST http://127.0.0.1:8756/scenes/<SCENE_ID>/elements -H "Content-Type: application/json" \
  -d '{"element_type":"scene_heading","text":"INT. HOUSE - DAY"}'
curl -X PATCH http://127.0.0.1:8756/scenes/elements/<ELEMENT_ID> -H "Content-Type: application/json" \
  -d '{"text":"INT. HOUSE - NIGHT"}'
curl -X DELETE http://127.0.0.1:8756/scenes/elements/<ELEMENT_ID>
curl -X POST http://127.0.0.1:8756/scenes/<SCENE_ID>/elements/reorder -H "Content-Type: application/json" \
  -d '["<ELEMENT_ID_2>","<ELEMENT_ID_1>"]'
```

## Canvas (per-book membership, positions, edges)

```bash
curl http://127.0.0.1:8756/books/<BOOK_ID>/canvas          # {nodes:[...], edges:[...]}
# add an existing scene to a book's canvas (optionally with position/color)
curl -X POST http://127.0.0.1:8756/books/<BOOK_ID>/scenes/<SCENE_ID> -H "Content-Type: application/json" \
  -d '{"canvas_x":120,"canvas_y":80,"color":"#8b5cf6"}'
curl -X PATCH http://127.0.0.1:8756/books/<BOOK_ID>/scenes/<SCENE_ID> -H "Content-Type: application/json" \
  -d '{"canvas_x":200,"canvas_y":140}'
curl -X DELETE http://127.0.0.1:8756/books/<BOOK_ID>/scenes/<SCENE_ID>   # UNLINK only (scene survives)

# edges (connection_type: sequence|causal|reference|contradiction|custom)
curl http://127.0.0.1:8756/books/<BOOK_ID>/edges
curl -X POST http://127.0.0.1:8756/books/<BOOK_ID>/edges -H "Content-Type: application/json" \
  -d '{"source_scene_id":"<A>","target_scene_id":"<B>","connection_type":"sequence"}'
curl -X PATCH http://127.0.0.1:8756/edges/<EDGE_ID> -H "Content-Type: application/json" -d '{"label":"then"}'
curl -X DELETE http://127.0.0.1:8756/edges/<EDGE_ID>

# cross-book move (re-links same scene, 0 new rows) / copy (new scene + copied elements)
curl -X POST "http://127.0.0.1:8756/books/<DEST_BOOK>/scenes/<SCENE_ID>/move?from_book_id=<SRC_BOOK>"
curl -X POST  http://127.0.0.1:8756/books/<DEST_BOOK>/scenes/<SCENE_ID>/copy
```

## Codex (characters/locations/factions/objects; shared like scenes)

```bash
# entry_type: character | location | faction | object_lore
curl -X POST http://127.0.0.1:8756/codex -H "Content-Type: application/json" \
  -d '{"entry_type":"character","name":"Aria","summary":"the protagonist"}'
curl "http://127.0.0.1:8756/codex?entry_type=character"
curl http://127.0.0.1:8756/codex/<CODEX_ID>
curl -X PATCH http://127.0.0.1:8756/codex/<CODEX_ID> -H "Content-Type: application/json" \
  -d '{"summary":"the reluctant protagonist","custom_fields":{"eye_color":"green"}}'
curl -X DELETE http://127.0.0.1:8756/codex/<CODEX_ID>
# link codex <-> scene / book
curl -X POST   http://127.0.0.1:8756/codex/<CODEX_ID>/scenes/<SCENE_ID>
curl -X DELETE http://127.0.0.1:8756/codex/<CODEX_ID>/scenes/<SCENE_ID>
curl http://127.0.0.1:8756/scenes/<SCENE_ID>/codex
curl -X POST   http://127.0.0.1:8756/codex/<CODEX_ID>/books/<BOOK_ID>
curl -X DELETE http://127.0.0.1:8756/codex/<CODEX_ID>/books/<BOOK_ID>
```

## LLM / Enhance (streaming SSE) + audit + Groq key

```bash
# Enhance streams Server-Sent Events. mode: grammar | prose | continuity.
# Under QUILLNIGHT_LLM_STUB=1 it echoes the task text; a real model runs on the AI laptop.
curl -N -X POST http://127.0.0.1:8756/llm/enhance -H "Content-Type: application/json" \
  -d '{"mode":"grammar","text":"the hero wakes","scene_id":"<SCENE_ID>","book_id":"<BOOK_ID>","field":"description"}'
# -> data: {"delta":"...","provider":"ollama"} ...  then  event: done  data: {"provider":"...","log_id":"..."}
# Enhance NEVER writes to the scene — accepting is a separate PATCH /scenes/{id}. Record accept/reject:
curl -X POST http://127.0.0.1:8756/llm/log/<LOG_ID>/accept -H "Content-Type: application/json" -d '{"accepted":true}'

# Groq key seam (in-memory dev seam; never stored to disk/SQLite; real key -> OS keyring via Tauri later)
curl -X POST   http://127.0.0.1:8756/llm/groq-key -H "Content-Type: application/json" -d '{"key":"gsk_..."}'
curl -X DELETE http://127.0.0.1:8756/llm/groq-key
curl -X POST   http://127.0.0.1:8756/llm/test-connection    # {ok, reason?, provider?}
```

## Voice / dictation

```bash
# POST the raw audio bytes as the body (browser sends a MediaRecorder blob). Max 100 MB.
# Under QUILLNIGHT_STT_STUB=1 returns a fixed transcript; real Parakeet/Groq on the AI laptop.
curl -X POST http://127.0.0.1:8756/voice/transcribe --data-binary @clip.webm -H "Content-Type: audio/webm"
curl http://127.0.0.1:8756/voice                          # list voice notes
curl -X POST http://127.0.0.1:8756/voice/<NOTE_ID>/attach -H "Content-Type: application/json" \
  -d '{"attached_entity_type":"scene","attached_entity_id":"<SCENE_ID>"}'
curl -X POST http://127.0.0.1:8756/voice/<NOTE_ID>/discard        # status only; audio kept on disk
curl -X POST http://127.0.0.1:8756/voice/<NOTE_ID>/retranscribe   # reuse stored audio
```

---

## Quick end-to-end smoke (PowerShell one-liners)

```powershell
$B="http://127.0.0.1:8756"
$book = (Invoke-RestMethod "$B/books" -Method Post -ContentType application/json -Body '{"title":"Demo","book_type":"story_book"}')
$scene = (Invoke-RestMethod "$B/scenes" -Method Post -ContentType application/json -Body '{"node_type":"scene","title":"Opening","description":"the hero wakes"}')
Invoke-RestMethod "$B/books/$($book.id)/scenes/$($scene.id)" -Method Post -ContentType application/json -Body '{"canvas_x":100,"canvas_y":100}'
Invoke-RestMethod "$B/books/$($book.id)/canvas"
```

> Endpoints added in later phases (auth/profiles, images, outline/timeline, continuity, export, backup) will be appended here as they ship.
