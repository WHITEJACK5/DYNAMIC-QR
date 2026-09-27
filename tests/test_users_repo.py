"""Phase 3c1: users/folders/templates repos on the ORM.

Runs the identical assertions twice: once on SQLite (default) and once
against the real PostgreSQL container when TEST_DATABASE_URL is set. That
is the actual proof of the "SQLite -> PostgreSQL" migration for these
repositories — same code, both dialects.
"""
import datetime
import json
import os
import sys

import pytest
from sqlalchemy import create_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

import jwt as _jwt

from core import migrations as mig
from core import tokens
from core import folders_repo, templates_repo, users_repo

SECRET = "test-secret-key-for-ci-must-be-long-enough-32chars"
PG_URL = os.getenv("TEST_DATABASE_URL", "").strip()


@pytest.fixture
def session(tmp_path):
    """A Session on a schema-migrated database (SQLite or PostgreSQL).

    State is normalized first (metadata.drop_all) so the fixture does not
    depend on whatever schema a previous test left behind.
    """
    from sqlalchemy.orm import sessionmaker

    from core.models import Base

    if PG_URL:
        eng0 = create_engine(PG_URL)
        Base.metadata.drop_all(eng0)
        with eng0.connect() as conn:  # drop_all leaves the version row behind
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
            conn.commit()
        eng0.dispose()
        mig.upgrade_to_head(PG_URL)
        eng = create_engine(PG_URL)
    else:
        url = f"sqlite:///{(tmp_path / 'repos.db').as_posix()}"
        mig.upgrade_to_head(url)
        eng = create_engine(url, connect_args={"check_same_thread": False})
    s = sessionmaker(bind=eng, expire_on_commit=False)()
    yield s
    s.close()
    eng.dispose()


def test_user_lifecycle(session):
    assert users_repo.find_id_by_email(session, "a@x.com") is None
    uid = users_repo.create_user(session, "a@x.com", "hash1", "A")
    assert users_repo.find_id_by_email(session, "a@x.com") == uid
    pub = users_repo.find_public_by_id(session, uid)
    assert pub["email"] == "a@x.com" and "password_hash" not in pub
    assert users_repo.find_public_by_id(session, 999999) is None
    users_repo.set_reset_token(session, "a@x.com", "th", "2030-01-01T00:00:00")
    assert users_repo.find_reset(session, "a@x.com")["reset_token"] == "th"
    users_repo.complete_reset(session, "a@x.com", "hash2")
    row = users_repo.find_reset(session, "a@x.com")
    assert row["reset_token"] is None
    assert users_repo.find_by_email(session, "a@x.com")["password_hash"] == "hash2"


def test_2fa_lifecycle(session):
    uid = users_repo.create_user(session, "b@x.com", "h", "B")
    assert users_repo.get_2fa(session, uid)["twofa_enabled"] == 0
    users_repo.set_2fa_secret(session, uid, "S")
    users_repo.set_2fa_enabled(session, uid, True)
    assert users_repo.get_2fa(session, uid) == {"twofa_secret": "S", "twofa_enabled": 1}
    users_repo.clear_2fa(session, uid)
    assert users_repo.get_2fa(session, uid) == {"twofa_secret": None, "twofa_enabled": 0}
    assert users_repo.get_2fa(session, 999999) is None


def test_folders_and_templates(session):
    uid = users_repo.create_user(session, "c@x.com", "h", "C")
    out = folders_repo.create_for_user(session, uid, "Work")
    assert out["name"] == "Work" and out["id"]
    assert folders_repo.count_for_user(session, uid) == 1
    names = [f["name"] for f in folders_repo.list_for_user(session, uid)]
    assert names == ["Work"]
    folders_repo.create_for_user(session, uid, "Personal")
    page = folders_repo.list_for_user(session, uid, limit=1, offset=0)
    assert len(page) == 1 and folders_repo.count_for_user(session, uid) == 2

    t = templates_repo.create_for_user(session, uid, "T", {"fg": "#000"})
    assert t["name"] == "T"
    rows = templates_repo.list_for_user(session, uid)
    assert len(rows) == 1 and json.loads(rows[0]["config_json"]) == {"fg": "#000"}
    assert templates_repo.count_for_user(session, uid) == 1
    templates_repo.create_for_user(session, uid, "T2", None)
    assert templates_repo.list_for_user(session, uid, limit=1)[0]["name"] == "T2"


def test_isolation_between_users(session):
    a = users_repo.create_user(session, "iso-a@x.com", "h", "A")
    b = users_repo.create_user(session, "iso-b@x.com", "h", "B")
    folders_repo.create_for_user(session, a, "only-a")
    assert folders_repo.list_for_user(session, b) == []
    assert templates_repo.list_for_user(session, b) == []


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
