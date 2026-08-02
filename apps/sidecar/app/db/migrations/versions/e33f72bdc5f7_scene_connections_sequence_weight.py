"""scene_connections.sequence_weight

Workstream B: history/merge/undo, task 3. Adds a nullable ``sequence_weight`` column to
``scene_connections`` (app/models/orm.py `SceneConnection`) — a pure rendering/sort hint so
the canvas can later distinguish "this edge represents lineage/sequence" from arbitrary
free-form connections, without introducing a new ordering system (chronological order stays
in ``book_scene_order``/`BookSceneOrder`, unrelated).

Additive-only: a plain nullable ``Integer`` column, no default, no data migration. Every
existing row gets ``NULL`` on upgrade, meaning "not part of the lineage view" — the correct
state for all pre-existing edges. Schema/API/service layers are intentionally not touched in
this task; a later task wires the frontend to actually set this field.

Uses ``batch_alter_table`` for the add/drop, matching this repo's other simple additive
column migrations (e.g. ``f3a8b1c9d2e4``'s ``entity_images.order_index`` add).

Revision ID: e33f72bdc5f7
Revises: b8e2f4a71c9d
Create Date: 2026-07-30
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e33f72bdc5f7'
down_revision: str | None = 'b8e2f4a71c9d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('scene_connections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sequence_weight', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scene_connections', schema=None) as batch_op:
        batch_op.drop_column('sequence_weight')
