"""LAN Notes — the SEPARATE, security-isolated LAN-exposed surface (docs/06 roadmap tasks
T5+T10) that lets a second device (phone) on the same Wi-Fi read/write the one shared
'lan' scratch-note over the network, without exposing anything else this app owns.

Hard isolation rule (see app/lan/server.py's `build_lan_app` docstring for the mechanism):
this package NEVER imports `app.main`/`create_app()` or any `app.api.*` router. Its own
`app.lan.routes.router` is the entire route surface a LAN caller can ever reach — /pair,
GET /note, PUT /note, nothing else. `app.main` only reaches INTO this package (to start/
stop the LAN server and mint pairing codes from the trusted 127.0.0.1 side); this package
never reaches back into `app.main`.

Modules:
    security.py — in-memory (process-lifetime, never persisted) pairing-code + device-token
                  state, mirroring app/services/groq_key.py's secret-seam pattern.
    routes.py    — the APIRouter with ONLY /pair, /note.
    server.py    — `build_lan_app()` (the isolated FastAPI instance) + start/stop/status
                  helpers for the actual 0.0.0.0 uvicorn server.
"""

from __future__ import annotations
