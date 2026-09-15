"""Phase 2p: micro-list pagination (legacy array by default)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.setdefault("BASE_URL", "http://localhost:5000")

import pytest

import app as nare
from app import app
from core.pagination import parse_pagination


@pytest.fixture(autouse=True)
def _clear():
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


def test_parse_unit():
    assert parse_pagination({}) == (False, None, None, None)
    assert parse_pagination({"limit": "2"})[:3] == (True, 2, 0)
    assert parse_pagination({"limit": "0"})[3] == "limit must be 1..200"
    assert parse_pagination({"offset": "-1"})[3] == "offset must be >= 0"
    assert parse_pagination({"limit": "x"})[3] == "limit/offset must be integers"


def test_folders_templates_endpoints(client):
    r = client.post("/api/register", json={"email": "m@x.com", "password": "StrongPass123!", "name": "M"})
    h = {"Authorization": f"Bearer {r.json['token']}"}
    for i in range(3):
        client.post("/api/folders", json={"name": f"F{i}"}, headers=h)
        client.post("/api/templates", json={"name": f"T{i}", "config": {}}, headers=h)
    r = client.get("/api/folders", headers=h)
    assert isinstance(r.json, list) and len(r.json) == 4  # + seeded "My QR Codes"
    r = client.get("/api/folders?limit=2&offset=1", headers=h)
    assert r.json["total"] == 4 and len(r.json["items"]) == 2
    r = client.get("/api/v1/templates?limit=10", headers=h)
    assert r.json["total"] == 3
    r = client.get("/api/templates?limit=999", headers=h)
    assert r.status_code == 400
