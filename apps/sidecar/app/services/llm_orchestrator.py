"""LLM provider orchestrator — LiteLLM-backed Offline/Online/Hybrid routing with
provider-agnostic streaming + cancellation (docs/08-AI-PROVIDER-MODES.md,
docs/04-LLM-INTEGRATION.md, docs/11-AI-INTELLIGENCE.md §5).

This module is the ONLY place in the sidecar that imports ``litellm``. Route handlers
(and `prompt_builder.py`) call :class:`ProviderClient`/:func:`get_provider_client` and
never touch LiteLLM directly, so the underlying client library can be swapped later
without touching call sites (docs/08 "Architecture: provider abstraction via LiteLLM").

## Hard rules enforced here

* **Offline-first: no import-time network call.** ``LITELLM_LOCAL_MODEL_COST_MAP`` is
  forced to ``"True"`` *before* ``litellm`` is imported below — otherwise importing
  litellm fetches a remote model-cost-map JSON from GitHub, which stalls/warns behind a
  corporate TLS proxy on every sidecar start. This must stay the very first executable
  statement in this module, ahead of the ``import litellm`` line.
* **The Groq API key is never read from SQLite/settings/disk.** It only ever arrives as
  the ``groq_key`` parameter to :meth:`ProviderClient.stream`, sourced by the caller from
  the OS keyring via the Rust shell (docs/08 "Secure API key storage"). If it's absent
  (or the configured Groq model name is absent), Online/Hybrid degrade to local rather
  than raising — this module never surfaces a "you forgot your key" error mid-stream; it
  just serves the request locally, per docs/08's "seamless fallback" design intent.
* **Auto-suggest callers must pass ``ai_mode="offline"`` regardless of the user's
  configured mode** (docs/08 "One rule that applies in every mode") — that policy lives
  in the caller (the future `/llm` router, task D1), not here; this module simply routes
  whatever ``ai_mode`` it's given.
"""

from __future__ import annotations

import os

# MUST run before `import litellm` (see module docstring above) — order matters.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import asyncio  # noqa: E402
from collections.abc import AsyncIterator, Awaitable, Callable  # noqa: E402
from typing import Literal, TypedDict  # noqa: E402

import litellm  # noqa: E402

from app.config import get_settings  # noqa: E402

AIMode = Literal["offline", "online", "hybrid"]
ProviderName = Literal["ollama", "groq"]

# Default Groq model for the "online heavy-lift" tasks, per docs/08 "Model selection on
# Groq". Only used when the caller doesn't pass an explicit `groq_model` — the real
# authoritative value lives in `app_settings.groq_model_name` (settings_service.py), which
# this module never reads directly (it has no DB session).
_DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"

# Env flag selected by the factory below (docs/06 Phase 2 task C2). Real Ollama/Groq
# network calls are NOT exercised on this build machine — see docs/07 and CLAUDE.md
# "Environment constraints"; the stub lets routing/fallback/cancel logic be verified
# without a model.
_STUB_ENV_VAR = "QUILLNIGHT_LLM_STUB"


class Chunk(TypedDict):
    """One streamed token/delta, tagged with the provider that actually served it."""

    delta: str
    provider: ProviderName


class ProviderUnavailable(Exception):
    """Raised internally by a single provider leg (auth failure, no key, connection
    error, rate limit, etc.). Callers of :meth:`ProviderClient.stream` never see this
    directly in Hybrid mode unless every configured leg fails — see the fallback loop
    in :meth:`ProviderClient.stream`."""


IsDisconnected = Callable[[], "bool | Awaitable[bool]"]


