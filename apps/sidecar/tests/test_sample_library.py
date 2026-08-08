"""Tests for the Phase 14 sample-library seeder (``app.services.sample_library``,
PHASE14.md): ``seed_sample_library(db) -> int`` turns ``content.py``'s pure-data spec into
four demo Books' worth of real rows.

## Isolation strategy: (A) fully isolated engine, NOT the shared suite database

tests/conftest.py's module docstring explains that ``app.db.base`` builds ONE SQLAlchemy
``engine``/``SessionLocal`` at import time, from whichever settings won that race — every
``test_*.py`` module that imports ``app.main``/``app.db.base`` ends up sharing that one
SQLite database for the whole pytest session. ``seed_sample_library``'s own guard treats
"no marker AND no Books" as "fresh install, please seed", which is exactly the shared
suite database's starting state — that's precisely what broke
``test_bundle_import_inspect.py::test_inspect_empty_db_everything_created`` and the
migration round-trip tests once already (see conftest.py + ``seeder.py``'s module
docstring), and it's why conftest.py sets ``QUILLNIGHT_SKIP_SAMPLE_SEED=1`` for the whole
session.

This module needs to call the *real* seeder repeatedly (idempotency, deletion/no-
resurrection, the skip flag itself) against a database it fully controls, so instead of
using the shared engine at all, every test here builds its OWN throwaway SQLite file +
its own ``create_engine``/``sessionmaker``, runs Alembic against that file directly (a
``Config`` built the same way ``app.db.migrate.make_alembic_config`` does, just pointed at
our URL instead of the process-global one), and passes that isolated ``Session`` into
``seed_structure_templates``/``seed_sample_library`` — both take a plain ``Session`` and
never reach for the global engine themselves. That makes every assertion here provably
independent of collection order and of what any other test module does to the shared
database — nothing in this file ever touches it.

Two known, accepted exceptions to full isolation (per the task brief, not bugs):

* ``search_index_service.upsert_entity`` (called internally by
  ``scene_service.create_scene``/``codex_service.create_entry``) reaches for the
  process-global ``app.db.base.engine`` directly and swallows all errors — its writes land
  on whatever database that global engine points to, not ours. This module never asserts
  on ``search_fts``/``embeddings``.
* ``images_service.save_image`` writes real PNG bytes under the process-global
  ``get_settings().media_dir`` — not something this module controls either. A
  ``QUILLNIGHT_DATA_DIR`` fallback is set below (a ``setdefault``, so it never clobbers
  another already-collected module's choice) purely so that IF this module happens to be
  the first to import anything under ``app.*`` in a given test run, those files land in a
  throwaway temp directory rather than a real machine's AppData folder — the same safety
  net every other test module in this suite already applies.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Safety net only (see module docstring's second bullet) — does not by itself provide
# isolation from the shared suite database, which is what the per-test isolated engines
# below actually do.
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-sample-library-")
os.environ.setdefault("QUILLNIGHT_DATA_DIR", _TMP_DATA_DIR)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, event, func, select  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.models.orm import (  # noqa: E402
    AppSetting,
    Book,
    BookCodexLink,
    BookSceneLink,
    BookSceneOrder,
    Chapter,
    CodexArcState,
    CodexEntry,
    CodexRelationship,
    CodexSceneLink,
    ContinuityFlag,
    EntityImage,
    Image,
    ImageTag,
    Scene,
    SceneConnection,
    SceneMerge,
    SceneRevision,
    ScreenplayElement,
    StructureTemplate,
    UndoLog,
)
from app.services import book_service, images_service  # noqa: E402
from app.services.sample_library import seed_sample_library  # noqa: E402
from app.services.structure_templates import seed_structure_templates  # noqa: E402

# apps/sidecar/tests/test_sample_library.py -> parents[1] == apps/sidecar
_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "app" / "db" / "migrations"


def _isolated_alembic_config(db_url: str) -> Config:
    """Mirrors ``app.db.migrate.make_alembic_config`` exactly, except the URL is whatever
    the caller passes rather than the process-global ``get_settings().database_url`` — this
    is the one line that makes migrations land in our own throwaway file instead of the
    shared suite database."""
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _new_isolated_session(db_path: Path) -> tuple[Session, Engine]:
    """Migrates a brand-new SQLite file at ``db_path`` to head, then returns a bound
    ``Session`` + its ``Engine`` (caller is responsible for closing/disposing both).

    Mirrors ``app.db.base``'s own connection setup (``PRAGMA foreign_keys=ON``) so
    ``ON DELETE CASCADE`` behaves identically to production when a test deletes a Book.
    Deliberately does NOT load the ``sqlite-vec`` extension on this engine: the
    ``embeddings``/``search_fts`` virtual tables this migration set creates are only ever
    written to via the process-global engine (see module docstring), never through a
    session built here, so nothing on this engine ever touches them.
    """
    db_url = f"sqlite:///{db_path.as_posix()}"
    command.upgrade(_isolated_alembic_config(db_url), "head")

    engine = create_engine(db_url, connect_args={"check_same_thread": False}, future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fks(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory(), engine


@contextlib.contextmanager
def _sample_seed_enabled():
    """Temporarily clears ``QUILLNIGHT_SKIP_SAMPLE_SEED`` (set to ``"1"`` for the whole
    pytest session by tests/conftest.py) so calls inside this block exercise the real
    seeder, then restores whatever value — or absence — the variable had before. Read at
    CALL time by ``seed_sample_library`` (see its module docstring), so this is the
    documented, supported way for a test to opt back in without affecting any other
    module in the suite."""
    var = "QUILLNIGHT_SKIP_SAMPLE_SEED"
    previous = os.environ.pop(var, None)
    try:
        yield
    finally:
        if previous is not None:
            os.environ[var] = previous


# Every table the seeder writes to (plus SceneMerge/UndoLog, which it must NEVER write to)
# — used by the idempotency check to prove a second call adds/changes nothing anywhere.
_ALL_SEEDED_TABLES: tuple[type, ...] = (
    Book,
    Chapter,
    Scene,
    ScreenplayElement,
    BookSceneLink,
    SceneConnection,
    BookSceneOrder,
    CodexEntry,
    CodexRelationship,
    CodexArcState,
    BookCodexLink,
    CodexSceneLink,
    Image,
    ImageTag,
    EntityImage,
    ContinuityFlag,
    SceneRevision,
    SceneMerge,
    UndoLog,
    AppSetting,
)


def _row_counts(db: Session) -> dict[str, int]:
    return {
        model.__tablename__: db.execute(select(func.count()).select_from(model)).scalar_one()
        for model in _ALL_SEEDED_TABLES
    }


@dataclass
class SeededLibrary:
    db: Session
    engine: Engine
    first_seed_count: int
    second_seed_count: int
    counts_before_reseed: dict[str, int]
    counts_after_reseed: dict[str, int]


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> SeededLibrary:
    """One seeded sample library, shared read-only by every assertion test below except
    the ones that specifically exercise re-seeding-after-deletion or the skip flag — those
    build their own fresh isolated database instead, so they never disturb this one."""
    db_path = tmp_path_factory.mktemp("sample-library-seed") / "quillnight.sqlite"
    db, engine = _new_isolated_session(db_path)

    seed_structure_templates(db)
    with _sample_seed_enabled():
        first_seed_count = seed_sample_library(db)
    assert first_seed_count == 4

    counts_before_reseed = _row_counts(db)
    with _sample_seed_enabled():
        second_seed_count = seed_sample_library(db)
    counts_after_reseed = _row_counts(db)

    yield SeededLibrary(
        db=db,
        engine=engine,
        first_seed_count=first_seed_count,
        second_seed_count=second_seed_count,
        counts_before_reseed=counts_before_reseed,
        counts_after_reseed=counts_after_reseed,
    )
    db.close()
    engine.dispose()


# ── 1. Seeds 4 Books, one of every book_type ───────────────────────────────────────────
def test_seeds_four_books_covering_every_book_type(seeded: SeededLibrary) -> None:
    assert seeded.first_seed_count == 4
    book_types = seeded.db.execute(select(Book.book_type)).scalars().all()
    assert sorted(book_types) == sorted(
        ["story_book", "movie_script", "short_film_script", "single_scene"]
    )


# ── 2. Idempotent: second call returns 0 and adds/changes nothing anywhere ─────────────
def test_second_call_is_idempotent(seeded: SeededLibrary) -> None:
    assert seeded.second_seed_count == 0
    assert seeded.counts_after_reseed == seeded.counts_before_reseed


# ── 3. Marker shape ─────────────────────────────────────────────────────────────────────
def test_marker_records_version_seeded_at_and_matching_book_ids(seeded: SeededLibrary) -> None:
    marker = seeded.db.execute(
        select(AppSetting).where(AppSetting.user_id.is_(None), AppSetting.key == "sample_library")
    ).scalar_one()

    value = marker.value
    assert value["version"] == 1
    assert value["seeded_at"]  # non-empty ISO timestamp string

    book_ids = value["book_ids"]
    assert len(book_ids) == 4
    actual_book_ids = set(seeded.db.execute(select(Book.id)).scalars())
    assert set(book_ids) == actual_book_ids


# ── 4. No resurrection after deletion — the whole reason the marker exists ─────────────
def test_no_resurrection_after_deleting_all_books(tmp_path: Path) -> None:
    """Deletes all 4 seeded Books, then calls the seeder again on the SAME database: it
    must still return 0, proving the marker alone — not `books` being non-empty — is what
    blocks re-seeding. Uses its own isolated database (not the `seeded` fixture) because it
    deliberately destroys the library."""
    db_path = tmp_path / "quillnight.sqlite"
    db, engine = _new_isolated_session(db_path)
    try:
        seed_structure_templates(db)
        with _sample_seed_enabled():
            assert seed_sample_library(db) == 4

        book_ids = list(db.execute(select(Book.id)).scalars())
        assert len(book_ids) == 4
        for book_id in book_ids:
            assert book_service.delete_book(db, book_id) is True

        assert db.execute(select(func.count()).select_from(Book)).scalar_one() == 0

        with _sample_seed_enabled():
            assert seed_sample_library(db) == 0

        # Still empty — the marker blocked it; nothing resurrected.
        assert db.execute(select(func.count()).select_from(Book)).scalar_one() == 0
    finally:
        db.close()
        engine.dispose()


# ── 5. Skip flag honored ────────────────────────────────────────────────────────────────
def test_skip_env_var_honored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "quillnight.sqlite"
    db, engine = _new_isolated_session(db_path)
    try:
        monkeypatch.setenv("QUILLNIGHT_SKIP_SAMPLE_SEED", "1")
        assert seed_sample_library(db) == 0
        assert db.execute(select(func.count()).select_from(Book)).scalar_one() == 0
        assert db.execute(select(func.count()).select_from(AppSetting)).scalar_one() == 0
    finally:
        db.close()
        engine.dispose()


# ── 6. Zero UndoLog rows ────────────────────────────────────────────────────────────────
def test_seeding_writes_zero_undo_log_rows(seeded: SeededLibrary) -> None:
    # `SceneConnection` rows are written directly via the ORM (RULE 1 in seeder.py's module
    # docstring) rather than through `canvas_service.create_edge`, which also writes an
    # `UndoLog` row — using it here would arm a fresh install's canvas Undo button to
    # delete sample content the user never touched. A correct seed must leave zero
    # UndoLog rows behind.
    assert seeded.db.execute(select(func.count()).select_from(UndoLog)).scalar_one() == 0


# ── 7. Enum coverage — every legal value appears at least once ────────────────────────
_ENUM_COVERAGE_CASES: list[tuple[str, type, str, set]] = [
    ("scenes.node_type", Scene, "node_type", {"scene", "plot_point", "thought"}),
    ("scenes.status", Scene, "status", {"draft", "revised", "final"}),
    (
        "scene_connections.connection_type",
        SceneConnection,
        "connection_type",
        {"sequence", "causal", "reference", "contradiction", "custom", None},
    ),
    (
        "screenplay_elements.element_type",
        ScreenplayElement,
        "element_type",
        {
            "scene_heading",
            "action",
            "character",
            "dialogue",
            "parenthetical",
            "transition",
            "shot",
            "dual_dialogue",
        },
    ),
    (
        "codex_entries.entry_type",
        CodexEntry,
        "entry_type",
        {"character", "location", "faction", "object_lore"},
    ),
    ("images.bucket", Image, "bucket", {"finalized_scene", "reference_pool"}),
    ("entity_images.entity_type", EntityImage, "entity_type", {"book", "scene", "codex_entry"}),
    (
        "continuity_flags.flag_type",
        ContinuityFlag,
        "flag_type",
        {"early_appearance", "trait_contradiction", "timeline_conflict", "custom"},
    ),
    ("continuity_flags.severity", ContinuityFlag, "severity", {"critical", "warning", "hint"}),
    ("continuity_flags.status", ContinuityFlag, "status", {"open", "dismissed", "resolved"}),
    ("continuity_flags.source", ContinuityFlag, "source", {"deterministic", "ai", "manual"}),
    (
        "scene_revisions.change_source",
        SceneRevision,
        "change_source",
        {"manual_edit", "enhance_accept", "ai_merge", "restore"},
    ),
]


@pytest.mark.parametrize(
    "label,model,column_name,expected",
    _ENUM_COVERAGE_CASES,
    ids=[case[0] for case in _ENUM_COVERAGE_CASES],
)
def test_every_enum_value_is_represented_at_least_once(
    seeded: SeededLibrary, label: str, model: type, column_name: str, expected: set
) -> None:
    column = getattr(model, column_name)
    actual = set(seeded.db.execute(select(column)).scalars())
    missing = expected - actual
    assert not missing, f"{label} is missing values: {missing}"


# ── 8. Structural edge cases ────────────────────────────────────────────────────────────
def test_one_scene_is_linked_to_two_books_at_different_canvas_positions(
    seeded: SeededLibrary,
) -> None:
    shared_scene_ids = seeded.db.execute(
        select(BookSceneLink.scene_id)
        .group_by(BookSceneLink.scene_id)
        .having(func.count(BookSceneLink.id) > 1)
    ).scalars().all()
    assert shared_scene_ids, "expected at least one Scene linked to more than one Book"

    links = seeded.db.execute(
        select(BookSceneLink).where(BookSceneLink.scene_id == shared_scene_ids[0])
    ).scalars().all()
    assert len(links) >= 2
    positions = {(link.canvas_x, link.canvas_y) for link in links}
    assert len(positions) == len(links), "expected each placement to sit at a distinct position"


def test_one_codex_entry_is_linked_to_two_books(seeded: SeededLibrary) -> None:
    shared_entry_ids = seeded.db.execute(
        select(BookCodexLink.codex_entry_id)
        .group_by(BookCodexLink.codex_entry_id)
        .having(func.count(BookCodexLink.id) > 1)
    ).scalars().all()
    assert shared_entry_ids, "expected at least one CodexEntry cast in more than one Book"


def test_at_least_one_canvas_link_is_archived(seeded: SeededLibrary) -> None:
    archived_count = seeded.db.execute(
        select(func.count())
        .select_from(BookSceneLink)
        .where(BookSceneLink.archived_at.is_not(None))
    ).scalar_one()
    assert archived_count >= 1


def test_at_least_one_book_has_zero_chapters(seeded: SeededLibrary) -> None:
    all_book_ids = set(seeded.db.execute(select(Book.id)).scalars())
    book_ids_with_chapters = set(seeded.db.execute(select(Chapter.book_id)).scalars())
    assert all_book_ids - book_ids_with_chapters


def test_some_book_has_a_flashback_outline_vs_timeline_mismatch(seeded: SeededLibrary) -> None:
    book_ids = seeded.db.execute(select(Book.id)).scalars().all()
    for book_id in book_ids:
        rows = seeded.db.execute(
            select(
                BookSceneOrder.scene_id,
                BookSceneOrder.outline_order_index,
                BookSceneOrder.timeline_order_index,
            ).where(BookSceneOrder.book_id == book_id)
        ).all()
        if len(rows) < 2:
            continue
        by_outline = [row.scene_id for row in sorted(rows, key=lambda r: r.outline_order_index)]
        by_timeline = [
            row.scene_id
            for row in sorted(
                rows, key=lambda r: (r.timeline_order_index is None, r.timeline_order_index)
            )
        ]
        if by_outline != by_timeline:
            return  # found the flashback book — test passes
    pytest.fail("expected at least one Book whose outline order differs from its timeline order")


def test_some_structure_beat_matches_no_beat_in_its_template(seeded: SeededLibrary) -> None:
    templates_by_id = {t.id: t for t in seeded.db.execute(select(StructureTemplate)).scalars()}
    rows = seeded.db.execute(
        select(BookSceneOrder.structure_beat, Book.structure_template_id)
        .join(Book, Book.id == BookSceneOrder.book_id)
        .where(BookSceneOrder.structure_beat.is_not(None))
    ).all()

    for structure_beat, structure_template_id in rows:
        template = templates_by_id.get(structure_template_id)
        beat_names = {beat["name"] for beat in (template.beats or [])} if template else set()
        if structure_beat not in beat_names:
            return  # found the "Unassigned" lane case — test passes
    pytest.fail(
        "expected at least one book_scene_order.structure_beat matching no beat name of "
        "its Book's structure template"
    )


# ── 9. Every seeded Image is a real, non-empty file on disk ────────────────────────────
def test_every_seeded_image_resolves_to_a_real_nonempty_file(seeded: SeededLibrary) -> None:
    images = seeded.db.execute(select(Image)).scalars().all()
    assert images, "expected the seeder to have created at least one Image"
    for image in images:
        path = images_service.resolve_path(image)
        assert path.is_file(), f"Image {image.id} ({image.display_name!r}) has no file at {path}"
        assert path.stat().st_size > 0, f"Image {image.id} ({image.display_name!r}) is empty"
