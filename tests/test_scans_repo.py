"""Phase 3c3: scans repo on the ORM — same assertions on SQLite and PostgreSQL."""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

from app import migrations as mig
from app.repositories import scans_repo
from app.models import Base, User

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
        url = f"sqlite:///{(tmp_path / 'scans.db').as_posix()}"
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


def _qr(s, uid, name="q", code="SCAN123"):
    from app.repositories import qr_repo

    return qr_repo.create_full(
        s, user_id=uid, name=name, type="url", content="https://example.com",
        data_json="{}", is_dynamic=1, short_code=code)


def test_record_and_geo(s):
    uid = _user(s)
    qid = _qr(s, uid)
    sid = scans_repo.record_scan(s, qid, "2026-01-01T00:00:00", "9.9.9.9", "ua", "Mobile", "Chrome", "Android")
    assert sid
    from app.models import Scan

    row = s.get(Scan, sid)
    assert (row.country, row.city) == ("Pending", "Pending")
    from app.repositories import qr_repo

    assert qr_repo.get_owned(s, qid, uid).scan_count == 1
    scans_repo.update_geo(s, sid, "Testland", "Testville")
    assert s.get(Scan, sid).country == "Testland"
    # missing scan id is a no-op, not a crash
    scans_repo.update_geo(s, 999999, "X", "Y")


def test_overview_scoped_and_shaped(s):
    a, b = _user(s, "a@x.com"), _user(s, "b@x.com")
    qa, qb = _qr(s, a, "a", "SCANA1"), _qr(s, b, "b", "SCANB1")
    scans_repo.record_scan(s, qa, "2026-02-01 10:00:00", "1.1.1.1", "u", "Mobile", "Chrome", "X")
    scans_repo.record_scan(s, qb, "2026-02-01 11:00:00", "2.2.2.2", "u", "Desktop", "Safari", "Y")
    ov = scans_repo.overview_for_user(s, a)
    assert ov["total_qrs"] == 1 and ov["total_scans"] == 1
    assert ov["timeline"] == [{"d": "2026-02-01", "c": 1}]
    assert ov["devices"] == [{"device": "Mobile", "c": 1}]
    assert [t["name"] for t in ov["top"]] == ["a"]
    d = scans_repo.detail_for_qr(s, qa)
    assert len(d["scans"]) == 1 and d["timeline"][0]["c"] == 1
    assert d["countries"] == [{"country": "Pending", "c": 1}]
