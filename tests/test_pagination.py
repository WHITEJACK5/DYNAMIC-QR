"""Phase 2b: GET /api/qrcodes pagination (limit/offset, backwards-compat)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.setdefault("BASE_URL", "http://localhost:5000")

import pytest

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


def _register(client, email="page@example.com"):
    r = client.post("/api/register", json={"email": email, "password": "StrongPass123!", "name": "P"})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.json["token"]


def _make(client, tok, name):
    r = client.post(
        "/api/generate",
        json={"type": "url", "data": {"url": "https://example.com/" + name}, "is_dynamic": True, "name": name},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.json["qr_id"]


def test_legacy_no_params_returns_list(client):
    tok = _register(client)
    _make(client, tok, "a")
    r = client.get("/api/qrcodes", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert isinstance(r.json, list)
    assert len(r.json) == 1


def test_paginated_envelope_and_slices(client):
    tok = _register(client)
    for n in ["a", "b", "c", "d", "e"]:
        _make(client, tok, n)
    r = client.get("/api/qrcodes?limit=2&offset=0", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json["total"] == 5
    assert r.json["limit"] == 2 and r.json["offset"] == 0
    assert len(r.json["items"]) == 2
    r2 = client.get("/api/qrcodes?limit=2&offset=2", headers={"Authorization": f"Bearer {tok}"})
    assert [i["name"] for i in r2.json["items"]] != [i["name"] for i in r.json["items"]]
    r3 = client.get("/api/qrcodes?limit=10&offset=4", headers={"Authorization": f"Bearer {tok}"})
    assert len(r3.json["items"]) == 1 and r3.json["total"] == 5


def test_pagination_validation(client):
    tok = _register(client)
    for bad in ["?limit=0", "?limit=201", "?limit=abc", "?offset=-1", "?offset=x"]:
        r = client.get(f"/api/qrcodes{bad}", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400, bad


def test_pagination_scoped_to_owner(client):
    tok_a = _register(client, "a@x.com")
    tok_b = _register(client, "b@x.com")
    _make(client, tok_a, "only-a")
    r = client.get("/api/qrcodes?limit=10", headers={"Authorization": f"Bearer {tok_b}"})
    assert r.json["total"] == 0 and r.json["items"] == []
