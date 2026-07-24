"""FastAPI application factory + entrypoint for the Quillnight sidecar.

Startup runs Alembic migrations (bringing a fresh DB straight to the schema of record) and
probes Ollama (non-fatal — the runtime may not be bundled yet). CORS is locked to localhost
and the Tauri WebView origins; the sidecar is never exposed off-host (docs/02).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import (
    auth as auth_api,
    books as books_api,
    canvas as canvas_api,
    chapters as chapters_api,
    codex as codex_api,
    continuity as continuity_api,
    health,
    images as images_api,
    llm as llm_api,
    outline as outline_api,
    profiles as profiles_api,
    scenes as scenes_api,
    settings as settings_api,
    structure_templates as structure_templates_api,
    voice as voice_api,
)
from app.config import get_settings
from app.db.base import SessionLocal
from app.db.migrate import run_migrations
from app.services.ollama_health import check_ollama
from app.services.structure_templates import seed_structure_templates

logger = logging.getLogger("quillnight")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# localhost (any port) + Tauri's WebView origins on Windows.
_ALLOW_ORIGIN_REGEX = r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost|https://tauri\.localhost)$"


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    logger.info("Quillnight sidecar starting — data dir: %s", cfg.data_dir)
    run_migrations()
    logger.info("Database migrated to head: %s", cfg.db_path)
    try:
        with SessionLocal() as db:
            seeded = seed_structure_templates(db)
        logger.info("Structure templates seeded (%d new).", seeded)
    except Exception:  # noqa: BLE001 — seeding must never block startup
        logger.exception("Structure template seeding failed; continuing without it.")
    probe = check_ollama()
    logger.info("Ollama %s (%s)", "reachable" if probe.reachable else "unreachable", probe.detail)
    yield
    logger.info("Quillnight sidecar shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Quillnight Sidecar",
        version=__version__,
        summary="Local domain/AI backend for the Quillnight story app.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_ALLOW_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(profiles_api.router)
    app.include_router(auth_api.router)
    app.include_router(settings_api.router)
    app.include_router(books_api.router)
    app.include_router(scenes_api.router)
    app.include_router(canvas_api.router)
    app.include_router(codex_api.router)
    app.include_router(images_api.router)
    app.include_router(llm_api.router)
    app.include_router(voice_api.router)
    app.include_router(structure_templates_api.router)
    app.include_router(chapters_api.router)
    app.include_router(outline_api.router)
    app.include_router(continuity_api.router)

    @app.get("/", tags=["health"])
    def root() -> dict[str, str]:
        return {"service": "quillnight-sidecar", "version": __version__, "docs": "/docs"}

    return app


app = create_app()


def main() -> None:
    """Standalone/PyInstaller entrypoint."""
    cfg = get_settings()
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
