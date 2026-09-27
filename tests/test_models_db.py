"""Phase 3a: SQLAlchemy models match the legacy DDL on SQLite *and* the
real Postgres container, and pooling config is dialect-correct.

Postgres tests are skipped unless TEST_DATABASE_URL is set, so CI/local
stays SQLite-only and honest.
"""
import os
import sqlite3
import sys
import tempfile

import pytest
from sqlalchemy import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

import server as nare
from app import db as cdb
from app.models import Base, QRCode, Scan, User

PG_URL = os.getenv("TEST_DATABASE_URL", "").strip()
requires_pg = pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL not set (Postgres not available)")

EXPECTED_TABLES = {"users", "folders", "qrcodes", "scans", "templates"}


def _legacy_db():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old = nare.DB_PATH
    nare.DB_PATH = tmp.name
    nare.init_db()
    return tmp.name, old


def _teardown(path, old):
    try:
        os.unlink(path)
    except OSError:
        pass
    nare.DB_PATH = old


def test_models_create_all_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path.as_posix()}/orm.db"
    eng = cdb.build_engine(url)
    cdb.create_all(eng)
    insp = inspect(eng)
    assert EXPECTED_TABLES.issubset(set(insp.get_table_names()))
    eng.dispose()


def test_columns_match_legacy_init_db():
    """Columns AND nullability must equal app.py:init_db (no drift).

    Nullability matters: the repositories INSERT via raw SQL and rely on
    "DEFAULT 0" columns staying nullable (an ORM-side NOT NULL would 500).
    """
    legacy_path, old = _legacy_db()
    try:
        con = sqlite3.connect(legacy_path)
        legacy = {
            t: {r[1]: {"notnull": bool(r[3]), "default": r[4]} for r in con.execute(f"PRAGMA table_info({t})")}
            for t in EXPECTED_TABLES
        }
        con.close()
    finally:
        _teardown(legacy_path, old)
    orm = {
        t.name: {c.name: {"notnull": not c.nullable, "default": c.server_default} for c in t.columns}
        for t in Base.metadata.tables.values()
    }
    assert set(legacy) == set(orm)
    for table, cols in legacy.items():
        assert set(cols) == set(orm[table]), f"{table}: columns differ"
        for col, meta in cols.items():
            assert meta["notnull"] == orm[table][col]["notnull"], (
                f"{table}.{col}: legacy notnull={meta['notnull']} orm={orm[table][col]['notnull']}"
            )
        defaults = {c for c, m in cols.items() if m["default"] is not None}
        orm_defaults = {c for c, m in orm[table].items() if m["default"] is not None}
        assert defaults == orm_defaults, f"{table}: defaults legacy={defaults} orm={orm_defaults}"


def test_sqlite_pool_and_wal(tmp_path):
    eng = cdb.build_engine(f"sqlite:///{tmp_path.as_posix()}/p.db")
    cdb.create_all(eng)
    with eng.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
    assert str(mode).lower() == "wal"
    assert int(timeout) == 5000
    eng.dispose()


@requires_pg
def test_postgres_roundtrip_and_pooling():
    assert cdb.is_postgres(PG_URL)
    eng = cdb.build_engine(PG_URL)
    pool = eng.pool
    assert pool.__class__.__name__ == "QueuePool"
    assert pool.size() == cdb._int_env("DB_POOL_SIZE", 5)
    assert pool._max_overflow == cdb._int_env("DB_MAX_OVERFLOW", 10)
    assert eng.dialect.name == "postgresql"
    # create/drop a scratch schema to prove connectivity + DDL works
    Base.metadata.drop_all(eng)
    cdb.create_all(eng)
    insp = inspect(eng)
    assert EXPECTED_TABLES.issubset(set(insp.get_table_names()))
    S = cdb.sessionmaker(bind=eng)
    with S() as s:
        u = User(email="pg@x.com", password_hash="h", name="PG")
        s.add(u)
        s.commit()
        q = QRCode(user_id=u.id, name="n", type="url", content="https://e.com",
                   short_code="PGCODE1", scan_count=0, has_password=0)
        s.add(q)
        s.commit()
        s.add(Scan(qr_id=q.id, timestamp="t", ip="1.1.1.1"))
        s.commit()
        assert s.query(QRCode).filter_by(short_code="PGCODE1").one().name == "n"
        assert s.query(Scan).count() == 1
    Base.metadata.drop_all(eng)
    eng.dispose()


def test_default_url_is_local_sqlite():
    cdb.set_default_sqlite(None)
    os.environ.pop("DATABASE_URL", None)
    assert cdb.database_url() == cdb.DEFAULT_SQLITE
    assert cdb.is_postgres() is False
    cdb.set_default_sqlite("C:/tmp/override.db")
    assert cdb.database_url() == "sqlite:///C:/tmp/override.db"
    os.environ["DATABASE_URL"] = "postgresql://u:p@h:5432/d"
    assert cdb.is_postgres() is True
    os.environ.pop("DATABASE_URL")
    cdb.set_default_sqlite(None)
