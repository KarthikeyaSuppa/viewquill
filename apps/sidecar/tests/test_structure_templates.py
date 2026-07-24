"""Tests for the built-in structure-template seed + /structure-templates listing
(docs/03-DATA-MODEL.md `structure_templates`, docs/06 Phase 4 task BE-2).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB is migrated + seeded to head for this test run only — never touches a real
app-data directory.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services.structure_templates import (  # noqa: E402
    STRUCTURE_TEMPLATES,
    seed_structure_templates,
)


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head,
    # then the structure-template seed) against the throwaway QUILLNIGHT_DATA_DIR above.
    with TestClient(app) as test_client:
        yield test_client


def test_seed_is_idempotent(client: TestClient) -> None:
    # The lifespan already seeded once on entering the `client` fixture above; seed again
    # directly and confirm the total row count and name set are unaffected.
    with SessionLocal() as db:
        seed_structure_templates(db)
        seed_structure_templates(db)

    resp = client.get("/structure-templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) == len(STRUCTURE_TEMPLATES) == 3

    names = [t["name"] for t in templates]
    assert sorted(names) == sorted(t["name"] for t in STRUCTURE_TEMPLATES)
    assert len(set(names)) == len(names)  # unique


def test_list_returns_beats(client: TestClient) -> None:
    templates = {t["name"]: t for t in client.get("/structure-templates").json()}

    three_act = templates["Three-Act"]
    assert len(three_act["beats"]) == 7
    assert three_act["beats"][0]["name"] == "Setup"
    assert three_act["beats"][0]["order_index"] == 0

    hero = templates["Hero's Journey"]
    assert len(hero["beats"]) == 11
    assert hero["beats"][-1]["name"] == "Return with the Elixir"

    freeform = templates["Freeform"]
    assert freeform["beats"] == []


def test_filter_by_book_type(client: TestClient) -> None:
    # Freeform applies to every book type (applicable_book_types is null).
    single_scene = client.get("/structure-templates", params={"book_type": "single_scene"})
    assert single_scene.status_code == 200
    single_scene_names = {t["name"] for t in single_scene.json()}
    assert single_scene_names == {"Freeform"}

    story_book = client.get("/structure-templates", params={"book_type": "story_book"})
    assert story_book.status_code == 200
    story_book_names = {t["name"] for t in story_book.json()}
    assert story_book_names == {"Three-Act", "Hero's Journey", "Freeform"}

    unfiltered = client.get("/structure-templates")
    assert len(unfiltered.json()) == 3
