"""Phase 2m: folders/templates repos (isolation + passthrough)."""
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

import app as nare
from core import folders_repo, templates_repo


def _db():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old = nare.DB_PATH
    nare.DB_PATH = tmp.name
    nare.init_db()
    return nare.get_db(), tmp.name, old


def _teardown(db, path, old):
    db.close()
    try:
        os.unlink(path)
    except OSError:
        pass
    nare.DB_PATH = old


def _user(db, email="a@x.com"):
    cur = db.cursor()
    cur.execute(
        "INSERT INTO users (email,password_hash,name,created_at) VALUES (?,?,?,?)",
        (email, "h", "A", datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return cur.lastrowid


def test_folders_isolated():
    db, path, old = _db()
    try:
        a, b = _user(db, "a@x.com"), _user(db, "b@x.com")
        out = folders_repo.create_for_user(db, a, "Work")
        assert out["name"] == "Work" and out["id"]
        assert [f["name"] for f in folders_repo.list_for_user(db, a)] == ["Work"]
        assert folders_repo.list_for_user(db, b) == []
    finally:
        _teardown(db, path, old)


def test_templates_config_roundtrip():
    db, path, old = _db()
    try:
        uid = _user(db)
        out = templates_repo.create_for_user(db, uid, "T", {"fg": "#000"})
        assert out["name"] == "T"
        rows = templates_repo.list_for_user(db, uid)
        assert len(rows) == 1
        import json as _j

        assert _j.loads(rows[0]["config_json"]) == {"fg": "#000"}
    finally:
        _teardown(db, path, old)
