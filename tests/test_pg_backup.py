"""Phase 3e: the documented backup/restore procedure is proven for real.

Strategy: the PostgreSQL client binaries live inside the database
container, so the round-trip (pg_dump -Fc -> wipe -> pg_restore) is
executed there and the restored rows are asserted. Tests skip cleanly
when no TEST_DATABASE_URL / container is available — never a fake pass.
The Python helper in scripts/pgbackup.py is exercised separately.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import pgbackup

PG_URL = os.getenv("TEST_DATABASE_URL", "").strip()
requires_pg = pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL not set")


def _have_clients():
    from shutil import which

    return all(which(b) for b in ("pg_dump", "pg_restore", "psql"))


def _sql(url, statements, dbname="DR"):
    """Run SQL against the target using the containerized psql.

    `url` is kept for the caller's context; the container is addressed by
    dbname because these tests drive a local container, not a network host.
    """
    container = os.getenv("TEST_PG_CONTAINER", "DR-pg")
    script = "; ".join(statements)
    return subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", "DR", "-d", dbname, "-tAc", script],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _admin():
    """A connection to the 'postgres' maintenance database.

    Needed to create and drop scratch databases. Separate statements, because
    CREATE/DROP DATABASE cannot run inside a transaction block and psql -c
    wraps multiple statements in one.
    """
    container = os.getenv("TEST_PG_CONTAINER", "DR-pg")

    def run(statement):
        return subprocess.run(
            ["docker", "exec", "-i", container, "psql", "-U", "DR",
             "-d", "postgres", "-tAc", statement],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    return run


def _scratch(name):
    """Create an isolated database and return its URL.

    The round trip used to seed the shared `DR` database, which only works
    while nothing else is using it. With the compose stack running, the app
    holds connections there and the DROP fails. Owning a scratch database
    makes the test independent of whatever else is attached to the server.
    """
    run = _admin()
    run(f"DROP DATABASE IF EXISTS {name}")
    run(f"CREATE DATABASE {name}")
    return _url_for(name)


def _seed_statements():
    return [
        "CREATE TABLE users (id serial PRIMARY KEY, email text UNIQUE NOT NULL,"
        " password_hash text NOT NULL, name text, created_at text)",
        "CREATE TABLE qrcodes (id serial PRIMARY KEY, user_id integer REFERENCES users(id),"
        " name text, content text, scan_count integer DEFAULT 0)",
        "INSERT INTO users (email,password_hash,name,created_at) VALUES"
        " ('backup@test.local','h','Backup','2026-01-01')",
        "INSERT INTO qrcodes (user_id,name,content,scan_count)"
        " SELECT id,'survivor','https://example.com/keep-me',7 FROM users",
    ]


@requires_pg
@pytest.mark.skipif(not os.getenv("TEST_PG_CONTAINER"), reason="TEST_PG_CONTAINER not set")
def test_dump_restore_roundtrip_in_container(tmp_path):
    """pg_dump -Fc -> restore into a clean database -> assert the data survived.

    Restores into a scratch database rather than back into `DR`. Restoring
    over the source database only works while nothing else in the schema
    exists, so it broke whenever an earlier test in the same session had
    created tables the dump also contains. Restoring into a fresh database
    is also what disaster recovery actually looks like.
    """
    source = _scratch("DR_backup_src")
    _sql(source, _seed_statements())
    assert _sql(source, ["SELECT count(*) FROM qrcodes"]) == "1"

    dump_in_container = "/tmp/DR-test.dump"
    subprocess.run(
        ["docker", "exec", "DR-pg", "pg_dump", "-U", "DR", "-d", "DR_backup_src", "-Fc",
         "-f", dump_in_container],
        check=True, capture_output=True, text=True,
    )
    size = subprocess.run(
        ["docker", "exec", "DR-pg", "sh", "-c", f"wc -c < {dump_in_container}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert int(size) > 0, "dump file is empty"

    restore_db = "DR_backup_probe"
    # separate statements: CREATE DATABASE cannot run in a transaction block
    _admin()(f"DROP DATABASE IF EXISTS {restore_db}")
    _admin()(f"CREATE DATABASE {restore_db}")

    r = subprocess.run(
        ["docker", "exec", "DR-pg", "pg_restore", "-U", "DR", "-d", restore_db,
         "--no-owner", "--no-privileges", dump_in_container],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"pg_restore failed: {r.stderr}"
    assert _sql(_url_for(restore_db), ["SELECT count(*) FROM users"]) == "1"
    row = _sql(_url_for(restore_db),
               ["SELECT name || '|' || content || '|' || scan_count FROM qrcodes"])
    assert row == "survivor|https://example.com/keep-me|7"

    _admin()(f"DROP DATABASE IF EXISTS {restore_db}")
    _admin()("DROP DATABASE IF EXISTS DR_backup_src")
    subprocess.run(["docker", "exec", "DR-pg", "rm", "-f", dump_in_container], check=False)


def _url_for(dbname):
    """Same server/credentials as PG_URL, different database."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(PG_URL)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", "", ""))


@requires_pg
@pytest.mark.skipif(not _have_clients(), reason="pg client binaries not on PATH")
def test_python_helper_dump_restore(tmp_path, monkeypatch):
    _sql_or_skip = _have_clients() and os.getenv("TEST_PG_CONTAINER")
    if not _sql_or_skip:
        pytest.skip("needs client binaries and a reachable container")
    from sqlalchemy import create_engine, text

    eng = create_engine(PG_URL)
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS qrcodes, users CASCADE"))
        conn.execute(text("CREATE TABLE users (id serial PRIMARY KEY, email text, note text)"))
        conn.execute(text("INSERT INTO users (email,note) VALUES ('helper@test.local','via-python-helper')"))
    eng.dispose()

    monkeypatch.setenv("DATABASE_URL", PG_URL)
    out = str(tmp_path / "helper.dump")
    pgbackup.dump(out)
    assert os.path.getsize(out) > 0

    eng = create_engine(PG_URL)
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE users CASCADE"))
    eng.dispose()
    pgbackup.restore(out, drop_first=True)
    eng = create_engine(PG_URL)
    with eng.connect() as conn:
        assert conn.execute(text("SELECT note FROM users")).scalar() == "via-python-helper"
    eng.dispose()


def test_helper_rejects_non_postgres_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///nope.db")
    with pytest.raises(SystemExit) as e:
        pgbackup._dsn_parts()
    assert "postgresql" in str(e.value)


def test_helper_parses_dsn(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg2://alice:s3cr3t@db.internal:6543/DR"
    )
    p = pgbackup._dsn_parts()
    assert (p["host"], p["port"], p["user"], p["dbname"]) == (
        "db.internal", "6543", "alice", "DR"
    )
    assert pgbackup._env(p)["PGPASSWORD"] == "s3cr3t"


def test_missing_binary_message_is_actionable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/d")
    monkeypatch.setattr(
        pgbackup, "_pg_bin",
        lambda name: (_ for _ in ()).throw(SystemExit("'pg_dump' not found on PATH")),
    )
    with pytest.raises(SystemExit) as e:
        pgbackup.dump("x.dump")
    assert "not found on PATH" in str(e.value)
