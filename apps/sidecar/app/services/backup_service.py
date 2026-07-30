"""Local SQLite backup rotation (docs/07-EXPORT-IMPORT-SECURITY.md, Phase 7 task 8).

Snapshots the live database via ``VACUUM INTO`` — a consistent point-in-time copy that
doesn't require stopping writers — into ``data_dir/backups/quillnight-<UTC ISO
timestamp>.sqlite`` (colons replaced with ``-`` for Windows filename safety), then trims
down to the newest ``keep`` snapshots. Filenames sort chronologically because the timestamp
is ISO-8601, so "oldest" is simply "alphabetically first".

Uses its own throwaway SQLAlchemy engine/connection rather than ``app.db.base``'s
module-level engine — ``VACUUM INTO`` cannot run inside a transaction, so this needs a
fresh AUTOCOMMIT connection, and it means rotation never has to reason about the app's
long-lived connection pool or WAL state.

Restoring is never a silent overwrite: ``restore_backup`` always takes a fresh safety
snapshot of the CURRENT database before replacing it, so a bad restore is itself
recoverable from another backup.
"""

from __future__ import annotations

import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine

from app.config import get_settings

_PREFIX = "quillnight-"
_SUFFIX = ".sqlite"

# Serializes run_rotation()'s body between call sites: the periodic timer (app/main.py,
# via asyncio.to_thread) and the manual "run now" endpoint (api/backups.py, via FastAPI's
# threadpool) are both real OS threads, not coroutines on the same event loop, so an
# asyncio.Lock would not help here -- only a threading.Lock actually excludes them from
# each other. Without this, two rotations landing in the same microsecond tick could pick
# an identical snapshot filename and have VACUUM INTO raise (the filename is otherwise
# only as unique as the clock's resolution -- see _timestamp below). Scoped to just the
# snapshot+trim body, not the module -- list_backups/backup_status/restore_backup's own
# reads/writes are unaffected (restore_backup's internal run_rotation call still goes
# through this same lock, it's just not held for restore's copy/dispose work).
_rotation_lock = threading.Lock()


class BackupError(Exception):
    """Raised for invalid backup names or a missing backup file — never for ordinary
    filesystem errors, which should bubble up as-is."""


def _backups_dir() -> Path:
    d = get_settings().data_dir / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _timestamp(now: datetime | None = None) -> str:
    # Microsecond precision (not just seconds) — two rotations can legitimately happen
    # within the same second (e.g. the startup rotation immediately followed by a
    # manual "run now"), and VACUUM INTO errors out ("output file already exists") on a
    # filename collision.
    dt = now or datetime.now(UTC)
    return dt.isoformat(timespec="microseconds").replace(":", "-")


def _trim(backups_dir: Path, keep: int) -> None:
    files = sorted(backups_dir.glob(f"{_PREFIX}*{_SUFFIX}"))
    excess = len(files) - keep
    for stale in files[: max(excess, 0)]:
        stale.unlink(missing_ok=True)


def run_rotation(keep: int = 7, now: datetime | None = None) -> str:
    """Snapshot the live DB, then delete the oldest snapshots beyond ``keep``.

    Returns the new snapshot's absolute path as a string.
    """
    with _rotation_lock:
        cfg = get_settings()
        backups_dir = _backups_dir()
        snapshot_path = backups_dir / f"{_PREFIX}{_timestamp(now)}{_SUFFIX}"

        engine = create_engine(cfg.database_url, connect_args={"check_same_thread": False})
        try:
            conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
            try:
                conn.exec_driver_sql(f"VACUUM INTO '{snapshot_path.as_posix()}'")
            finally:
                conn.close()
        finally:
            engine.dispose()

        _trim(backups_dir, keep)
        return str(snapshot_path)


def list_backups() -> list[dict]:
    """Newest-first list of ``{name, size_bytes, created_at}`` for every snapshot on disk."""
    backups_dir = _backups_dir()
    files = sorted(backups_dir.glob(f"{_PREFIX}*{_SUFFIX}"), reverse=True)
    out: list[dict] = []
    for f in files:
        stat = f.stat()
        out.append(
            {
                "name": f.name,
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=UTC
                ).isoformat(timespec="seconds"),
            }
        )
    return out


def backup_status() -> dict:
    """Read-only ``{last_backup_at, next_backup_at}`` for a frontend backup-staleness nudge
    (Phase 9 task 2, docs/14-DEFERRED-ENHANCEMENTS.md §B2).

    Never touches rotation/restore state -- purely derived from whatever's already on disk
    (``list_backups``, newest-first) plus the configured ``backup_interval_minutes``. Both
    fields are ``None`` when no backup has ever run yet (e.g. a brand-new install before
    startup's first rotation completes).
    """
    backups = list_backups()
    if not backups:
        return {"last_backup_at": None, "next_backup_at": None}

    last_backup_at = backups[0]["created_at"]
    interval_minutes = get_settings().backup_interval_minutes
    last_dt = datetime.fromisoformat(last_backup_at)
    next_backup_at = (last_dt + timedelta(minutes=interval_minutes)).isoformat(
        timespec="seconds"
    )
    return {"last_backup_at": last_backup_at, "next_backup_at": next_backup_at}


def restore_backup(name: str) -> None:
    """Replace the live DB with a chosen backup, after first snapshotting the current DB.

    Raises ``BackupError`` if ``name`` looks like a path-traversal attempt or doesn't
    resolve to a real, in-bounds file under the backups directory.
    """
    if not name or "/" in name or "\\" in name or ".." in name:
        raise BackupError(f"Invalid backup name: {name!r}")

    backups_dir = _backups_dir()
    candidate = (backups_dir / name).resolve()
    backups_dir_resolved = backups_dir.resolve()
    if backups_dir_resolved not in (candidate, *candidate.parents):
        raise BackupError(f"Invalid backup name: {name!r}")
    if candidate.parent != backups_dir_resolved or not candidate.is_file():
        raise BackupError(f"Backup not found: {name!r}")

    # Never lose data on a bad restore: snapshot the CURRENT db first.
    run_rotation()

    cfg = get_settings()

    # The app runs SQLite in WAL mode (app/db/base.py PRAGMA journal_mode=WAL). The
    # module-level pooled engine may be holding open connections against the live db
    # file, and its `-wal`/`-shm` sidecars can contain frames that haven't been
    # checkpointed into the main file yet. If we copy the backup over cfg.db_path while
    # those connections/sidecars are still around, SQLite can replay the *old* WAL
    # frames against the *new* (restored) main file on next open and corrupt it. So:
    # dispose the pool first to drop all live connections, do the copy, then remove the
    # live db's stale -wal/-shm sidecars so nothing stale gets replayed against the
    # freshly-restored file.
    from app.db.base import engine

    engine.dispose()

    shutil.copyfile(candidate, cfg.db_path)

    for suffix in ("-wal", "-shm"):
        Path(str(cfg.db_path) + suffix).unlink(missing_ok=True)
