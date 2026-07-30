"""entity_images.order_index

PHASE-UI-EFFECTS-2.md §4 (B2) / §5 task 2: adds a nullable ``order_index`` column to
``entity_images`` (app/models/orm.py `EntityImage`) so a user can explicitly pick which
attached image is the "cover" (``order_index = 0``) and control the thumbnail-strip order,
instead of the current implicit ``created_at DESC, id DESC`` attachment-recency ordering.

Additive-only: a plain nullable ``Integer`` column, no default, no data migration. Every
existing row gets ``NULL`` on upgrade, which is exactly the "no explicit order" state —
``entity_images_service.list_for_entity``'s ``ORDER BY`` is updated (same commit) to sort
NULL rows after any non-NULL ones and fall back to the original ``created_at DESC, id DESC``
among rows sharing the same order_index-null-ness, so behavior for all pre-existing data is
unchanged until a user actually reorders.

Uses ``batch_alter_table`` for the add/drop, matching this repo's other simple additive
column migrations (e.g. ``21b2ddd10525``'s ``writing_sessions.user_id`` add).

Revision ID: f3a8b1c9d2e4
Revises: e51867fcdc66
Create Date: 2026-07-30
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3a8b1c9d2e4'
down_revision: str | None = 'e51867fcdc66'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('entity_images', schema=None) as batch_op:
        batch_op.add_column(sa.Column('order_index', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('entity_images', schema=None) as batch_op:
        batch_op.drop_column('order_index')
