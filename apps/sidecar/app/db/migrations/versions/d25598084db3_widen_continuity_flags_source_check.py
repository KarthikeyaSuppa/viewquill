"""widen continuity_flags source check

`docs/11-AI-INTELLIGENCE.md` §4 requires Tier-1 deterministic continuity checks to be stored with
`continuity_flags.source = 'deterministic'`, but the original CHECK constraint
(`ck_continuity_flags_source`, from the initial schema migration `9cc2ce21fa1e`) only
allowed `'ai'` or `'manual'`. This widens it to `'deterministic'`, `'ai'`, `'manual'`.

SQLite cannot ALTER a CHECK constraint in place, so this rebuilds `continuity_flags` via
`op.batch_alter_table(..., recreate="always")` — every other column, the other three CHECK
constraints (flag_type/severity/status), and both foreign keys (to `scenes`/`codex_entries`,
plus the CASCADE one to `books`) are preserved verbatim; only the `source` CHECK's allowed
value set changes. All existing rows (which can only be `'ai'` or `'manual'` today) already
satisfy the wider check, so this upgrade is lossless.

Revision ID: d25598084db3
Revises: 21b2ddd10525
Create Date: 2026-07-24
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd25598084db3'
down_revision: Union[str, None] = '21b2ddd10525'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('continuity_flags', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(op.f('ck_continuity_flags_source'), type_='check')
        batch_op.create_check_constraint(
            op.f('ck_continuity_flags_source'), "source IN ('deterministic','ai','manual')"
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Narrowing back to ('ai','manual') is only lossless if no 'deterministic' rows exist.
    # Normal flow up to this revision never wrote 'deterministic' (this migration is what
    # introduces it), so this is a no-op in practice — but if a downgrade is ever run after
    # deterministic flags have actually been created, those rows would violate the narrower
    # CHECK once the table is rebuilt. Rather than let batch_alter_table's rebuild raise on a
    # dirty table (or silently corrupt the constraint), we explicitly delete only the rows
    # that would no longer be valid; every 'ai'/'manual' row is untouched and unaffected.
    bind.execute(sa.text("DELETE FROM continuity_flags WHERE source = 'deterministic'"))

    with op.batch_alter_table('continuity_flags', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(op.f('ck_continuity_flags_source'), type_='check')
        batch_op.create_check_constraint(
            op.f('ck_continuity_flags_source'), "source IN ('ai','manual')"
        )
