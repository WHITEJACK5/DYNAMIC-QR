"""Phase 2h: cache unit behavior + endpoint HIT/MISS headers."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.setdefault("BASE_URL", "http://localhost:5000")
os.environ.pop("REDIS_URL", None)

import pytest

import app as nare
from app import app
from core import cache


@pytest.fixture(autouse=True)
def _clean():
    os.environ.pop("REDIS_URL", None)
    cache.reset_state()
    nare._rate_store.clear()
    yield
    cache.reset_state()
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


def test_key_deterministic():
    a = cache.key_for("p", {"x": 1, "y": 2})
    b = cache.key_for("p", {"y": 2, "x": 1})
    assert a == b
    assert cache.key_for("p", {"x": 2}) != a


def test_memory_ttl_expiry():
    cache.cache_set("k", "v", 1)
    assert cache.cache_get("k") == "v"
    time.sleep(1.2)
    assert cache.cache_get("k") is None


def test_redis_down_still_caches():
    os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"
    cache.cache_set("k", "v", 60)
    assert cache.cache_get("k") == "v"


def test_preview_hit_header(client):
    body = {"content": "https://example.com/cache-me", "fg_color": "#0A0A0A", "bg_color": "#FFFFFF"}
    r1 = client.post("/api/preview", json=body)
    assert r1.status_code == 200 and r1.headers.get("X-Cache") == "MISS"
    r2 = client.post("/api/preview", json=body)
    assert r2.headers.get("X-Cache") == "HIT"
    assert r2.json["image_base64"] == r1.json["image_base64"]


def test_analytics_hit_header(client):
    r = client.post("/api/register", json={"email": "c@x.com", "password": "StrongPass123!", "name": "C"})
    tok = r.json["token"]
    h = {"Authorization": f"Bearer {tok}"}
    r1 = client.get("/api/analytics/overview", headers=h)
    assert r1.headers.get("X-Cache") == "MISS"
    r2 = client.get("/api/analytics/overview", headers=h)
    assert r2.headers.get("X-Cache") == "HIT"
    assert r2.json == r1.json
