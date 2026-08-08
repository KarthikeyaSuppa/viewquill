"""The ENTIRE route surface of the LAN-exposed app: ``POST /pair``, ``GET /note``,
``PUT /note``. Nothing else may ever be added to this router.

SECURITY — this module IS the attack surface of ``app.lan.server.build_lan_app()`` (which
mounts ``router`` below and nothing else). Unlike every other API module in this codebase
(``app/api/*.py``, reachable only via the 127.0.0.1-bound main app and therefore protected by
the OS network stack / "never leaves this machine"), these handlers run behind a socket bound
``0.0.0.0`` and so cannot assume the caller is this machine, this user, or even a well-behaved
HTTP client. ``tests/test_lan_isolation.py`` asserts this router's path set is exactly
``{/pair, /note}`` — do not add a route here without updating that test's allowlist.

Checks enforced on ``/note`` (both GET and PUT) via ``require_lan_auth``, in this order:
    1. **No ``Origin`` header at all.** A real browser (Chrome/Safari/Edge/...) always sends
       ``Origin`` on a cross-origin ``fetch``/XHR; a native mobile HTTP client (the intended
       caller here) never does. Rejecting any request that carries one blocks DNS-rebinding
       and "malicious webpage silently probes 192.168.x.x" drive-by attacks against this
       LAN-bound server. Checked FIRST and unconditionally (before even looking at the
       token), so a browser-based attacker can never get far enough to brute-force a token.
    2. **``X-Quillnight-LAN: 1`` header present.** A cheap, free filter against blind
       scanners/curl-without-reading-the-docs hitting the open port. NOT itself a security
       boundary (trivially spoofable) — it exists purely to keep noise out of the real check
       below, so 401s for "just don't know about this header" don't hide 401s for "wrong
       token" in logs/monitoring.
    3. **``Authorization: Bearer <device_token>``, verified via
       ``security.verify_device_token``.** The actual authorization gate. A device_token
       only exists after a successful ``/pair`` exchange (single-use 6-digit code, ~120s
       TTL, rate-limited — see app/lan/security.py).

``/pair`` deliberately does NOT go through ``require_lan_auth`` — pairing is how a device
gets its FIRST token, so requiring one already would be a chicken-and-egg deadlock. It DOES
still share check #1 above (``require_no_browser_origin``, factored out of
``require_lan_auth`` into ``_reject_browser_origin``) — a native client never sends
``Origin`` either way, so this costs it nothing while closing the same drive-by vector on
pairing itself. Beyond that, ``/pair``'s protection is entirely in
``security.redeem_pairing``: single-use code, short TTL, and a hard per-code attempt cap.

Host-header allowlist: deliberately NOT enforced by default (`_host_allowed` is a hook,
currently always-true) because the LAN IP is DHCP-assigned and can change session to session;
enforcing it would risk locking legitimate users out for no real security gain over the
Origin+token checks above. Left as an explicit extension point for a future stricter mode
rather than silently doing nothing with no trace of the decision.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.lan import security
from app.models.schemas import NoteRead, NoteWrite
from app.services import notes_service

router = APIRouter(tags=["lan-notes"])

# The one and only note channel the LAN surface ever touches — matches the local
# 127.0.0.1 side's convention (app/api/notes.py's `channel` path param), hardcoded here
# rather than taken from the caller so a LAN client can never address any other channel.
LAN_CHANNEL = "lan"


class PairRequest(BaseModel):
    code: str


class PairResponse(BaseModel):
    device_token: str


def _get_db() -> Session:
    """Uses the SAME sessionmaker the main (127.0.0.1) app uses — imported directly from
    ``app.db.base``, never through ``app.main`` or any ``app.api.*`` module. This router has
    zero import-time dependency on the main FastAPI app object, which is exactly what makes
    ``build_lan_app()`` (app/lan/server.py) a genuinely separate app instance rather than a
    re-export of the main one."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _host_allowed(_host_header: str | None) -> bool:
    """Extension point for a future Host-header allowlist (spec: "optionally enforce"). Not
    enforced today — see module docstring for why — but kept as a named, tested hook rather
    than inlined so turning it on later is a one-line change here, not a new code path."""
    return True


def _reject_browser_origin(origin: str | None) -> None:
    """Anti DNS-rebinding / drive-by-browser check, factored out so both ``/pair`` and
    ``/note`` (via ``require_lan_auth``) enforce the exact same rule: a native mobile HTTP
    client never sends ``Origin`` at all, so unconditionally rejecting any request that
    carries one is harmless to the intended caller and closes a same-origin drive-by vector
    against ``/pair`` too — not just the already-protected ``/note`` routes."""
    if origin is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origin header not permitted on the LAN Notes API")


def require_no_browser_origin(origin: str | None = Header(default=None)) -> None:
    """Standalone FastAPI dependency wrapping ``_reject_browser_origin`` — used on ``/pair``,
    which otherwise has no auth dependency at all (see module docstring: pairing is how a
    device gets its first token, so a token-requiring dependency would deadlock it)."""
    _reject_browser_origin(origin)


def require_lan_auth(
    authorization: str | None = Header(default=None),
    x_quillnight_lan: str | None = Header(default=None, alias="X-Quillnight-LAN"),
    origin: str | None = Header(default=None),
    host: str | None = Header(default=None),
) -> None:
    """FastAPI dependency guarding every route below except ``/pair`` — see module
    docstring for the exact checks and their order."""
    # 1) Anti DNS-rebinding / drive-by-browser — checked first, unconditionally.
    _reject_browser_origin(origin)

    # 2) Cheap scanner filter — not a security boundary by itself.
    if x_quillnight_lan != "1":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-Quillnight-LAN header")

    # 3) The real gate: a valid, currently-live device token.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer device token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or not security.verify_device_token(token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked device token")

    # 4) Optional Host allowlist hook — currently always permissive, see module docstring.
    if not _host_allowed(host):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Host not permitted on the LAN Notes API")


@router.post("/pair", response_model=PairResponse, dependencies=[Depends(require_no_browser_origin)])
def pair(payload: PairRequest) -> PairResponse:
    """Exchanges a single-use 6-digit pairing code (minted desktop-side via
    ``security.start_pairing()``, shown as text + folded into the QR payload — see
    app/lan/server.py) for a long-lived device_token. No TOKEN dependency here by design —
    see module docstring — but it does share the same unconditional Origin-header rejection
    ``/note`` uses (``require_no_browser_origin``), since a native mobile client never sends
    ``Origin`` either way and this closes a same-origin drive-by vector against pairing
    itself."""
    token = security.redeem_pairing(payload.code)
    if token is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid, expired, already-used, or rate-limited pairing code",
        )
    return PairResponse(device_token=token)


@router.get("/note", response_model=NoteRead, dependencies=[Depends(require_lan_auth)])
def get_note(db: Session = Depends(_get_db)) -> NoteRead:
    return NoteRead.model_validate(notes_service.get_note(db, LAN_CHANNEL))


@router.put("/note", response_model=NoteRead, dependencies=[Depends(require_lan_auth)])
def put_note(payload: NoteWrite, db: Session = Depends(_get_db)) -> NoteRead:
    return NoteRead.model_validate(notes_service.apply_note(db, LAN_CHANNEL, payload))
