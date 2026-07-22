"""Screenplay element CRUD (docs/03-DATA-MODEL.md `screenplay_elements`, docs/01 Node Canvas,
docs/06 Phase 2 task A6).

DATA-SENSITIVE: ``screenplay_elements`` rows are a *structured* representation of a scene's
content that coexists with — and must NEVER clear or touch — ``Scene.description`` (the prose
representation). Every function here only ever reads/writes ``ScreenplayElement`` rows; the
parent ``Scene`` row (and its ``description``) is never mutated.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import new_uuid
from app.models.orm import ScreenplayElement


def list_elements(db: Session, scene_id: str) -> list[ScreenplayElement]:
    return list(
        db.execute(
            select(ScreenplayElement)
            .where(ScreenplayElement.scene_id == scene_id)
            .order_by(ScreenplayElement.order_index)
        ).scalars()
    )


def get_element(db: Session, element_id: str) -> ScreenplayElement | None:
    return db.get(ScreenplayElement, element_id)


def _next_order_index(db: Session, scene_id: str) -> int:
    max_index = db.execute(
        select(func.max(ScreenplayElement.order_index)).where(
            ScreenplayElement.scene_id == scene_id
        )
    ).scalar_one_or_none()
    return 0 if max_index is None else max_index + 1


def create_element(
    db: Session,
    *,
    scene_id: str,
    element_type: str,
    text: str,
    order_index: int | None = None,
) -> ScreenplayElement:
    element = ScreenplayElement(
        id=new_uuid(),
        scene_id=scene_id,
        element_type=element_type,
        text=text,
        order_index=order_index if order_index is not None else _next_order_index(db, scene_id),
    )
    db.add(element)
    db.commit()
    db.refresh(element)
    return element


def update_element(
    db: Session, element_id: str, values: dict[str, Any]
) -> ScreenplayElement | None:
    """Partial update — only keys present in ``values`` are applied."""
    element = db.get(ScreenplayElement, element_id)
    if element is None:
        return None
    for key, value in values.items():
        setattr(element, key, value)
    db.commit()
    db.refresh(element)
    return element


def delete_element(db: Session, element_id: str) -> bool:
    element = db.get(ScreenplayElement, element_id)
    if element is None:
        return False
    db.delete(element)
    db.commit()
    return True


def reorder_elements(
    db: Session, scene_id: str, element_ids: list[str]
) -> list[ScreenplayElement] | None:
    """Persist a new order for ``scene_id``'s elements.

    ``element_ids`` must be exactly the set of element ids currently belonging to the
    scene (no more, no less) — returns ``None`` if the scene has no elements or the
    provided ids don't match the scene's existing elements, so the caller can 400/404
    without silently dropping or orphaning rows.
    """
    existing = list_elements(db, scene_id)
    if not existing:
        return None
    existing_ids = {el.id for el in existing}
    if set(element_ids) != existing_ids or len(element_ids) != len(existing):
        return None

    by_id = {el.id: el for el in existing}
    for index, element_id in enumerate(element_ids):
        by_id[element_id].order_index = index
    db.commit()
    return list_elements(db, scene_id)
