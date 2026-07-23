"""profiles and per-user settings

Adds local profiles (a UI/profile LOCK, NOT encryption — the SQLite database stays
plaintext on disk; see app/services/password_service.py) and reshapes `app_settings`
from a bare key->value table into a per-user-or-global table, so a later task can thread
per-user scoping through the settings endpoints without another schema change.

`app_settings` cannot be reshaped with a simple ALTER on SQLite (its primary key is
changing from `key` to a new `id` column), so this migration rebuilds it via a
create-new/copy/drop/rename sequence rather than `batch_alter_table`. Every existing row
is preserved: each gets a freshly generated `id` and `user_id = NULL` (i.e. it stays a
global setting), with its `key`/`value` untouched. Two partial unique indexes then
enforce "at most one row per key" within each scope (global, and per-user).

Revision ID: 21b2ddd10525
Revises: 9cc2ce21fa1e
Create Date: 2026-07-22
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21b2ddd10525'
down_revision: Union[str, None] = '9cc2ce21fa1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. New `users` table — local profiles.
    #    Username uniqueness is enforced case-insensitively via a `COLLATE NOCASE` unique
    #    index (not a plain UniqueConstraint) so "Alice" and "alice" can never both exist
    #    — this matches app/models/orm.py's `User.__table_args__` and backstops
    #    profiles_service's own case-insensitive check even under a threadpool race.
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('avatar', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('is_active', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    )
    op.create_index(
        'uq_users_username', 'users', [sa.text('username COLLATE NOCASE')], unique=True,
    )

    # 2. Rebuild `app_settings`: (key PK, value) -> (id PK, user_id, key, value).
    #    SQLite can't change a primary key column via ALTER, so: create the new shape
    #    under a temp name, copy every existing row across (new uuid id, user_id=NULL,
    #    key/value preserved verbatim), drop the old table, rename the new one into place.
    op.create_table(
        'app_settings_new',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_app_settings_user_id_users'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_app_settings')),
    )

    # Untyped column handles for the copy so the raw stored JSON text is passed straight
    # through (no re-encode/double-encode via the typed JSON column).
    app_settings_new = sa.table(
        'app_settings_new',
        sa.column('id'), sa.column('user_id'), sa.column('key'), sa.column('value'),
    )
    existing_rows = bind.execute(sa.text('SELECT key, value FROM app_settings')).fetchall()
    for row in existing_rows:
        bind.execute(
            app_settings_new.insert().values(
                id=str(uuid.uuid4()), user_id=None, key=row.key, value=row.value
            )
        )

    op.drop_table('app_settings')
    op.rename_table('app_settings_new', 'app_settings')

    # Partial unique indexes: at most one row per key per scope.
    op.create_index(
        'uq_app_settings_user_key', 'app_settings', ['user_id', 'key'],
        unique=True, sqlite_where=sa.text('user_id IS NOT NULL'),
    )
    op.create_index(
        'uq_app_settings_global_key', 'app_settings', ['key'],
        unique=True, sqlite_where=sa.text('user_id IS NULL'),
    )

    # 3. `writing_sessions.user_id` — nullable, SET NULL if the profile is deleted.
    with op.batch_alter_table('writing_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.String(), nullable=True))
        batch_op.create_foreign_key(
            op.f('fk_writing_sessions_user_id_users'), 'users', ['user_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    bind = op.get_bind()

    # 3. Drop writing_sessions.user_id first — it references `users`.
    with op.batch_alter_table('writing_sessions', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_writing_sessions_user_id_users'), type_='foreignkey')
        batch_op.drop_column('user_id')

    # 2. Revert app_settings to (key PK, value). Only global (`user_id IS NULL`) rows
    #    can round-trip into the old shape — the old schema has no per-user concept.
    #    Fresh databases (or ones that never used per-user settings, i.e. every task up
    #    to and including this one) have no non-global rows, so this is lossless for the
    #    current codebase; it is a documented limitation of downgrading once per-user
    #    settings rows exist.
    op.create_table(
        'app_settings_old',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('key', name=op.f('pk_app_settings')),
    )
    app_settings_old = sa.table('app_settings_old', sa.column('key'), sa.column('value'))
    global_rows = bind.execute(
        sa.text('SELECT key, value FROM app_settings WHERE user_id IS NULL')
    ).fetchall()
    for row in global_rows:
        bind.execute(app_settings_old.insert().values(key=row.key, value=row.value))

    op.drop_table('app_settings')
    op.rename_table('app_settings_old', 'app_settings')

    # 1. Finally, drop `users` — nothing references it anymore. Dropping the table also
    #    drops its `uq_users_username` COLLATE NOCASE index, so no separate index-drop
    #    is needed (same pattern as `app_settings`'s partial unique indexes above).
    op.drop_table('users')
