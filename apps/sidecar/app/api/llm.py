"""/llm — the Enhance streaming endpoint + its audit log (docs/04-LLM-INTEGRATION.md,
docs/06 Phase 2 tasks D1/D2, docs/11-AI-INTELLIGENCE.md §5).

DATA-SENSITIVE (flagged for a later `reviewer` pass, per CLAUDE.md): the streaming routes
here have NO code path that writes to `scenes` or `screenplay_elements`. `/llm/enhance`
only reads text out of the request body + Codex context, streams a suggestion back over
SSE, and writes exactly one row to `llm_request_log` (the audit trail). Accepting a
suggestion into a Scene/element is a separate, explicit client-driven write — for Enhance,
a PATCH to `/scenes/...`; for a merge, the non-streaming `POST /llm/merge-scenes/accept`
below (PHASE11.md Workstream B task 11), which delegates its entire write to
`merge_service.accept_merge` (task 10) — never implied by either streaming route.
`/llm/log/{id}/accept` only ever flips that one log row's `accepted` flag.

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
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import SessionLocal, get_db
from app.models.orm import BookSceneLink
from app.models.schemas import (
    EnhanceRequest,
    GroqKeyPresence,
    GroqKeySet,
    LlmLogRead,
    LogAccept,
    MergeScenesAcceptRequest,
    MergeScenesAcceptResponse,
    MergeScenesRequest,
    TestConnectionResult,
)
from app.services import groq_key, llm_log_service, merge_service
from app.services.canvas_service import to_canvas_node
from app.services.llm_orchestrator import ProviderUnavailable, get_provider_client
from app.services.prompt_builder import build_enhance_prompt, build_merge_prompt, temperature_for
from app.services.settings_service import get_all_settings

router = APIRouter(prefix="/llm", tags=["llm"])


def _sse(event: str | None, data: dict) -> str:
    payload = json.dumps(data)
    if event is None:
        return f"data: {payload}\n\n"
    return f"event: {event}\ndata: {payload}\n\n"


def _handle_value_error(exc: ValueError) -> HTTPException:
    """Mirrors `api/outline.py`'s `_handle_value_error` — the repo's established pattern
    for turning a service-layer `ValueError` sentinel into an HTTP error (module docstring
    "sentinel pattern"), rather than inventing a second mechanism here."""
    code = str(exc)
    if code == "SCENE_NOT_FOUND":
        return HTTPException(status_code=404, detail="Scene not found")
    if code == "SCENE_IDS_REQUIRED":
        return HTTPException(status_code=422, detail="scene_ids is required")
    if code == "BOOK_NOT_FOUND":
        return HTTPException(status_code=404, detail="Book not found")
    if code == "SOURCE_SCENES_REQUIRED":
        return HTTPException(status_code=422, detail="source_scene_ids is required")
    if code == "SCENE_NOT_IN_BOOK":
        return HTTPException(status_code=422, detail="Scene is not on this Book's canvas")
    raise exc


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


@router.post("/merge-scenes")
async def merge_scenes(
    payload: MergeScenesRequest, request: Request, db: Session = Depends(get_db)
) -> StreamingResponse:
    """Stream an AI-assisted multi-scene merge suggestion over SSE (PHASE11.md Workstream
    B, "AI-assisted multi-node merge reusing the Enhance seam exactly").

    Mirrors `/llm/enhance` EXACTLY: same SSE event shape (bare ``delta``/``provider``
    events, then a single ``done`` event carrying ``log_id``, or an ``error`` event), same
    audit-log timing (one `llm_request_log` row started before the stream, finished after),
    same provider streaming mechanics via `llm_orchestrator.py` — only the prompt-assembly
    call differs (`prompt_builder.build_merge_prompt` instead of `build_enhance_prompt`).
    Like `/llm/enhance`, this endpoint ONLY streams a suggestion back for review — nothing
    is written to `scenes`/`screenplay_elements` here; accepting a merge into the canvas is
    a separate, later, explicit client action (PHASE11.md task 11), not implied by this
    route.
    """
    settings = get_all_settings(db)
    ai_mode = settings.get("ai_mode", "offline")
    groq_model = settings.get("groq_model_name")
    groq_zdr_enabled = settings.get("groq_zdr_enabled", True)
    local_model_name = settings.get("local_model_name")

    try:
        messages = build_merge_prompt(db, payload.scene_ids, book_id=payload.book_id)
    except ValueError as exc:
        raise _handle_value_error(exc) from exc

    temperature = temperature_for("continuity")

    log_id = llm_log_service.start_log(
        db,
        request_type="merge",
        entity_type=None,
        entity_id=None,
        book_id=payload.book_id,
    )

    # Dev seam (task F1/F2) — see module docstring "The Groq key seam".
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


@router.post("/merge-scenes/accept", response_model=MergeScenesAcceptResponse)
def accept_merge_scenes(
    payload: MergeScenesAcceptRequest, db: Session = Depends(get_db)
) -> MergeScenesAcceptResponse:
    """Write the merge the user just reviewed from ``/llm/merge-scenes``'s SSE suggestion
    into the canvas (PHASE11.md Workstream B task 11). Unlike `/llm/enhance` and
    `/llm/merge-scenes` above, this is a plain synchronous write-then-respond POST — there
    is no LLM/streaming call here at all, since `merge_service.accept_merge` is a single DB
    transaction, not a model call. Nothing about this route depends on `ai_mode`, the Groq
    key, or `QUILLNIGHT_LLM_STUB`.
    """
    try:
        merged_scene = merge_service.accept_merge(
            db,
            book_id=payload.book_id,
            source_scene_ids=payload.source_scene_ids,
            merged_title=payload.merged_title,
            merged_description=payload.merged_description,
        )
    except ValueError as exc:
        raise _handle_value_error(exc) from exc

    # accept_merge already committed the merged scene's BookSceneLink for this book — reuse
    # canvas_service's exact node-serialization helper so the frontend can drop this node
    # straight into React Flow state without a full canvas refetch.
    link = db.execute(
        select(BookSceneLink).where(
            BookSceneLink.book_id == payload.book_id,
            BookSceneLink.scene_id == merged_scene.id,
            BookSceneLink.archived_at.is_(None),
        )
    ).scalar_one()
    return MergeScenesAcceptResponse(node=to_canvas_node(link, merged_scene))


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