class ProviderClient:
    """Wraps LiteLLM behind Quillnight's own streaming interface.

    ``stream()`` resolves a small ordered list of "legs" (provider, model) from
    ``ai_mode`` + key availability, then tries each leg in order, falling through to the
    next only if the current leg raises *before it starts yielding output has finished
    successfully*. Each yielded :class:`Chunk` is tagged with the provider that actually
    served it, per docs/08's "provider indicator" requirement.
    """

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        ai_mode: AIMode,
        groq_model: str | None = None,
        groq_key: str | None = None,
        groq_zdr_enabled: bool = True,
        temperature: float | None = None,
        cancel: asyncio.Event | None = None,
        is_disconnected: IsDisconnected | None = None,
    ) -> AsyncIterator[Chunk]:
        """Stream chat completion deltas from the provider(s) implied by ``ai_mode``.

        - ``offline`` -> local Ollama only.
        - ``online`` -> Groq only if ``groq_key`` (and a resolvable model) is present,
          else degrades to local (docs/08: "If absent, Online/Hybrid degrade to local").
        - ``hybrid`` -> Groq first (if a key is present), automatic fallback to Ollama on
          any failure of the Groq leg; Groq-less Hybrid behaves like Offline.

        ``cancel`` (an ``asyncio.Event``) and/or ``is_disconnected`` (a zero-arg
        sync-or-async callable, e.g. FastAPI's ``request.is_disconnected``) are checked
        between every chunk; the moment either signals true, the generator stops
        yielding and closes the upstream stream — no further provider legs are tried.
        """
        settings = get_settings()
        legs = self._resolve_legs(
            ai_mode=ai_mode,
            groq_model=groq_model,
            groq_key=groq_key,
            local_model=settings.default_local_model,
        )

        last_error: Exception | None = None
        for provider, model in legs:
            try:
                leg_stream = self._stream_one(
                    provider,
                    messages,
                    model=model,
                    temperature=temperature,
                    groq_key=groq_key,
                    groq_zdr_enabled=groq_zdr_enabled,
                )
                async for chunk in leg_stream:
                    if await self._is_cancelled(cancel, is_disconnected):
                        return
                    yield chunk
                return  # this leg produced (or legitimately yielded zero) output — done
            except Exception as exc:  # noqa: BLE001 — provider-agnostic fallback boundary
                last_error = exc
                continue

        # Every configured leg failed (only reachable if the LAST leg itself raised).
        if last_error is not None:
            raise last_error

    @staticmethod
    def _resolve_legs(
        *,
        ai_mode: AIMode,
        groq_model: str | None,
        groq_key: str | None,
        local_model: str,
    ) -> list[tuple[ProviderName, str]]:
        """Ordered (provider, model) legs to attempt, per docs/08's three-mode table.
        Groq is only ever attempted when a key is present; a missing key silently
        degrades Online/Hybrid to local rather than raising."""
        groq_usable = bool(groq_key)
        resolved_groq_model = groq_model or _DEFAULT_GROQ_MODEL

        if ai_mode == "offline":
            return [("ollama", local_model)]
        if ai_mode == "online":
            if groq_usable:
                return [("groq", resolved_groq_model)]
            return [("ollama", local_model)]
        if ai_mode == "hybrid":
            if groq_usable:
                return [("groq", resolved_groq_model), ("ollama", local_model)]
            return [("ollama", local_model)]
        raise ValueError(f"Unknown ai_mode: {ai_mode!r}")

    @staticmethod
    async def _is_cancelled(
        cancel: asyncio.Event | None,
        is_disconnected: IsDisconnected | None,
    ) -> bool:
        if cancel is not None and cancel.is_set():
            return True
        if is_disconnected is not None:
            result = is_disconnected()
            if isinstance(result, Awaitable):
                result = await result
            return bool(result)
        return False

    async def _stream_one(
        self,
        provider: ProviderName,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float | None,
        groq_key: str | None,
        groq_zdr_enabled: bool,
    ) -> AsyncIterator[Chunk]:
        """One provider leg's real LiteLLM call. Deliberately a separate, overridable
        method (the "testable fallback seam") — tests subclass ProviderClient and
        override this to force the 'groq' leg to raise without any network access, then
        assert Hybrid still completes via 'ollama'. Do not inline this into `stream()`.
        """
        if provider == "groq":
            if not groq_key:
                raise ProviderUnavailable("groq: no API key provided")
            response = await litellm.acompletion(
                model=f"groq/{model}",
                messages=messages,
                stream=True,
                temperature=temperature,
                api_key=groq_key,
                # Groq's Zero Data Retention is currently an account-level console
                # toggle, not a documented per-request parameter (docs/08 "Privacy &
                # consent"). `groq_zdr_enabled` is accepted here for forward-compat / the
                # audit trail (`llm_request_log`) — if Groq later exposes a request-level
                # ZDR flag, wire it into `extra_body`/`extra_headers` here.
            )
        elif provider == "ollama":
            response = await litellm.acompletion(
                model=f"ollama/{model}",
                messages=messages,
                stream=True,
                temperature=temperature,
                api_base=get_settings().ollama_base_url,
                # How long Ollama keeps this model resident in RAM after the request
                # completes (docs/06 Phase 9 task 11 "idle RAM/perf tuning") — configurable
                # via QUILLNIGHT_OLLAMA_KEEP_ALIVE so idle memory footprint can be tuned
                # without a code change. Groq (above) has no equivalent — it's a hosted
                # API, not a local model process.
                keep_alive=get_settings().ollama_keep_alive,
            )
        else:  # pragma: no cover — exhaustive per ProviderName
            raise ValueError(f"Unknown provider: {provider!r}")

        try:
            async for part in response:
                delta = ""
                choices = getattr(part, "choices", None) or []
                if choices:
                    delta = getattr(choices[0].delta, "content", None) or ""
                if delta:
                    yield Chunk(delta=delta, provider=provider)
        finally:
            aclose = getattr(response, "aclose", None)
            if aclose is not None:
                await aclose()


class EchoProvider(ProviderClient):
    """Test/dev stub — no litellm, no network, ever. Streams the last user message back
    token-by-token (split on whitespace, one trailing space per token), always tagged
    ``provider="ollama"`` (Echo simulates the local/offline leg). Selected by
    :func:`get_provider_client` when ``QUILLNIGHT_LLM_STUB=1`` is set.

    Overrides `stream()` directly (rather than `_stream_one`) so it also stands in for
    the *routing* behavior under test without needing litellm importable/callable at
    all — Offline/Online/Hybrid all echo identically since there's nothing to fail over
    from in this stub.
    """

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        ai_mode: AIMode,
        groq_model: str | None = None,
        groq_key: str | None = None,
        groq_zdr_enabled: bool = True,
        temperature: float | None = None,
        cancel: asyncio.Event | None = None,
        is_disconnected: IsDisconnected | None = None,
    ) -> AsyncIterator[Chunk]:
        last_user = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                last_user = message.get("content", "")
                break

        for token in last_user.split():
            if await self._is_cancelled(cancel, is_disconnected):
                return
            await asyncio.sleep(0)
            yield Chunk(delta=f"{token} ", provider="ollama")


def get_provider_client() -> ProviderClient:
    """Factory: returns the stub client when `QUILLNIGHT_LLM_STUB=1` is set in the
    environment (test/dev, no litellm calls), else the real LiteLLM-backed client.
    Callers should always go through this factory rather than instantiating either
    class directly, so the stub/real split stays centralized."""
    if os.environ.get(_STUB_ENV_VAR) == "1":
        return EchoProvider()
    return ProviderClient()
