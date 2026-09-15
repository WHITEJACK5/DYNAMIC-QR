"""Phase 2n: scans repo (writes never raise, aggregates user-scoped)."""
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

import app as nare
from core import scans_repo


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


def _qr(db, uid, name="q"):
    import secrets as _s

    cur = db.cursor()
    cur.execute(
        "INSERT INTO qrcodes (user_id,name,type,content,short_code,created_at,updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (uid, name, "url", "https://example.com", _s.token_hex(4),
         datetime.datetime.utcnow().isoformat(), datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return cur.lastrowid


def test_record_and_geo():
    db, path, old = _db()
    try:
        uid = _user(db)
        qid = _qr(db, uid)
        sid = scans_repo.record_scan(db, qid, "2026-01-01T00:00:00", "9.9.9.9", "ua", "Mobile", "Chrome", "Android")
        assert sid
        cur = db.cursor()
        cur.execute("SELECT country, city FROM scans WHERE id=?", (sid,))
        assert tuple(cur.fetchone()) == ("Pending", "Pending")
        cur.execute("SELECT scan_count FROM qrcodes WHERE id=?", (qid,))
        assert cur.fetchone()[0] == 1
        scans_repo.update_geo(db, sid, "Testland", "Testville")
        cur.execute("SELECT country FROM scans WHERE id=?", (sid,))
        assert cur.fetchone()[0] == "Testland"
    finally:
        _teardown(db, path, old)


def test_overview_scoped_and_shaped():
    db, path, old = _db()
    try:
        a, b = _user(db, "a@x.com"), _user(db, "b@x.com")
        qa, qb = _qr(db, a, "a"), _qr(db, b, "b")
        scans_repo.record_scan(db, qa, "2026-02-01T10:00:00", "1.1.1.1", "u", "Mobile", "Chrome", "X")
        scans_repo.record_scan(db, qb, "2026-02-01T11:00:00", "2.2.2.2", "u", "Desktop", "Safari", "Y")
        ov = scans_repo.overview_for_user(db, a)
        assert ov["total_qrs"] == 1 and ov["total_scans"] == 1
        assert ov["timeline"] == [{"d": "2026-02-01", "c": 1}]
        assert ov["devices"] == [{"device": "Mobile", "c": 1}]
        assert [t["name"] for t in ov["top"]] == ["a"]
        d = scans_repo.detail_for_qr(db, qa)
        assert len(d["scans"]) == 1 and d["timeline"][0]["c"] == 1
    finally:
        _teardown(db, path, old)
