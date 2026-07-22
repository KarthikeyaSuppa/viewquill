# Quillnight sidecar (FastAPI)

Local domain/AI backend. Owns all data + AI orchestration; the React frontend talks to it
over `127.0.0.1` only. See `../../docs/02-ARCHITECTURE.md`.

## Run (standalone dev)

```powershell
cd apps/sidecar
python -m venv .venv                       # first time only
./.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
# dev app-data lives in a gitignored ./app-data folder:
$env:QUILLNIGHT_DATA_DIR = "$PWD/app-data"
./.venv/Scripts/python.exe -m app.main     # serves http://127.0.0.1:8756
```

- `GET /health` — readiness (DB + Ollama probe). Ollama shows `reachable: false` until it's
  installed on a capable machine — expected on the build laptop (no models here).
- `GET /settings` / `PATCH /settings` — the `app_settings` key/value store (theme, fonts,
  delight, AI mode, …). No secrets ever pass through it.
- `GET /docs` — interactive OpenAPI UI.

## Database & migrations

SQLite via SQLAlchemy 2.0 + Alembic. The schema of record is `../../docs/03-DATA-MODEL.md`,
mapped 1:1 in `app/models/orm.py`. Migrations run automatically on startup; to run by hand:

```powershell
$env:QUILLNIGHT_DATA_DIR = "$PWD/app-data"
./.venv/Scripts/python.exe -m alembic -c alembic.ini upgrade head
# after editing app/models/orm.py:
./.venv/Scripts/python.exe -m alembic -c alembic.ini revision --autogenerate -m "message"
```

## Layout

```
app/
  main.py              app factory, CORS (localhost only), startup migration + Ollama probe
  config.py            operational config (bind, data dir, model-name fallbacks)
  api/                 routers: health.py, settings.py  (books/scenes/… added per phase)
  services/            settings_service.py, ollama_health.py  (llm/continuity/etc. per phase)
  models/              orm.py (schema of record) + schemas.py (Pydantic contracts)
  db/                  base.py (engine/session), migrate.py, migrations/ (Alembic)
```

## Not installed on the build laptop (deferred to their phases / the AI laptop)

`litellm`, `onnx-asr`/`sounddevice`/`silero-vad` (voice), `weasyprint`/`python-docx`/
`jinja2`/`screenplay-tools` (export), `pyrage` (encryption), `sqlite-vec` (semantic). No LLM
model is ever downloaded here — AI testing happens on a second machine (see `../../CLAUDE.md`).
