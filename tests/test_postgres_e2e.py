"""Phase 3c4: the FULL app on PostgreSQL — the actual "SQLite -> PostgreSQL
migration" proof.

Skipped unless DATABASE_URL is set, so CI/local stay SQLite-only and the
skip is honest rather than a fake pass. Run it with:

    DATABASE_URL=postgresql+psycopg2://user:pw@host:5432/db \
        pytest tests/test_postgres_e2e.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DB_URL = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DB_URL.startswith("postgresql"),
    reason="DATABASE_URL not set to a PostgreSQL URL",
)

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

import server as DR  # noqa: E402  (must come after DATABASE_URL is set)
from server import app as flask_app  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_rate():
    DR._rate_store.clear()
    yield
    DR._rate_store.clear()


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def _reset_schema():
    """
    Drop everything and migrate to head, explicitly.

    Deliberately not init_db(): importing server already runs init_db() at
    module scope, so the two race and the version row could survive the
    reset, leaving init_db() convinced the database was migrated. Doing it
    explicitly here makes the test self-contained regardless of import-time
    side effects — which is the right property for a database test.
    """
    from app import migrations as mig
    from app.db import get_engine
    from app.models import Base

    eng = get_engine()
    Base.metadata.drop_all(eng)
    with eng.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    mig.upgrade_to_head()
    assert mig.current_revision() == mig.head_revision()
    assert mig.user_tables(), "reset left the database without tables"


def test_full_stack_on_postgres(client):
    _reset_schema()
    assert DR.get_session().execute(
        __import__("sqlalchemy").text("select version()")
    ).scalar().startswith("PostgreSQL")

    r = client.post("/api/register", json={"email": "pg@x.com", "password": "StrongPass123!", "name": "PG"})
    assert r.status_code == 200, r.get_data(as_text=True)
    _verify("pg@x.com")   # Phase 4d: dynamic QRs need a verified address
    tok = r.json["token"]
    h = {"Authorization": f"Bearer {tok}"}

    r = client.post("/api/generate", json={
        "type": "url", "data": {"url": "https://example.com/pg"},
        "is_dynamic": True, "name": "PGQR"}, headers=h)
    assert r.status_code == 200, r.get_data(as_text=True)
    code = r.json["short_code"]
    qid = r.json["qr_id"]
    assert code and qid

    # list + pagination envelope
    r = client.get("/api/qrcodes?limit=10", headers=h)
    assert r.status_code == 200 and r.json["total"] == 1

    # scan it: 302 + tracked
    r = client.get(f"/r/{code}", follow_redirects=False,
                   headers={"User-Agent": "Mozilla/5.0 (Linux; Android 10)"})
    assert r.status_code == 302
    assert r.headers["Location"] == "https://example.com/pg"

    # edit
    r = client.put(f"/api/v1/qrcodes/{qid}", json={"name": "Renamed"}, headers=h)
    assert r.status_code == 200 and r.json["name"] == "Renamed"

    # analytics reflect the scan
    r = client.get("/api/analytics/overview", headers=h)
    assert r.status_code == 200 and r.json["total_qrs"] == 1 and r.json["total_scans"] == 1
    r = client.get(f"/api/qrcodes/{qid}/analytics", headers=h)
    assert r.status_code == 200 and len(r.json["scans"]) == 1

    # folders/templates + duplicate + delete
    assert client.post("/api/folders", json={"name": "Work"}, headers=h).status_code == 200
    assert client.post("/api/templates", json={"name": "T", "config": {}}, headers=h).status_code == 200
    r = client.post(f"/api/qrcodes/{qid}/duplicate", headers=h)
    assert r.status_code == 200
    assert client.delete(f"/api/qrcodes/{qid}", headers=h).status_code == 200

    # login works
    r = client.post("/api/login", json={"email": "pg@x.com", "password": "StrongPass123!"})
    assert r.status_code == 200 and "token" in r.json


def _verify(email):
    """
    Confirm an address for a test that is not about verification.

    Phase 4d gates dynamic QR creation behind a verified email, and this
    suite predates it — it was silently returning 403 and only surfaced when
    the PostgreSQL legs were run.     The verification flow itself is covered in
    test_email_verification.py (in-process) and test_e2e_playwright.py
    (through real SMTP).
    """
    from sqlalchemy import text

    from app.db import get_engine
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("UPDATE users SET email_verified = 1 WHERE email = :e"),
                     {"e": email})


def test_cross_user_isolation_on_postgres(client):
    _reset_schema()
    a = client.post("/api/register", json={"email": "a@x.com", "password": "StrongPass123!", "name": "A"}).json
    b = client.post("/api/register", json={"email": "b@x.com", "password": "StrongPass123!", "name": "B"}).json
    _verify("a@x.com")
    ha, hb = {"Authorization": f"Bearer {a['token']}"}, {"Authorization": f"Bearer {b['token']}"}
    qid = client.post("/api/generate", json={
        "type": "url", "data": {"url": "https://example.com/a"}, "is_dynamic": True, "name": "AQR"},
        headers=ha).json["qr_id"]
    for method, path in (("get", f"/api/qrcodes/{qid}"), ("put", f"/api/qrcodes/{qid}"),
                         ("delete", f"/api/qrcodes/{qid}")):
        kwargs = {"headers": hb}
        if method == "put":
            kwargs["json"] = {"name": "hijack"}
        r = getattr(client, method)(path, **kwargs)
        assert r.status_code in (403, 404), f"{method} {path} -> {r.status_code}"
    assert client.get(f"/api/qrcodes/{qid}", headers=ha).status_code == 200
