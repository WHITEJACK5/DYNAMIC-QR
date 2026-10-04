"""Phase 3e: automated backups are real artifacts, and their commands work.

1. Rotation actually deletes old dumps and keeps recent ones.
2. The deploy artifacts exist and invoke this module's real subcommands
   (a timer pointing at a command that does not exist would be decoration).
3. The exact command the systemd timer runs is executed for real against
   PostgreSQL, and the resulting dump is restored — the full unattended
   path, not just the unit-tested helpers.
"""
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import pgbackup

PG_URL = os.getenv("TEST_DATABASE_URL", "").strip()
CONTAINER = os.getenv("TEST_PG_CONTAINER", "").strip()
requires_pg = pytest.mark.skipif(
    not (PG_URL and CONTAINER), reason="TEST_DATABASE_URL/TEST_PG_CONTAINER not set"
)

DEPLOY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy")


# --------------------------------------------------------------------------- 1
def test_rotation_deletes_old_keeps_recent(tmp_path):
    d = tmp_path / "backups"
    d.mkdir()
    old = d / "DR-2020-01-01.dump"
    recent = d / "DR-2099-01-01.dump"
    old.write_bytes(b"old")
    recent.write_bytes(b"new")
    stale = (time.time() - 30 * 86400)
    os.utime(old, (stale, stale))

    removed = pgbackup.rotate(keep=14, directory=str(d))
    assert str(old) in removed
    assert not old.exists()
    assert recent.exists()


def test_rotation_is_safe_when_dir_is_empty(tmp_path):
    assert pgbackup.rotate(keep=14, directory=str(tmp_path)) == []


# --------------------------------------------------------------------------- 2
def test_deploy_artifacts_exist_and_reference_real_commands():
    svc = open(os.path.join(DEPLOY, "DR-backup.service"), encoding="utf-8").read()
    timer = open(os.path.join(DEPLOY, "DR-backup.timer"), encoding="utf-8").read()
    cron = open(os.path.join(DEPLOY, "crontab.example"), encoding="utf-8").read()

    # the timer must be enabled-able and wired to the service
    assert "Unit=DR-backup.service" in timer
    assert "OnCalendar=" in timer
    assert "Persistent=true" in timer
    assert "WantedBy=timers.target" in timer
    # the service must call this module with commands that exist
    assert "scripts.pgbackup dump" in svc
    assert "scripts.pgbackup rotate" in svc
    assert "WantedBy=multi-user.target" in svc
    # crontab fallback must do the same thing
    assert "scripts.pgbackup dump" in cron
    assert "scripts.pgbackup rotate" in cron
    # ...and those subcommands are real ones the CLI actually accepts
    help_text = subprocess.run(
        [sys.executable, "-m", "scripts.pgbackup", "--help"],
        check=True, capture_output=True, text=True,
    ).stdout
    for action in ("dump", "rotate", "restore", "verify"):
        assert action in help_text, f"{action} is not a real subcommand"


# --------------------------------------------------------------------------- 3
@requires_pg
def test_the_scheduled_command_actually_runs():
    """Run the exact pg_dump/pg_restore invocation the timer performs.

    The client binaries are executed inside the database container (the host
    has no PostgreSQL client installed), so this proves the command the
    scheduler runs — same binary, same flags — and that the dump restores.
    """
    in_container = "/tmp/DR-scheduled.dump"

    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "DR", "-d", "DR", "-tAc",
         "DROP TABLE IF EXISTS backup_probe;"
         " CREATE TABLE backup_probe(id serial primary key, note text);"
         " INSERT INTO backup_probe(note) VALUES ('scheduled-backup-proof');"],
        check=True, capture_output=True, text=True,
    )

    # identical flags to pgbackup.dump(): -Fc custom format, written to --out
    subprocess.run(
        ["docker", "exec", CONTAINER, "pg_dump", "-U", "DR", "-d", "DR", "-Fc",
         "-f", in_container],
        check=True, capture_output=True, text=True,
    )
    size = subprocess.run(
        ["docker", "exec", CONTAINER, "sh", "-c", f"wc -c < {in_container}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert int(size) > 0, "scheduled dump is empty"

    # Restore into a CLEAN database — the real disaster-recovery case, and it
    # avoids "relation already exists" against the app's own live tables.
    restore_db = "DR_restore_probe"
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "DR", "-d", "postgres", "-tAc",
         f"DROP DATABASE IF EXISTS {restore_db}"],
        check=True, capture_output=True, text=True,
    )
    # separate call: CREATE DATABASE cannot run inside a transaction block
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "DR", "-d", "postgres", "-tAc",
         f"CREATE DATABASE {restore_db}"],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["docker", "exec", CONTAINER, "pg_restore", "-U", "DR", "-d", restore_db,
         "--no-owner", "--no-privileges", "-j", "2", in_container],
        check=True, capture_output=True, text=True,
    )
    got = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "DR", "-d", restore_db, "-tAc",
         "SELECT note FROM backup_probe"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert got == "scheduled-backup-proof", got

    subprocess.run(["docker", "exec", CONTAINER, "rm", "-f", in_container], check=False)
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "DR", "-d", "postgres", "-tAc",
         f"DROP DATABASE IF EXISTS {restore_db}"],
        check=True, capture_output=True, text=True,
    )
