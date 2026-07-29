"""/backups — local SQLite backup rotation + restore (docs/07-EXPORT-IMPORT-SECURITY.md,
Phase 7 task 8). Rotation also runs automatically on app startup (see app/main.py); these
routes let the user trigger a backup on demand, browse existing snapshots, and restore one.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import backup_service
from app.services.backup_service import BackupError

router = APIRouter(tags=["backups"])


@router.post("/backups/run")
def run_backup() -> dict:
    path = backup_service.run_rotation()
    return {"path": path}


@router.get("/backups")
def get_backups() -> list[dict]:
    return backup_service.list_backups()


@router.post("/backups/{name}/restore")
def restore(name: str) -> dict:
    try:
        backup_service.restore_backup(name)
    except BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"restored": name}
