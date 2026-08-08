"""DEV TOOL — irreversibly wipes all story data from the local Quillnight SQLite DB.

This is **not** shipped app behavior; it exists purely to give developers a fast way
to get back to a "fresh install, still logged in" state during manual QA without
having to delete `app-data/` by hand (which would also nuke profiles/settings).

**Destructive.** It deletes every Book, Scene, Codex entry, Image, canvas edge,
outline/timeline row, continuity flag, draft version, undo-log entry, revision/merge
history row, voice note, writing session, and achievement — plus every media/draft/
audio file on disk that belongs to those rows.

**Preserved, always**: local profiles (`users`), all settings (`app_settings`),
seeded `structure_templates`, the personal spellcheck dictionary
(`personal_dictionary`), and Alembic's own `alembic_version` bookkeeping table. You
will not be logged out and your AI-mode/theme/accessibility settings survive.

**Re-seeding note**: because `app_settings` is preserved wholesale, the
`sample_library` seed marker (a global `AppSetting` row) survives the wipe if it was
already present. `seed_sample_library` (`app/services/sample_library/seeder.py`)
skips seeding whenever that marker exists, regardless of whether `books` is empty —
so a DB that has ever completed a sample-library seed will **not** be re-seeded on
the next sidecar start; it stays genuinely empty. Only a DB that never had the
marker written (first-ever seed attempt failed, or the marker was manually removed)
will get the 4 demo Books re-seeded next start. This is intended behavior, not a bug
in this script — the closing summary reports which case applies to your DB.

**A full-DB backup snapshot is taken BEFORE any deletion** (via
``services.backup_service.run_rotation``, the same rotation the app runs on
startup and hourly thereafter), and then **copied to a pinned filename**
(`pre-reset-quillnight-<timestamp>.sqlite`) that the rotation's `quillnight-*` glob
can never match or trim — the rotating snapshot alone would otherwise be evicted
within ~7 hours of continued app use (`backup_service._trim` keeps only 7). If
either the snapshot or the pin-copy fails, the wipe is aborted — nothing is
deleted. If you change your mind after running this, restore the PINNED path
printed in the summary via ``POST /backups/{name}/restore`` (see
`app/api/backups.py`) — note the pinned file will not show up in `GET /backups` or
the backups UI list (its name doesn't match the `quillnight-*` glob those use), but
the restore endpoint itself has no such prefix requirement and accepts it by name.

Refuses to run the destructive path (`--yes`) while the sidecar appears to be live
at `cfg.host:cfg.port` (`GET /health` answers) — pass `--force` to override that
check if you're sure. Preview (`--dry-run` or no flags) always runs regardless.

Run from apps/sidecar:
    ./.venv/Scripts/python.exe scripts/reset_library.py            # preview only (no --yes)
    ./.venv/Scripts/python.exe scripts/reset_library.py --dry-run  # same, explicit
    ./.venv/Scripts/python.exe scripts/reset_library.py --yes      # actually wipe
    ./.venv/Scripts/python.exe scripts/reset_library.py --yes --force  # skip the live-sidecar check
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

# `QUILLNIGHT_DATA_DIR` must be set BEFORE importing anything under `app.*` —
# `app.config.get_settings()` reads it at import time, and `app.db.base` calls
# `get_settings().ensure_dirs()` (and opens the engine) at module load. Default to
# apps/sidecar/app-data (relative to this script), the same dev data dir
# `scripts/dev.ps1` (repo root) uses, when the caller hasn't already set it.
#
# Recorded BEFORE the setdefault below so the preview/wipe output can tell the
# operator whether `cfg.data_dir` came from an inherited env var (which silently
# wins and could point at a DIFFERENT database than the one you expect) or from
# this script's own default.
_ENV_DATA_DIR_INHERITED = "QUILLNIGHT_DATA_DIR" in os.environ
_SIDECAR_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QUILLNIGHT_DATA_DIR", str(_SIDECAR_ROOT / "app-data"))

sys.path.insert(0, str(_SIDECAR_ROOT))

from sqlalchemy import delete, func, select, text  # noqa: E402
from sqlalchemy.orm import DeclarativeBase, Session  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.base import SessionLocal, engine  # noqa: E402
from app.models import orm  # noqa: E402
from app.services import backup_service  # noqa: E402

# Deletion order matters for FK safety, even though most of these already cascade
# from books/scenes/codex_entries/images (app/db/base.py sets
# `PRAGMA foreign_keys=ON`) — deleting explicitly, leaves-first, keeps this script
# correct regardless of future cascade-config drift. Mirrors the table list/order
# from the task spec.
_DELETE_MODELS: list[type[DeclarativeBase]] = [
    orm.UndoLog,
    orm.SceneMerge,
    orm.SceneRevision,
    orm.ContinuityFlag,
    orm.DraftVersion,
    orm.BookSceneOrder,
    orm.BookSceneLink,
    orm.BookCodexLink,
    orm.CodexSceneLink,
    orm.CodexRelationship,
    orm.CodexArcState,
    orm.Chapter,
    orm.SceneConnection,
    orm.ScreenplayElement,
    orm.EntityImage,
    orm.ImageTag,
    # WritingSession.book_id -> books.id is ON DELETE NO ACTION (not CASCADE), so it must be
    # deleted BEFORE Book — SQLite FKs are checked IMMEDIATE with PRAGMA foreign_keys=ON, and
    # this table is 0 rows today only because session tracking hasn't shipped yet.
    orm.WritingSession,
    orm.Book,
    orm.Scene,
    orm.CodexEntry,
    orm.Image,
    orm.VoiceNote,
    orm.LlmRequestLog,
    orm.Achievement,
]

# Never touched. Row counts are compared before/after inline in `_wipe` (no separate
# assertion helper — see the `after_preserved != before_preserved` check there).
_PRESERVED_MODELS: list[type[DeclarativeBase]] = [
    orm.User,
    orm.AppSetting,
    orm.StructureTemplate,
    orm.PersonalDictionary,
]

# Derived/rebuildable search index virtual tables (Phase 10) — no ORM model, see
# app/services/search_index_service.py for the same raw-SQL-via-text() convention.
_VIRTUAL_TABLES = ["search_fts", "embeddings"]


def _row_counts(db: Session, models: list[type[DeclarativeBase]]) -> dict[str, int]:
    return {
        model.__tablename__: db.execute(select(func.count()).select_from(model)).scalar_one()
        for model in models
    }


def _count_files_under(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for p in root.rglob("*") if p.is_file())


def _delete_files_under(root: Path) -> tuple[int, list[tuple[Path, OSError]]]:
    """Delete every file under `root`, keeping `root` itself. Refuses to touch
    anything that doesn't resolve to inside `root` (traversal guard).

    Never raises for an individual file failure — this runs AFTER the DB commit, so a
    Windows `PermissionError`/`WinError 32` (file held open by the sidecar, Defender, or
    Explorer's thumbnail handler) must not abort the run and leave the operator with an
    uncaught traceback and no summary. Failures are collected and returned instead;
    `missing_ok=True` still handles the ordinary "already gone" case silently.
    """
    if not root.is_dir():
        return 0, []

    resolved_root = root.resolve()
    deleted = 0
    failed: list[tuple[Path, OSError]] = []
    # Deepest paths first so files are removed before their now-empty parent dirs.
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        resolved = path.resolve()
        if resolved_root not in (resolved, *resolved.parents):
            continue  # outside root — never touch (traversal guard)
        if path.is_symlink() or path.is_file():
            try:
                path.unlink(missing_ok=True)
                deleted += 1
            except OSError as exc:
                failed.append((path, exc))
        elif path.is_dir():
            try:
                path.rmdir()  # only succeeds once empty; leave non-empty dirs alone
            except OSError:
                pass
    return deleted, failed


def _print_delete_summary(
    root: Path, deleted: int, failed: list[tuple[Path, OSError]]
) -> None:
    line = f"  {root}: {deleted} file(s) deleted"
    if failed:
        line += f" — could not delete ({len(failed)} files still on disk)"
    print(line)
    for path, exc in failed:
        print(f"    FAILED: {path}  ({exc!r})")


def _print_data_dir_info(cfg) -> None:
    source = (
        "inherited from the QUILLNIGHT_DATA_DIR environment variable"
        if _ENV_DATA_DIR_INHERITED
        else "defaulted to apps/sidecar/app-data (QUILLNIGHT_DATA_DIR was not set)"
    )
    print(f"Data dir: {cfg.data_dir}  [{source}]")
    print(f"DB path:  {cfg.db_path}")


def _sidecar_is_running(cfg) -> bool:
    """Probe `GET /health` with a short timeout. Any response at all — even a non-200 —
    means something is listening on that host:port; a connection error/timeout means
    the sidecar is not running there."""
    url = f"http://{cfg.host}:{cfg.port}/health"
    try:
        urllib.request.urlopen(url, timeout=1)
        return True
    except urllib.error.HTTPError:
        return True  # answered, just not a 200 — still means something is listening
    except Exception:  # noqa: BLE001 — connection refused/timeout/etc all mean "not running"
        return False


def _clear_search_index() -> dict[str, str]:
    """`DELETE FROM search_fts` / `embeddings`, log-and-continue per table. The
    `embeddings` vec0 table needs the sqlite-vec extension; if it's unavailable the
    wipe must still succeed for everything else."""
    results: dict[str, str] = {}
    for table in _VIRTUAL_TABLES:
        try:
            with engine.begin() as conn:
                # `table` only ever comes from the fixed `_VIRTUAL_TABLES` literal above,
                # never from user/request input, so this isn't an injection vector.
                conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608
            results[table] = "cleared"
        except Exception as exc:  # noqa: BLE001 — best-effort, must never block the wipe
            results[table] = f"skipped ({exc!r})"
    return results


def _print_table(title: str, before: dict[str, int], after: dict[str, int] | None = None) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    width = max((len(name) for name in before), default=0)
    for name, count in before.items():
        if after is None:
            print(f"  {name.ljust(width)}  {count:>8} row(s)")
        else:
            print(f"  {name.ljust(width)}  {count:>8} -> {after[name]:>8}")


def _preview(db: Session, cfg) -> None:
    delete_counts = _row_counts(db, _DELETE_MODELS)
    preserved_counts = _row_counts(db, _PRESERVED_MODELS)
    media_files = _count_files_under(cfg.media_dir)
    draft_files = _count_files_under(cfg.drafts_dir)
    audio_files = _count_files_under(cfg.audio_dir)

    print("DRY RUN — nothing will be deleted. Pass --yes to actually wipe.")
    _print_data_dir_info(cfg)
    _print_table("Would DELETE all rows from:", delete_counts)
    _print_table("Would PRESERVE (untouched):", preserved_counts)
    print("\nWould delete files under:")
    print(f"  {cfg.media_dir}   {media_files} file(s)")
    print(f"  {cfg.drafts_dir}  {draft_files} file(s)")
    print(f"  {cfg.audio_dir}   {audio_files} file(s)")
    print(f"\nWould clear search index tables: {', '.join(_VIRTUAL_TABLES)}")
    print(
        "\nA backup snapshot would be taken first via backup_service.run_rotation(), then "
        "copied to a pinned 'pre-reset-*' filename that backup rotation never trims."
    )


def _wipe(db: Session, cfg) -> None:
    before_delete = _row_counts(db, _DELETE_MODELS)
    before_preserved = _row_counts(db, _PRESERVED_MODELS)

    _print_data_dir_info(cfg)

    # 1. Backup BEFORE any delete. Abort the whole wipe if this fails.
    try:
        snapshot_path = backup_service.run_rotation()
    except Exception as exc:  # noqa: BLE001 — must abort, not proceed without a safety net
        print(f"\nERROR: backup snapshot failed, aborting wipe. Nothing was deleted.\n  {exc!r}",
              file=sys.stderr)
        sys.exit(1)

    # 1b. Copy the snapshot to a pinned filename the rotation glob (`quillnight-*`) can
    # never match/trim — run_rotation() alone keeps only 7 snapshots, and both startup and
    # the hourly timer call it, so the pre-wipe snapshot would otherwise be evicted within
    # ~7 hours of continued app use, leaving no copy of the wiped data at all. If the pin
    # copy fails, abort before deleting anything — an unpinned snapshot is not good enough.
    snapshot_path_obj = Path(snapshot_path)
    pinned_path = snapshot_path_obj.with_name(f"pre-reset-{snapshot_path_obj.stem}.sqlite")
    try:
        shutil.copyfile(snapshot_path_obj, pinned_path)
    except OSError as exc:
        print(
            f"\nERROR: could not pin the safety snapshot to {pinned_path}, aborting wipe. "
            f"Nothing was deleted.\n  {exc!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Backup snapshot taken: {snapshot_path}")
    print(f"PINNED restore point (never auto-trimmed): {pinned_path}")
    print(
        "Restore via  POST /backups/{name}/restore  using the PINNED filename above if you "
        "change your mind. NOTE: because its name doesn't match the 'quillnight-*' glob "
        "list_backups()/GET /backups use, the pinned file will NOT appear in that list or "
        "the backups UI — but restore_backup() only checks that the name has no path "
        "separators/'..' and resolves directly under backups/, with no 'quillnight-' prefix "
        "requirement, so restoring it by name still works."
    )

    # 2. Delete story-data tables, in dependency order, as one transaction.
    for model in _DELETE_MODELS:
        db.execute(delete(model))
    db.commit()

    after_delete = _row_counts(db, _DELETE_MODELS)
    _print_table("Deleted rows:", before_delete, after_delete)

    # 3. Assert preserved tables are untouched.
    after_preserved = _row_counts(db, _PRESERVED_MODELS)
    _print_table("Preserved rows (before -> after, must be unchanged):",
                 before_preserved, after_preserved)
    if after_preserved != before_preserved:
        print(
            "\nERROR: a preserved table's row count changed — this should be impossible. "
            f"Restore the PINNED snapshot at {pinned_path} and investigate before trusting "
            "this DB.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 4. Clear the derived search index (best-effort, never blocks the wipe).
    index_results = _clear_search_index()
    print("\nSearch index:")
    for table, result in index_results.items():
        print(f"  {table}: {result}")
    if any(result.startswith("skipped") for result in index_results.values()):
        print("  Note: run  POST /search/backfill  afterwards to re-derive the skipped index.")

    # 5. Delete media/draft/audio files on disk (never touch backups/ or the sqlite files).
    media_deleted, media_failed = _delete_files_under(cfg.media_dir)
    draft_deleted, draft_failed = _delete_files_under(cfg.drafts_dir)
    audio_deleted, audio_failed = _delete_files_under(cfg.audio_dir)
    print("\nFiles deleted:")
    _print_delete_summary(cfg.media_dir, media_deleted, media_failed)
    _print_delete_summary(cfg.drafts_dir, draft_deleted, draft_failed)
    _print_delete_summary(cfg.audio_dir, audio_deleted, audio_failed)

    # 6. Report whether the next sidecar start will re-seed the sample library — see the
    # module docstring's "Re-seeding note" for why this depends on the marker, not on
    # `books` being empty (which it always is here, right after step 2).
    marker_present = (
        db.execute(
            select(orm.AppSetting.id).where(
                orm.AppSetting.user_id.is_(None), orm.AppSetting.key == "sample_library"
            )
        ).first()
        is not None
    )
    print("\nSample library re-seed on next sidecar start:")
    if marker_present:
        print(
            "  NO — the 'sample_library' marker in app_settings survived the wipe "
            "(app_settings is always preserved). The library stays genuinely empty."
        )
    else:
        print(
            "  YES — no 'sample_library' marker was found in app_settings, so "
            "seed_sample_library() will seed the 4 demo Books on next start. This is "
            "intended (see app/services/sample_library/seeder.py)."
        )

    print("\nDone. Profiles, settings, and structure templates were preserved.")
    print(f"Restore point if needed: {pinned_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DEV TOOL: destructively wipe all story data from the local "
        "Quillnight DB, preserving profiles/settings. Takes a backup snapshot first.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually perform the wipe (required to delete anything).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly request preview-only mode (this is also the default without --yes).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip the live-sidecar check that otherwise blocks --yes when GET /health "
        "answers at cfg.host:cfg.port. Has no effect on preview mode.",
    )
    args = parser.parse_args()

    cfg = get_settings()

    with SessionLocal() as db:
        if args.dry_run or not args.yes:
            _preview(db, cfg)
            sys.exit(0)

        if not args.force and _sidecar_is_running(cfg):
            print(
                f"Sidecar is running at http://{cfg.host}:{cfg.port} — stop it first "
                "(Ctrl-C in scripts/dev.ps1), or re-run with --force to override.",
                file=sys.stderr,
            )
            sys.exit(1)

        _wipe(db, cfg)


if __name__ == "__main__":
    main()
