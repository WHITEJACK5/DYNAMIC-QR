"""Phase 2d: /api/v1 aliases proxy to same handlers; legacy carries Deprecation."""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.setdefault("BASE_URL", "http://localhost:5000")

import app as nare
from app import app


@pytest.fixture(autouse=True)
def _clear_rate():
    nare._rate_store.clear()
    yield
    nare._rate_store.clear()


@pytest.fixture
def client():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old = nare.DB_PATH
    nare.DB_PATH = tmp.name
    nare.init_db()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    nare.DB_PATH = old
    nare._rate_store.clear()


def test_health_both_versions(client):
    old = client.get("/api/health")
    new = client.get("/api/v1/health")
    assert old.status_code == 200 and new.status_code == 200
    assert old.json["status"] == new.json["status"] == "ok"
    assert old.headers.get("Deprecation") == "true"
    assert 'rel="successor-version"' in old.headers.get("Link", "")
    assert "Deprecation" not in new.headers


def test_register_login_list_parity(client):
    r = client.post("/api/register", json={"email": "leg@x.com", "password": "StrongPass123!", "name": "L"})
    assert r.status_code == 200
    assert r.headers.get("Deprecation") == "true"
    nare._rate_store.clear()
    r = client.post("/api/v1/register", json={"email": "v1@x.com", "password": "StrongPass123!", "name": "V"})
    assert r.status_code == 200
    assert "Deprecation" not in r.headers
    tok = r.json["token"]
    r = client.post("/api/v1/login", json={"email": "v1@x.com", "password": "StrongPass123!"})
    assert r.status_code == 200 and "token" in r.json
    client.post(
        "/api/v1/generate",
        json={"type": "url", "data": {"url": "https://example.com"}, "is_dynamic": True, "name": "one"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    for lp in ("/api/qrcodes", "/api/v1/qrcodes"):
        rl = client.get(lp, headers={"Authorization": f"Bearer {tok}"})
        assert rl.status_code == 200 and len(rl.json) == 1, lp
    rp = client.get("/api/v1/qrcodes?limit=1&offset=0", headers={"Authorization": f"Bearer {tok}"})
    assert rp.json["total"] == 1 and len(rp.json["items"]) == 1
