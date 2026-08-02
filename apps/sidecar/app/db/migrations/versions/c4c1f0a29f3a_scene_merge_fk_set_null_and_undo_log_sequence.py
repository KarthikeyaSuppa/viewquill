"""scene_merges FK to SET NULL + undo_log.sequence tiebreaker (Opus reviewer MUST-FIX 1 +
SHOULD-FIX, PHASE11.md Workstream B merge/undo audit)

Two independent fixes landed together since both touch this same audit pass:

1. ``scene_merges.merged_scene_id`` / ``scene_merges.source_scene_id`` were
   ``ondelete='CASCADE'`` — but ``SceneMerge``'s own docstring (app/models/orm.py) says its
   frozen snapshot columns (``source_snapshot_title``/``source_snapshot_description``) exist
   so the merge record "remains inspectable even if the source Scene is later
   hard-deleted." CASCADE contradicted that: hard-deleting a source Scene via the ordinary
   ``DELETE /scenes/{id}`` path (untouched/allowed — sources are meant to survive a merge as
   ordinary scenes) also deleted the ``SceneMerge`` row recording it, destroying exactly the
   data the docstring promises survives. The same issue applies symmetrically to
   ``merged_scene_id`` — hard-deleting the merged scene itself would erase the same history.
   Both FKs are changed to ``ondelete='SET NULL'`` (and made nullable), mirroring
   ``scene_revisions.parent_revision_id``'s existing self-referential ``SET NULL`` pattern
   (``a7c4e91f3b6d``) — a hard-delete on either side now just detaches the reference,
   leaving the ``SceneMerge`` row (and its frozen snapshot) intact.

   SQLite doesn't support ``ALTER TABLE`` for foreign-key constraints in place, so this uses
   ``batch_alter_table(..., recreate='always')`` — a full table rebuild — exactly as
   ``alembic``'s SQLite dialect requires for any FK change (no prior migration in this repo
   has altered an existing FK's `ondelete`; every previous FK-bearing migration only
   ever *created* new tables/columns with the FK already correct, e.g. ``a7c4e91f3b6d``,
   ``b8e2f4a71c9d``).

2. ``undo_log.sequence`` — a plain (non-primary-key) autoincrementing-in-spirit integer
   tiebreaker for ``undo_service``'s ``created_at DESC`` ordering. ``utcnow_iso()`` only has
   1-second resolution, so two actions logged in the same second were otherwise ambiguously
   ordered; ``undo_log.id`` is a uuid4 string (not creation-ordered), so it can't serve as
   the tiebreaker. Populated in Python at insert time (``undo_service.next_sequence`` —
   compute current max + 1), the same pattern ``scene_service.py`` already uses for
   ``scene_revisions.revision_number``, since SQLite `AUTOINCREMENT` only applies to a
   table's single `INTEGER PRIMARY KEY` rowid alias (``undo_log.id`` is a text uuid, so
   that's not available here). Added as nullable first, backfilled for any pre-existing
   rows (ordered by ``created_at`` then ``id`` as a stable-but-arbitrary tiebreaker for rows
   that predate this column and therefore have no better ordering signal), then tightened
   to ``NOT NULL``.

Revision ID: c4c1f0a29f3a
Revises: e33f72bdc5f7
Create Date: 2026-07-30
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4c1f0a29f3a'
down_revision: str | None = 'e33f72bdc5f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. scene_merges FKs: CASCADE -> SET NULL (+ nullable) ────────────────────────────
    with op.batch_alter_table('scene_merges', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('merged_scene_id', existing_type=sa.String(), nullable=True)
        batch_op.alter_column('source_scene_id', existing_type=sa.String(), nullable=True)
        batch_op.drop_constraint('fk_scene_merges_merged_scene_id_scenes', type_='foreignkey')
        batch_op.drop_constraint('fk_scene_merges_source_scene_id_scenes', type_='foreignkey')
        batch_op.create_foreign_key(
            batch_op.f('fk_scene_merges_merged_scene_id_scenes'),
            'scenes', ['merged_scene_id'], ['id'], ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            batch_op.f('fk_scene_merges_source_scene_id_scenes'),
            'scenes', ['source_scene_id'], ['id'], ondelete='SET NULL',
        )

    # ── 2. undo_log.sequence: add nullable, backfill, then tighten to NOT NULL ───────────
    with op.batch_alter_table('undo_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sequence', sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE undo_log
        SET sequence = (
            SELECT COUNT(*) FROM undo_log AS earlier
            WHERE earlier.created_at < undo_log.created_at
               OR (earlier.created_at = undo_log.created_at AND earlier.id <= undo_log.id)
        )
        """
    )

    with op.batch_alter_table('undo_log', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('sequence', existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('undo_log', schema=None, recreate='always') as batch_op:
        batch_op.drop_column('sequence')

    with op.batch_alter_table('scene_merges', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint('fk_scene_merges_merged_scene_id_scenes', type_='foreignkey')
        batch_op.drop_constraint('fk_scene_merges_source_scene_id_scenes', type_='foreignkey')
        batch_op.create_foreign_key(
            batch_op.f('fk_scene_merges_merged_scene_id_scenes'),
            'scenes', ['merged_scene_id'], ['id'], ondelete='CASCADE',
        )
        batch_op.create_foreign_key(
            batch_op.f('fk_scene_merges_source_scene_id_scenes'),
            'scenes', ['source_scene_id'], ['id'], ondelete='CASCADE',
        )
        batch_op.alter_column('merged_scene_id', existing_type=sa.String(), nullable=False)
        batch_op.alter_column('source_scene_id', existing_type=sa.String(), nullable=False)
