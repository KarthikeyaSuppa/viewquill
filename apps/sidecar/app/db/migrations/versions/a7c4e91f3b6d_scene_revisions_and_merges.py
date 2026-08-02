"""scene_revisions and scene_merges (Workstream B: history/merge/undo, task 1)

Adds two purely additive, append-only tables backing the new git-like scene history
subsystem (app/models/orm.py `SceneRevision` / `SceneMerge`):

* ``scene_revisions`` — one row per "commit" of a Scene's title/description/status,
  self-referencing ``parent_revision_id`` (``ON DELETE SET NULL``) to chain history
  without cascading a whole branch away if an ancestor is pruned.
* ``scene_merges`` — one row per source Scene absorbed into a merged Scene (N:1 with
  the resulting scene), with frozen snapshot columns so the merge stays inspectable
  even after a hard-delete of the source.

No existing table is touched.

Revision ID: a7c4e91f3b6d
Revises: f3a8b1c9d2e4
Create Date: 2026-07-30
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c4e91f3b6d'
down_revision: str | None = 'f3a8b1c9d2e4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'scene_revisions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('scene_id', sa.String(), nullable=False),
        sa.Column('revision_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('change_source', sa.String(), nullable=False),
        sa.Column('parent_revision_id', sa.String(), nullable=True),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.CheckConstraint(
            "change_source IN ('manual_edit','enhance_accept','ai_merge','restore')",
            name=op.f('ck_scene_revisions_change_source'),
        ),
        sa.ForeignKeyConstraint(
            ['scene_id'], ['scenes.id'],
            name=op.f('fk_scene_revisions_scene_id_scenes'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['parent_revision_id'], ['scene_revisions.id'],
            name=op.f('fk_scene_revisions_parent_revision_id_scene_revisions'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_scene_revisions')),
    )

    op.create_table(
        'scene_merges',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('merged_scene_id', sa.String(), nullable=False),
        sa.Column('source_scene_id', sa.String(), nullable=False),
        sa.Column('source_snapshot_title', sa.String(), nullable=False),
        sa.Column('source_snapshot_description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ['merged_scene_id'], ['scenes.id'],
            name=op.f('fk_scene_merges_merged_scene_id_scenes'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['source_scene_id'], ['scenes.id'],
            name=op.f('fk_scene_merges_source_scene_id_scenes'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_scene_merges')),
    )


def downgrade() -> None:
    op.drop_table('scene_merges')
    op.drop_table('scene_revisions')
