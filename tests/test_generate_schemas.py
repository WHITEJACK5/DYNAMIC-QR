"""Phase 2j: generate/preview schemas (unit + endpoint parity + fixes)."""
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
from core.schemas import GenerateRequest, PreviewRequest, first_error


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


def test_unit_rules():
    assert GenerateRequest.model_validate({}).type == "url"
    assert GenerateRequest.model_validate({"data": "https://x.com"}).data == {"content": "https://x.com"}
    # "false" string is properly False (old truthiness made it True)
    assert GenerateRequest.model_validate({"is_dynamic": "false"}).is_dynamic is False
    assert GenerateRequest.model_validate({"is_dynamic": "true"}).is_dynamic is True
    with pytest.raises(ValidationError) as e:
        GenerateRequest.model_validate({"fg_color": "nope"})
    assert first_error(e.value) == "Invalid color fg_color"
    with pytest.raises(ValidationError) as e:
        PreviewRequest.model_validate({"bg_color": "#ZZZ"})
    assert first_error(e.value) == "Invalid color bg_color"


def test_generate_endpoint(client):
    r = client.post("/api/generate", json={"type": "url", "data": {"url": "https://example.com"}})
    assert r.status_code == 200 and "image_base64" in r.json
    r = client.post("/api/generate", json={"type": "url", "data": {}, "fg_color": "bad"})
    assert r.status_code == 400 and r.json["error"] == "Invalid color fg_color"
    # v1 parity
    r = client.post("/api/v1/preview", json={"content": "hi"})
    assert r.status_code == 200 and "image_base64" in r.json
    r = client.post("/api/preview", json={"content": "hi", "fg_color": "bad"})
    assert r.status_code == 400 and r.json["error"] == "Invalid color fg_color"
