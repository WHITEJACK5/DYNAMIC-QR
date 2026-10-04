"""Phase 4a: stop accepting JWTs from the query string.

A token in a URL leaks: web-server access logs, proxy/CDN logs, browser
history, and the Referer header sent to every third party the page loads.
So `?token=` must not authenticate anything.

Kept: the Authorization header, and the `token` cookie for browser use
(cookie policy and CSRF are the next Phase 4 items, deliberately separate).
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

import server as DR  # noqa: E402
from server import app  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(HERE, rel), encoding="utf-8") as f:
        return f.read()


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
def authed(client):
    client.post("/api/register", json={
        "email": "leak@example.com", "password": "StrongPass123!", "name": "Leak"})
    from conftest import mark_verified
    mark_verified("leak@example.com")  # Phase 4d: dynamic QRs need a verified address
    r = client.post("/api/login", json={
        "email": "leak@example.com", "password": "StrongPass123!"})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["token"]


PROTECTED = ["/api/qrcodes", "/api/folders", "/api/analytics/overview",
             "/api/templates"]


# --------------------------------------------------------------- the leak itself
@pytest.mark.parametrize("path", PROTECTED)
def test_query_string_token_is_rejected(client, authed, path):
    r = client.get(f"{path}?token={authed}")
    assert r.status_code == 401, f"{path} accepted a token from the query string"
    assert r.get_json()["error"] == "Missing token"


def test_download_endpoint_rejects_query_string_token(client, authed):
    """The endpoint that motivated ?token= in the first place."""
    r = client.get(f"/api/download/1?format=png&token={authed}")
    assert r.status_code == 401
    assert r.get_json()["error"] == "Missing token"


def test_valid_bearer_token_still_works(client, authed):
    r = client.get("/api/qrcodes", headers={"Authorization": f"Bearer {authed}"})
    assert r.status_code == 200, r.get_json()


def test_download_still_works_with_bearer_header(client, authed):
    """The dashboard download path: header, not URL."""
    h = {"Authorization": f"Bearer {authed}"}
    q = client.post("/api/generate", headers=h, json={
        "type": "url", "data": {"url": "https://example.com"},
        "is_dynamic": True, "name": "DL"})
    assert q.status_code == 200, (q.status_code, q.get_json())
    qr_id = q.get_json()["qr_id"]
    r = client.get(f"/api/download/{qr_id}?format=png", headers=h)
    assert r.status_code == 200, r.get_json()
    assert r.data[:4] == b"\x89PNG", "download did not return a PNG"


# ------------------------------------------------------ cookie path removed (4e)
def test_cookie_token_is_rejected(client, authed):
    """Phase 4e: cookie auth removed, so a browser cannot attach credentials
    to a cross-site request automatically."""
    client.set_cookie("token", authed)
    r = client.get("/api/qrcodes")
    assert r.status_code == 401
    assert r.get_json()["error"] == "Missing token"


# ------------------------------------------------------------------------- guards
def test_source_does_not_read_token_from_query_string():
    """Structural guard: nobody re-adds request.args token lookups."""
    for rel in ("app/extensions.py",):
        src = _read(rel)
        assert 'request.args.get("token")' not in src, rel
        assert "request.args.get('token')" not in src, rel


def test_frontend_does_not_put_tokens_in_urls():
    """Covers every shipped frontend: the dashboard and the legacy SPA.

    app.js had its own download path that leaked the same token; the guard
    exists so a third one cannot appear unnoticed.
    """
    leaks = ("?token=${", "&token=${", "?token='", "&token='",
             '?token="', '&token="')
    for rel in ("frontend/dashboard.html", "frontend/index.html",
                "static/js/app.js"):
        src = _read(rel)
        for bad in leaks:
            assert bad not in src, f"{rel} still builds a token URL ({bad})"


def test_download_uses_a_header_not_a_token_url():
    """Both download paths: header, blob download, no token navigation."""
    dash = _read("frontend/dashboard.html")
    i = dash.index("async function downloadQr")
    body = dash[i:dash.index("async function", i + 10)]
    assert "Authorization" in body, "dashboard downloadQr does not send the header"
    assert "createObjectURL" in body, "dashboard downloadQr does not use a blob"
    assert "window.location" not in body, "dashboard downloadQr still navigates with the token"

    spa = _read("static/js/app.js")
    j = spa.index("[data-dl]")
    seg = spa[j:j + 700]
    assert "Authorization" in seg, "app.js download path does not send the header"
    assert "createObjectURL" in seg, "app.js download path does not use a blob"
    assert "window.location" not in seg, "app.js download path still navigates with the token"
