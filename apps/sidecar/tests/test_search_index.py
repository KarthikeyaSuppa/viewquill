"""Tests for the Phase 10 embed-on-save wiring (PHASE10.md task 3,
docs/11-AI-INTELLIGENCE.md §2): app/services/search_index_service.py's `upsert_entity`/
`delete_entity`, their hooks in scene_service.py/codex_service.py, and the
`POST /search/backfill` catch-up endpoint (app/api/search.py).

No Ollama/network/model involved — QUILLNIGHT_LLM_STUB=1 is set before `app.main` is
imported so every embed() call here takes the deterministic stub path (same convention as
tests/test_embedding_service.py, tests/test_semantic_search_migration.py).
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-searchindex-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["QUILLNIGHT_LLM_STUB"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.orm import CodexEntry, Scene  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        yield test_client


def _fts_rows(entity_type: str, entity_id: str) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT title, body FROM search_fts "
                "WHERE entity_type = :t AND entity_id = :i"
            ),
            {"t": entity_type, "i": entity_id},
        ).fetchall()


def _embedding_rows(entity_type: str, entity_id: str) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT entity_type, entity_id FROM embeddings "
                "WHERE entity_type = :t AND entity_id = :i"
            ),
            {"t": entity_type, "i": entity_id},
        ).fetchall()


# ── Scene create/update/delete ──────────────────────────────────────────────────
def test_creating_scene_populates_search_fts_and_embeddings(client: TestClient) -> None:
    resp = client.post(
        "/scenes",
        json={
            "node_type": "scene",
            "title": "The Windmere Signal",
            "description": "Captain Thalen decodes the signal.",
        },
    )
    assert resp.status_code == 201
    scene_id = resp.json()["id"]

    fts_rows = _fts_rows("scene", scene_id)
    assert len(fts_rows) == 1
    assert fts_rows[0].title == "The Windmere Signal"
    assert fts_rows[0].body == "Captain Thalen decodes the signal."

    assert len(_embedding_rows("scene", scene_id)) == 1


def test_updating_scene_reindexes_without_duplicate_rows(client: TestClient) -> None:
    create_resp = client.post(
        "/scenes",
        json={
            "node_type": "scene",
            "title": "Original Title",
            "description": "Original body.",
        },
    )
    scene_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/scenes/{scene_id}",
        json={"title": "Updated Title", "description": "Updated body."},
    )
    assert patch_resp.status_code == 200

    fts_rows = _fts_rows("scene", scene_id)
    assert len(fts_rows) == 1  # no stale/duplicate row left behind
    assert fts_rows[0].title == "Updated Title"
    assert fts_rows[0].body == "Updated body."

    assert len(_embedding_rows("scene", scene_id)) == 1


def test_deleting_scene_removes_indexed_row(client: TestClient) -> None:
    create_resp = client.post("/scenes", json={"node_type": "scene", "title": "To Delete"})
    scene_id = create_resp.json()["id"]
    assert len(_fts_rows("scene", scene_id)) == 1
    assert len(_embedding_rows("scene", scene_id)) == 1

    delete_resp = client.delete(f"/scenes/{scene_id}")
    assert delete_resp.status_code == 204

    assert _fts_rows("scene", scene_id) == []
    assert _embedding_rows("scene", scene_id) == []


# ── CodexEntry create/update/delete ──────────────────────────────────────────────
def test_creating_codex_entry_populates_search_fts_and_embeddings(client: TestClient) -> None:
    resp = client.post(
        "/codex",
        json={
            "entry_type": "character",
            "name": "Thalen",
            "summary": "A former harbor pilot of Windmere.",
        },
    )
    assert resp.status_code == 201
    entry_id = resp.json()["id"]

    fts_rows = _fts_rows("codex_entry", entry_id)
    assert len(fts_rows) == 1
    assert fts_rows[0].title == "Thalen"
    assert fts_rows[0].body == "A former harbor pilot of Windmere."

    assert len(_embedding_rows("codex_entry", entry_id)) == 1


def test_updating_codex_entry_reindexes_without_duplicate_rows(client: TestClient) -> None:
    create_resp = client.post(
        "/codex", json={"entry_type": "location", "name": "Windmere", "summary": "A fortress town."}
    )
    entry_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/codex/{entry_id}",
        json={"name": "Windmere Keep", "summary": "A fortified keep on the border."},
    )
    assert patch_resp.status_code == 200

    fts_rows = _fts_rows("codex_entry", entry_id)
    assert len(fts_rows) == 1
    assert fts_rows[0].title == "Windmere Keep"
    assert fts_rows[0].body == "A fortified keep on the border."

    assert len(_embedding_rows("codex_entry", entry_id)) == 1


def test_deleting_codex_entry_removes_indexed_row(client: TestClient) -> None:
    create_resp = client.post("/codex", json={"entry_type": "character", "name": "To Delete"})
    entry_id = create_resp.json()["id"]
    assert len(_fts_rows("codex_entry", entry_id)) == 1
    assert len(_embedding_rows("codex_entry", entry_id)) == 1

    delete_resp = client.delete(f"/codex/{entry_id}")
    assert delete_resp.status_code == 204

    assert _fts_rows("codex_entry", entry_id) == []
    assert _embedding_rows("codex_entry", entry_id) == []


# ── Backfill: catches up rows inserted directly via the ORM, bypassing the service layer
# (simulating legacy data that predates the embed-on-save hooks) ────────────────────────
def test_backfill_indexes_preexisting_rows_inserted_directly_via_orm(client: TestClient) -> None:
    with SessionLocal() as db:
        legacy_scene = Scene(
            id="legacy-scene-1",
            node_type="scene",
            title="Legacy Scene",
            description="Predates the embed-on-save hook.",
        )
        legacy_entry = CodexEntry(
            id="legacy-codex-1",
            entry_type="character",
            name="Legacy Character",
            summary="Also predates the hook.",
        )
        db.add(legacy_scene)
        db.add(legacy_entry)
        db.commit()

    # Bypassing scene_service/codex_service means nothing indexed these yet.
    assert _fts_rows("scene", "legacy-scene-1") == []
    assert _embedding_rows("scene", "legacy-scene-1") == []
    assert _fts_rows("codex_entry", "legacy-codex-1") == []
    assert _embedding_rows("codex_entry", "legacy-codex-1") == []

    resp = client.post("/search/backfill")
    assert resp.status_code == 200
    body = resp.json()
    # At least the two legacy rows plus everything created by earlier tests in this module.
    assert body["scenes_indexed"] >= 1
    assert body["codex_entries_indexed"] >= 1

    legacy_scene_fts = _fts_rows("scene", "legacy-scene-1")
    assert len(legacy_scene_fts) == 1
    assert legacy_scene_fts[0].title == "Legacy Scene"
    assert len(_embedding_rows("scene", "legacy-scene-1")) == 1

    legacy_entry_fts = _fts_rows("codex_entry", "legacy-codex-1")
    assert len(legacy_entry_fts) == 1
    assert legacy_entry_fts[0].title == "Legacy Character"
    assert len(_embedding_rows("codex_entry", "legacy-codex-1")) == 1


def test_backfill_is_idempotent_no_duplicate_rows_on_rerun(client: TestClient) -> None:
    resp = client.post("/search/backfill")
    assert resp.status_code == 200

    assert len(_fts_rows("scene", "legacy-scene-1")) == 1
    assert len(_embedding_rows("scene", "legacy-scene-1")) == 1
