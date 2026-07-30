"""Tests for GET /backups/status (Phase 9 task 2, docs/14-DEFERRED-ENHANCEMENTS.md §B2).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app), matching
the pattern in tests/test_export.py -- the app's own lifespan runs a startup backup rotation
(app/main.py), so by the time the ``client`` fixture is ready a first snapshot already
exists; the "no backup yet" / null case is covered at the service level in
tests/test_backup_service.py instead, where the throwaway data dir is never touched by
lifespan startup.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

from datetime import datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (migrations + the startup
    # backup rotation) against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        yield test_client


def test_backup_status_populated_after_startup_rotation(client: TestClient) -> None:
    resp = client.get("/backups/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"last_backup_at", "next_backup_at"}
    assert body["last_backup_at"] is not None
    assert body["next_backup_at"] is not None

    last_dt = datetime.fromisoformat(body["last_backup_at"])
    next_dt = datetime.fromisoformat(body["next_backup_at"])
    interval = get_settings().backup_interval_minutes
    assert next_dt - last_dt == timedelta(minutes=interval)


def test_backup_status_advances_after_a_manual_run(client: TestClient) -> None:
    before = client.get("/backups/status").json()

    resp = client.post("/backups/run")
    assert resp.status_code == 200

    after = client.get("/backups/status").json()
    before_dt = datetime.fromisoformat(before["last_backup_at"])
    after_dt = datetime.fromisoformat(after["last_backup_at"])
    assert after_dt >= before_dt


def test_manual_run_returns_clean_500_instead_of_raw_traceback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reviewer-flagged gap: POST /backups/run had no error handling at all, so a rare
    run_rotation() failure (e.g. a filename collision) would surface as an unhandled 500
    with a raw traceback rather than a clean JSON error response."""
    from app.services import backup_service

    def boom(*args, **kwargs):
        raise RuntimeError("simulated VACUUM INTO collision")

    monkeypatch.setattr(backup_service, "run_rotation", boom)

    resp = client.post("/backups/run")

    assert resp.status_code == 500
    assert "simulated VACUUM INTO collision" in resp.json()["detail"]
