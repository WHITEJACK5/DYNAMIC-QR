"""Phase 2c: auth schema tests (unit + endpoint parity)."""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.setdefault("BASE_URL", "http://localhost:5000")

from pydantic import ValidationError

import app as nare
from app import app
from core.schemas import LoginRequest, RegisterRequest, first_error


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


def test_register_schema_normalizes_and_enforces():
    r = RegisterRequest.model_validate({"email": "  YOU@Nare.Local ", "password": "StrongPass123!", "name": "Y"})
    assert r.email == "you@nare.local"
    with pytest.raises(ValidationError) as e:
        RegisterRequest.model_validate({"email": "bad", "password": "StrongPass123!"})
    assert first_error(e.value) == "Invalid email format"
    with pytest.raises(ValidationError) as e:
        RegisterRequest.model_validate({"email": "a@b.com", "password": "short"})
    assert "at least 8" in first_error(e.value)
    with pytest.raises(ValidationError) as e:
        RegisterRequest.model_validate({})
    assert first_error(e.value) == "Email and password required"


def test_login_schema_shape_only_no_strength_gate():
    # Weak but present password passes shape validation (401 comes from handler, not 400)
    r = LoginRequest.model_validate({"email": "A@B.COM", "password": "whatever"})
    assert r.email == "a@b.com"
    with pytest.raises(ValidationError) as e:
        LoginRequest.model_validate({"email": "a@b.com"})
    assert first_error(e.value) == "Email and password required"


def test_endpoint_parity(client):
    # Weak register -> 400 with legacy message
    r = client.post("/api/register", json={"email": "bad", "password": "123"})
    assert r.status_code == 400
    assert "at least 8" in r.json["error"].lower() or "invalid email" in r.json["error"].lower()
    # Happy register -> 200 token
    r = client.post("/api/register", json={"email": "s@x.com", "password": "StrongPass123!", "name": "S"})
    assert r.status_code == 200 and "token" in r.json
    # Empty login -> 400 legacy string
    r = client.post("/api/login", json={"email": "", "password": ""})
    assert r.status_code == 400 and r.json["error"] == "Email and password required"
    # Wrong password -> 401 (not 400): strength never gates login
    r = client.post("/api/login", json={"email": "s@x.com", "password": "WrongPass123!"})
    assert r.status_code == 401
    # Correct -> 200
    r = client.post("/api/login", json={"email": "s@x.com", "password": "StrongPass123!"})
    assert r.status_code == 200 and "token" in r.json
