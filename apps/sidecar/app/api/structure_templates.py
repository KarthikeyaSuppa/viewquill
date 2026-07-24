"""/structure-templates — read-only listing of the built-in structure templates
(docs/03-DATA-MODEL.md `structure_templates`, docs/06 Phase 4 task BE-2).

Rows are seeded at startup by ``app.services.structure_templates.seed_structure_templates``
(app/main.py lifespan) — this module never writes to the table, it only lists it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.orm import StructureTemplate
from app.models.schemas import StructureTemplateRead

router = APIRouter(tags=["structure-templates"])


@router.get("/structure-templates", response_model=list[StructureTemplateRead])
def list_structure_templates(
    book_type: str | None = Query(default=None), db: Session = Depends(get_db)
) -> list[StructureTemplateRead]:
    templates = list(db.execute(select(StructureTemplate)).scalars())
    if book_type is not None:
        templates = [
            template
            for template in templates
            if template.applicable_book_types is None
            or book_type in template.applicable_book_types
        ]
    return [StructureTemplateRead.model_validate(template) for template in templates]
