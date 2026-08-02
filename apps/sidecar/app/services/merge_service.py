"""AI-assisted multi-scene merge — the core write for Workstream B task 10 (PHASE11.md).

Kept as its own module rather than folded into ``canvas_service.py``: a merge is not
fundamentally "a canvas positioning operation" — it creates a ``Scene``, its first
``SceneRevision``, one ``SceneMerge`` row per absorbed source, and an ``UndoLog`` entry,
archiving (never hard-deleting) each source's ``BookSceneLink`` along the way. The canvas
midpoint position is the LAST and smallest step of that write, not what defines it.
``canvas_service`` stays scoped to per-Book layout/edges exactly as its own module
docstring already frames it; this module is the multi-table writer, built with the same
data-integrity posture ``bundle_import.py`` uses per CLAUDE.md (reviewer-gated after
landing — a bad merge can corrupt canvas/scene data).

``accept_merge`` does everything in ONE transaction:

1. Validate every ``source_scene_id`` exists AND has a non-archived ``BookSceneLink`` on
   ``book_id`` — raises before any write happens, so a bad id leaves nothing committed.
2. Create the new merged ``Scene``.
3. Write its ``SceneRevision`` #1 (``change_source='ai_merge'``) — since there is no prior
   state for a brand-new node, revision 1 holds the scene's content AS OF this commit
   (right after creation), not a pre-image, consistent with "revision N is what the scene
   looked like once revision N had been applied."
4. Write one ``SceneMerge`` row per source, freezing each source's CURRENT title/description
   — read before step 5 archives anything.
5. Archive (set ``archived_at``, never delete) each source's ``BookSceneLink`` for this book.
6. Create a new, non-archived ``BookSceneLink`` for the merged scene at the midpoint of the
   sources' (just-archived) canvas positions.
7. Write one ``UndoLog`` row with everything ``undo_service`` needs to reverse steps 2-6.

Sentinel ``ValueError`` strings match the rest of the service layer (see
``outline_service.py`` / ``prompt_builder.build_merge_prompt``): ``"BOOK_NOT_FOUND"``,
``"SOURCE_SCENES_REQUIRED"`` (empty list), ``"SCENE_NOT_FOUND"`` (an id isn't any Scene at
all), ``"SCENE_NOT_IN_BOOK"`` (it IS a Scene but has no active — non-archived —
``BookSceneLink`` on this Book, so there's nothing on this canvas to merge/archive).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import new_uuid, utcnow_iso
from app.models.orm import Book, BookSceneLink, Scene, SceneMerge, SceneRevision, UndoLog
from app.services import search_index_service, undo_service
from app.services.scene_service import _row_to_dict, _word_count


def accept_merge(
    db: Session,
    *,
    book_id: str,
    source_scene_ids: list[str],
    merged_title: str,
    merged_description: str,
) -> Scene:
    if db.get(Book, book_id) is None:
        raise ValueError("BOOK_NOT_FOUND")
    if not source_scene_ids:
        raise ValueError("SOURCE_SCENES_REQUIRED")

    # De-dup while preserving first-seen order — merging the same source id twice would
    # otherwise double-write its SceneMerge row and try to archive the same link twice.
    unique_source_ids = list(dict.fromkeys(source_scene_ids))

    # ── Step 1: validate every source BEFORE any write happens. Nothing is added to the
    # session in this loop, so a bad id here leaves the transaction with nothing to roll
    # back — a fresh query after a caught exception sees zero new rows. Also captures each
    # source's CURRENT (pre-archive) BookSceneLink and Scene here, since steps 4/7 need the
    # exact pre-merge snapshot and step 5 mutates these same link rows in place.
    source_scenes: dict[str, Scene] = {}
    source_links: dict[str, BookSceneLink] = {}
    for scene_id in unique_source_ids:
        scene = db.get(Scene, scene_id)
        if scene is None:
            raise ValueError("SCENE_NOT_FOUND")
        link = db.execute(
            select(BookSceneLink).where(
                BookSceneLink.book_id == book_id,
                BookSceneLink.scene_id == scene_id,
                BookSceneLink.archived_at.is_(None),
            )
        ).scalar_one_or_none()
        if link is None:
            raise ValueError("SCENE_NOT_IN_BOOK")
        source_scenes[scene_id] = scene
        source_links[scene_id] = link

    # Frozen snapshot of each source's link row EXACTLY as it is right now, for the
    # UndoLog payload — taken before step 5 archives anything.
    original_link_snapshots = {
        scene_id: _row_to_dict(source_links[scene_id]) for scene_id in unique_source_ids
    }

    # ── Step 2: create the new merged Scene. ``node_type`` defaults to 'scene' — a merge
    # produces a prose narrative node regardless of what node_type its sources were.
    merged_scene = Scene(
        id=new_uuid(),
        node_type="scene",
        title=merged_title,
        description=merged_description,
        word_count=_word_count(merged_description),
    )
    db.add(merged_scene)
    # Flush now so merged_scene.id exists for the FKs added below (SceneRevision, SceneMerge,
    # BookSceneLink) — SQLite enforces FKs immediately (PRAGMA foreign_keys=ON).
    db.flush()

    # ── Step 3: revision 1 — the scene's content as of this commit (there is no pre-image;
    # this node didn't exist a moment ago).
    db.add(
        SceneRevision(
            id=new_uuid(),
            scene_id=merged_scene.id,
            revision_number=1,
            title=merged_title,
            description=merged_description,
            status=merged_scene.status,
            change_source="ai_merge",
            parent_revision_id=None,
            created_at=utcnow_iso(),
        )
    )

    # ── Step 4: one SceneMerge row per source, using the snapshot taken in step 1 (still
    # the sources' live values — nothing has archived/changed them yet).
    for scene_id in unique_source_ids:
        source_scene = source_scenes[scene_id]
        db.add(
            SceneMerge(
                id=new_uuid(),
                merged_scene_id=merged_scene.id,
                source_scene_id=scene_id,
                source_snapshot_title=source_scene.title,
                source_snapshot_description=source_scene.description,
                created_at=utcnow_iso(),
            )
        )

    # ── Step 5: archive (never hard-delete) each source's BookSceneLink for this book. The
    # Scene rows themselves are untouched — a merge must always be reversible.
    archive_ts = utcnow_iso()
    for scene_id in unique_source_ids:
        source_links[scene_id].archived_at = archive_ts

    # ── Step 6: new node's canvas position = midpoint of the sources' positions (computed
    # from the pre-archive snapshot, same values the now-archived rows still hold).
    snapshots = original_link_snapshots.values()
    xs = [snap["canvas_x"] for snap in snapshots if snap["canvas_x"] is not None]
    ys = [snap["canvas_y"] for snap in snapshots if snap["canvas_y"] is not None]
    midpoint_x = sum(xs) / len(xs) if xs else None
    midpoint_y = sum(ys) / len(ys) if ys else None
    db.add(
        BookSceneLink(
            id=new_uuid(),
            book_id=book_id,
            scene_id=merged_scene.id,
            canvas_x=midpoint_x,
            canvas_y=midpoint_y,
            added_at=utcnow_iso(),
        )
    )

    # ── Step 7: UndoLog — enough to reverse steps 2-6. The merged Scene/SceneRevision/
    # SceneMerge rows are never deleted by undo (see undo_service._restore_merge_scenes), so
    # only the merged scene's id (to find/archive its link) and each source's ORIGINAL
    # (pre-archive) link snapshot (to restore archived_at/position exactly) are needed.
    undo_payload = {
        "merged_scene_id": merged_scene.id,
        "sources": [
            {"scene_id": scene_id, "book_scene_link": original_link_snapshots[scene_id]}
            for scene_id in unique_source_ids
        ],
    }
    db.add(
        UndoLog(
            id=new_uuid(),
            book_id=book_id,
            action_type="merge_scenes",
            payload=undo_payload,
            created_at=utcnow_iso(),
            sequence=undo_service.next_sequence(db),
        )
    )

    db.commit()
    db.refresh(merged_scene)
    # Embed-on-save (Phase 10 task 3) — the merged scene is a brand-new Scene row and needs
    # indexing exactly like create_scene's.
    search_index_service.upsert_entity(
        "scene", merged_scene.id, merged_scene.title, merged_scene.description
    )
    return merged_scene
