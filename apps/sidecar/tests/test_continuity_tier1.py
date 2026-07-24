"""Tests for Continuity Checker v2 Tier 1 — deterministic SQL checks (docs/11-AI-
INTELLIGENCE.md §4 "Tier 1 — Deterministic", docs/06 Phase 4 task BE-4).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing app) so a
fresh SQLite DB is migrated to head for this test run only — never touches a real
app-data directory. Scenarios are built entirely through the real endpoints (no direct
ORM/DB access), matching the pattern in test_outline.py.
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
from app.models.orm import ContinuityFlag  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering as a context manager runs the app's lifespan (Alembic migrations to head)
    # against the throwaway QUILLNIGHT_DATA_DIR set above.
    with TestClient(app) as test_client:
        yield test_client


def _create_book(client: TestClient, title: str = "Book") -> str:
    resp = client.post("/books", json={"title": title, "book_type": "story_book"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_scene(client: TestClient, title: str = "Scene") -> str:
    resp = client.post("/scenes", json={"node_type": "scene", "title": title})
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_to_canvas(client: TestClient, book_id: str, scene_id: str) -> None:
    resp = client.post(f"/books/{book_id}/scenes/{scene_id}")
    assert resp.status_code == 201


def _assign_outline(client: TestClient, book_id: str, scene_id: str, index: int) -> None:
    resp = client.post(
        f"/books/{book_id}/scenes/{scene_id}/assign", json={"outline_order_index": index}
    )
    assert resp.status_code == 200


def _set_timeline(
    client: TestClient,
    book_id: str,
    scene_id: str,
    sort_key: float,
    label: str | None = None,
) -> None:
    payload: dict = {"in_story_time_sort_key": sort_key}
    if label is not None:
        payload["in_story_time_label"] = label
    resp = client.post(f"/books/{book_id}/scenes/{scene_id}/timeline", json=payload)
    assert resp.status_code == 200


def _create_codex_entry(client: TestClient, name: str = "Entity") -> str:
    resp = client.post("/codex", json={"entry_type": "character", "name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def _link_codex_scene(client: TestClient, entry_id: str, scene_id: str) -> None:
    resp = client.post(f"/codex/{entry_id}/scenes/{scene_id}")
    assert resp.status_code == 201


def _create_arc_state(client: TestClient, entry_id: str, book_id: str, index: int) -> None:
    resp = client.post(
        f"/codex/{entry_id}/arc-states",
        json={"book_id": book_id, "as_of_outline_order_index": index},
    )
    assert resp.status_code == 201


def _run_check(client: TestClient, book_id: str) -> list[dict]:
    resp = client.post(f"/books/{book_id}/continuity/check")
    assert resp.status_code == 200
    return resp.json()


def _get_flags(client: TestClient, book_id: str, status: str | None = None) -> list[dict]:
    params = {"status": status} if status is not None else {}
    resp = client.get(f"/books/{book_id}/continuity/flags", params=params)
    assert resp.status_code == 200
    return resp.json()


# ── Check A — early_appearance ──────────────────────────────────────────────────


def test_early_appearance_flagged_when_scene_before_introduction(client: TestClient) -> None:
    book_id = _create_book(client, "Early Appearance Book")
    early_scene = _create_scene(client, "Early Scene")
    intro_scene = _create_scene(client, "Intro Scene")
    for scene_id in (early_scene, intro_scene):
        _add_to_canvas(client, book_id, scene_id)
    _assign_outline(client, book_id, early_scene, 2)
    _assign_outline(client, book_id, intro_scene, 5)

    entry_id = _create_codex_entry(client, "Sir Reginald")
    _create_arc_state(client, entry_id, book_id, 5)
    _link_codex_scene(client, entry_id, early_scene)

    flags = _run_check(client, book_id)
    early_flags = [f for f in flags if f["flag_type"] == "early_appearance"]
    assert len(early_flags) == 1
    flag = early_flags[0]
    assert flag["scene_id"] == early_scene
    assert flag["codex_entry_id"] == entry_id
    assert flag["severity"] == "warning"
    assert flag["source"] == "deterministic"
    assert flag["status"] == "open"
    assert "Sir Reginald" in flag["description"]
    assert "2" in flag["description"]
    assert "5" in flag["description"]


def test_early_appearance_skipped_when_no_arc_state(client: TestClient) -> None:
    book_id = _create_book(client, "No Arc State Book")
    scene_id = _create_scene(client, "Some Scene")
    _add_to_canvas(client, book_id, scene_id)
    _assign_outline(client, book_id, scene_id, 0)

    entry_id = _create_codex_entry(client, "Unintroduced Entity")
    _link_codex_scene(client, entry_id, scene_id)

    flags = _run_check(client, book_id)
    assert [f for f in flags if f["flag_type"] == "early_appearance"] == []


def test_early_appearance_not_flagged_when_at_or_after_intro(client: TestClient) -> None:
    book_id = _create_book(client, "On Time Book")
    intro_scene = _create_scene(client, "Intro Scene")
    later_scene = _create_scene(client, "Later Scene")
    for scene_id in (intro_scene, later_scene):
        _add_to_canvas(client, book_id, scene_id)
    _assign_outline(client, book_id, intro_scene, 3)
    _assign_outline(client, book_id, later_scene, 4)

    entry_id = _create_codex_entry(client, "On-Time Entity")
    _create_arc_state(client, entry_id, book_id, 3)
    _link_codex_scene(client, entry_id, intro_scene)  # exactly at intro
    _link_codex_scene(client, entry_id, later_scene)  # after intro

    flags = _run_check(client, book_id)
    assert [f for f in flags if f["flag_type"] == "early_appearance"] == []


# ── Check B — timeline_conflict ─────────────────────────────────────────────────


def test_timeline_conflict_flagged_on_adjacent_inversion(client: TestClient) -> None:
    book_id = _create_book(client, "Timeline Conflict Book")
    scene_a = _create_scene(client, "Scene A")
    scene_b = _create_scene(client, "Scene B")
    for scene_id in (scene_a, scene_b):
        _add_to_canvas(client, book_id, scene_id)
    _assign_outline(client, book_id, scene_a, 0)
    _assign_outline(client, book_id, scene_b, 1)
    _set_timeline(client, book_id, scene_a, 2.0)
    _set_timeline(client, book_id, scene_b, 1.0)

    flags = _run_check(client, book_id)
    conflict_flags = [f for f in flags if f["flag_type"] == "timeline_conflict"]
    assert len(conflict_flags) == 1
    flag = conflict_flags[0]
    assert flag["scene_id"] == scene_b
    assert flag["severity"] == "hint"
    assert flag["source"] == "deterministic"


def test_timeline_conflict_suppressed_for_flashback(client: TestClient) -> None:
    book_id = _create_book(client, "Flashback Book")
    scene_a = _create_scene(client, "Scene A")
    scene_b = _create_scene(client, "Scene B")
    for scene_id in (scene_a, scene_b):
        _add_to_canvas(client, book_id, scene_id)
    _assign_outline(client, book_id, scene_a, 0)
    _assign_outline(client, book_id, scene_b, 1)
    _set_timeline(client, book_id, scene_a, 2.0)
    _set_timeline(client, book_id, scene_b, 1.0, label="Flashback to Day 1")

    flags = _run_check(client, book_id)
    assert [f for f in flags if f["flag_type"] == "timeline_conflict"] == []


def test_clean_book_has_zero_deterministic_flags(client: TestClient) -> None:
    book_id = _create_book(client, "Clean Book")
    scene_a = _create_scene(client, "Scene A")
    scene_b = _create_scene(client, "Scene B")
    for scene_id in (scene_a, scene_b):
        _add_to_canvas(client, book_id, scene_id)
    _assign_outline(client, book_id, scene_a, 0)
    _assign_outline(client, book_id, scene_b, 1)
    _set_timeline(client, book_id, scene_a, 1.0)
    _set_timeline(client, book_id, scene_b, 2.0)

    entry_id = _create_codex_entry(client, "Clean Entity")
    _create_arc_state(client, entry_id, book_id, 0)
    _link_codex_scene(client, entry_id, scene_a)

    flags = _run_check(client, book_id)
    assert flags == []


# ── Regeneration semantics ───────────────────────────────────────────────────────


def test_rerun_is_idempotent_and_preserves_manual_flags(client: TestClient) -> None:
    book_id = _create_book(client, "Idempotent Book")
    early_scene = _create_scene(client, "Early Scene")
    intro_scene = _create_scene(client, "Intro Scene")
    for scene_id in (early_scene, intro_scene):
        _add_to_canvas(client, book_id, scene_id)
    _assign_outline(client, book_id, early_scene, 0)
    _assign_outline(client, book_id, intro_scene, 3)

    entry_id = _create_codex_entry(client, "Repeat Entity")
    _create_arc_state(client, entry_id, book_id, 3)
    _link_codex_scene(client, entry_id, early_scene)

    first_run = _run_check(client, book_id)
    first_deterministic = [f for f in first_run if f["source"] == "deterministic"]
    assert len(first_deterministic) == 1

    # A pre-existing manual flag on the same book — inserted directly, mirroring
    # test_continuity_flags_migration.py's pattern (no dedicated "create manual flag"
    # endpoint exists yet) — must survive re-runs untouched: run_tier1 only ever deletes
    # source='deterministic' rows for this book.
    with SessionLocal() as db:
        manual_flag = ContinuityFlag(
            book_id=book_id,
            description="A human noted this by hand.",
            source="manual",
            status="open",
        )
        db.add(manual_flag)
        db.commit()
        manual_flag_id = manual_flag.id

    second_run = _run_check(client, book_id)
    second_deterministic = [f for f in second_run if f["source"] == "deterministic"]
    assert len(second_deterministic) == 1
    assert second_deterministic[0]["description"] == first_deterministic[0]["description"]
    manual_after_second = [f for f in second_run if f["id"] == manual_flag_id]
    assert len(manual_after_second) == 1
    assert manual_after_second[0]["source"] == "manual"
    assert manual_after_second[0]["status"] == "open"

    # A third run still yields exactly one deterministic flag (never duplicated) and the
    # manual flag is still untouched.
    third_run = _run_check(client, book_id)
    third_deterministic = [f for f in third_run if f["source"] == "deterministic"]
    assert len(third_deterministic) == 1
    assert any(f["id"] == manual_flag_id and f["source"] == "manual" for f in third_run)


# ── PATCH flag status ────────────────────────────────────────────────────────────


def test_patch_flag_status_dismissed_excluded_from_open_filter(client: TestClient) -> None:
    book_id = _create_book(client, "Dismiss Book")
    early_scene = _create_scene(client, "Early Scene")
    intro_scene = _create_scene(client, "Intro Scene")
    for scene_id in (early_scene, intro_scene):
        _add_to_canvas(client, book_id, scene_id)
    _assign_outline(client, book_id, early_scene, 0)
    _assign_outline(client, book_id, intro_scene, 4)

    entry_id = _create_codex_entry(client, "Dismiss Entity")
    _create_arc_state(client, entry_id, book_id, 4)
    _link_codex_scene(client, entry_id, early_scene)

    flags = _run_check(client, book_id)
    assert len(flags) == 1
    flag_id = flags[0]["id"]

    open_flags = _get_flags(client, book_id, status="open")
    assert any(f["id"] == flag_id for f in open_flags)

    patch_resp = client.patch(f"/continuity/flags/{flag_id}", json={"status": "dismissed"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "dismissed"

    open_flags_after = _get_flags(client, book_id, status="open")
    assert all(f["id"] != flag_id for f in open_flags_after)

    dismissed_flags = _get_flags(client, book_id, status="dismissed")
    assert any(f["id"] == flag_id for f in dismissed_flags)


def test_patch_flag_status_missing_flag_404(client: TestClient) -> None:
    resp = client.patch("/continuity/flags/does-not-exist", json={"status": "resolved"})
    assert resp.status_code == 404


def test_run_check_missing_book_404(client: TestClient) -> None:
    resp = client.post("/books/does-not-exist/continuity/check")
    assert resp.status_code == 404
