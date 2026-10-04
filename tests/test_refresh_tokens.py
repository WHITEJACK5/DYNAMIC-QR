"""Phase 4c: 15-minute access tokens, refresh rotation, Redis-backed revocation.

The directive: "Add refresh tokens with short-lived (15 min) access tokens,
and a token revocation list (Redis-backed) so compromised tokens can actually
be invalidated before natural expiry."

Each test below maps to one clause of that sentence.
"""
import datetime
import os
import sys
import tempfile
import time

import jwt
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

import server as DR  # noqa: E402
from server import app  # noqa: E402
from app import cache  # noqa: E402
from app.config import JWT_ALGO, JWT_SECRET  # noqa: E402
from app.services import tokens as T  # noqa: E402

CREDS = {"email": "refresh@example.com", "password": "StrongPass123!"}


@pytest.fixture(autouse=True)
def _clean_revocation():
    T.reset_state()
    cache.reset_state()
    yield
    T.reset_state()
    cache.reset_state()


@pytest.fixture
def client():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old_path = DR.DB_PATH
    DR.DB_PATH = tmp.name
    DR.init_db()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    DR.DB_PATH = old_path
    DR._rate_store.clear()


@pytest.fixture
def logged_in(client):
    client.post("/api/register", json={"email": CREDS["email"],
                                       "password": CREDS["password"],
                                       "name": "R"})
    r = client.post("/api/login", json=CREDS)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _auth(pair):
    return {"Authorization": f"Bearer {pair['access_token']}"}


# ------------------------------------------------- short-lived access tokens
def test_access_token_lives_exactly_fifteen_minutes():
    tok = T.mint_access_token(1, "a@x.com", JWT_SECRET, JWT_ALGO)
    p = T.decode(tok, JWT_SECRET, JWT_ALGO)
    assert p["typ"] == T.ACCESS
    assert p["exp"] - p["iat"] == 15 * 60


def test_refresh_token_is_longer_lived_than_access():
    a = T.decode(T.mint_access_token(1, "a@x.com", JWT_SECRET, JWT_ALGO),
                 JWT_SECRET, JWT_ALGO)
    r = T.decode(T.mint_refresh_token(1, "a@x.com", JWT_SECRET, JWT_ALGO),
                 JWT_SECRET, JWT_ALGO)
    assert r["exp"] - r["iat"] > a["exp"] - a["iat"]


def test_login_returns_a_pair_and_declares_the_lifetime(logged_in):
    assert logged_in["access_token"]
    assert logged_in["refresh_token"]
    assert logged_in["access_token"] != logged_in["refresh_token"]
    assert logged_in["expires_in"] == 900
    # "token" remains for existing clients
    assert logged_in["token"] == logged_in["access_token"]


def test_access_token_authenticates_normally(client, logged_in):
    assert client.get("/api/qrcodes", headers=_auth(logged_in)).status_code == 200


# --------------------------------------------------------- the refresh flow
def test_refresh_issues_a_new_pair(client, logged_in):
    r = client.post("/api/refresh", json={"refresh_token": logged_in["refresh_token"]})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["access_token"] and body["refresh_token"]
    assert body["access_token"] != logged_in["access_token"]
    # and the new access token works
    assert client.get("/api/qrcodes",
                      headers={"Authorization": f"Bearer {body['access_token']}"}).status_code == 200


def test_old_refresh_token_is_revoked_by_rotation(client, logged_in):
    """A captured refresh token must be usable at most once."""
    first = client.post("/api/refresh", json={"refresh_token": logged_in["refresh_token"]})
    assert first.status_code == 200
    replay = client.post("/api/refresh", json={"refresh_token": logged_in["refresh_token"]})
    assert replay.status_code == 401
    assert "revoked" in replay.get_json()["error"].lower()


def test_access_token_cannot_be_used_to_refresh(client, logged_in):
    """Otherwise a 15-minute token could mint itself a 30-day credential."""
    r = client.post("/api/refresh", json={"refresh_token": logged_in["access_token"]})
    assert r.status_code == 401
    assert r.get_json()["error"] == "Not a refresh token"


def test_refresh_rejects_garbage_and_missing_token(client):
    assert client.post("/api/refresh", json={"refresh_token": "nope"}).status_code == 401
    assert client.post("/api/refresh", json={}).status_code == 400


