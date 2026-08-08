"""widen undo_log.action_type check for canvas edge actions

Canvas undo/redo coverage is being extended from scenes/merges only
(`'delete_scene'`/`'merge_scenes'`, added in `b8e2f4a71c9d`) to also cover canvas edges:
`'create_edge'`, `'delete_edge'`, `'update_edge'`. This widens the `ck_undo_log_action_type`
CHECK constraint to allow all five values; no existing row (which can only be
`'delete_scene'`/`'merge_scenes'` today) is affected, so the upgrade is lossless — same
"widen a CHECK, rebuild via batch_alter_table" shape as `d25598084db3` (continuity_flags.source).

SQLite cannot ALTER a CHECK constraint in place, so this rebuilds `undo_log` via
`op.batch_alter_table(..., recreate='always')` — every other column, the `sequence`
tiebreaker (added in `c4c1f0a29f3a`), and the `book_id` foreign key are preserved verbatim;
only the `action_type` CHECK's allowed value set changes.

Revision ID: 9694678ecc85
Revises: c4c1f0a29f3a
Create Date: 2026-08-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9694678ecc85'
down_revision: str | None = 'c4c1f0a29f3a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('undo_log', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(op.f('ck_undo_log_action_type'), type_='check')
        batch_op.create_check_constraint(
            op.f('ck_undo_log_action_type'),
            "action_type IN ('delete_scene','merge_scenes','create_edge','delete_edge','update_edge')",
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Narrowing back to ('delete_scene','merge_scenes') is only lossless if no edge-action
    # rows exist. Normal flow up to this revision never wrote the three edge action types
    # (this migration is what introduces them), so this is a no-op in practice — but if a
    # downgrade is ever run after edge-undo entries have actually been logged, those rows
    # would violate the narrower CHECK once the table is rebuilt. Rather than let
    # batch_alter_table's rebuild raise on a dirty table (or silently corrupt the
    # constraint), we explicitly delete only the rows that would no longer be valid; every
    # 'delete_scene'/'merge_scenes' row is untouched and unaffected — following the same
    # precedent as `d25598084db3`'s downgrade (continuity_flags.source).
    bind.execute(
        sa.text(
            "DELETE FROM undo_log WHERE action_type IN "
            "('create_edge','delete_edge','update_edge')"
        )
    )

    with op.batch_alter_table('undo_log', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(op.f('ck_undo_log_action_type'), type_='check')
        batch_op.create_check_constraint(
            op.f('ck_undo_log_action_type'),
            "action_type IN ('delete_scene','merge_scenes')",
        )
