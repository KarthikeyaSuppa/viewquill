"""Tests for app.services.llm_orchestrator — Offline/Online/Hybrid routing, fallback,
streaming, and cancellation, verified WITHOUT any real network/model (docs/06 Phase 2
task C2's [MODEL-DEFERRED-TEST] note: real Ollama/Groq calls are exercised later on the
AI laptop; here we prove the routing/fallback/stream/cancel logic via the stub + an
injectable fallback seam).

Run with: QUILLNIGHT_LLM_STUB=1 pytest apps/sidecar/tests/test_llm_orchestrator.py -q
(the stub env var is also set programmatically below so the suite is self-contained).
"""

from __future__ import annotations

import asyncio
import os

# Must be set before `app.services.llm_orchestrator` is imported so `get_provider_client()`
# resolves to the no-network EchoProvider stub for the whole module.
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402

from app.services.llm_orchestrator import (  # noqa: E402
    Chunk,
    EchoProvider,
    ProviderClient,
    get_provider_client,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _collect(gen) -> list[Chunk]:
    return [chunk async for chunk in gen]


# ── 1. Offline stub echoes the input, every chunk tagged 'ollama' ─────────────────────────


@pytest.mark.anyio
async def test_offline_stub_echoes_full_message(anyio_backend):
    client = EchoProvider()
    text = "The quick brown fox jumps over the lazy dog"
    messages = [
        {"role": "system", "content": "sys prompt"},
        {"role": "user", "content": text},
    ]

    chunks = await _collect(client.stream(messages, ai_mode="offline"))

    assert chunks, "expected at least one chunk"
    assert all(c["provider"] == "ollama" for c in chunks)
    reconstructed = "".join(c["delta"] for c in chunks).strip()
    assert reconstructed == text


@pytest.mark.anyio
async def test_factory_returns_echo_provider_under_stub_env(anyio_backend):
    assert os.environ.get("QUILLNIGHT_LLM_STUB") == "1"
    client = get_provider_client()
    assert isinstance(client, EchoProvider)


# ── 2. Cancel mid-stream stops the generator early ─────────────────────────────────────────


@pytest.mark.anyio
async def test_cancel_event_stops_stream_early(anyio_backend):
    client = EchoProvider()
    text = "one two three four five six seven eight nine ten"
    total_tokens = len(text.split())
    messages = [{"role": "user", "content": text}]

    cancel = asyncio.Event()
    collected: list[Chunk] = []
    async for chunk in client.stream(messages, ai_mode="offline", cancel=cancel):
        collected.append(chunk)
        if len(collected) == 3:
            cancel.set()

    assert 0 < len(collected) < total_tokens


@pytest.mark.anyio
async def test_is_disconnected_callable_stops_stream_early(anyio_backend):
    client = EchoProvider()
    text = "alpha beta gamma delta epsilon zeta eta theta"
    total_tokens = len(text.split())
    messages = [{"role": "user", "content": text}]

    disconnected = False

    async def is_disconnected() -> bool:
        return disconnected

    collected: list[Chunk] = []
    stream = client.stream(messages, ai_mode="offline", is_disconnected=is_disconnected)
    async for chunk in stream:
        collected.append(chunk)
        if len(collected) == 2:
            disconnected = True

    assert 0 < len(collected) < total_tokens


# ── 3. Hybrid fallback via the injectable `_stream_one` seam — no network ─────────────────


class _FakeGroqFailsClient(ProviderClient):
    """Forces the 'groq' leg to raise before yielding anything, and serves a canned
    response on the 'ollama' leg — proves Hybrid mode's fallback loop in `stream()`
    without ever calling litellm/a network."""

    def __init__(self, canned_text: str) -> None:
        self._canned_text = canned_text
        self.attempted_providers: list[str] = []

    async def _stream_one(
        self, provider, messages, *, model, temperature, groq_key, groq_zdr_enabled
    ):
        self.attempted_providers.append(provider)
        if provider == "groq":
            raise RuntimeError("simulated groq failure (e.g. 429/connection error)")
            yield  # pragma: no cover — makes this an async generator function
        for token in self._canned_text.split():
            await asyncio.sleep(0)
            yield Chunk(delta=f"{token} ", provider="ollama")


@pytest.mark.anyio
async def test_hybrid_falls_back_to_ollama_when_groq_leg_raises(anyio_backend):
    client = _FakeGroqFailsClient(canned_text="fallback response text")
    messages = [{"role": "user", "content": "irrelevant"}]

    chunks = await _collect(
        client.stream(
            messages,
            ai_mode="hybrid",
            groq_key="fake-key-never-sent-anywhere",
            groq_model="fake-model",
        )
    )

    assert client.attempted_providers == ["groq", "ollama"], (
        "expected groq to be tried first and fail, then ollama to be tried"
    )
    assert chunks, "expected the ollama leg to still produce output"
    assert all(c["provider"] == "ollama" for c in chunks)
    assert "".join(c["delta"] for c in chunks).strip() == "fallback response text"


@pytest.mark.anyio
async def test_hybrid_without_groq_key_never_attempts_groq(anyio_backend):
    client = _FakeGroqFailsClient(canned_text="local only")
    messages = [{"role": "user", "content": "irrelevant"}]

    chunks = await _collect(client.stream(messages, ai_mode="hybrid", groq_key=None))

    assert client.attempted_providers == ["ollama"], "no key -> degrade straight to local"
    assert all(c["provider"] == "ollama" for c in chunks)


@pytest.mark.anyio
async def test_offline_never_attempts_groq_even_with_a_key(anyio_backend):
    client = _FakeGroqFailsClient(canned_text="local only")
    messages = [{"role": "user", "content": "irrelevant"}]

    chunks = await _collect(
        client.stream(messages, ai_mode="offline", groq_key="fake-key", groq_model="fake-model")
    )

    assert client.attempted_providers == ["ollama"]
    assert all(c["provider"] == "ollama" for c in chunks)


# ── 4. Groq key is never sourced from the DB/settings — code-structure check ─────────────


# ── 5. `ollama_keep_alive` setting reaches the Ollama-leg LiteLLM call ────────────────────


@pytest.mark.anyio
async def test_ollama_leg_passes_configured_keep_alive_to_litellm(anyio_backend, monkeypatch):
    """Proves app.config.Settings.ollama_keep_alive is threaded into the real
    ProviderClient's Ollama-leg `litellm.acompletion(...)` call (Phase 9 task 11), without
    ever making a real network/model call — `litellm.acompletion` itself is monkeypatched
    to a no-network fake that just records the kwargs it was called with."""
    from app.config import get_settings
    from app.services import llm_orchestrator as orch_module

    get_settings.cache_clear()
    monkeypatch.setenv("QUILLNIGHT_OLLAMA_KEEP_ALIVE", "42m")

    captured_kwargs: dict = {}

    class _FakeResponse:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def aclose(self):
            pass

    async def fake_acompletion(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(orch_module.litellm, "acompletion", fake_acompletion)

    client = ProviderClient()
    messages = [{"role": "user", "content": "irrelevant"}]
    chunks = await _collect(client.stream(messages, ai_mode="offline"))

    assert chunks == []
    assert captured_kwargs.get("keep_alive") == "42m"

    get_settings.cache_clear()


def test_module_never_imports_db_session_or_settings_table_for_the_key():
    """The Groq key must only ever arrive via the `groq_key` function parameter (sourced
    by the caller from the OS keyring via the Rust shell). This module must have no
    *import* giving it a path to read the key from SQLite/app_settings/a secrets lib —
    checked via the actual parsed import statements (not prose/comments, which are free
    to mention those modules by name when explaining the design)."""
    import ast
    import inspect

    from app.services import llm_orchestrator

    source = inspect.getsource(llm_orchestrator)
    tree = ast.parse(source)

    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)
            for alias in node.names:
                imported_names.add(alias.name)

    forbidden_imports = [
        "sqlalchemy",
        "Session",
        "AppSetting",
        "settings_service",
        "keyring",
        "app.db",
        "app.db.base",
        "app.models.orm",
    ]
    for name in forbidden_imports:
        assert name not in imported_names, (
            f"llm_orchestrator.py must never import {name!r} — the Groq key comes only "
            "from the `groq_key` parameter, never from the DB or a local secrets lib"
        )

    # The only symbol that may legitimately carry "key" in its name is the parameter/local
    # itself, not a lookup helper.
    assert "def stream(" in source
    assert "groq_key: str | None = None" in source
