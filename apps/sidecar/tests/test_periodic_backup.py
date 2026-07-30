"""Tests for the periodic backup timer (app/main.py's ``_backup_rotation_loop`` /
``_periodic_backup_loop`` / ``_effective_backup_interval_seconds``, Phase 9 task 1,
docs/14-DEFERRED-ENHANCEMENTS.md §B2).

Uses the same ``anyio``/``asyncio_backend`` pattern as tests/test_llm_orchestrator.py. The
loop's own ``backup_service.run_rotation`` is monkeypatched out for every test here so these
never touch a real SQLite file or a real clock -- the production rotation logic already has
full coverage in tests/test_backup_service.py; this module is only about the *scheduling and
cancellation* wrapper around it.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from app import main as main_module


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ── 1. interval floor ──────────────────────────────────────────────────────────────────────


def test_effective_interval_floors_misconfigured_values() -> None:
    assert main_module._effective_backup_interval_seconds(1) == 5 * 60
    assert main_module._effective_backup_interval_seconds(0) == 5 * 60
    assert main_module._effective_backup_interval_seconds(-30) == 5 * 60


def test_effective_interval_passes_through_above_floor() -> None:
    assert main_module._effective_backup_interval_seconds(60) == 60 * 60
    assert main_module._effective_backup_interval_seconds(10) == 10 * 60


# ── 2. the loop actually fires repeatedly ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_loop_fires_more_than_once_within_short_window(monkeypatch) -> None:
    call_count = 0

    def fake_rotation() -> str:
        nonlocal call_count
        call_count += 1
        return f"snapshot-{call_count}"

    monkeypatch.setattr(main_module.backup_service, "run_rotation", fake_rotation)

    task = asyncio.create_task(main_module._backup_rotation_loop(0.05))
    await asyncio.sleep(0.3)  # ~6 tick windows at 0.05s -- plenty of headroom for CI jitter

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert call_count >= 2, f"expected multiple rotations, got {call_count}"


# ── 3. cancellation is clean and never leaves a partial snapshot ──────────────────────────


@pytest.mark.anyio
async def test_cancel_during_rotation_does_not_leak_and_finishes_the_snapshot(
    monkeypatch,
) -> None:
    """Simulates shutdown landing exactly while a rotation is mid-flight.

    ``fake_rotation`` marks the snapshot file only *after* its (simulated) slow work, so if
    cancellation ever interrupted the rotation itself, the file would either be missing or
    left in a half-written state. Because the loop shields the rotation call, the file must
    always end up fully written, and ``task.cancel()`` must not raise or hang.
    """
    started = threading.Event()
    finished = threading.Event()
    snapshot_written = threading.Event()

    def fake_rotation() -> str:
        started.set()
        # Simulate VACUUM INTO taking a noticeable moment -- long enough that the test can
        # reliably cancel while this is running.
        import time

        time.sleep(0.2)
        snapshot_written.set()  # the "file" only ever appears fully written, never partial
        finished.set()
        return "snapshot"

    monkeypatch.setattr(main_module.backup_service, "run_rotation", fake_rotation)

    task = asyncio.create_task(main_module._backup_rotation_loop(0.01))

    # Wait until the fake rotation has actually started running in its worker thread.
    await asyncio.get_event_loop().run_in_executor(None, started.wait, 2.0)
    assert started.is_set(), "rotation never started -- test setup is wrong"
    assert not snapshot_written.is_set(), "rotation finished before we could cancel it"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The shielded rotation must have been allowed to run to completion -- no partial file,
    # no dangling thread, no leaked/swallowed-elsewhere exception.
    assert finished.is_set()
    assert snapshot_written.is_set()
