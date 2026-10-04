"""Phase 4e: CSRF — the cookie-auth surface is removed, not defended.

Directive: "Add CSRF protection for any cookie-authenticated state-changing
route."

The premise ("cookie-authenticated routes") turned out not to exist. Nothing
in the server, and nothing in any frontend, ever set the `token` cookie —
the only code that read it was one line in token_required. A cookie the
browser attaches automatically to every cross-site request is the CSRF
vector itself, so defending an unused one with a token would have been
ceremony.

The control here is structural: a credential that the browser never sends
ambiently cannot be abused by a cross-site page. These tests prove the
surface is gone, so it cannot be reintroduced by accident.
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

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(HERE, "app", "extensions.py")

SERVER_SOURCES = [
    "app/extensions.py", "app/routes/auth.py", "app/routes/qr.py",
    "app/routes/analytics.py", "app/routes/redirect.py", "app/routes/meta.py",
    "app/routes/pages.py", "server.py", "wsgi.py",
]

CLIENT_SOURCES = [
    "static/js/app.js", "static/js/session.js", "frontend/index.html",
    "frontend/dashboard.html",
]


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
    from conftest import mark_verified

    client.post("/api/register", json={
        "email": "csrf@example.com", "password": "StrongPass123!", "name": "C"})
    mark_verified("csrf@example.com")
    r = client.post("/api/login", json={
        "email": "csrf@example.com", "password": "StrongPass123!"})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["token"]


# ------------------------------------------------- no cookie is ever consulted
def test_server_does_not_read_a_cookie_token():
    src = _read("app/extensions.py")
    assert 'request.cookies.get("token")' not in src
    assert "request.cookies.get('token')" not in src


@pytest.mark.parametrize("rel", SERVER_SOURCES)
def test_no_server_module_reads_or_writes_an_auth_cookie(rel):
    src = _read(rel)
    assert "request.cookies" not in src, f"{rel} still reads cookies"
    assert "set_cookie" not in src, f"{rel} still sets a cookie"


@pytest.mark.parametrize("rel", CLIENT_SOURCES)
def test_no_client_uses_document_cookie(rel):
    assert "document.cookie" not in _read(rel), f"{rel} uses document.cookie"


# ------------------------------------------------------- no CSRF-able surface
def test_cors_does_not_allow_credentials():
    """Ambient credentials are what make CSRF possible; they are off."""
    src = _read("app/extensions.py")
    assert "supports_credentials=False" in src
    assert "supports_credentials=True" not in src


def test_optional_auth_is_also_header_only():
    """The routes that accept anonymous callers still must not read a
    cookie, or they would be CSRF-able in exactly the same way."""
    src = _read("app/extensions.py")
    fn = re.search(r"def optional_auth\(\):.*?(?=\ndef |\Z)", src, re.S)
    assert fn, "optional_auth not found"
    body = fn.group(0)
    assert "request.cookies" not in body
    assert 'request.headers.get("Authorization"' in body


def _route_blocks(src):
    """Yield (route_decorators, function_name, function_body) for each view."""
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("def "):
            continue
        name = re.match(r"def (\w+)\(", line)
        if not name:
            continue
        # walk back over decorators
        decos, j = [], i - 1
        while j >= 0 and lines[j].startswith("@"):
            decos.insert(0, lines[j])
            j -= 1
        # body runs to the next top-level decorator or def
        k = i + 1
        while k < len(lines) and not (lines[k].startswith("@")
                                      or lines[k].startswith("def ")):
            k += 1
        yield "".join(decos), name.group(1), "\n".join(lines[i:k])


def test_state_changing_routes_are_reachable_only_with_a_header_credential():
    """
    Every mutating route must sit behind token_required, or resolve the
    caller with optional_auth (header-only, asserted separately).

    Either way the credential is something the browser does not attach
    automatically, so a cross-site form post arrives unauthenticated.
    """
    public_ok = ("register", "login", "refresh", "logout", "forgot",
                 "reset", "2fa", "verify", "resend", "preview")
    problems = []
    for rel in ("app/routes/auth.py", "app/routes/qr.py",
                "app/routes/analytics.py"):
        for decos, name, body in _route_blocks(_read(rel)):
            if not any(x in decos.upper() for x in ('"POST"', '"PUT"',
                                                    '"PATCH"', '"DELETE"')):
                continue
            if "token_required" in decos or "optional_auth" in body:
                continue
            if any(a in name.lower() for a in public_ok):
                continue
            problems.append(f"{rel}:{name}")
    assert not problems, ("mutating routes with no header-only credential: "
                           + ", ".join(problems))


def test_no_flask_wtf_csrf_is_claimed_as_the_control():
    """
    The control is the absence of ambient credentials, not a CSRF library.

    Guarding against a future claim that CSRF is 'handled' while cookie
    auth is quietly reintroduced.
    """
    src = _read(EXT)
    assert "CSRFProtect" not in src, \
        "CSRFProtect would be reasonable only if cookie auth existed"


def test_preview_is_stateless_so_its_exemption_holds():
    """Why /api/preview is exempt above: it touches no user data and
    persists nothing, so a cross-site POST cannot act on anyone's behalf."""
    for decos, name, body in _route_blocks(_read("app/routes/qr.py")):
        if name != "preview":
            continue
        assert "get_session" not in body
        assert "optional_auth" not in body
        assert not any(x in body for x in ("_repo.", "repo.create", ".commit("))
        return
    raise AssertionError("preview view not found")


def test_security_headers_remain_after_the_change():
    """Removing cookie auth must not have taken the headers with it."""
    from app import security

    assert "Content-Security-Policy" in security.STATIC_HEADERS
    assert security.STATIC_HEADERS["X-Frame-Options"] == "DENY"
    assert security.STATIC_HEADERS["Referrer-Policy"] == "no-referrer"


def test_authorization_header_still_works(client, authed):
    """The supported path is unchanged."""
    r = client.get("/api/qrcodes", headers={"Authorization": f"Bearer {authed}"})
    assert r.status_code == 200, r.get_json()
