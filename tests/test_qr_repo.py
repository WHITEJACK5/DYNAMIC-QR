"""Phase 3c2: QR repository on the ORM — identical assertions on SQLite and
PostgreSQL (TEST_DATABASE_URL), so the repo is proven dialect-agnostic.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

import sqlalchemy.exc
from sqlalchemy.orm import sessionmaker

from core import migrations as mig
from core import qr_repo
from core.models import Base, Scan, User

PG_URL = os.getenv("TEST_DATABASE_URL", "").strip()


@pytest.fixture
def s(tmp_path):
    """Session on a freshly migrated DB (SQLite by default, PG when asked)."""
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
        url = f"sqlite:///{(tmp_path / 'qr.db').as_posix()}"
        mig.upgrade_to_head(url)
        eng = create_engine(url, connect_args={"check_same_thread": False})
    sess = sessionmaker(bind=eng, expire_on_commit=False)()
    yield sess
    sess.close()
    eng.dispose()


def _user(s, email="a@x.com"):
    u = User(email=email, password_hash="h", name="A")
    s.add(u)
    s.commit()
    return u.id


def _qr(s, uid, name="q", code=None):
    return qr_repo.create_full(
        s, user_id=uid, name=name, type="url", content="https://example.com",
        data_json="{}", is_dynamic=1, short_code=code or "CODE123",
        fg_color="#0A0A0A", bg_color="#FFFFFF")


def test_list_count_order_and_isolation(s):
    a, b = _user(s, "a@x.com"), _user(s, "b@x.com")
    qa1, qa2, _qb = _qr(s, a, "a1", "CODE1"), _qr(s, a, "a2", "CODE2"), _qr(s, b, "b1", "CODE3")
    assert qr_repo.count_owned(s, a) == 2
    rows = qr_repo.list_owned(s, a)
    assert [r.name for r in rows] == ["a2", "a1"]  # newest first
    page = qr_repo.list_owned(s, a, limit=1, offset=1)
    assert len(page) == 1 and page[0].name == "a1"
    assert qr_repo.get_owned(s, qa1, b) is None
    assert qr_repo.get_by_short(s, "CODE1") is not None
    assert qr_repo.get_by_short(s, "NOPE") is None
    assert qa1 and qa2


def test_to_internal_keeps_password_hash(s):
    uid = _user(s)
    qid = _qr(s, uid, "prot", "PROT001")
    qr_repo.apply_update(s, qid, uid, {"password": "Secret123!"})
    qr = qr_repo.get_owned(s, qid, uid)
    assert "password_hash" not in qr_repo.to_public(qr)
    assert qr_repo.to_internal(qr)["password_hash"]


def test_to_public_strips_secret(s):
    uid = _user(s)
    qid = _qr(s, uid)
    pub = qr_repo.to_public(qr_repo.get_owned(s, qid, uid))
    assert "password_hash" not in pub and pub["name"] == "q"


def test_apply_update_and_password_clear(s):
    uid = _user(s)
    qid = _qr(s, uid)
    out = qr_repo.apply_update(s, qid, uid, {"name": "New", "fg_color": "#00FF88", "evil": 1})
    assert out["name"] == "New" and "evil" not in out
    qr_repo.apply_update(s, qid, uid, {"password": "Secret123!"})
    assert qr_repo.get_owned(s, qid, uid).has_password == 1
    qr_repo.apply_update(s, qid, uid, {"password": ""})
    fresh = qr_repo.get_owned(s, qid, uid)
    assert fresh.has_password == 0 and fresh.password_hash is None
    out = qr_repo.apply_update(s, qid, uid, {"scan_limit": "5"})
    assert out["scan_limit"] == 5
    assert qr_repo.apply_update(s, 999999, uid, {"name": "x"}) is None


def test_delete_cascades_scans(s):
    uid = _user(s)
    qid = _qr(s, uid)
    s.add(Scan(qr_id=qid, timestamp="t", ip="1.2.3.4"))
    s.commit()
    assert qr_repo.delete_owned(s, qid, uid) is True
    assert s.query(Scan).filter(Scan.qr_id == qid).count() == 0
    assert qr_repo.delete_owned(s, qid, uid) is False


def test_mint_avoids_collision(s, monkeypatch):
    uid = _user(s)
    _qr(s, uid, "taken", code="TAKEN123")
    seq = iter(["TAKEN123", "FRESH999"])
    monkeypatch.setattr(qr_repo, "generate_short_code", lambda n=8: next(seq))
    assert qr_repo.mint_unique_short(s, 5) == "FRESH999"


def test_create_and_duplicate_roundtrip(s):
    a, b = _user(s, "a@x.com"), _user(s, "b@x.com")
    qid = qr_repo.create_full(
        s, user_id=a, name="orig", type="url", content="https://example.com",
        data_json="{}", is_dynamic=1, short_code="DUPME123", fg_color="#0A0A0A",
        bg_color="#FFFFFF")
    assert qr_repo.get_owned(s, qid, a).short_code == "DUPME123"
    nid = qr_repo.duplicate_owned(s, qid, a)
    copy = qr_repo.get_owned(s, nid, a)
    assert copy.name == "orig (Copy)" and copy.scan_count == 0
    assert copy.short_code != "DUPME123"
    assert qr_repo.duplicate_owned(s, qid, b) is None  # other user's QR
    with pytest.raises(ValueError):
        qr_repo.create_full(s, user_id=a, bogus_col=1)


def test_unique_short_code_rejected(s):
    a = _user(s)
    _qr(s, a, "first", code="UNIQ001")
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        _qr(s, a, "second", code="UNIQ001")
    s.rollback()

