"""Embedding service — real interface + deterministic stub (docs/11-AI-INTELLIGENCE.md §2,
PHASE10.md task 2).

This module is the ONLY place in the sidecar that will call the embedding model, mirroring
`llm_orchestrator.py`'s "one module owns the provider library" convention. It defines
:func:`embed` as the stable call site every future caller (embed-on-save trigger, bulk
backfill, hybrid search) should use — the schema (`app/db/migrations/versions/
e51867fcdc66_semantic_search_fts5_and_vec0.py`) already fixes the shape: one 1024-dim
``qwen3-embedding:0.6b`` vector per (entity_type, entity_id), title+body embedded as a
single unit, no arbitrary splitting.

## Stub vs real, same seam as `QUILLNIGHT_LLM_STUB`

This build machine never runs Ollama (CLAUDE.md "Environment constraints") — the real
`qwen3-embedding:0.6b` call is deferred to the ASUS TUF F15. Real vs. stub is gated by the
exact same env-var convention already used in `llm_orchestrator.py`
(`QUILLNIGHT_LLM_STUB`) and `speech_stt.py` (`QUILLNIGHT_STT_STUB`) — a raw
``os.environ.get(...) == "1"`` check, not a pydantic-settings field, so it stays consistent
with those two modules rather than inventing a third convention.

## Dropping in the real call later

`_embed_real` is intentionally a two-line stub raising `NotImplementedError` — on the
target machine, replace its body with something like::

    import litellm
    response = litellm.embedding(
        model=f"ollama/{get_settings().default_embedding_model}",
        input=text,
        api_base=get_settings().ollama_base_url,
        num_gpu=0,  # CPU-pinned, per docs/11 §2 "VRAM discipline"
    )
    return response.data[0]["embedding"]

No other function in this module needs to change — `embed()` already dispatches on the
stub flag, and `pack_embedding`/callers are agnostic to which path produced the vector.
"""

from __future__ import annotations

import hashlib
import math
import os
import struct

from app.config import get_settings

# Same env flag `llm_orchestrator.py` reads for `QUILLNIGHT_LLM_STUB=1` — this module
# doesn't introduce a second stub flag; embeddings are model-dependent output exactly like
# chat completions, so they're gated by the same switch.
_STUB_ENV_VAR = "QUILLNIGHT_LLM_STUB"

# Per docs/11 §2 / the e51867fcdc66 migration's EMBEDDING_DIM — kept in sync manually since
# the migration can't import this (not-yet-existing at migration time) module and this
# module has no reason to import Alembic revision code.
EMBEDDING_DIM = 1024


def _is_stub_mode() -> bool:
    return os.environ.get(_STUB_ENV_VAR) == "1"


def _stub_embed(text: str) -> list[float]:
    """Deterministic, non-degenerate stand-in for the real embedding call.

    Same input text always yields the same vector (hash the text into a seed, then derive
    1024 floats from a seeded PRNG — no real randomness, no network, no model). Different
    input text yields a genuinely different vector, not just noise: each float is derived
    from ``sha256(text + str(i))`` for component ``i``, so distinct texts diverge across
    the whole vector rather than differing by a shared offset.

    Normalized to unit length (L2 norm 1), matching real embedding-model output and making
    the vec0 table's default L2 (Euclidean) distance monotonic with cosine distance/rank —
    docs/11 §2's hybrid retrieval is designed around cosine similarity.
    """
    components: list[float] = []
    for i in range(EMBEDDING_DIM):
        digest = hashlib.sha256(f"{text}:{i}".encode()).digest()
        # First 8 bytes -> an unsigned int -> [0, 1) -> shift to [-1, 1).
        as_int = int.from_bytes(digest[:8], "big")
        unit_interval = as_int / (2**64 - 1)
        components.append(unit_interval * 2.0 - 1.0)

    norm = math.sqrt(sum(c * c for c in components))
    if norm == 0.0:  # astronomically unlikely (all 1024 hashed components exactly 0)
        components[0] = 1.0
        norm = 1.0
    return [c / norm for c in components]


def _embed_real(text: str) -> list[float]:
    """The real `qwen3-embedding:0.6b` call via Ollama — NOT implemented on this machine
    (no Ollama here, none should ever be installed/downloaded, per CLAUDE.md "Environment
    constraints"). See the module docstring for the exact drop-in replacement to make on
    the target machine (ASUS TUF F15)."""
    raise NotImplementedError(
        "Real embedding calls require Ollama, which is deliberately not installed on this "
        "machine. Set QUILLNIGHT_LLM_STUB=1 for stub embeddings here; the real call is "
        "deferred to the ASUS TUF F15 (see PHASE10.md §3, docs/11-AI-INTELLIGENCE.md §2)."
    )


def embed(text: str) -> list[float]:
    """Embed ``text`` (per docs/11 §2's "embed per entity (title + body), no arbitrary
    splitting" rule — callers pass the already-joined title+body unit, this function does
    no chunking of its own) into a 1024-dim vector.

    Routes to the deterministic stub under ``QUILLNIGHT_LLM_STUB=1`` (this machine's only
    exercised path); otherwise calls the real model via ``settings.default_embedding_model``
    (not yet implemented here — see :func:`_embed_real`).
    """
    if _is_stub_mode():
        return _stub_embed(text)
    return _embed_real(text)


def pack_embedding(values: list[float]) -> bytes:
    """Packs a 1024-dim float vector into the little-endian float32 blob the `embeddings`
    `vec0` table expects on insert/query — same ``struct.pack(f"<{DIM}f", *values)`` shape
    established by `tests/test_semantic_search_migration.py`'s `_fake_embedding` helper, so
    every caller (this service, that test, future hybrid-search code) packs identically.
    """
    if len(values) != EMBEDDING_DIM:
        raise ValueError(f"expected {EMBEDDING_DIM} values, got {len(values)}")
    return struct.pack(f"<{EMBEDDING_DIM}f", *values)


def embedding_model_name() -> str:
    """The configured embedding model name (``settings.default_embedding_model`` — already
    defined in `app/config.py` alongside `default_local_model`/`default_grammar_model`,
    docs/09 principle #9 "Model names are settings, not constants"), for callers/logs that
    want to record which model an embedding came from without reaching into `app.config`
    directly."""
    return get_settings().default_embedding_model
