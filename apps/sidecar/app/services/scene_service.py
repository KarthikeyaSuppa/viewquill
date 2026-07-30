"""Scene CRUD — the canonical node entity behind the Node Canvas (docs/01-PRODUCT-VISION.md,
docs/03-DATA-MODEL.md `scenes`, docs/06 Phase 2).

Scenes are canonical and shared across Books (like Codex entries) — this module only
manages the scene row itself; per-Book canvas placement/links are separate tables
(``book_scene_links``, ``book_scene_order``) added by later Phase 2 tasks.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import new_uuid, utcnow_iso
from app.models.orm import Scene
from app.services import search_index_service


def _word_count(description: str | None) -> int:
    if not description:
        return 0
    return len(description.split())


def create_scene(
    db: Session,
    *,
    node_type: str,
    title: str,
    description: str | None = None,
) -> Scene:
    scene = Scene(
        id=new_uuid(),
        node_type=node_type,
        title=title,
        description=description,
        word_count=_word_count(description),
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)
    # Embed-on-save (Phase 10 task 3, PHASE10.md) — derived data, never blocks this save;
    # see search_index_service's module docstring.
    search_index_service.upsert_entity("scene", scene.id, scene.title, scene.description)
    return scene


def list_scenes(db: Session) -> list[Scene]:
    return list(db.execute(select(Scene).order_by(Scene.updated_at.desc())).scalars())


def get_scene(db: Session, scene_id: str) -> Scene | None:
    return db.get(Scene, scene_id)


def update_scene(db: Session, scene_id: str, values: dict[str, Any]) -> Scene | None:
    """Partial update — only keys present in ``values`` are applied.

    Recomputes ``word_count`` whenever ``description`` is one of the changed keys.
    """
    scene = db.get(Scene, scene_id)
    if scene is None:
        return None
    for key, value in values.items():
        setattr(scene, key, value)
    if "description" in values:
        scene.word_count = _word_count(scene.description)
    # `updated_at` has an `onupdate` default, but that only fires on a flush that detects a
    # change; touch it explicitly so a no-op-looking patch still bumps the timestamp.
    scene.updated_at = utcnow_iso()
    db.commit()
    db.refresh(scene)
    # Embed-on-save (Phase 10 task 3) — re-index unconditionally so the search index never
    # drifts from the saved row, even on a patch that didn't touch title/description.
    search_index_service.upsert_entity("scene", scene.id, scene.title, scene.description)
    return scene


def delete_scene(db: Session, scene_id: str) -> bool:
    scene = db.get(Scene, scene_id)
    if scene is None:
        return False
    db.delete(scene)
    db.commit()
    # Virtual tables (search_fts/embeddings) aren't real FK targets, so there's no DB-level
    # cascade delete for them — clean up the index row explicitly (Phase 10 task 3).
    search_index_service.delete_entity("scene", scene_id)
    return True
