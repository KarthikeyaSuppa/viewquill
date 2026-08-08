"""notes (LAN LWW scratch-note)

New `notes` table (app/models/orm.py `Note`) — one singleton row per `channel` (e.g.
`'lan'`) holding a shared scratch-note, resolved last-write-wins on the caller-supplied
`updated_at` epoch-millisecond clock (see app/services/notes_service.py's `apply_note`).
Purely additive: no existing table is touched.

Revision ID: b1f4a6e9d3c7
Revises: 9694678ecc85
Create Date: 2026-08-09
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1f4a6e9d3c7'
down_revision: str | None = '9694678ecc85'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'notes',
        sa.Column('channel', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Integer(), nullable=False),
        sa.Column('updated_by', sa.String(), nullable=False),
        sa.Column('rev', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('channel', name=op.f('pk_notes')),
    )


def downgrade() -> None:
    op.drop_table('notes')
