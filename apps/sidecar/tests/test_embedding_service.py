"""Tests for `app/services/embedding_service.py` (Phase 10 task 2,
docs/11-AI-INTELLIGENCE.md §2, PHASE10.md).

Covers the deterministic stub's math (same text -> same vector, different text -> a
genuinely different vector, valid 1024-length output) plus a real integration round-trip:
packing a stub embedding via `pack_embedding` and inserting it into the actual `embeddings`
`vec0` table from the `e51867fcdc66` migration, then running a KNN query against it — same
schema/extension-loading wiring proven by tests/test_semantic_search_migration.py, reused
here to prove the *service's* packed output round-trips through it correctly.

No Ollama/network/model involved anywhere in this file — QUILLNIGHT_LLM_STUB=1 is set
before `app.services.embedding_service` is imported so every `embed()` call in this module
takes the stub path only.
"""

from __future__ import annotations

import math
import os
import tempfile

# Per tests/conftest.py's module docstring: QUILLNIGHT_DATA_DIR only "wins" for whichever
# test module the collector imports first, and every module that needs its own migrated
# schema state just calls run_migrations() (idempotent) against the shared engine — same
# pattern as tests/test_semantic_search_migration.py.
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-embeddingservice-")
os.environ.setdefault("QUILLNIGHT_DATA_DIR", _TMP_DATA_DIR)
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import engine  # noqa: E402
from app.db.migrate import run_migrations  # noqa: E402
from app.services.embedding_service import (  # noqa: E402
    EMBEDDING_DIM,
    embed,
    embedding_model_name,
    pack_embedding,
)


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    run_migrations()


# ── Determinism: same text -> byte-identical vector ────────────────────────────
def test_embed_is_deterministic_for_same_text() -> None:
    first = embed("Elyndra confronts the traitor at the Ashgate.")
    second = embed("Elyndra confronts the traitor at the Ashgate.")
    assert first == second


# ── Non-degenerate: different text -> a genuinely different vector ─────────────
def test_embed_differs_for_different_text() -> None:
    a = embed("Elyndra confronts the traitor at the Ashgate.")
    b = embed("A quiet morning in the garden, nothing happens.")
    assert a != b
    # Not just a couple of components differing — a real embedding function should
    # diverge across most of the vector, not degenerate to a near-constant offset.
    differing = sum(1 for x, y in zip(a, b, strict=True) if abs(x - y) > 1e-9)
    assert differing > EMBEDDING_DIM * 0.9


# ── Not a constant vector regardless of input ───────────────────────────────────
def test_embed_is_not_a_constant_vector() -> None:
    values = embed("some text")
    distinct = {round(v, 6) for v in values}
    assert len(distinct) > EMBEDDING_DIM // 2


# ── Valid shape: 1024-length, unit-normalized (cosine-similarity-ready) ─────────
def test_embed_output_is_valid_1024_vector() -> None:
    values = embed("The Ashgate Betrayal")
    assert len(values) == EMBEDDING_DIM
    assert all(isinstance(v, float) for v in values)
    norm = math.sqrt(sum(v * v for v in values))
    assert norm == pytest.approx(1.0, abs=1e-6)


# ── embedding_model_name() reflects settings, not a hardcoded constant ──────────
def test_embedding_model_name_matches_settings_default() -> None:
    from app.config import get_settings

    assert embedding_model_name() == get_settings().default_embedding_model


# ── pack_embedding: wrong length rejected ───────────────────────────────────────
def test_pack_embedding_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="expected 1024"):
        pack_embedding([0.0, 1.0])


# ── Real integration round-trip: pack -> insert into vec0 -> KNN query ──────────
def test_packed_embedding_round_trips_through_vec0_knn_search() -> None:
    scene_vec = embed("Elyndra confronts the traitor at the Ashgate.")
    codex_vec = embed("A quiet morning in the garden, nothing happens.")

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO embeddings(entity_type, entity_id, embedding) "
                "VALUES ('scene', 'embedsvc-scene-1', :emb)"
            ),
            {"emb": pack_embedding(scene_vec)},
        )
        conn.execute(
            text(
                "INSERT INTO embeddings(entity_type, entity_id, embedding) "
                "VALUES ('codex_entry', 'embedsvc-codex-1', :emb)"
            ),
            {"emb": pack_embedding(codex_vec)},
        )
        conn.commit()

        # KNN query with the scene's own (re-derived, deterministic) embedding should
        # return the scene as the nearest match, not the unrelated codex entry.
        rows = conn.execute(
            text(
                "SELECT entity_type, entity_id, distance FROM embeddings "
                "WHERE embedding MATCH :q AND k = 2 ORDER BY distance"
            ),
            {"q": pack_embedding(embed("Elyndra confronts the traitor at the Ashgate."))},
        ).fetchall()

    assert len(rows) == 2
    assert rows[0].entity_type == "scene"
    assert rows[0].entity_id == "embedsvc-scene-1"
    assert rows[0].distance == pytest.approx(0.0, abs=1e-6)
    assert rows[1].distance > rows[0].distance
