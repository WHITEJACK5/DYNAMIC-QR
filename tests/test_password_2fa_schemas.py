"""Phase 2k: forgot/reset/2FA schemas preserve every legacy 400 string."""
import os
import sys
import tempfile

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.setdefault("BASE_URL", "http://localhost:5000")

import app as nare
from app import app
from core.schemas import ForgotRequest, Login2FARequest, ResetRequest, TwoFACodeRequest, first_error


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


def test_unit_messages():
    with pytest.raises(ValidationError) as e:
        ForgotRequest.model_validate({"email": "bad"})
    assert first_error(e.value) == "Valid email required"
    with pytest.raises(ValidationError) as e:
        ForgotRequest.model_validate({})
    assert first_error(e.value) == "Valid email required"
    with pytest.raises(ValidationError) as e:
        ResetRequest.model_validate({"email": "a@b.com"})
    assert first_error(e.value) == "email, token and new_password required"
    # password alias still accepted
    r = ResetRequest.model_validate({"email": "a@b.com", "token": "t", "password": "StrongPass123!"})
    assert r.new_password == "StrongPass123!"
    with pytest.raises(ValidationError) as e:
        ResetRequest.model_validate({"email": "a@b.com", "token": "t", "new_password": "weak"})
    assert "at least 8" in first_error(e.value)
    with pytest.raises(ValidationError) as e:
        TwoFACodeRequest.model_validate({"code": "  "})
    assert first_error(e.value) == "code required"
    with pytest.raises(ValidationError) as e:
        Login2FARequest.model_validate({"temp_token": "t"})
    assert first_error(e.value) == "temp_token and code required"


def test_endpoint_parity(client):
    r = client.post("/api/forgot-password", json={"email": "bad"})
    assert r.status_code == 400 and r.json["error"] == "Valid email required"
    r = client.post("/api/forgot-password", json={"email": "nobody@x.com"})
    assert r.status_code == 200  # no enumeration
    client.post("/api/register", json={"email": "r@x.com", "password": "StrongPass123!", "name": "R"})
    r = client.post("/api/reset-password", json={"email": "r@x.com", "token": "t"})
    assert r.status_code == 400 and r.json["error"] == "email, token and new_password required"
    # full reset round-trip still works
    nare._rate_store.clear()
    r = client.post("/api/forgot-password", json={"email": "r@x.com"})
    tok = r.json["reset_token"]
    nare._rate_store.clear()
    r = client.post("/api/reset-password", json={"email": "r@x.com", "token": tok, "new_password": "NewStrong123!"})
    assert r.status_code == 200
    nare._rate_store.clear()
    r = client.post("/api/login", json={"email": "r@x.com", "password": "NewStrong123!"})
    assert r.status_code == 200
    # 2FA code endpoints keep their 400s
    r = client.post("/api/2fa/login-verify", json={"temp_token": "", "code": ""})
    assert r.status_code == 400 and r.json["error"] == "temp_token and code required"
