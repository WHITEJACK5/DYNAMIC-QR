"""Phase 2i: update/folder/template schemas preserve legacy 400 strings."""
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
from core.schemas import FolderCreateRequest, QRUpdateRequest, TemplateCreateRequest, first_error


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


def _token(client, email="u@x.com"):
    r = client.post("/api/register", json={"email": email, "password": "StrongPass123!", "name": "U"})
    assert r.status_code == 200
    return r.json["token"]


def _mk(client, tok, name="q"):
    r = client.post(
        "/api/generate",
        json={"type": "url", "data": {"url": "https://example.com"}, "is_dynamic": True, "name": name},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    return r.json["qr_id"]


def test_unit_messages():
    with pytest.raises(ValidationError) as e:
        QRUpdateRequest.model_validate({"fg_color": "nope"})
    assert first_error(e.value) == "Invalid color fg_color"
    with pytest.raises(ValidationError) as e:
        QRUpdateRequest.model_validate({"password": "abc"})
    assert first_error(e.value) == "Password too short"
    with pytest.raises(ValidationError) as e:
        QRUpdateRequest.model_validate({"scan_limit": 0})
    assert first_error(e.value) == "Invalid scan_limit"
    assert QRUpdateRequest.model_validate({}).model_dump(exclude_none=True) == {}
    with pytest.raises(ValidationError) as e:
        FolderCreateRequest.model_validate({"name": "x" * 61})
    assert first_error(e.value) == "Invalid folder name"
    with pytest.raises(ValidationError) as e:
        TemplateCreateRequest.model_validate({"config": {"d": "x" * 10001}})
    assert first_error(e.value) == "Config too large"


def test_put_endpoint_parity(client):
    tok = _token(client)
    qid = _mk(client, tok)
    h = {"Authorization": f"Bearer {tok}"}
    r = client.put(f"/api/qrcodes/{qid}", json={"fg_color": "bad"}, headers=h)
    assert r.status_code == 400 and r.json["error"] == "Invalid color fg_color"
    r = client.put(f"/api/qrcodes/{qid}", json={"password": "abc"}, headers=h)
    assert r.status_code == 400 and r.json["error"] == "Password too short"
    r = client.put(f"/api/qrcodes/{qid}", json={"scan_limit": -1}, headers=h)
    assert r.status_code == 400 and r.json["error"] == "Invalid scan_limit"
    r = client.put(f"/api/v1/qrcodes/{qid}", json={"name": "New"}, headers=h)
    assert r.status_code == 200 and r.json["name"] == "New"


def test_folder_template_parity(client):
    tok = _token(client, "f@x.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/api/folders", json={"name": ""}, headers=h)
    assert r.status_code == 400 and r.json["error"] == "Invalid folder name"
    r = client.post("/api/folders", json={"name": "Work"}, headers=h)
    assert r.status_code == 200 and r.json["name"] == "Work"
    r = client.post("/api/templates", json={"name": "T", "config": {"d": "x" * 10001}}, headers=h)
    assert r.status_code == 400 and r.json["error"] == "Config too large"
