"""Phase 2f: rate limiting is Flask-Limiter, Redis-backed when REDIS_URL is set.

These assert the real mechanism (a live Flask app making real requests), not a
stand-in for it.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.setdefault("BASE_URL", "http://localhost:5000")
os.environ.pop("REDIS_URL", None)

import server as nare
from app import ratelimit
from server import app as flask_app


@pytest.fixture(autouse=True)
def _reset():
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
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    nare.DB_PATH = old


def test_limiter_is_flask_limiter():
    from flask_limiter import Limiter

    assert isinstance(nare.limiter, Limiter)


def test_storage_uri_follows_redis_url():
    os.environ.pop("REDIS_URL", None)
    assert ratelimit.storage_uri() == "memory://"
    os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/0"
    assert ratelimit.storage_uri() == "redis://127.0.0.1:6379/0"
    os.environ.pop("REDIS_URL", None)


def test_login_is_rate_limited_to_five_per_minute(client):
    codes = []
    for _ in range(8):
        r = client.post("/api/login", json={"email": "a@b.com", "password": "WrongPass123!"})
        codes.append(r.status_code)
    assert codes[:5] == [401] * 5, codes
    assert codes[5:] == [429] * 3, codes
    assert "Too many requests" in client.post(
        "/api/login", json={"email": "a@b.com", "password": "x"}
    ).json["error"]


def test_rate_limit_headers_are_emitted(client):
    r = client.post("/api/login", json={"email": "a@b.com", "password": "WrongPass123!"})
    assert r.status_code == 401
    assert r.headers.get("X-RateLimit-Limit") == "5"
    assert int(r.headers.get("X-RateLimit-Remaining")) <= 4


def test_buckets_are_independent_per_endpoint(client):
    # burn the login bucket
    for _ in range(6):
        client.post("/api/login", json={"email": "a@b.com", "password": "WrongPass123!"})
    assert client.post("/api/login", json={"email": "a@b.com", "password": "x"}).status_code == 429
    # forgot-password has its own 3/10min bucket and is unaffected
    r = client.post("/api/forgot-password", json={"email": "nobody@x.com"})
    assert r.status_code == 200
    # and generate is not blocked either
    r = client.post("/api/generate", json={"type": "url", "data": {"url": "https://example.com"}})
    assert r.status_code == 200


def test_reset_clears_the_counters(client):
    for _ in range(6):
        client.post("/api/login", json={"email": "a@b.com", "password": "x"})
    assert client.post("/api/login", json={"email": "a@b.com", "password": "x"}).status_code == 429
    nare._rate_store.clear()
    r = client.post("/api/login", json={"email": "a@b.com", "password": "x"})
    assert r.status_code == 401
