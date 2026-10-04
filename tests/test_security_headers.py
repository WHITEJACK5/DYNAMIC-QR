"""Phase 4b: security headers.

The directive requires CSP, X-Content-Type-Options, X-Frame-Options and
HSTS. These tests assert the header is actually on the wire, and — just as
importantly — that the policy is one this app's own pages can satisfy. A CSP
that blocks your own frontend is not a security control, it is an outage.

Note on scope: CSP and HSTS are enforced by the *browser*, not the server, so
these tests verify what the server sends. They cannot prove enforcement in a
real browser; the enforced part is covered by asserting the policy's own
directives.
"""
import os
import re
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

import server as DR  # noqa: E402
from server import app  # noqa: E402
from app import security  # noqa: E402

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


# ------------------------------------------------------------- the four required
def test_required_headers_present_on_pages(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in r.headers
    # HSTS is intentionally absent over plain HTTP (see app/security.py)
    assert "Strict-Transport-Security" not in r.headers


def test_required_headers_present_on_api_and_errors(client):
    for path in ("/api/health", "/api/qrcodes", "/nope-does-not-exist"):
        r = client.get(path)
        assert "Content-Security-Policy" in r.headers, path
        assert r.headers["X-Content-Type-Options"] == "nosniff", path
        assert r.headers["X-Frame-Options"] == "DENY", path


def test_hsts_sent_over_https(client):
    r = client.get("/", base_url="https://localhost")
    assert r.headers.get("Strict-Transport-Security") == security.HSTS


def test_hsts_honours_forwarded_proto_from_nginx(client):
    r = client.get("/", headers={"X-Forwarded-Proto": "https"})
    assert "Strict-Transport-Security" in r.headers


def test_hsts_not_trusted_from_forwarded_proto_http(client):
    r = client.get("/", headers={"X-Forwarded-Proto": "http"})
    assert "Strict-Transport-Security" not in r.headers


def test_forwarded_proto_takes_the_client_facing_value(client):
    """A proxy chain puts the first value closest to the client."""
    r = client.get("/", headers={"X-Forwarded-Proto": "https, http"})
    assert "Strict-Transport-Security" in r.headers


def test_referrer_policy_stops_url_leaks(client):
    """Other half of Phase 4a: don't leak full URLs to third parties."""
    assert client.get("/").headers["Referrer-Policy"] == "no-referrer"


# ------------------------------------------------------------------ CSP content
def test_csp_is_a_well_formed_policy():
    csp = security.CSP
    assert csp.endswith(";" ) is False
    directives = [d.strip() for d in csp.split(";") if d.strip()]
    names = [d.split()[0] for d in directives]
    assert len(names) == len(set(names)), "duplicate CSP directive"
    for required in ("default-src", "script-src", "style-src", "img-src",
                     "object-src", "base-uri", "frame-ancestors", "form-action",
                     "connect-src", "font-src"):
        assert required in names, f"missing {required}"


def test_csp_forbids_plugins_and_framing():
    assert "object-src 'none'" in security.CSP
    assert "frame-ancestors 'none'" in security.CSP


def test_csp_allows_data_uris_for_base64_previews():
    assert "img-src 'self' data:" in security.CSP


def test_csp_allows_the_font_origins_the_pages_actually_use():
    """Google Fonts is loaded on every page, so the policy must permit it."""
    assert "https://fonts.googleapis.com" in security.CSP
    assert "https://fonts.gstatic.com" in security.CSP
    for page in ("index.html", "dashboard.html", "manual.html",
                  "pricing.html"):
        src = _read(os.path.join("frontend", page))
        if "fonts.googleapis.com" in src:
            assert "https://fonts.googleapis.com" in security.CSP, page


def test_csp_allows_inline_script_and_style_used_today():
    """Current frontend needs 'unsafe-inline'; Phase 8 removes the need.

    If a future change drops the inline handlers, the test should be updated
    to assert the opposite — that is the point of naming the dependency.
    """
    assert "'unsafe-inline'" in security.CSP
    dash = _read("frontend/dashboard.html")
    assert re.search(r"(?s)<script(?![^>]*\bsrc=)[^>]*>", dash), \
        "dashboard no longer has an inline script; consider dropping 'unsafe-inline'"


def test_csp_needs_no_external_script_host():
    """No page loads JS from a CDN, so script-src must not widen."""
    script_src = [d for d in security.CSP.split(";") if d.strip().startswith("script-src")][0]
    assert "http://" not in script_src and "https://" not in script_src, script_src


# ------------------------------------------------------- does it break the app?
def test_pages_still_render_with_the_policy_applied(client):
    for path in ("/", "/dashboard", "/manual", "/api/v1/docs"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        assert "Content-Security-Policy" in r.headers


def test_static_assets_still_served(client):
    r = client.get("/static/js/app.js")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_inline_event_handlers_present_so_unsafe_inline_is_justified():
    """Ties the policy to reality rather than to a stale comment."""
    count = 0
    for page in ("frontend/index.html", "frontend/dashboard.html"):
        count += len(re.findall(r'\son(click|load|input|change|submit)=', _read(page)))
    assert count > 0, "no inline handlers found; 'unsafe-inline' may be removable"
