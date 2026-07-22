"""/llm — the Enhance streaming endpoint + its audit log (docs/04-LLM-INTEGRATION.md,
docs/06 Phase 2 tasks D1/D2, docs/11-AI-INTELLIGENCE.md §5).

DATA-SENSITIVE (flagged for a later `reviewer` pass, per CLAUDE.md): this router has NO
code path that writes to `scenes` or `screenplay_elements`. `/llm/enhance` only reads
text out of the request body + Codex context, streams a suggestion back over SSE, and
writes exactly one row to `llm_request_log` (the audit trail). Accepting a suggestion into
a Scene/element is a separate, explicit client-driven PATCH to `/scenes/...` — never
implied here. `/llm/log/{id}/accept` only ever flips that one log row's `accepted` flag.

## The Groq key seam

The real Groq API key is read from the OS keyring by the Rust/Tauri shell and handed to
the sidecar. On this build machine (no Tauri here per CLAUDE.md "Environment
constraints"), task F1/F2's ``app/services/groq_key.py`` stands in for that binding: an
in-memory, process-lifetime module variable, set via ``POST /llm/groq-key`` below and read
via ``groq_key.get_key()`` at call time — see that module's docstring for the full
DEV-SEAM-ONLY guarantee. Production replaces ``POST /llm/groq-key`` with a Rust keyring
write and never routes the key through this sidecar's HTTP surface at all. If no key is
present, Online/Hybrid silently degrade to the local Ollama leg (see
``llm_orchestrator.ProviderClient._resolve_legs``) — this endpoint never raises a
"missing key" error to the caller.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.base import SessionLocal, get_db
from app.models.schemas import (
    EnhanceRequest,
    GroqKeyPresence,
    GroqKeySet,
    LlmLogRead,
    LogAccept,
    TestConnectionResult,
)
from app.services import groq_key, llm_log_service
from app.services.llm_orchestrator import ProviderUnavailable, get_provider_client
from app.services.prompt_builder import build_enhance_prompt, temperature_for
from app.services.settings_service import get_all_settings

router = APIRouter(prefix="/llm", tags=["llm"])


def _sse(event: str | None, data: dict) -> str:
    payload = json.dumps(data)
    if event is None:
        return f"data: {payload}\n\n"
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/enhance")
async def enhance(
    payload: EnhanceRequest, request: Request, db: Session = Depends(get_db)
) -> StreamingResponse:
    """Stream an Enhance/continuity suggestion over SSE.

    All DB reads (settings, codex context for the prompt) and the initial audit-log row
    happen here, synchronously, using the request-scoped ``db`` session — before the
    response is returned. The async generator below intentionally opens its OWN fresh
    session (``SessionLocal()``) for `finish_log`, rather than reusing ``db`` after this
    function returns: FastAPI/Starlette may tear the yield-dependency down as soon as the
    route function returns a ``StreamingResponse``, before the body is actually streamed,
    so relying on ``db`` staying open across the whole stream would be fragile.
    """
    settings = get_all_settings(db)
    ai_mode = settings.get("ai_mode", "offline")
    groq_model = settings.get("groq_model_name")
    groq_zdr_enabled = settings.get("groq_zdr_enabled", True)
    local_model_name = settings.get("local_model_name")

    messages = build_enhance_prompt(
        db,
        mode=payload.mode,
        text=payload.text,
        scene_id=payload.scene_id,
        book_id=payload.book_id,
    )
    temperature = temperature_for(payload.mode)

    log_id = llm_log_service.start_log(
        db,
        request_type=payload.mode,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        book_id=payload.book_id,
    )

    # Dev seam (task F1/F2): sourced from the in-memory module variable, never settings/DB.
    # Production sources this from the OS keyring via the Rust shell instead — see module
    # docstring "The Groq key seam" and app/services/groq_key.py.
    resolved_groq_key = groq_key.get_key()

    provider_client = get_provider_client()

    async def gen() -> AsyncIterator[str]:
        start = time.perf_counter()
        last_provider = "ollama"
        log_db = SessionLocal()
        try:
            async for chunk in provider_client.stream(
                messages,
                ai_mode=ai_mode,
                groq_model=groq_model,
                groq_key=resolved_groq_key,
                groq_zdr_enabled=groq_zdr_enabled,
                temperature=temperature,
                is_disconnected=request.is_disconnected,
            ):
                last_provider = chunk["provider"]
                yield _sse(None, {"delta": chunk["delta"], "provider": chunk["provider"]})

            latency_ms = int((time.perf_counter() - start) * 1000)
            model_name = groq_model if last_provider == "groq" else local_model_name
            llm_log_service.finish_log(
                log_db,
                log_id,
                provider=last_provider,
                model_name=model_name,
                latency_ms=latency_ms,
            )
            yield _sse("done", {"provider": last_provider, "log_id": log_id})
        except (ProviderUnavailable, Exception) as exc:  # noqa: BLE001 — stream-boundary catch-all
            # A mid-stream provider error must still finish the audit log and end the SSE
            # stream cleanly rather than dropping the connection with no explanation.
            latency_ms = int((time.perf_counter() - start) * 1000)
            llm_log_service.finish_log(
                log_db,
                log_id,
                provider=last_provider,
                model_name=None,
                latency_ms=latency_ms,
            )
            yield _sse("error", {"message": str(exc), "log_id": log_id})
        finally:
            log_db.close()

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/log/{log_id}/accept", response_model=LlmLogRead)
def accept_log(log_id: str, payload: LogAccept, db: Session = Depends(get_db)) -> LlmLogRead:
    log = llm_log_service.set_accepted(db, log_id, payload.accepted)
    if log is None:
        raise HTTPException(status_code=404, detail="LLM request log not found")
    return LlmLogRead.model_validate(log)


@router.post("/groq-key", response_model=GroqKeyPresence)
def set_groq_key(payload: GroqKeySet) -> GroqKeyPresence:
    """Dev seam (task F1) — stores the key in the in-memory `groq_key` module variable
    only (see app/services/groq_key.py). Production replaces this whole endpoint with a
    Rust-shell write straight into the OS keyring; the key is never written to SQLite,
    `app_settings`, disk, or a log line here, and this response never echoes it back."""
    groq_key.set_key(payload.key)
    return GroqKeyPresence(present=True)


@router.delete("/groq-key", status_code=status.HTTP_204_NO_CONTENT)
def delete_groq_key() -> None:
    groq_key.clear_key()


@router.post("/test-connection", response_model=TestConnectionResult)
async def test_connection(db: Session = Depends(get_db)) -> TestConnectionResult:
    """Fires exactly one minimal Groq call (mode "online") to confirm the currently-set
    key + configured model actually work, without ever echoing the key back. Declines
    (``ok=False``) without any network attempt when AI mode is offline or no key is set —
    matching the "seamless fallback, never a missing-key error" policy the streaming
    `/llm/enhance` endpoint follows (see module docstring "The Groq key seam")."""
    settings = get_all_settings(db)
    ai_mode = settings.get("ai_mode", "offline")
    resolved_groq_key = groq_key.get_key()

    if ai_mode == "offline":
        return TestConnectionResult(ok=False, reason="AI mode is offline")
    if resolved_groq_key is None:
        return TestConnectionResult(ok=False, reason="No Groq API key is set")

    groq_model = settings.get("groq_model_name")
    groq_zdr_enabled = settings.get("groq_zdr_enabled", True)
    provider_client = get_provider_client()
    last_provider = "ollama"
    try:
        async for chunk in provider_client.stream(
            [{"role": "user", "content": "ping"}],
            ai_mode="online",
            groq_model=groq_model,
            groq_key=resolved_groq_key,
            groq_zdr_enabled=groq_zdr_enabled,
            temperature=0,
        ):
            last_provider = chunk["provider"]
            break
    except (ProviderUnavailable, Exception) as exc:  # noqa: BLE001 — any provider failure is a "not ok" result, not a 500
        return TestConnectionResult(ok=False, reason=str(exc))
    return TestConnectionResult(ok=True, provider=last_provider)
