"""/scenes and nested screenplay elements — the Node Canvas's canonical node entity plus its
structured screenplay content (docs/01-PRODUCT-VISION.md, docs/03-DATA-MODEL.md `scenes` /
`screenplay_elements`, docs/06 Phase 2 tasks A1/A2/A6).

Scenes are canonical and shared across Books (like Codex entries); per-Book canvas
placement/links are handled by later Phase 2 endpoints, not here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.schemas import (
    SceneCreate,
    SceneRead,
    SceneRevisionRead,
    SceneUpdate,
    ScreenplayElementCreate,
    ScreenplayElementRead,
    ScreenplayElementReorder,
    ScreenplayElementUpdate,
)
from app.services import scene_service, screenplay_service

router = APIRouter(prefix="/scenes", tags=["scenes"])


@router.post("", response_model=SceneRead, status_code=status.HTTP_201_CREATED)
def create_scene(payload: SceneCreate, db: Session = Depends(get_db)) -> SceneRead:
    scene = scene_service.create_scene(
        db,
        node_type=payload.node_type,
        title=payload.title,
        description=payload.description,
    )
    return SceneRead.model_validate(scene)


@router.get("", response_model=list[SceneRead])
def list_scenes(db: Session = Depends(get_db)) -> list[SceneRead]:
    return [SceneRead.model_validate(scene) for scene in scene_service.list_scenes(db)]


@router.get("/{scene_id}", response_model=SceneRead)
def get_scene(scene_id: str, db: Session = Depends(get_db)) -> SceneRead:
    scene = scene_service.get_scene(db, scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return SceneRead.model_validate(scene)


@router.patch("/{scene_id}", response_model=SceneRead)
def update_scene(scene_id: str, payload: SceneUpdate, db: Session = Depends(get_db)) -> SceneRead:
    values = payload.model_dump(exclude_unset=True)
    scene = scene_service.update_scene(db, scene_id, values)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return SceneRead.model_validate(scene)


@router.delete("/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene(scene_id: str, db: Session = Depends(get_db)) -> None:
    if not scene_service.delete_scene(db, scene_id):
        raise HTTPException(status_code=404, detail="Scene not found")


@router.get("/{scene_id}/revisions", response_model=list[SceneRevisionRead])
def list_revisions(scene_id: str, db: Session = Depends(get_db)) -> list[SceneRevisionRead]:
    if scene_service.get_scene(db, scene_id) is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return [
        SceneRevisionRead.model_validate(revision)
        for revision in scene_service.list_revisions(db, scene_id)
    ]


# ── Screenplay elements — nested under a scene (docs/03, docs/06 task A6) ────────
# DATA-SENSITIVE: these endpoints must NEVER modify `scenes.description` — see
# app/services/screenplay_service.py docstring.


def _require_scene(db: Session, scene_id: str) -> None:
    if scene_service.get_scene(db, scene_id) is None:
        raise HTTPException(status_code=404, detail="Scene not found")


@router.get("/{scene_id}/elements", response_model=list[ScreenplayElementRead])
def list_elements(scene_id: str, db: Session = Depends(get_db)) -> list[ScreenplayElementRead]:
    _require_scene(db, scene_id)
    return [
        ScreenplayElementRead.model_validate(el)
        for el in screenplay_service.list_elements(db, scene_id)
    ]


@router.post(
    "/{scene_id}/elements",
    response_model=ScreenplayElementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_element(
    scene_id: str, payload: ScreenplayElementCreate, db: Session = Depends(get_db)
) -> ScreenplayElementRead:
    _require_scene(db, scene_id)
    element = screenplay_service.create_element(
        db,
        scene_id=scene_id,
        element_type=payload.element_type,
        text=payload.text,
        order_index=payload.order_index,
    )
    return ScreenplayElementRead.model_validate(element)


@router.post("/{scene_id}/elements/reorder", response_model=list[ScreenplayElementRead])
def reorder_elements(
    scene_id: str, payload: ScreenplayElementReorder, db: Session = Depends(get_db)
) -> list[ScreenplayElementRead]:
    _require_scene(db, scene_id)
    elements = screenplay_service.reorder_elements(db, scene_id, payload.element_ids)
    if elements is None:
        raise HTTPException(
            status_code=400,
            detail="element_ids must match exactly the scene's existing element ids",
        )
    return [ScreenplayElementRead.model_validate(el) for el in elements]


@router.patch("/elements/{element_id}", response_model=ScreenplayElementRead)
def update_element(
    element_id: str, payload: ScreenplayElementUpdate, db: Session = Depends(get_db)
) -> ScreenplayElementRead:
    values = payload.model_dump(exclude_unset=True)
    element = screenplay_service.update_element(db, element_id, values)
    if element is None:
        raise HTTPException(status_code=404, detail="Screenplay element not found")
    return ScreenplayElementRead.model_validate(element)


@router.delete("/elements/{element_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_element(element_id: str, db: Session = Depends(get_db)) -> None:
    if not screenplay_service.delete_element(db, element_id):
        raise HTTPException(status_code=404, detail="Screenplay element not found")