def test_refresh_rejects_expired_refresh_token(client, logged_in):
    expired = jwt.encode({
        "user_id": 1, "email": CREDS["email"], "typ": T.REFRESH, "jti": "x",
        "exp": datetime.datetime.utcnow() - datetime.timedelta(seconds=1),
    }, JWT_SECRET, algorithm=JWT_ALGO)
    r = client.post("/api/refresh", json={"refresh_token": expired})
    assert r.status_code == 401


# -------------------------------------------------- revocation really revokes
def test_logout_invalidates_the_access_token_before_expiry(client, logged_in):
    r = client.post("/api/logout", headers=_auth(logged_in))
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["revoked"] >= 1
    after = client.get("/api/qrcodes", headers=_auth(logged_in))
    assert after.status_code == 401
    assert after.get_json()["error"] == "Token revoked"


def test_logout_also_revokes_the_refresh_token(client, logged_in):
    client.post("/api/logout", headers=_auth(logged_in),
                json={"refresh_token": logged_in["refresh_token"]})
    r = client.post("/api/refresh", json={"refresh_token": logged_in["refresh_token"]})
    assert r.status_code == 401


def test_revocation_beats_a_valid_signature(client, logged_in):
    """The whole point: invalidation before natural expiry."""
    token = logged_in["access_token"]
    assert client.get("/api/qrcodes", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    T.revoke(T.decode(token, JWT_SECRET, JWT_ALGO))
    assert client.get("/api/qrcodes", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_refresh_token_cannot_authenticate_a_normal_request(client, logged_in):
    r = client.get("/api/qrcodes",
                   headers={"Authorization": f"Bearer {logged_in['refresh_token']}"})
    assert r.status_code == 401
    assert "refresh" in r.get_json()["error"].lower()


def test_logout_is_idempotent(client, logged_in):
    assert client.post("/api/logout", headers=_auth(logged_in)).status_code == 200
    assert client.post("/api/logout", headers=_auth(logged_in)).status_code == 200


# ---------------------------------------------------- Redis is the denylist
class FakeRedis:
    """Records what the code writes, so 'Redis-backed' is actually asserted."""

    def __init__(self):
        self.store = {}
        self.expiries = {}

    def setex(self, key, ttl, value):
        self.store[key] = value
        self.expiries[key] = ttl

    def exists(self, key):
        return 1 if key in self.store else 0

    def get(self, key):
        v = self.store.get(key)
        return v.encode() if isinstance(v, str) else v

    def delete(self, key):
        self.store.pop(key, None)


def test_revocation_is_written_to_redis_when_configured(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    token = T.mint_access_token(1, "a@x.com", JWT_SECRET, JWT_ALGO)
    payload = T.decode(token, JWT_SECRET, JWT_ALGO)
    assert T.revoke(payload) is True
    key = f"revoked:{payload['jti']}"
    assert key in fake.store, "revocation did not reach Redis"
    # TTL must match the token's remaining lifetime, so the denylist self-cleans
    assert 0 < fake.expiries[key] <= 900
    assert T.is_revoked(payload["jti"]) is True


def test_unrevoked_token_is_not_in_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    token = T.mint_access_token(1, "a@x.com", JWT_SECRET, JWT_ALGO)
    p = T.decode(token, JWT_SECRET, JWT_ALGO)
    assert T.is_revoked(p["jti"]) is False
    assert fake.store == {}


def test_revoking_an_expired_token_is_a_noop():
    """An expired token is already rejected by the signature check, so no
    denylist entry is created for it."""
    past = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
    assert T.revoke({"jti": "old", "exp": past}) is False


def test_revoking_an_already_expired_token_needs_no_entry(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    past = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
    assert T.revoke({"jti": "old", "exp": past}) is False
    assert fake.store == {}


def test_memory_fallback_still_revokes_when_redis_is_absent(monkeypatch):
    monkeypatch.setattr(cache, "get_redis", lambda: None)
    token = T.mint_access_token(1, "a@x.com", JWT_SECRET, JWT_ALGO)
    p = T.decode(token, JWT_SECRET, JWT_ALGO)
    assert T.revoke(p) is True
    assert T.is_revoked(p["jti"]) is True
    # and it expires on its own
    T._revoked[p["jti"]] = time.time() - 1
    assert T.is_revoked(p["jti"]) is False


def test_every_token_carries_a_unique_jti():
    js = {T.decode(T.mint_access_token(1, "a@x.com", JWT_SECRET, JWT_ALGO),
                   JWT_SECRET, JWT_ALGO)["jti"] for _ in range(50)}
    assert len(js) == 50
