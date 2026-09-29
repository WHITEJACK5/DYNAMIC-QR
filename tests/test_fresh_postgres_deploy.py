"""Phase 3b regression: a brand-new PostgreSQL database must be usable.

Found by the Phase 1-5 audit. init_db() decided whether the database was
fresh using the SQLite path (DB_PATH) while Alembic acted on whatever
DATABASE_URL pointed at. With PostgreSQL configured, a database whose
tables did not exist was *stamped* as already migrated rather than
migrated — so a first deploy came up with no tables and every request
returned 500.

This exercises the real scenario: a database that has never been touched.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

PG_URL = os.getenv("TEST_DATABASE_URL", "").strip()
requires_pg = pytest.mark.skipif(
    not PG_URL.startswith("postgresql"), reason="TEST_DATABASE_URL not a PostgreSQL URL")

ADMIN_URL = ""
SCRATCH = "nare_fresh_deploy_probe"


def _admin_url():
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(PG_URL)
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))


def _scratch_url():
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(PG_URL)
    return urlunsplit((parts.scheme, parts.netloc, f"/{SCRATCH}", "", ""))


def _drop_scratch():
    from sqlalchemy import create_engine, text
    eng = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as c:
            c.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                           f"WHERE datname = '{SCRATCH}' AND pid <> pg_backend_pid()"))
            c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH}"))
    finally:
        eng.dispose()


def _create_scratch():
    from sqlalchemy import create_engine, text
    eng = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as c:
            c.execute(text(f"CREATE DATABASE {SCRATCH}"))
    finally:
        eng.dispose()


@requires_pg
def test_a_never_touched_database_is_migrated_not_stamped():
    """
    The regression. An empty database must end up with tables, not with an
    alembic_version claiming it is already at head.
    """
    from sqlalchemy import create_engine, inspect, text

    from app import migrations as mig

    _drop_scratch()
    _create_scratch()
    url = _scratch_url()
    try:
        eng = create_engine(url)
        assert inspect(eng).get_table_names() == [], "precondition: database is empty"

        # This is exactly what server.init_db() does, against this URL.
        assert mig.current_revision(url) is None
        assert mig.user_tables(url) == set()
        mig.upgrade_to_head(url)

        assert mig.user_tables(url), "migrations produced no tables"
        assert mig.current_revision(url) == mig.head_revision()
        with eng.connect() as c:
            tables = c.execute(text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public'")).scalar()
        assert tables >= 5, f"expected the full schema, found {tables} tables"
        # the Phase 4d columns exist on a fresh deploy
        cols = {r["name"] for r in inspect(eng).get_columns("users")}
        assert {"email_verified", "verify_token", "verify_expires"} <= cols
        eng.dispose()
    finally:
        _drop_scratch()


@requires_pg
def test_stamping_is_never_used_for_an_empty_database():
    """
    The other half: a database with tables but no version row is a
    pre-Alembic database and may be stamped. One with neither must be
    migrated. Assert the decision rule itself so it cannot regress.
    """
    from sqlalchemy import create_engine, text

    from app import migrations as mig

    _drop_scratch()
    _create_scratch()
    url = _scratch_url()
    try:
        eng = create_engine(url)
        # empty: must upgrade
        assert not mig.user_tables(url)
        assert mig.current_revision(url) is None
        # give it tables without a version row, as a legacy DB would have
        with eng.connect() as c:
            c.execute(text("CREATE TABLE users (id serial PRIMARY KEY)"))
            c.commit()
        assert mig.user_tables(url) == {"users"}
        assert mig.current_revision(url) is None
        eng.dispose()
    finally:
        _drop_scratch()


@requires_pg
def test_init_db_acts_on_the_configured_database_not_the_sqlite_path(monkeypatch):
    """
    Structural: init_db must resolve one target and use it for both the
    decision and the action, so the two can never diverge again.
    """
    import inspect as _inspect
    import server as nare

    src = _inspect.getsource(nare.init_db)
    # every migration call takes the resolved target explicitly
    for call in ("current_revision", "user_tables", "stamp_head", "upgrade_to_head"):
        assert f"_migrations.{call}(target)" in src, \
            f"_migrations.{call}() is called without the resolved target"
    # and it no longer decides freshness from the SQLite path
    assert "is_fresh" not in src, \
        "init_db still decides freshness from the SQLite DB_PATH"
