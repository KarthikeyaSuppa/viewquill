"""undo_log and book_scene_links.archived_at (Workstream B: history/merge/undo, task 2)

Adds:

* ``undo_log`` — one row per Book's last reversible destructive/AI action
  (app/models/orm.py `UndoLog`). ``action_type`` is CHECK-constrained to
  ``'delete_scene'``/``'merge_scenes'``; ``payload`` is a JSON blob holding
  whatever action-specific data is needed to reconstruct the prior state
  (e.g. the deleted scene row, or the absorbed source scenes/links); ``undone_at``
  is nullable and set once the entry has been consumed by an undo.
* ``book_scene_links.archived_at`` — nullable soft-delete marker so a scene can be
  unlinked from the canvas but still recoverable, instead of hard-deleting the
  link row. Purely additive: every existing row gets ``NULL`` (unarchived) on
  upgrade; no existing query logic is touched in this migration.

Uses ``batch_alter_table`` for the ``book_scene_links`` column add, matching this
repo's other simple additive column migrations (e.g. ``f3a8b1c9d2e4``'s
``entity_images.order_index``, ``21b2ddd10525``'s ``writing_sessions.user_id``).

Revision ID: b8e2f4a71c9d
Revises: a7c4e91f3b6d
Create Date: 2026-07-30
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8e2f4a71c9d'
down_revision: str | None = 'a7c4e91f3b6d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'undo_log',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('book_id', sa.String(), nullable=False),
        sa.Column('action_type', sa.String(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('undone_at', sa.String(), nullable=True),
        sa.CheckConstraint(
            "action_type IN ('delete_scene','merge_scenes')",
            name=op.f('ck_undo_log_action_type'),
        ),
        sa.ForeignKeyConstraint(
            ['book_id'], ['books.id'],
            name=op.f('fk_undo_log_book_id_books'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_undo_log')),
    )

    with op.batch_alter_table('book_scene_links', schema=None) as batch_op:
        batch_op.add_column(sa.Column('archived_at', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('book_scene_links', schema=None) as batch_op:
        batch_op.drop_column('archived_at')

    op.drop_table('undo_log')
