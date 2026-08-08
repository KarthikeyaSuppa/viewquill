"""Lifecycle tests for ``app/lan/server.py``'s ``start_lan_server``/``stop_lan_server`` —
regression coverage for the review fix "bind-failure is silently swallowed."

Before the fix, a bind failure (e.g. ``lan_port`` already taken by another process) left
``_server`` set anyway, so ``is_running()``/``get_share_status()`` kept reporting
``sharing: true`` for a listener that never actually came up — and worse, because
``uvicorn.Server.startup()`` signals a bind failure via ``sys.exit`` rather than an ordinary
exception, letting that propagate out of the background ``asyncio.Task`` unguarded would
crash the entire process's event loop, not just this LAN feature.

Unlike ``tests/test_lan_isolation.py`` (which only ever exercises ``build_lan_app()`` via
``TestClient``'s in-process ASGI transport and never binds a real socket), this module is the
one place that actually calls ``start_lan_server()``/``stop_lan_server()`` and binds
``0.0.0.0:<lan_port>`` for real.

Throwaway-DB fixture mirrors ``tests/test_lan_isolation.py``/``tests/test_notes_service.py``:
``QUILLNIGHT_DATA_DIR`` is set to a fresh temp dir before ``app.config``/``app.lan.server`` are
ever imported. This module previously skipped that setup — harmless on its own, since none of
its tests touch note content — but per ``tests/conftest.py``'s module docstring, whichever test
module is collected *first* in a given ``pytest`` invocation "wins" the one-time
engine/``SessionLocal`` build for the whole session. Left unset here, and with this module
listed first on the command line (exactly as documented in this task's own verify command),
that meant THIS module's import was what pinned every other module in the run onto the real
``app-data/quillnight.sqlite`` instead of an isolated temp DB — silently polluting production
note-channel rows (``tests/test_lan_isolation.py``'s ``"lan"`` channel,
``tests/test_notes_service.py``'s ``"lan-test-*"`` channels) across every real test run, and
then failing on any *subsequent* run once those channels' clocks had already moved forward.
Setting this here — even though this module's own tests don't need it — is what makes running
these three files together (as this task's verify step does) actually get a fresh, real
isolated DB every time.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-lanserver-")
os.environ.setdefault("QUILLNIGHT_DATA_DIR", _TMP_DATA_DIR)

import asyncio  # noqa: E402
import socket  # noqa: E402

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.lan import server  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
async def _ensure_stopped():
    """Every test starts and ends with the LAN server confirmed stopped — ``server.py``'s
    module-level ``_server``/``_serve_task`` are process-lifetime state, so tests would
    otherwise leak a real bound socket into each other."""
    await server.stop_lan_server()
    yield
    await server.stop_lan_server()


@pytest.mark.anyio
async def test_start_then_stop_reports_accurate_status() -> None:
    assert server.is_running() is False
    assert server.get_share_status()["sharing"] is False

    await server.start_lan_server()
    assert server.is_running() is True
    assert server.get_share_status()["sharing"] is True

    await server.stop_lan_server()
    assert server.is_running() is False
    assert server.get_share_status()["sharing"] is False


@pytest.mark.anyio
async def test_double_start_is_a_no_op_not_a_double_bind() -> None:
    await server.start_lan_server()
    first_task = server._serve_task

    await server.start_lan_server()  # must no-op: no second bind, no orphaned first task
    assert server._serve_task is first_task
    assert server.is_running() is True


@pytest.mark.anyio
async def test_bind_failure_raises_and_leaves_state_not_running() -> None:
    """The core regression: if the port is already taken by something else,
    ``start_lan_server`` must raise — never silently succeed — and must leave
    ``is_running()``/``get_share_status()['sharing']`` reporting ``False`` afterward, never
    ``True`` for a listener that never came up. Also proves the failure doesn't take the
    whole process down with it (uvicorn's own bind-failure path is a raw ``sys.exit``,
    unsafe to let escape a background ``asyncio.Task`` unguarded — see ``start_lan_server``'s
    comments in ``app/lan/server.py``): if it had, this test process would already be dead
    before the assertions below ever ran.
    """
    port = get_settings().lan_port
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("0.0.0.0", port))
    blocker.listen(1)
    try:
        with pytest.raises(RuntimeError):
            await server.start_lan_server()
    finally:
        blocker.close()

    assert server.is_running() is False
    assert server.get_share_status()["sharing"] is False
    assert server._server is None
    assert server._serve_task is None

    # The process (and this event loop) is still perfectly usable afterward — prove it by
    # successfully starting for real now that the port has been freed.
    await server.start_lan_server()
    assert server.is_running() is True


@pytest.mark.anyio
async def test_cancellation_during_start_does_not_orphan_the_listener() -> None:
    """Regression test for the review fix: `start_lan_server` must tear down its background
    ``serve()`` task and reset module state even if the coroutine running it is cancelled
    while parked on the readiness poll — exactly what happens in production when Starlette
    cancels the ``start_lan_share`` request handler's task because the client disconnected
    during the up-to-2s start window. Before the fix, the cancellation propagated straight
    out of ``start_lan_server`` with ``_server``/``_serve_task`` never assigned, leaving a
    real bound listener with no module handle: ``is_running()`` reported ``False`` so nothing
    would ever call ``stop_lan_server()`` on it, and the port stayed wedged.

    Uses a fake ``uvicorn.Server`` (rather than the real one) that genuinely binds/listens
    on ``lan_port`` — so the "orphaned real listener" failure mode is faithfully reproduced
    — but deliberately never flips ``started``, and signals an ``asyncio.Event`` the instant
    it has bound. That makes the cancellation point deterministic (always mid-poll, never a
    race against how fast a real uvicorn happens to bind on this machine): we only cancel
    once the event confirms a real socket is already listening. The fake is scoped with its
    own ``monkeypatch.context()`` (rather than the function-scoped ``monkeypatch`` fixture) so
    it's guaranteed reverted to the real ``uvicorn.Server`` *before* the "fresh start after"
    assertion below — ``monkeypatch``'s fixture-scoped undo only runs at test teardown, which
    would otherwise still be in effect for that later call within this same test.
    """
    port = get_settings().lan_port
    bound = asyncio.Event()

    class _BoundButNeverStartedServer:
        """Binds a real socket (proving a real, orphan-able listener exists) but never sets
        ``started`` — so the readiness poll in ``start_lan_server`` never returns on its own
        and is guaranteed to still be parked on ``asyncio.sleep(...)`` when we cancel."""

        def __init__(self, config: object) -> None:
            self.started = False
            self.should_exit = False
            self._sock: socket.socket | None = None

        async def startup(self, sockets: list | None = None) -> None:
            pass  # `start_lan_server` reads/replaces this attribute unconditionally.

        async def serve(self) -> None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("0.0.0.0", port))
            sock.listen(1)
            self._sock = sock
            bound.set()
            try:
                while not self.should_exit:
                    await asyncio.sleep(0.01)
            finally:
                sock.close()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server.uvicorn, "Server", _BoundButNeverStartedServer)

        start_task = asyncio.create_task(server.start_lan_server())
        # Deterministic: wait for confirmation the fake server has actually bound the socket
        # (so we know `serve_task` is running and `start_lan_server` is parked on the poll's
        # `asyncio.sleep`, never having reached `server.started`) before cancelling —
        # standing in for Starlette cancelling the request-handler task on client disconnect.
        await asyncio.wait_for(bound.wait(), timeout=2.0)
        start_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await start_task

    # Module state must be back to "not running" — no orphaned task/handle left behind.
    assert server.is_running() is False
    assert server._server is None
    assert server._serve_task is None

    # The real proof: the port must be genuinely free, not wedged by an abandoned listener
    # that nothing has a handle to anymore.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("0.0.0.0", port))
        probe.listen(1)
    finally:
        probe.close()

    # And a fresh start (against the real uvicorn.Server — the monkeypatch above is already
    # reverted by its own `with` block, not just at test teardown) works cleanly afterward.
    await server.start_lan_server()
    assert server.is_running() is True


@pytest.mark.anyio
async def test_start_timeout_raises_and_resets_state_with_no_orphaned_task() -> None:
    """Forces the never-signals-``started`` path (distinct from the bind-failure path already
    covered above) by shrinking the readiness timeout to something the poll loop cannot
    possibly beat, given a server that runs forever without ever setting ``server.started``.
    Must raise ``RuntimeError`` and leave module state fully reset — no orphaned task, no
    wedged port.

    Uses its own ``monkeypatch.context()`` (rather than the function-scoped ``monkeypatch``
    fixture) so the shrunk timeout and fake ``uvicorn.Server`` are guaranteed reverted
    *before* the "fresh start after" assertion below, not just at test teardown.
    """

    class _NeverStartsServer:
        """Stands in for ``uvicorn.Server``: ``started`` never flips ``True``, and
        ``serve()`` just runs until ``should_exit`` is set — modelling a server that is
        alive but never reports readiness within the timeout."""

        def __init__(self, config: object) -> None:
            self.started = False
            self.should_exit = False

        async def startup(self, sockets: list | None = None) -> None:
            """``start_lan_server`` unconditionally reads/replaces ``server.startup`` before
            ever calling ``serve()`` — needs to exist, but this test doesn't go anywhere near
            the bind-failure path, so it's a no-op."""

        async def serve(self) -> None:
            while not self.should_exit:
                await asyncio.sleep(0.01)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server, "_START_TIMEOUT_SECONDS", 0.05)
        mp.setattr(server, "_START_POLL_INTERVAL_SECONDS", 0.01)

        fake_server = _NeverStartsServer(config=None)
        mp.setattr(server.uvicorn, "Server", lambda config: fake_server)

        with pytest.raises(RuntimeError):
            await server.start_lan_server()

        assert server.is_running() is False
        assert server._server is None
        assert server._serve_task is None

        # No orphaned task left running in the background.
        await asyncio.sleep(0)
        assert fake_server.should_exit is True

    # A fresh start (against the real uvicorn.Server and the real timeout — both monkeypatches
    # above are already reverted by their own `with` block) works cleanly afterward — nothing
    # about the port/loop was left in a bad state.
    await server.start_lan_server()
    assert server.is_running() is True
