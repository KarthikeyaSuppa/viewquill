"""Built-in structure-template seed data (docs/03-DATA-MODEL.md `structure_templates`,
docs/06 Phase 4 task BE-2).

``StructureTemplate.beats`` is a JSON list of ``{name, order_index, description}`` dicts
consumed by the Outline view; ``applicable_book_types`` is a JSON list of ``Book.book_type``
values it applies to, or ``None`` to apply to every book type.

These three templates are common-knowledge story-structure frameworks (not copyrighted
text) — the beat descriptions here are original, one-line summaries written for this app.

Seeding is idempotent and UPSERTs by the unique ``name``: existing rows are updated in
place (so a template edited here on a later build reaches existing users), new ones are
inserted. It is intentionally never destructive — it only ever writes to
``structure_templates`` rows it owns by name, never touches ``books`` or any other table.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import new_uuid
from app.models.orm import StructureTemplate

logger = logging.getLogger("quillnight")


def _beats(*names_and_descriptions: tuple[str, str]) -> list[dict]:
    return [
        {"name": name, "order_index": index, "description": description}
        for index, (name, description) in enumerate(names_and_descriptions)
    ]


STRUCTURE_TEMPLATES: list[dict] = [
    {
        "name": "Three-Act",
        "applicable_book_types": ["story_book", "movie_script", "short_film_script"],
        "beats": _beats(
            ("Setup", "Establish the ordinary world, protagonist, and stakes."),
            ("Inciting Incident", "The event that disrupts the status quo and starts the story."),
            ("Rising Action", "Escalating complications as the protagonist pursues their goal."),
            ("Midpoint", "A major turn that raises the stakes or reframes the goal."),
            ("Climax", "The final confrontation that decides the outcome."),
            ("Falling Action", "Immediate consequences of the climax play out."),
            ("Resolution", "The new equilibrium; loose threads are tied off."),
        ),
    },
    {
        "name": "Hero's Journey",
        "applicable_book_types": ["story_book", "movie_script", "short_film_script"],
        "beats": _beats(
            ("Ordinary World", "The hero's life before the adventure begins."),
            ("Call to Adventure", "A problem or opportunity disrupts the hero's world."),
            ("Refusal", "The hero hesitates or resists answering the call."),
            ("Meeting the Mentor", "A guide provides wisdom, tools, or training."),
            ("Crossing the Threshold", "The hero commits and leaves the ordinary world behind."),
            ("Tests & Allies", "Trials, allies, and enemies test the hero along the way."),
            ("Ordeal", "The hero faces their greatest fear or most dangerous challenge."),
            ("Reward", "The hero seizes the prize earned by surviving the ordeal."),
            ("The Road Back", "The hero commits to returning, often chased by consequences."),
            ("Resurrection", "A final test where the hero is transformed for good."),
            ("Return with the Elixir", "The hero returns home changed, bringing something of value."),
        ),
    },
    {
        "name": "Freeform",
        "applicable_book_types": None,
        "beats": [],
    },
]


def seed_structure_templates(db: Session) -> int:
    """UPSERT the built-in templates by unique ``name``. Returns the number of rows
    inserted (existing rows are updated in place, not counted as newly "seeded")."""
    inserted = 0
    for template in STRUCTURE_TEMPLATES:
        existing = db.execute(
            select(StructureTemplate).where(StructureTemplate.name == template["name"])
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                StructureTemplate(
                    id=new_uuid(),
                    name=template["name"],
                    applicable_book_types=template["applicable_book_types"],
                    beats=template["beats"],
                )
            )
            inserted += 1
        else:
            existing.applicable_book_types = template["applicable_book_types"]
            existing.beats = template["beats"]
    db.commit()
    return inserted
