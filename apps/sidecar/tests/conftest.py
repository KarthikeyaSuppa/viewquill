"""Shared pytest helpers for the sidecar test suite.

Cross-module test-database isolation note: ``app.config.get_settings()`` is
``@lru_cache``-d and ``app.db.base`` builds its SQLAlchemy ``engine``/``SessionLocal``
ONCE, at import time, from whichever settings won that race — see ``app/db/base.py``'s
module docstring. Because pytest imports every test module during collection before any
test runs, every ``test_*.py`` module in this package that sets ``QUILLNIGHT_DATA_DIR``
before importing ``app.main`` ends up sharing ONE SQLite database for the whole test
session (whichever module is collected first "wins" that one-time build).

Most of this suite tolerates that just fine — every test creates its own uniquely-named
book/scene/codex entry, so there's no cross-module collision. The profile/auth tests do
NOT: ``users.username`` is globally UNIQUE and there's a hard cap of 2 profiles
(``app/services/profiles_service.py`` ``MAX_PROFILES``), so any two test modules that both
create real profiles against the shared database collide with each other's leftover rows
— this is exactly what broke tests/test_profiles_auth.py (409s where 200/201 was expected)
and tests/test_settings_peruser.py (login never returns a token, so the module-scoped
``user_a_headers``/``user_b_headers`` fixtures raise before any dependent test even runs).

``reset_users_table()`` below gives a test module a guaranteed-empty ``users`` table (and,
via the existing ``ON DELETE CASCADE`` + ``PRAGMA foreign_keys=ON`` from app/db/base.py,
any per-user ``app_settings`` rows that hung off it) regardless of what ran before it or
in what order. Used by the ``client`` fixture in tests/test_auth_migration.py,
tests/test_profiles_auth.py, and tests/test_settings_peruser.py — the three modules that
create real profiles and rely on those global invariants. This intentionally does NOT
rebuild the engine/session (that would leave the module-level ``SessionLocal`` import in
app/api/llm.py, and the one in tests/test_prompt_builder.py, pointed at a stale/orphaned
database — those are captured once, at collection time, and never re-read) — it just clears
the one table whose constraints are actually global, on the one shared database everyone
already uses.
"""

from __future__ import annotations

import os

# Disable the Phase 14 sample-library seeder for the entire test session.
#
# `app/main.py`'s lifespan calls `seed_sample_library`, whose guard is "no marker AND no
# Books" — i.e. exactly the state the shared test database is in. Without this, the first
# test module to enter `TestClient(app)` seeds 4 demo Books + 27 Scenes + 14 Images into
# the one database every other module shares, breaking anything that asserts on an empty
# or precisely-known library (`test_bundle_import_inspect.py::test_inspect_empty_db_
# everything_created` and the three migration round-trip tests all failed this way).
#
# Set here rather than in each test module because conftest.py is imported before any
# `test_*.py`, and the seeder reads this at call time — so tests/test_sample_library.py can
# still exercise the real seeder by clearing it around the specific calls under test.
os.environ.setdefault("QUILLNIGHT_SKIP_SAMPLE_SEED", "1")


def reset_users_table() -> None:
    """Deletes every row from ``users`` on the shared test database.

    Must be called AFTER the app's lifespan has already run (i.e. after entering
    ``TestClient(app)`` as a context manager), since that's what migrates the table into
    existence. Imports are local/deferred so this doesn't force an early import of
    ``app.db.base`` (which would build the engine before a caller's own
    ``QUILLNIGHT_DATA_DIR`` is set) and so it always reads whatever
    ``app.db.base.SessionLocal`` currently is.
    """
    from app.db.base import SessionLocal
    from app.models.orm import User

    with SessionLocal() as db:
        db.query(User).delete()
        db.commit()
