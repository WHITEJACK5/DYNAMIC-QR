"""Phase 2l: QR repository — user-scoped SQL, tested without Flask."""
import datetime
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

import app as nare
from core import qr_repo


def _db():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old = nare.DB_PATH
    nare.DB_PATH = tmp.name
    nare.init_db()
    db = nare.get_db()
    return db, tmp.name, old


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


def _qr(db, uid, name="q", code=None):
    import secrets as _s

    cur = db.cursor()
    cur.execute(
        "INSERT INTO qrcodes (user_id,name,type,content,short_code,created_at,updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (uid, name, "url", "https://example.com", code or _s.token_hex(4),
         datetime.datetime.utcnow().isoformat(), datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return cur.lastrowid


def test_list_count_order_and_isolation():
    db, path, old = _db()
    try:
        a, b = _user(db, "a@x.com"), _user(db, "b@x.com")
        _qr(db, a, "a1")
        _qr(db, a, "a2")
        _qr(db, b, "b1")
        assert qr_repo.count_owned(db, a) == 2
        rows = qr_repo.list_owned(db, a)
        assert [r["name"] for r in rows] == ["a2", "a1"]  # newest first
        page = qr_repo.list_owned(db, a, limit=1, offset=1)
        assert len(page) == 1 and page[0]["name"] == "a1"
        assert qr_repo.get_owned(db, rows[0]["id"], b) is None
    finally:
        _teardown(db, path, old)


def test_to_public_strips_secret():
    db, path, old = _db()
    try:
        uid = _user(db)
        qid = _qr(db, uid)
        pub = qr_repo.to_public(qr_repo.get_owned(db, qid, uid))
        assert "password_hash" not in pub and pub["name"] == "q"
    finally:
        _teardown(db, path, old)


def test_apply_update_and_password_clear():
    db, path, old = _db()
    try:
        uid = _user(db)
        qid = _qr(db, uid)
        out = qr_repo.apply_update(db, qid, uid, {"name": "New", "fg_color": "#00FF88", "evil": 1})
        assert out["name"] == "New" and "evil" not in out
        out = qr_repo.apply_update(db, qid, uid, {"password": "Secret123!"})
        cur = db.cursor()
        cur.execute("SELECT has_password FROM qrcodes WHERE id=?", (qid,))
        assert cur.fetchone()["has_password"] == 1
        qr_repo.apply_update(db, qid, uid, {"password": ""})
        cur.execute("SELECT has_password, password_hash FROM qrcodes WHERE id=?", (qid,))
        row = cur.fetchone()
        assert row["has_password"] == 0 and row["password_hash"] is None
        assert qr_repo.apply_update(db, 999999, uid, {"name": "x"}) is None
    finally:
        _teardown(db, path, old)


def test_delete_cascades_scans():
    db, path, old = _db()
    try:
        uid = _user(db)
        qid = _qr(db, uid)
        cur = db.cursor()
        cur.execute(
            "INSERT INTO scans (qr_id,timestamp,ip) VALUES (?,?,?)", (qid, "t", "1.2.3.4")
        )
        db.commit()
        assert qr_repo.delete_owned(db, qid, uid) is True
        cur.execute("SELECT COUNT(*) FROM scans WHERE qr_id=?", (qid,))
        assert cur.fetchone()[0] == 0
        assert qr_repo.delete_owned(db, qid, uid) is False
    finally:
        _teardown(db, path, old)


def test_mint_avoids_collision(monkeypatch):
    import core.qr_repo as _qrmod

    db, path, old = _db()
    try:
        uid = _user(db)
        _qr(db, uid, "taken", code="TAKEN123")
        seq = iter(["TAKEN123", "FRESH999"])
        monkeypatch.setattr(_qrmod, "generate_short_code", lambda n=8: next(seq))
        assert qr_repo.mint_unique_short(db, 5) == "FRESH999"
    finally:
        _teardown(db, path, old)


def test_create_and_duplicate_roundtrip():
    db, path, old = _db()
    try:
        a, b = _user(db, "a@x.com"), _user(db, "b@x.com")
        qid = qr_repo.create_full(
            db, user_id=a, name="orig", type="url", content="https://example.com",
            data_json="{}", is_dynamic=1, short_code="DUPME123", fg_color="#0A0A0A",
            bg_color="#FFFFFF")
        assert qr_repo.get_owned(db, qid, a)["short_code"] == "DUPME123"
        nid = qr_repo.duplicate_owned(db, qid, a)
        copy = qr_repo.get_owned(db, nid, a)
        assert copy["name"] == "orig (Copy)" and copy["scan_count"] == 0
        assert copy["short_code"] != "DUPME123"
        assert qr_repo.duplicate_owned(db, qid, b) is None  # other user's QR
        with pytest.raises(Exception):
            qr_repo.create_full(db, user_id=a, bogus_col=1)
    finally:
        _teardown(db, path, old)
