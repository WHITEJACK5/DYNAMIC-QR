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


def _sql(url, statements):
    """Run SQL against the target using the containerized psql."""
    container = os.getenv("TEST_PG_CONTAINER", "nare-pg")
    script = "; ".join(statements)
    return subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", "nare", "-d", "nare", "-tAc", script],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _seed_statements():
    return [
        "DROP TABLE IF EXISTS scans, qrcodes, folders, templates, users CASCADE",
        "DROP TABLE IF EXISTS alembic_version",
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
    """pg_dump -Fc -> drop -> pg_restore, then assert the data survived."""
    _sql(PG_URL, _seed_statements())
    assert _sql(PG_URL, ["SELECT count(*) FROM qrcodes"]) == "1"

    dump_in_container = "/tmp/nare-test.dump"
    subprocess.run(
        ["docker", "exec", "nare-pg", "pg_dump", "-U", "nare", "-d", "nare", "-Fc",
         "-f", dump_in_container],
        check=True, capture_output=True, text=True,
    )
    size = subprocess.run(
        ["docker", "exec", "nare-pg", "sh", "-c", f"wc -c < {dump_in_container}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert int(size) > 0, "dump file is empty"

    # Wipe the data, keeping the schema-less state the restore will rebuild
    _sql(PG_URL, ["DROP TABLE IF EXISTS qrcodes CASCADE", "DROP TABLE IF EXISTS users CASCADE"])
    assert _sql(PG_URL, [
        "SELECT count(*) FROM information_schema.tables"
        " WHERE table_schema='public' AND table_name IN ('users','qrcodes')"
    ]) == "0"

    subprocess.run(
        ["docker", "exec", "nare-pg", "pg_restore", "-U", "nare", "-d", "nare",
         "--no-owner", "--no-privileges", dump_in_container],
        check=True, capture_output=True, text=True,
    )
    assert _sql(PG_URL, ["SELECT count(*) FROM users"]) == "1"
    row = _sql(PG_URL, ["SELECT name || '|' || content || '|' || scan_count FROM qrcodes"])
    assert row == "survivor|https://example.com/keep-me|7"
    subprocess.run(["docker", "exec", "nare-pg", "rm", "-f", dump_in_container], check=False)


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
        "DATABASE_URL", "postgresql+psycopg2://alice:s3cr3t@db.internal:6543/nare"
    )
    p = pgbackup._dsn_parts()
    assert (p["host"], p["port"], p["user"], p["dbname"]) == (
        "db.internal", "6543", "alice", "nare"
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
