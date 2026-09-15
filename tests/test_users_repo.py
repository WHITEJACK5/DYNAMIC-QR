"""Phase 2q2: users repo isolation + token service round-trips."""
import datetime
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

import jwt as _jwt

import app as nare
from core import tokens, users_repo

SECRET = "test-secret-key-for-ci-must-be-long-enough-32chars"


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


def test_user_lifecycle():
    db, path, old = _db()
    try:
        assert users_repo.find_id_by_email(db, "a@x.com") is None
        uid = users_repo.create_user(db, "a@x.com", "hash1", "A")
        assert users_repo.find_id_by_email(db, "a@x.com") == uid
        pub = users_repo.find_public_by_id(db, uid)
        assert pub["email"] == "a@x.com" and "password_hash" not in pub
        assert users_repo.find_public_by_id(db, 999999) is None
        users_repo.set_reset_token(db, "a@x.com", "th", "2030-01-01T00:00:00")
        assert users_repo.find_reset(db, "a@x.com")["reset_token"] == "th"
        users_repo.complete_reset(db, "a@x.com", "hash2")
        row = users_repo.find_reset(db, "a@x.com")
        assert row["reset_token"] is None and users_repo.find_by_email(db, "a@x.com")["password_hash"] == "hash2"
    finally:
        _teardown(db, path, old)


def test_2fa_lifecycle():
    db, path, old = _db()
    try:
        uid = users_repo.create_user(db, "b@x.com", "h", "B")
        assert users_repo.get_2fa(db, uid)["twofa_enabled"] == 0
        users_repo.set_2fa_secret(db, uid, "S")
        users_repo.set_2fa_enabled(db, uid, True)
        assert users_repo.get_2fa(db, uid) == {"twofa_secret": "S", "twofa_enabled": 1}
        users_repo.clear_2fa(db, uid)
        assert users_repo.get_2fa(db, uid) == {"twofa_secret": None, "twofa_enabled": 0}
        assert users_repo.get_2fa(db, 999999) is None
    finally:
        _teardown(db, path, old)


def test_tokens_roundtrip():
    tok = tokens.mint_user_token(7, "a@x.com", SECRET, "HS256")
    payload = tokens.decode(tok, SECRET, "HS256")
    assert (payload["user_id"], payload["email"]) == (7, "a@x.com")
    assert "2fa_pending" not in payload
    temp = tokens.mint_temp_token(7, "a@x.com", SECRET, "HS256")
    assert tokens.decode(temp, SECRET, "HS256")["2fa_pending"] is True
    with pytest.raises(_jwt.ExpiredSignatureError):
        exp = _jwt.encode(
            {"user_id": 1, "exp": datetime.datetime.utcnow() - datetime.timedelta(seconds=1)},
            SECRET, algorithm="HS256",
        )
        tokens.decode(exp, SECRET, "HS256")
    with pytest.raises(_jwt.InvalidTokenError):
        tokens.decode("garbage", SECRET, "HS256")
