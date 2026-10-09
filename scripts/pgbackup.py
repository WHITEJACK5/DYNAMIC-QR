"""PostgreSQL backup + restore helpers (Phase 3e).

Managed Postgres (RDS/Supabase/Railway) offers PITR/backups natively —
prefer that in production and use this for self-hosted/containers. Run
this on a schedule (cron, Task Scheduler, systemd timer) and ship the file
somewhere durable: a dump on the same disk is not a backup.

Usage:
    python -m scripts.pgbackup dump   --out backups/DR-20260927.dump
    python -m scripts.pgbackup restore --in backups/DR-20260927.dump
    python -m scripts.pgbackup list

DATABASE_URL decides the target; no credentials are stored here.
"""
import argparse
import os
import subprocess
import sys
from urllib.parse import urlparse

DEFAULT_DIR = "backups"


def _dsn_parts():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        sys.exit("DATABASE_URL is not set (expected postgresql://user:pass@host:port/db)")
    if not url.startswith("postgresql"):
        sys.exit(f"DATABASE_URL must be a postgresql:// URL, got: {url[:24]}...")
    p = urlparse(url)
    return {
        "host": p.hostname or "localhost",
        "port": str(p.port or 5432),
        "user": p.username or "postgres",
        "password": p.password or "",
        "dbname": (p.path or "/postgres").lstrip("/"),
    }


def _env(parts):
    env = dict(os.environ)
    if parts["password"]:
        env["PGPASSWORD"] = parts["password"]
    return env


def _run(args, parts, **kw):
    return subprocess.run(args, env=_env(parts), check=True, **kw)


def _pg_bin(name):
    """Locate a PostgreSQL client binary (pg_dump / psql)."""
    from shutil import which

    found = which(name)
    if not found:
        sys.exit(
            f"'{name}' not found on PATH. Install the PostgreSQL client tools "
            "(Windows: 'pg_dump' ships with the PostgreSQL install; apt: postgresql-client)."
        )
    return found


def dump(out_path):
    parts = _dsn_parts()
    pg_dump = _pg_bin("pg_dump")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    # custom format: compressed, restorable with pg_restore, supports -j
    _run([
        pg_dump, "-h", parts["host"], "-p", parts["port"], "-U", parts["user"],
        "-d", parts["dbname"], "-Fc", "-f", out_path,
    ], parts)
    size = os.path.getsize(out_path)
    print(f"dumped {parts['dbname']} @ {parts['host']} -> {out_path} ({size} bytes)")
    return out_path


def restore(in_path, drop_first=True):
    if not os.path.exists(in_path):
        sys.exit(f"dump not found: {in_path}")
    parts = _dsn_parts()
    pg_restore = _pg_bin("pg_restore")
    psql = _pg_bin("psql")
    if drop_first:
        # Clean slate so object/constraint conflicts cannot abort the restore
        _run([
            psql, "-h", parts["host"], "-p", parts["port"], "-U", parts["user"],
            "-d", parts["dbname"],
            "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
        ], parts)
    _run([
        pg_restore, "-h", parts["host"], "-p", parts["port"], "-U", parts["user"],
        "-d", parts["dbname"], "--no-owner", "--no-privileges", "-j", "2", in_path,
    ], parts)
    print(f"restored {in_path} into {parts['dbname']} @ {parts['host']}")


def verify():
    """Sanity check the target DB is reachable and migrated."""
    parts = _dsn_parts()
    psql = _pg_bin("psql")
    out = subprocess.run([
        psql, "-h", parts["host"], "-p", parts["port"], "-U", parts["user"],
        "-d", parts["dbname"], "-tAc",
        "select count(*) from information_schema.tables where table_schema='public'",
    ], env=_env(parts), check=True, capture_output=True, text=True)
    count = out.stdout.strip()
    print(f"database {parts['dbname']} reachable; {count} tables in schema public")
    return int(count or 0)


def rotate(keep=14, directory=DEFAULT_DIR):
    """Delete dated dumps older than `keep` days. Returns removed paths."""
    import glob
    import time

    cutoff = time.time() - keep * 86400
    removed = []
    for path in glob.glob(os.path.join(directory, "DR-*.dump")):
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed.append(path)
        except OSError as e:
            print(f"could not remove {path}: {e}")
    if removed:
        print(f"rotated {len(removed)} dump(s) older than {keep} days")
    return removed


def main(argv=None):
    ap = argparse.ArgumentParser(description="PostgreSQL backup/restore for DRQR")
    ap.add_argument("action", choices=["dump", "rotate", "restore", "verify"])
    ap.add_argument("--out", default=os.path.join(DEFAULT_DIR, "DR-latest.dump"))
    ap.add_argument("--in", dest="inp", default=None)
    ap.add_argument("--keep", type=int, default=14, help="days to keep (rotate action)")
    ap.add_argument("--dir", dest="directory", default=DEFAULT_DIR)
    args = ap.parse_args(argv)
    if args.action == "dump":
        dump(args.out)
    elif args.action == "rotate":
        rotate(args.keep, args.directory)
    elif args.action == "restore":
        restore(args.inp or args.out)
    else:
        verify()


if __name__ == "__main__":
    main()
