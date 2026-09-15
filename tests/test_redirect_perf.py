"""Phase 1e: redirect must return before geo-IP/analytics work finishes.

Regression test for the blocking redirect: get_geo_from_ip() used to run two
chained external HTTP calls (2s timeout each) inline in GET /r/<code>, so a
slow geo service delayed every scan redirect by up to 4s+.

Now: the scan row is written with country/city "Pending", the 302 is sent,
and geo enrichment runs in a background thread afterwards.
"""
import os
import sqlite3
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault(
    "SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.setdefault("BASE_URL", "http://localhost:5000")

import app as nare
from app import app


@pytest.fixture(autouse=True)
def clear_rate_store():
    nare._rate_store.clear()
    yield
    nare._rate_store.clear()


@pytest.fixture
def client():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old_path = nare.DB_PATH
    nare.DB_PATH = tmp.name
    nare.init_db()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, tmp.name
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    nare.DB_PATH = old_path
    nare._rate_store.clear()


def _register_and_dynamic_qr(client, email, qr_type="url", data=None):
    r = client.post("/api/register", json={
        "email": email, "password": "StrongPass123!", "name": "Perf"})
    assert r.status_code == 200, r.get_json()
    tok = r.get_json()["token"]
    r = client.post("/api/generate", json={
        "type": qr_type, "data": data or {"url": "https://example.com/x"},
        "is_dynamic": True, "name": "PerfQR"},
        headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.get_json()
    return tok, r.get_json()["short_code"]


def _scan_country(db_path, short_code):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        cur = db.cursor()
        cur.execute("SELECT id FROM qrcodes WHERE short_code=?", (short_code,))
        qr = cur.fetchone()
        cur.execute("SELECT country, city FROM scans WHERE qr_id=? "
                    "ORDER BY id DESC LIMIT 1", (qr["id"],))
        row = cur.fetchone()
        return (row["country"], row["city"]) if row else (None, None)
    finally:
        db.close()


def test_redirect_returns_before_slow_geo_completes(client, monkeypatch):
    client, db_path = client

    def slow_geo(ip):
        time.sleep(4)
        return {"country": "Testland", "city": "Testville"}

    monkeypatch.setattr(nare, "get_geo_from_ip", slow_geo)
    _, code = _register_and_dynamic_qr(client, "perf1@example.com")

    start = time.monotonic()
    r = client.get(f"/r/{code}", follow_redirects=False)
    elapsed = time.monotonic() - start

    assert r.status_code == 302
    assert elapsed < 2.0, f"redirect blocked on geo: {elapsed:.2f}s"

    # Scan was recorded immediately (Pending), enrichment lands async.
    country, _ = _scan_country(db_path, code)
    assert country in ("Pending", "Testland")
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        country, city = _scan_country(db_path, code)
        if country == "Testland" and city == "Testville":
            break
        time.sleep(0.2)
    assert country == "Testland", f"async enrichment never landed: {country}"


def test_smart_resolve_needs_no_network(client, monkeypatch):
    client, _ = client

    def no_network(*a, **k):
        raise AssertionError("redirect path must not do network I/O")

    monkeypatch.setattr(nare.requests, "get", no_network)
    _, code = _register_and_dynamic_qr(
        client, "perf2@example.com", qr_type="smarturl",
        data={"primaryUrl": "https://example.com/default",
              "rules": "os:android -> https://play.google.com\n"
                       "os:ios -> https://apps.apple.com"})

    r = client.get("/r/" + code, follow_redirects=False,
                   headers={"User-Agent": "Mozilla/5.0 (Linux; Android 10)"})
    assert r.status_code == 302
    assert "play.google.com" in r.headers["Location"]

    r = client.get("/r/" + code, follow_redirects=False,
                   headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0)"})
    assert r.status_code == 302
    assert "apps.apple.com" in r.headers["Location"]


def test_country_rule_falls_back_without_geo(client, monkeypatch):
    """Documents the tradeoff: country: rules need async geo, so on the
    redirect itself they fall back to primary. Device/os/lang rules are
    unaffected (see test above)."""
    client, _ = client

    def no_network(*a, **k):
        raise AssertionError("redirect path must not do network I/O")

    monkeypatch.setattr(nare.requests, "get", no_network)
    _, code = _register_and_dynamic_qr(
        client, "perf3@example.com", qr_type="smarturl",
        data={"primaryUrl": "https://example.com/default",
              "rules": "country:Testland -> https://example.com/testland"})

    r = client.get("/r/" + code, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"] == "https://example.com/default"
