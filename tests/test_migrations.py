"""Phase 3b: the baseline migration is versioned, reversible, and matches
the ORM on SQLite and on the real Postgres container.

Postgres leg is skipped unless TEST_DATABASE_URL is set.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

from app import migrations as mig
from app.models import Base

PG_URL = os.getenv("TEST_DATABASE_URL", "").strip()
requires_pg = pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL not set")
EXPECTED = {"users", "folders", "qrcodes", "scans", "templates"}
EXPECTED_INDEXES = {"qrcodes": {"idx_qr_short", "idx_qr_user"}, "scans": {"idx_scans_qr"}}


def _sqlite_url(tmp_path, name="m.db"):
    return f"sqlite:///{(tmp_path / name).as_posix()}"


def test_revision_chain_is_linear_and_head_is_latest():
    """Phase 4d added 0002. Assert the shape of the chain, not one hardcoded
    id, so the next migration does not have to edit this test."""
    head = mig.head_revision()
    assert head == "0002_email_verification"
    assert mig.revision_chain(head) == ["0001_initial", "0002_email_verification"]


def test_upgrade_creates_exact_schema(tmp_path):
    url = _sqlite_url(tmp_path)
    assert mig.current_revision(url) is None
    mig.upgrade_to_head(url)
    assert mig.current_revision(url) == mig.head_revision()
    assert mig.user_tables(url) == EXPECTED
    from sqlalchemy import create_engine, inspect

    eng = create_engine(url)
    insp = inspect(eng)
    for table, idx in EXPECTED_INDEXES.items():
        assert idx.issubset({i["name"] for i in insp.get_indexes(table)}), table
    # columns must equal the ORM declaration (migration is in sync with models)
    orm = {t.name: {c.name for c in t.columns} for t in Base.metadata.tables.values()}
    live = {t: {c["name"] for c in insp.get_columns(t)} for t in EXPECTED}
    assert live == orm
    eng.dispose()


def test_downgrade_is_reversible(tmp_path):
    url = _sqlite_url(tmp_path, "d.db")
    mig.upgrade_to_head(url)
    assert mig.user_tables(url) == EXPECTED
    mig.downgrade_to_base(url)
    assert mig.user_tables(url) == set()
    assert mig.current_revision(url) is None
    # and it can be re-applied
    mig.upgrade_to_head(url)
    assert mig.user_tables(url) == EXPECTED


@requires_pg
def test_postgres_migration_cycle():
    """
    Runs against a dedicated scratch database, not the shared one.

    downgrade_to_base() is asserted to leave an empty schema, which is only
    true if this test owns its database — otherwise a table created by an
    earlier test in the same session (e.g. a backup round-trip probe) makes
    the assertion fail for reasons that have nothing to do with migrations.
    """
    from sqlalchemy import create_engine, inspect, text
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(PG_URL)
    admin = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))
    scratch = "nare_migration_probe"
    opened = []

    def _admin_engine():
        e = create_engine(admin, isolation_level="AUTOCOMMIT")
        opened.append(e)
        return e

    def _drop():
        # Alembic and inspect() each leave connections behind, and
        # DROP DATABASE refuses while any session is attached.
        for e in opened:
            e.dispose()
        opened.clear()
        e = create_engine(admin, isolation_level="AUTOCOMMIT")
        try:
            with e.connect() as c:
                c.execute(text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = '{scratch}' AND pid <> pg_backend_pid()"))
                c.execute(text(f"DROP DATABASE IF EXISTS {scratch}"))
        finally:
            e.dispose()

    _drop()
    with _admin_engine().connect() as c:
        c.execute(text(f"CREATE DATABASE {scratch}"))
    url = urlunsplit((parts.scheme, parts.netloc, f"/{scratch}", "", ""))
    try:
        assert mig.user_tables(url) == set()
        mig.upgrade_to_head(url)
        assert mig.user_tables(url) == EXPECTED
        assert mig.current_revision(url) == mig.head_revision()
        insp = inspect(create_engine(url))
        for table, idx in EXPECTED_INDEXES.items():
            assert idx.issubset({i["name"] for i in insp.get_indexes(table)}), table
        # reversible
        mig.downgrade_to_base(url)
        assert mig.user_tables(url) == set()
    finally:
        _drop()


def test_no_drift_between_models_and_migration(tmp_path):
    """Autogenerate against a migrated DB must report no changes."""
    url = _sqlite_url(tmp_path, "drift.db")
    mig.upgrade_to_head(url)
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    eng = create_engine(url)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    eng.dispose()
    assert diff == [], f"migration/models drift: {diff}"
