"""The SEPARATE, LAN-exposed FastAPI app + its start/stop/status lifecycle (docs/06 roadmap
tasks T5+T10).

SECURITY — ``build_lan_app()`` is a completely independent ``FastAPI()`` instance from
``app.main.create_app()``. It is built from scratch right here and mounts ONLY
``app.lan.routes.router`` (``POST /pair``, ``GET/PUT /note``). This module never imports
``app.main``, ``create_app``, or any ``app.api.*`` router — there is nothing else in this
file's import graph that could accidentally end up reachable through it. That absence of an
import path is what makes "structurally impossible to expose books/scenes/codex/etc." true
rather than just a promise: there is no `include_router` call anywhere in this module (or
anything it imports) that could pull in another resource's routes.
``tests/test_lan_isolation.py`` inspects ``build_lan_app()``'s route table directly to prove
this holds — do not add another ``include_router`` here without updating that test.

The LAN server binds ``0.0.0.0`` (any interface — so a phone on the same Wi-Fi can reach it),
UNLIKE the main app, which stays ``127.0.0.1``-only (``app/config.py``'s ``host``/``port``,
unchanged by this task). It only ever binds when ``start_lan_server()`` is called explicitly
(the Notes "Share on LAN" toggle, wired through ``app/main.py``'s
``POST /notes/lan/share/start``) and is torn down by ``stop_lan_server()`` — including from
the main app's own shutdown lifespan, so a running LAN server can never outlive the process.
Nothing in this module binds a socket at import time; importing this module is side-effect
free.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import socket
import time

import uvicorn
from fastapi import FastAPI

from app.config import get_settings
from app.lan.routes import router as lan_router

logger = logging.getLogger("quillnight.lan")

# Module-level, process-lifetime handles to the running server, if any. `None` means "not
# running" — the same not-bound-unless-started guarantee `start_lan_server`/`stop_lan_server`
# maintain below.
_server: uvicorn.Server | None = None
_serve_task: asyncio.Task | None = None

# How long `start_lan_server` waits for uvicorn to report a genuinely bound/listening socket
# (`server.started`) before giving up and treating the start as a failure (e.g. `lan_port`
# already in use by another process). Polled rather than awaited directly because uvicorn
# gives no "wait until started" primitive of its own.
_START_TIMEOUT_SECONDS = 2.0
_START_POLL_INTERVAL_SECONDS = 0.02


class _LanBindFailure(Exception):
    """Raised (in place of uvicorn's own ``sys.exit(STARTUP_FAILURE)``) when
    ``uvicorn.Server.startup()`` fails to bind — see ``start_lan_server``'s
    per-instance ``startup`` wrapper for why this substitution is necessary."""


def build_lan_app() -> FastAPI:
    """A fresh, minimal FastAPI app exposing ONLY the LAN note+pair routes.

    * ``docs_url``/``redoc_url``/``openapi_url`` all ``None`` — no ``/docs``, ``/redoc``, or
      ``/openapi.json`` on a surface that's reachable from any device on the LAN; there is
      no reason to publish this API's shape to whoever finds the open port.
    * NO CORS middleware — the intended caller is a native mobile HTTP client, not a browser
      (see ``app.lan.routes.require_lan_auth``'s Origin-header rejection: a browser caller is
      refused outright rather than accommodated via CORS).
    * ONLY ``lan_router`` included — see module docstring.
    """
    lan_app = FastAPI(
        title="Quillnight LAN Notes",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    lan_app.include_router(lan_router)
    return lan_app


async def start_lan_server() -> None:
    """Starts the uvicorn server bound ``0.0.0.0:<lan_port>`` as a background asyncio task,
    and does not return until the socket is genuinely listening (or raises).

    Guarded against double-start: a no-op if a server is already running (returns
    immediately rather than binding a second listener or replacing the running one, which
    would silently orphan the first task).

    Bind failures (most commonly ``lan_port`` already in use by another process) used to be
    silently swallowed: ``_server`` was set and the ``serve()`` task launched without ever
    confirming it actually bound, so ``is_running()``/``get_share_status()`` would keep
    reporting ``sharing: true`` for a listener that never came up. This now polls uvicorn's
    own ``server.started`` flag (set ``True`` once startup completes) for up to
    ``_START_TIMEOUT_SECONDS``, also watching for the ``serve()`` task finishing/raising
    early (e.g. ``OSError: [Errno 98] address already in use``). On any failure the task is
    cancelled/awaited and ALL module state is reset back to "not running" before a clear
    ``RuntimeError`` is raised — the caller (``app/main.py``'s share/start endpoint) is
    expected to surface that as an HTTP error rather than minting a pairing code for a dead
    server.
    """
    global _server, _serve_task
    if _server is not None:
        return

    cfg = get_settings()
    config = uvicorn.Config(
        build_lan_app(),
        host="0.0.0.0",  # noqa: S104 — intentional: this IS the LAN-exposed surface (see module docstring)
        port=cfg.lan_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    # uvicorn.Server.startup() calls `sys.exit(STARTUP_FAILURE)` on a bind OSError (e.g. the
    # port is already in use) rather than raising an ordinary exception. Because
    # `server.serve()` runs here as a background `asyncio.Task` (not via `uvicorn.run()`'s
    # own dedicated event loop/process), asyncio's Task machinery gives `SystemExit`/
    # `KeyboardInterrupt` special treatment: it re-raises them out of the task's step
    # callback instead of storing them as a normal, retrievable Task exception — which
    # crashes the ENTIRE process's event loop (confirmed by direct reproduction: the whole
    # sidecar process died with the bind-failure's exit code, not just this LAN feature)
    # rather than a graceful, catchable failure. Overriding just THIS `server` object's
    # `startup` (an ordinary instance-attribute; picked up by `Server._serve`'s
    # `await self.startup(...)` call) converts that `SystemExit` into a normal
    # `_LanBindFailure` before it ever reaches the Task machinery — no global `sys.exit`
    # patching, nothing outside this one server instance is touched.
    _original_startup = server.startup

    async def _guarded_startup(sockets: list | None = None) -> None:
        try:
            await _original_startup(sockets=sockets)
        except SystemExit as exc:
            raise _LanBindFailure(f"uvicorn startup failed (exit code {exc.code})") from exc

    server.startup = _guarded_startup  # type: ignore[method-assign]

    serve_task = asyncio.create_task(server.serve())

    try:
        deadline = time.monotonic() + _START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if serve_task.done():
                break
            if server.started:
                _server = server
                _serve_task = serve_task
                logger.info("LAN Notes server started on 0.0.0.0:%d", cfg.lan_port)
                return
            await asyncio.sleep(_START_POLL_INTERVAL_SECONDS)

        # Failure path: either the serve task ended (raised or exited) before signalling
        # `started`, or it never signalled `started` within the timeout at all. Either way,
        # this is not a running server — tear the task down and make sure no module state
        # (this function's own `_server`/`_serve_task`) is left claiming otherwise.
        exc: BaseException | None = None
        if serve_task.done():
            exc = serve_task.exception()
        else:
            server.should_exit = True
            serve_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await serve_task

        _server = None
        _serve_task = None
        detail = f"LAN port {cfg.lan_port} unavailable"
        if exc is not None:
            logger.error("%s: %s", detail, exc)
            raise RuntimeError(detail) from exc
        logger.error("%s: server did not report ready within %.1fs", detail, _START_TIMEOUT_SECONDS)
        raise RuntimeError(detail)
    except BaseException:
        # Covers cancellation of THIS coroutine (e.g. `start_lan_server` is awaited inside
        # `start_lan_share`'s request handler in `app/main.py`, and Starlette cancels that
        # handler's task if the client disconnects during the up-to-`_START_TIMEOUT_SECONDS`
        # start window — most commonly while parked on the `asyncio.sleep(...)` above) as well
        # as re-entering here for the ordinary `RuntimeError` raised just above. Without this,
        # a cancellation would propagate straight out, abandoning `serve_task` — a uvicorn
        # server that may already be bound to `0.0.0.0:<lan_port>` — with no module handle:
        # `is_running()` would report `False` (so `stop_lan_server()`/the shutdown lifespan
        # never touch it) while the orphaned listener keeps the port wedged for every later
        # start attempt. This block always tears `serve_task` down and resets module state
        # before re-raising, so the caller's exception (whatever it is) is unchanged.
        #
        # Only cancel+await `serve_task` here if it was still running (the real cancellation
        # case) — the explicit `RuntimeError` path above already fully drained it (either via
        # `serve_task.exception()` or its own cancel-and-await), so re-awaiting an
        # already-done task here would just re-raise whatever IT stored (e.g. the
        # `_LanBindFailure` from a bind conflict) and clobber the `RuntimeError` we're
        # actually propagating via the bare `raise` below.
        server.should_exit = True
        if not serve_task.done():
            serve_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await serve_task
        _server = None
        _serve_task = None
        raise


async def stop_lan_server() -> None:
    """Gracefully shuts the LAN server down, if one is running. Safe to call when nothing is
    running (no-op) — so both the explicit share/stop endpoint and the main app's shutdown
    lifespan can call this unconditionally without checking state first."""
    global _server, _serve_task
    if _server is None:
        return

    server = _server
    task = _serve_task
    _server = None
    _serve_task = None

    server.should_exit = True
    if task is not None:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    logger.info("LAN Notes server stopped.")


def is_running() -> bool:
    return _server is not None


def _local_ipv4_addresses() -> list[str]:
    """Best-effort list of this machine's LAN-facing IPv4 address(es).

    Uses the well-known UDP-connect-to-8.8.8.8 trick: ``connect()`` on a ``SOCK_DGRAM``
    socket only asks the OS to pick the local interface/address it WOULD use to route to
    that destination — for UDP this is purely a kernel routing-table lookup, no packet is
    actually sent on the wire. Wrapped in a broad ``except OSError`` because a machine with
    no route to the internet (fully offline) would otherwise raise here; in that case we
    simply report no host_ips rather than failing the whole status/share-start call.
    """
    ips: list[str] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ips.append(sock.getsockname()[0])
    except OSError:
        pass
    finally:
        sock.close()

    seen: set[str] = set()
    out: list[str] = []
    for ip in ips:
        if ip and ip != "0.0.0.0" and ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out


def _fingerprint(seed: str) -> str:
    """Short, non-secret fingerprint for the QR payload's ``fp`` field — lets the phone-side
    scanner display/log a short human-comparable value without exposing the pairing code or
    device token themselves in a QR-code screenshot's metadata. NOT a security control (the
    pairing code inside the same payload already is one)."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]


def build_qr_payload(pairing_code: str) -> dict:
    """The payload a phone's QR scanner reads to auto-fill pairing.

    Deliberately never includes a ``device_token`` — a token is only ever minted via a
    successful ``POST /pair`` exchange, never handed out ambiently. ``fp`` is derived from
    the pairing code plus the current time (an epoch value), so the same code re-rendered a
    moment later still produces a fresh, non-repeating fingerprint.
    """
    cfg = get_settings()
    ips = _local_ipv4_addresses()
    host = ips[0] if ips else "127.0.0.1"
    fp = _fingerprint(f"{pairing_code}:{time.time_ns()}")
    return {
        "v": 1,
        "host": host,
        "port": cfg.lan_port,
        "note_id": "lan",
        "pairing_code": pairing_code,
        "fp": fp,
    }


def get_share_status() -> dict:
    """No secrets in here — safe to expose on ``GET /notes/lan/share/status`` even to a
    caller that never went through pairing. Deliberately excludes ``pairing_code``: a status
    poll is not how a pairing code is meant to be discovered — only the ``share/start``
    response and its QR payload carry it."""
    cfg = get_settings()
    return {
        "sharing": is_running(),
        "lan_port": cfg.lan_port,
        "host_ips": _local_ipv4_addresses(),
    }


__all__ = [
    "build_lan_app",
    "build_qr_payload",
    "get_share_status",
    "is_running",
    "start_lan_server",
    "stop_lan_server",
]
