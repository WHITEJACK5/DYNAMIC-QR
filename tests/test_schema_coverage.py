"""Every mutating route has an explicit input schema (Phase 2 completeness)."""
import io
import os
import sys
import tempfile

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.setdefault("BASE_URL", "http://localhost:5000")

import server as nare
from app.schemas import BulkFormRequest, GenerateRequest
from server import app as flask_app


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
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    nare.DB_PATH = old
    nare._rate_store.clear()


def test_generate_schema_covers_access_control():
    r = GenerateRequest.model_validate(
        {"password": "S3cret!", "scan_limit": "25", "expiry_date": "2030-01-01T00:00:00"}
    )
    assert (r.password, r.scan_limit, r.expiry_date) == ("S3cret!", 25, "2030-01-01T00:00:00")
    # Rejected rather than coerced to "no limit" (Phase 5 audit).
    #
    # This previously asserted the opposite: junk and non-positive became
    # None, on the reasoning "never a 500". A merchant whose scan_limit
    # arrived mangled silently got an UNLIMITED QR — invisible, and the
    # opposite of what a limit is for. Pydantic turns the bad value into a
    # clean 400, so the no-500 justification did not hold.
    # The JSON and multipart paths now share this rule, so neither can be
    # the looser one.
    from pydantic import ValidationError

    for junk in ("abc", -3, 0, "99999999999999999999"):
        with pytest.raises(ValidationError):
            GenerateRequest.model_validate({"scan_limit": junk})
    # absent is still absent, not an error
    assert GenerateRequest.model_validate({}).scan_limit is None
    assert GenerateRequest.model_validate({"scan_limit": ""}).scan_limit is None
    assert GenerateRequest.model_validate({"scan_limit": 25}).scan_limit == 25
    assert GenerateRequest.model_validate({}).password is None


def test_bulk_form_schema():
    b = BulkFormRequest.model_validate({"type": "url", "fg_color": "#000000", "bg_color": "#FFFFFF"})
    assert (b.type, b.fg_color, b.bg_color) == ("url", "#000000", "#FFFFFF")
    assert BulkFormRequest.model_validate({}).type == "url"
    with pytest.raises(ValidationError):
        BulkFormRequest.model_validate({"fg_color": "not-a-color"})


def test_generate_endpoint_accepts_protection_fields(client):
    r = client.post("/api/register", json={"email": "prot@x.com", "password": "StrongPass123!", "name": "P"})
    from conftest import mark_verified
    mark_verified("prot@x.com")  # Phase 4d: dynamic QRs need a verified address
    tok = r.json["token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/api/generate", json={
        "type": "url", "data": {"url": "https://example.com/protected"},
        "is_dynamic": True, "name": "Protected",
        "password": "MyS3cret!", "scan_limit": 3, "expiry_date": "2030-01-01T00:00:00",
    }, headers=h)
    assert r.status_code == 200, r.get_data(as_text=True)
    code = r.json["short_code"]
    # GET is refused without the password (POST-only)
    assert client.get(f"/r/{code}").status_code == 401
    # correct password redirects
    r = client.post(f"/r/{code}", data={"pwd": "MyS3cret!"}, follow_redirects=False)
    assert r.status_code == 302


def test_bulk_endpoint_rejects_bad_form_colors(client):
    r = client.post("/api/register", json={"email": "b@x.com", "password": "StrongPass123!", "name": "B"})
    from conftest import mark_verified
    mark_verified("b@x.com")  # Phase 4d: bulk dynamic QRs need a verified address
    h = {"Authorization": f"Bearer {r.json['token']}"}
    csv = "url,name\nhttps://example.com/a,A\n"
    data = {"file": (io.BytesIO(csv.encode()), "b.csv"), "type": "url", "fg_color": "oops"}
    r = client.post("/api/qrcodes/bulk", data=data, content_type="multipart/form-data", headers=h)
    assert r.status_code == 400
    assert r.json["error"] == "Invalid color fg_color"
    # a valid form still works
    data = {"file": (io.BytesIO(csv.encode()), "b.csv"), "type": "url"}
    r = client.post("/api/qrcodes/bulk", data=data, content_type="multipart/form-data", headers=h)
    assert r.status_code == 200 and r.json["count"] == 1
