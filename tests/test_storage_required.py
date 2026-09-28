"""Phase 3d: an unconfigured/failed object store must not 500, and must not
silently write the logo to local disk.

These are HTTP-level tests: the storage contract is only really satisfied if
the route surfaces the problem to the caller.
"""
import base64
import io
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

from PIL import Image  # noqa: E402

import server as nare  # noqa: E402
from server import app  # noqa: E402
from app.services import storage  # noqa: E402

STORAGE_ENV = ("S3_BUCKET", "S3_ENDPOINT_URL", "AWS_REGION", "ALLOW_LOCAL_STORAGE")


@pytest.fixture(autouse=True)
def _no_storage_config():
    saved = {k: os.environ.pop(k, None) for k in STORAGE_ENV}
    storage.reset_state()
    yield
    for k, v in saved.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v
    storage.reset_state()


@pytest.fixture
def client():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old_path = nare.DB_PATH
    nare.DB_PATH = tmp.name
    nare.init_db()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    nare.DB_PATH = old_path
    nare._rate_store.clear()


def _logo_b64(color=(10, 20, 30)):
    buf = io.BytesIO()
    Image.new("RGBA", (32, 32), color).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _token(client):
    client.post("/api/register", json={
        "email": "logo@example.com", "password": "StrongPass123!", "name": "L"})
    r = client.post("/api/login", json={
        "email": "logo@example.com", "password": "StrongPass123!"})
    return r.get_json()["token"]


def test_upload_without_storage_returns_503_naming_the_variable(client, monkeypatch):
    monkeypatch.setattr(storage, "LOCAL_DIR",
                        os.path.join(tempfile.mkdtemp(), "uploads"))
    h = {"Authorization": f"Bearer {_token(client)}"}
    r = client.post("/api/generate", headers=h, json={
        "type": "url", "data": {"url": "https://example.com"},
        "logo_base64": _logo_b64()})
    assert r.status_code == 503, (r.status_code, r.get_json())
    err = r.get_json()["error"]
    assert "S3_BUCKET" in err and "ALLOW_LOCAL_STORAGE" in err, err


def test_upload_s3_failure_returns_503(client, monkeypatch, tmp_path):
    monkeypatch.setenv("S3_BUCKET", "nare-logos")
    monkeypatch.setattr(storage, "LOCAL_DIR", str(tmp_path / "uploads"))
    storage.reset_state()

    class BoomClient:
        def put_object(self, **kw):
            raise RuntimeError("network down")

    store = storage.S3LogoStore(bucket="nare-logos")
    store.client = BoomClient()
    monkeypatch.setattr(storage, "S3LogoStore",
                        lambda bucket, endpoint=None, region=None: store)
    storage.reset_state()

    h = {"Authorization": f"Bearer {_token(client)}"}
    r = client.post("/api/generate", headers=h, json={
        "type": "url", "data": {"url": "https://example.com"},
        "logo_base64": _logo_b64()})
    assert r.status_code == 503
    assert not os.path.exists(tmp_path / "uploads"), "logo leaked to local disk"
    assert not list(tmp_path.iterdir()), "anything written to local disk"


def test_generate_without_a_logo_still_works(client):
    """Storage being broken must not break QR generation that needs no logo."""
    h = {"Authorization": f"Bearer {_token(client)}"}
    r = client.post("/api/generate", headers=h, json={
        "type": "url", "data": {"url": "https://example.com"}})
    assert r.status_code == 200, (r.status_code, r.get_json())
    assert r.get_json()["image_base64"].startswith("data:image/png;base64,")
