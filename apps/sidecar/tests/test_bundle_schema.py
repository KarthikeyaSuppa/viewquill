"""Tests for app.services.bundle_schema — pure Pydantic models, no DB/app involved
(docs/05-EXPORT-IMPORT-SECURITY.md; Phase 7 task 1).
"""

from __future__ import annotations

import json

import pytest

from app.services.bundle_schema import (
    BundleManifest,
    BundlePayload,
    BundleSchemaError,
    validate_manifest_version,
)

_PAYLOAD_LIST_FIELDS = [
    "books",
    "scenes",
    "screenplay_elements",
    "book_scene_links",
    "scene_connections",
    "chapters",
    "book_scene_order",
    "codex_entries",
    "codex_relationships",
    "codex_arc_states",
    "book_codex_links",
    "codex_scene_links",
    "images",
    "image_tags",
    "entity_images",
    "continuity_flags",
    "draft_versions",
    "voice_notes",
]


def test_bundle_payload_round_trips_through_json() -> None:
    payload = BundlePayload(
        books=[{"id": "book-1", "title": "My Book"}],
        scenes=[
            {"id": "scene-1", "book_id": "book-1", "title": "Scene One"},
            {"id": "scene-2", "book_id": "book-1", "title": "Scene Two"},
        ],
    )

    dumped = payload.model_dump_json()
    reloaded = BundlePayload.model_validate(json.loads(dumped))

    assert len(reloaded.books) == len(payload.books) == 1
    assert len(reloaded.scenes) == len(payload.scenes) == 2
    assert reloaded.books == payload.books
    assert reloaded.scenes == payload.scenes


def test_bundle_manifest_version_validation() -> None:
    ok_manifest = BundleManifest(
        schema_version=1,
        book_id="book-1",
        exported_at="2026-07-28T00:00:00Z",
    )
    validate_manifest_version(ok_manifest)  # should not raise

    bad_manifest = BundleManifest(
        schema_version=99,
        book_id="book-1",
        exported_at="2026-07-28T00:00:00Z",
    )
    with pytest.raises(BundleSchemaError):
        validate_manifest_version(bad_manifest)


def test_fresh_bundle_payload_has_all_fields_empty() -> None:
    payload = BundlePayload()

    for field_name in _PAYLOAD_LIST_FIELDS:
        value = getattr(payload, field_name)
        assert value == []

    assert set(BundlePayload.model_fields.keys()) == set(_PAYLOAD_LIST_FIELDS)
