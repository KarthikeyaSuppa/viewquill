"""Canvas templates: seed a Book's Node Canvas with a starter graph (docs/14-DEFERRED
-ENHANCEMENTS.md "Canvas templates", Phase 9).

DATA-SENSITIVE / additive-only: this is deliberately a *different* system from
``structure_templates.py``/``book_scene_order`` (the Outline/beat-board tab's
pre-seeded beat rows) — applying a canvas template here creates brand-new, real
``Scene`` rows, links them onto the Book's canvas (``book_scene_links``) with a laid-out
``canvas_x``/``canvas_y`` position, and connects them in order via real
``scene_connections`` edges, using the exact same ``canvas_service`` helpers the
hand-built canvas UI uses (``add_scene_to_canvas`` / ``create_edge``). It never touches
``book_scene_order`` or the Outline tab's beats at all.

Guardrail: ``apply_template`` refuses (raises ``TemplateAlreadyAppliedError``) if the
Book's canvas already has any nodes on it — this only ever populates a genuinely blank
canvas, never interleaves into an existing graph.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.orm import BookSceneLink
from app.models.schemas import CanvasResponse
from app.services import canvas_service, scene_service

# Horizontal spacing between seeded nodes, and a fixed row height — a simple, readable
# left-to-right layout rather than anything fancier (no existing canvas layout algorithm
# to match; ``canvas_x``/``canvas_y`` are the only position columns ``BookSceneLink``
# already has, per ``models/orm.py``).
_NODE_SPACING_X = 260.0
_NODE_Y = 120.0


class TemplateAlreadyAppliedError(Exception):
    """Raised when a template is applied to a Book whose canvas already has nodes."""


class UnknownCanvasTemplateError(Exception):
    """Raised when ``template_key`` doesn't match a known template."""


# Each entry is a short list of (title, description) beat placeholders, in sequential
# order — the order they'll be laid out left-to-right and connected by edges.
CANVAS_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "three_act": [
        ("Act I — Setup", "Introduce the protagonist, world, and the inciting incident."),
        (
            "Act II — Confrontation",
            "Rising complications, midpoint turn, and the all-is-lost moment.",
        ),
        ("Act III — Resolution", "Climax and resolution of the central conflict."),
    ],
    "heros_journey": [
        ("Ordinary World", "The hero's normal life before the adventure begins."),
        ("Call to Adventure", "A challenge or quest is presented."),
        ("Refusal of the Call", "The hero hesitates, fearing the unknown."),
        ("Meeting the Mentor", "The hero gains guidance or gifts from a wise figure."),
        ("Crossing the Threshold", "The hero commits and leaves the ordinary world."),
        ("Tests, Allies, Enemies", "The hero faces trials and forms key relationships."),
        ("Approach to the Inmost Cave", "Preparation for the central ordeal."),
        ("Ordeal", "The hero faces their greatest fear or crisis."),
        ("Reward (Seizing the Sword)", "The hero claims the goal of the quest."),
        ("The Road Back", "The hero commits to finishing, pursued by consequences."),
        ("Resurrection", "A final, climactic test where the hero is transformed."),
        ("Return with the Elixir", "The hero returns home changed, bringing something of value."),
    ],
}


TEMPLATE_LABELS: dict[str, str] = {
    "three_act": "Three-Act Structure",
    "heros_journey": "Hero's Journey",
}


def _canvas_has_nodes(db: Session, book_id: str) -> bool:
    return (
        db.query(BookSceneLink.id).filter(BookSceneLink.book_id == book_id).first() is not None
    )


def apply_template(db: Session, book_id: str, template_key: str) -> CanvasResponse:
    """Seed ``book_id``'s canvas with the named template's Scenes + sequential edges.

    Raises ``UnknownCanvasTemplateError`` for an unrecognized ``template_key`` and
    ``TemplateAlreadyAppliedError`` if the Book's canvas already has any nodes — this
    function only ever populates a blank canvas, never merges into an existing one.
    """
    beats = CANVAS_TEMPLATES.get(template_key)
    if beats is None:
        raise UnknownCanvasTemplateError(f"Unknown canvas template: {template_key!r}")

    if _canvas_has_nodes(db, book_id):
        raise TemplateAlreadyAppliedError(
            "This Book's canvas already has nodes — canvas templates only apply to a "
            "blank canvas."
        )

    scene_ids: list[str] = []
    for index, (title, description) in enumerate(beats):
        scene = scene_service.create_scene(
            db, node_type="scene", title=title, description=description
        )
        canvas_service.add_scene_to_canvas(
            db,
            book_id,
            scene.id,
            canvas_x=index * _NODE_SPACING_X,
            canvas_y=_NODE_Y,
        )
        scene_ids.append(scene.id)

    for source_id, target_id in zip(scene_ids, scene_ids[1:], strict=False):
        canvas_service.create_edge(
            db,
            book_id,
            source_scene_id=source_id,
            target_scene_id=target_id,
            connection_type="sequence",
        )

    return canvas_service.get_canvas(db, book_id)
