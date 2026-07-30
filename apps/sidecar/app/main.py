"""FastAPI application factory + entrypoint for the Quillnight sidecar.

Startup runs Alembic migrations (bringing a fresh DB straight to the schema of record) and
probes Ollama (non-fatal — the runtime may not be bundled yet). CORS is locked to localhost
and the Tauri WebView origins; the sidecar is never exposed off-host (docs/02).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import (
    auth as auth_api,
    backups as backups_api,
    books as books_api,
    canvas as canvas_api,
    chapters as chapters_api,
    codex as codex_api,
    continuity as continuity_api,
    draft_preview as draft_preview_api,
    export as export_api,
    health,
    images as images_api,
    import_export as import_export_api,
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
from app.services import backup_service
from app.services.ollama_health import check_ollama
from app.services.structure_templates import seed_structure_templates

logger = logging.getLogger("quillnight")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# localhost (any port) + Tauri's WebView origins on Windows.
_ALLOW_ORIGIN_REGEX = r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost|https://tauri\.localhost)$"

# Floor on the periodic backup cadence regardless of what's configured (config.py's
# ``backup_interval_minutes``) — protects against a misconfiguration hammering the DB with
# back-to-back VACUUM INTO snapshots.
_MIN_BACKUP_INTERVAL_MINUTES = 5


def _effective_backup_interval_seconds(interval_minutes: int) -> float:
    return max(interval_minutes, _MIN_BACKUP_INTERVAL_MINUTES) * 60


async def _backup_rotation_loop(interval_seconds: float) -> None:
    """Runs ``backup_service.run_rotation`` every ``interval_seconds`` until cancelled.

    Takes a raw seconds value (no floor applied here) so tests can drive it with a tiny
    interval instead of waiting on real time; ``_periodic_backup_loop`` below is the
    production entrypoint that applies the configured-minutes floor.

    Cancellation (app shutdown) is only ever observed at the ``asyncio.sleep`` below, between
    rotations. Once a rotation has started it is shielded from this task's own cancellation,
    so a shutdown that lands mid-rotation can't interrupt ``VACUUM INTO`` and can't leave a
    partial snapshot file behind — the shielded rotation is always awaited to completion (even
    if that means shutdown waits a moment) before the ``CancelledError`` is re-raised. The loop
    is also strictly sequential: it only starts the next rotation after the previous one has
    fully finished, so two rotations from this timer can never overlap.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        rotation = asyncio.ensure_future(asyncio.to_thread(backup_service.run_rotation))
        try:
            await asyncio.shield(rotation)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):  # noqa: BLE001 — already shutting down
                await rotation
            raise
        except Exception:  # noqa: BLE001 — a failed periodic rotation must never kill the loop
            logger.exception("Periodic backup rotation failed; will retry next interval.")


async def _periodic_backup_loop(interval_minutes: int) -> None:
    """Production entrypoint: floors ``interval_minutes`` then runs the rotation loop."""
    await _backup_rotation_loop(_effective_backup_interval_seconds(interval_minutes))


@contextlib.asynccontextmanager
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
    try:
        snapshot = backup_service.run_rotation()
        logger.info("Backup rotation complete: %s", snapshot)
    except Exception:  # noqa: BLE001 — a failed backup must never block startup
        logger.exception("Backup rotation failed; continuing without it.")

    backup_task = asyncio.create_task(_periodic_backup_loop(cfg.backup_interval_minutes))
    try:
        yield
    finally:
        backup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await backup_task
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
    app.include_router(backups_api.router)
    app.include_router(profiles_api.router)
    app.include_router(auth_api.router)
    app.include_router(settings_api.router)
    app.include_router(books_api.router)
    app.include_router(scenes_api.router)
    app.include_router(canvas_api.router)
    app.include_router(codex_api.router)
    app.include_router(images_api.router)
    app.include_router(images_api.entities_router)
    app.include_router(llm_api.router)
    app.include_router(voice_api.router)
    app.include_router(structure_templates_api.router)
    app.include_router(chapters_api.router)
    app.include_router(outline_api.router)
    app.include_router(continuity_api.router)
    # Registered before export_api.router: FastAPI matches routes in registration order,
    # and export_api's `/{book_id}/export/{format}` path pattern would otherwise shadow
    # `/{book_id}/export/bundle` (both match the same path shape) and fail format
    # validation with a 422 before this router ever gets a chance to handle it.
    app.include_router(import_export_api.router)
    app.include_router(export_api.router)
    app.include_router(export_api.draft_versions_router)
    app.include_router(draft_preview_api.router)

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
